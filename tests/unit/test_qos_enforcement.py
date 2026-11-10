from datetime import datetime, timezone
import pytest

from qos.capabilities import LinuxCapabilityDetector, ModuleProbe
from qos.commands import build_download_commands, build_upload_commands
from qos.enforcement import LinuxTrafficEnforcer
from qos.models import (
    AllocationPlan,
    CapabilityError,
    CapabilityReport,
    ClientAllocation,
    Direction,
    EnforcementValidationError,
    EnforcementMode,
    LabLink,
    RequestedMode,
    UnsafeResourceError,
    VerificationError,
)
from qos.runner import CommandResult
from qos.verifier import read_interface_state, verify_direction


NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
CLIENT = "client-abcdefgh"
LINK = LabLink.for_slot(client_id=CLIENT, slot=1)


class FakeRunner:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.calls = []

    def run(self, args, *, timeout=10.0):
        command = tuple(args)
        self.calls.append(command)
        result = self.outputs.get(command, (0, ""))
        return CommandResult(command, result[0], result[1], "")


class StatefulTrafficControlRunner(FakeRunner):
    def __init__(self):
        super().__init__()
        self.qdiscs = {}
        self.rates = {}
        self.leaves = set()

    def run(self, args, *, timeout=10.0):
        command = tuple(args)
        self.calls.append(command)

        if command[:4] == ("tc", "qdisc", "show", "dev"):
            interface = command[4]
            kind = self.qdiscs.get(interface, "noqueue")
            if kind == "htb":
                output = (
                    "qdisc htb 1: root refcnt 2 default 0x10\n"
                    + (
                        "qdisc fq_codel 10: parent 1:10 limit 10240p\n"
                        if interface in self.leaves
                        else ""
                    )
                )
            elif kind == "cake":
                output = (
                    f"qdisc cake 8010: root refcnt 2 "
                    f"bandwidth {self.rates[interface]:g}Mbit\n"
                )
            else:
                output = f"qdisc {kind} 0: root refcnt 2\n"
            return CommandResult(command, 0, output, "")

        if command[:4] == ("tc", "class", "show", "dev"):
            interface = command[4]
            rate = self.rates.get(interface)
            output = (
                f"class htb 1:10 root rate {rate:g}Mbit ceil {rate:g}Mbit\n"
                if rate is not None
                else ""
            )
            return CommandResult(command, 0, output, "")

        if command[:3] == ("tc", "filter", "show"):
            return CommandResult(command, 0, "", "")

        if command[:4] == ("tc", "qdisc", "replace", "dev"):
            interface = command[4]
            if "root" in command:
                if "cake" in command:
                    self.qdiscs[interface] = "cake"
                    self.rates[interface] = float(command[command.index("bandwidth") + 1][:-4])
                elif "htb" in command:
                    self.qdiscs[interface] = "htb"
                    self.rates.pop(interface, None)
                    self.leaves.discard(interface)
            elif "fq_codel" in command:
                self.leaves.add(interface)
            return CommandResult(command, 0, "", "")

        if command[:3] == ("tc", "class", "replace"):
            interface = command[4]
            self.rates[interface] = float(command[command.index("rate") + 1][:-4])
            return CommandResult(command, 0, "", "")

        if command[:4] == ("tc", "qdisc", "del", "dev") and "root" in command:
            interface = command[4]
            self.qdiscs[interface] = "noqueue"
            self.rates.pop(interface, None)
            self.leaves.discard(interface)
            return CommandResult(command, 0, "", "")

        return CommandResult(command, 0, "", "")


class StubDetector:
    def __init__(self, report):
        self.report = report

    def detect(self, *, requested=RequestedMode.AUTO):
        return self.report


def capability_report(
    *,
    mode=EnforcementMode.HTB_FQ_CODEL,
    cake=False,
    htb=True,
    fq_codel=True,
    ifb=True,
    matchall=True,
    mirred=True,
):
    return CapabilityReport(
        checked_at=NOW,
        kernel_release="test-kernel",
        tc_version="tc utility, iproute2-test",
        cake=cake,
        htb=htb,
        fq_codel=fq_codel,
        ifb=ifb,
        matchall=matchall,
        mirred=mirred,
        selected_mode=mode,
        reason="test",
    )


def test_allocation_plan_enforces_capacity_per_direction():
    with pytest.raises(EnforcementValidationError, match="download allocations exceed"):
        AllocationPlan(
            capacity_mbps=10,
            allocations=(
                ClientAllocation(CLIENT, download_mbps=6),
                ClientAllocation("client-ijklmnop", download_mbps=5),
            ),
        )


def test_cake_download_is_selected_explicitly():
    plan = AllocationPlan(
        capacity_mbps=20,
        allocations=(ClientAllocation(CLIENT, download_mbps=10),),
        requested_mode=RequestedMode.CAKE,
    )
    commands = build_download_commands(
        LINK, plan.allocations[0], EnforcementMode.CAKE
    )

    assert commands.mode == EnforcementMode.CAKE
    assert commands.commands == (
        (
            "tc", "qdisc", "replace", "dev", LINK.download_interface,
            "root", "cake", "bandwidth", "10mbit", "besteffort",
        ),
    )


def test_upload_commands_redirect_ingress_to_the_project_ifb():
    allocation = ClientAllocation(CLIENT, upload_mbps=3)
    commands = build_upload_commands(
        LINK, allocation, EnforcementMode.HTB_FQ_CODEL
    )

    assert commands.ifb_interface == LINK.ifb_interface
    assert "matchall" in commands.commands[1]
    assert commands.commands[1][-1] == LINK.ifb_interface
    assert "fq_codel" in commands.commands[-1]


def test_module_probe_detects_installed_modules_and_loaded_modules(tmp_path: Path):
    modules = tmp_path / "modules"
    sys_modules = tmp_path / "sys"
    module_dir = modules / "test-kernel"
    module_dir.mkdir(parents=True)
    (module_dir / "modules.dep").write_text(
        "kernel/net/sched/sch_htb.ko.zst:\n",
        encoding="utf-8",
    )
    (sys_modules / "sch_fq_codel").mkdir(parents=True)
    probe = ModuleProbe(
        kernel_release="test-kernel",
        modules_root=modules,
        sys_module_root=sys_modules,
    )

    assert probe.available(("sch_htb",))
    assert probe.available(("sch_fq_codel",))
    assert not probe.available(("sch_cake",))


def test_capability_detector_selects_htb_only_when_supported(tmp_path: Path):
    root = tmp_path / "modules"
    kernel = root / "test-kernel"
    kernel.mkdir(parents=True)
    (kernel / "modules.dep").write_text(
        "\n".join(
            (
                "kernel/net/sched/sch_htb.ko:",
                "kernel/net/sched/sch_fq_codel.ko:",
            )
        ),
        encoding="utf-8",
    )
    runner = FakeRunner(
        {("tc", "-V"): (0, "tc utility, iproute2-test")}
    )
    detector = LinuxCapabilityDetector(
        runner=runner,
        module_probe=ModuleProbe(
            kernel_release="test-kernel",
            modules_root=root,
            sys_module_root=tmp_path / "sys",
        ),
        clock=lambda: NOW,
    )

    report = detector.detect()

    assert report.selected_mode == EnforcementMode.HTB_FQ_CODEL
    assert report.reason == "cake_unavailable_htb_fq_codel_fallback"
    assert not report.cake
    assert report.htb and report.fq_codel


def test_readback_command_failure_is_not_reported_as_empty_state():
    runner = FakeRunner(
        {("tc", "qdisc", "show", "dev", LINK.download_interface): (1, "")}
    )

    with pytest.raises(VerificationError):
        read_interface_state(runner, LINK.download_interface)


def test_htb_readback_verifies_leaf_and_rate():
    runner = FakeRunner(
        {
            ("tc", "qdisc", "show", "dev", LINK.download_interface): (
                0,
                "qdisc htb 1: root refcnt 2 default 0x10\n"
                "qdisc fq_codel 10: parent 1:10 limit 10240p\n",
            ),
            ("tc", "class", "show", "dev", LINK.download_interface): (
                0,
                "class htb 1:10 root rate 10Mbit ceil 10Mbit\n",
            ),
        }
    )
    allocation = ClientAllocation(CLIENT, download_mbps=10)

    result = verify_direction(
        link=LINK,
        allocation=allocation,
        mode=EnforcementMode.HTB_FQ_CODEL,
        direction=Direction.DOWNLOAD,
        runner=runner,
    )

    assert result.ok
    assert result.readback[0].root_rate_mbps == 10
    assert result.readback[0].leaf_kinds == ("fq_codel",)


def test_apply_refuses_an_unowned_interface_before_tc_mutation():
    report = capability_report()
    runner = FakeRunner()

    class Unowned:
        def exists(self, interface):
            return True

        def is_owned(self, interface):
            return False

    enforcer = LinuxTrafficEnforcer(
        runner=runner,
        detector=StubDetector(report),
        ownership=Unowned(),
    )
    plan = AllocationPlan(
        capacity_mbps=20,
        allocations=(ClientAllocation(CLIENT, download_mbps=10),),
    )

    with pytest.raises(UnsafeResourceError):
        enforcer.apply(plan, (LINK,))

    assert runner.calls == []


def test_apply_does_not_fall_back_when_requested_mode_is_unsupported():
    enforcer = LinuxTrafficEnforcer(
        runner=FakeRunner(),
        detector=StubDetector(capability_report(mode=EnforcementMode.NONE)),
        ownership=type(
            "Owned",
            (),
            {
                "exists": lambda self, interface: True,
                "is_owned": lambda self, interface: True,
            },
        )(),
    )
    plan = AllocationPlan(
        capacity_mbps=20,
        allocations=(ClientAllocation(CLIENT, download_mbps=10),),
        requested_mode=RequestedMode.CAKE,
    )

    with pytest.raises(CapabilityError):
        enforcer.apply(plan, (LINK,))


def test_update_verifies_and_replaces_the_previous_project_plan():
    runner = StatefulTrafficControlRunner()

    class Owned:
        def exists(self, interface):
            return True

        def is_owned(self, interface):
            return True

    enforcer = LinuxTrafficEnforcer(
        runner=runner,
        detector=StubDetector(capability_report()),
        ownership=Owned(),
        clock=lambda: NOW,
    )
    initial = AllocationPlan(
        capacity_mbps=20,
        allocations=(ClientAllocation(CLIENT, download_mbps=10),),
    )
    updated = AllocationPlan(
        capacity_mbps=20,
        allocations=(ClientAllocation(CLIENT, download_mbps=5),),
    )

    assert enforcer.apply(initial, (LINK,)).verified
    status = enforcer.update(updated, (LINK,))

    assert status.verified
    assert status.state.value == "healthy"
    assert runner.rates[LINK.download_interface] == 5
