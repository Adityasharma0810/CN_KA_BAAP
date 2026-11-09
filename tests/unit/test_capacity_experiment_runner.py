import inspect
import json
import subprocess

import pytest

from experiments.capacity_forecasting import run_capacity_experiment as runner


def qdisc_state(kind="noqueue", rate_mbps=None):
    root = {"kind": kind, "handle": "0:", "root": True, "options": {}}
    if rate_mbps is not None:
        root["options"]["rate"] = rate_mbps * 1_000_000 / 8
    return root, json.dumps([root])


class FakeBottleneck:
    def __init__(self):
        self.state = {"kind": "noqueue", "rate": None}
        self.commands = []
        self.snapshots = []
        self.manager = runner.BottleneckManager(
            command_runner=self.command,
            qdisc_reader=self.read,
            use_sudo=True,
        )

    def read(self):
        return qdisc_state(self.state["kind"], self.state["rate"])

    def command(self, command, **kwargs):
        assert kwargs["check"] is False
        self.commands.append(command)
        if command[-1] == "true":
            return subprocess.CompletedProcess(command, 0, "", "")
        if str(runner.BOTTLENECK_SCRIPT) in command:
            if command[-1] == "off":
                self.state = {"kind": "noqueue", "rate": None}
            else:
                self.state = {"kind": "tbf", "rate": int(command[-1])}
        return subprocess.CompletedProcess(command, 0, "ok", "")


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class FakeProcess:
    next_pid = 200

    def __init__(self):
        self.pid = FakeProcess.next_pid
        FakeProcess.next_pid += 1
        self.status = None
        self.signals = []
        self.wait_timeout = None

    def poll(self):
        return self.status

    def terminate(self):
        self.status = 0

    def send_signal(self, signal_value):
        self.signals.append(signal_value)
        self.status = 130

    def wait(self, timeout=None):
        self.wait_timeout = timeout
        self.status = 0 if self.status is None else self.status
        return self.status

    def kill(self):
        self.status = -9


@pytest.mark.parametrize(
    ("scenario", "duration", "expected"),
    [
        ("constant", 60, [(0, 100)]),
        ("step", 60, [(0, 100), (20, 40), (40, 100)]),
        ("periodic", 60, [(0, 80), (10, 120), (20, 80), (30, 120), (40, 80), (50, 120)]),
        ("step", 30, [(0, 100), (20, 40)]),
    ],
)
def test_scenario_scheduling(scenario, duration, expected):
    events = runner.scenario_schedule(scenario, duration)
    assert [(event.offset_s, event.capacity_mbps) for event in events] == expected


def test_scenario_schedule_rejects_bad_duration_and_name():
    with pytest.raises(ValueError, match="duration"):
        runner.scenario_schedule("constant", 0)
    with pytest.raises(ValueError, match="unsupported"):
        runner.scenario_schedule("unknown", 60)


def test_capacity_transitions_use_set_bottleneck_workflow_and_verify_state():
    fixture = FakeBottleneck()

    fixture.manager.preflight()
    fixture.manager.set_capacity(100, initial=True)
    fixture.manager.set_capacity(40)
    fixture.manager.set_capacity(100)

    assert fixture.state == {"kind": "tbf", "rate": 100}
    assert [entry["requested_capacity_mbps"] for entry in fixture.manager.snapshots] == [
        100,
        40,
        100,
    ]
    script_commands = [
        command for command in fixture.commands
        if str(runner.BOTTLENECK_SCRIPT) in command
    ]
    assert len(script_commands) == 3


def test_preflight_refuses_unexpected_root_qdisc():
    fixture = FakeBottleneck()
    fixture.state = {"kind": "fq_codel", "rate": None}

    with pytest.raises(runner.ExperimentError, match="unexpected root qdisc"):
        fixture.manager.preflight()

    assert fixture.commands == [
        ["sudo", "-n", "true"]
    ]


def test_transition_and_cleanup_preserve_a_replaced_unowned_qdisc():
    fixture = FakeBottleneck()
    fixture.manager.set_capacity(100, initial=True)
    fixture.state = {"kind": "fq_codel", "rate": None}

    with pytest.raises(runner.ExperimentError, match="runner-owned TBF"):
        fixture.manager.set_capacity(40)
    with pytest.raises(runner.ExperimentError, match="not the runner-owned TBF"):
        fixture.manager.cleanup()

    assert fixture.state["kind"] == "fq_codel"


def test_schedule_waits_monotonically_and_applies_transitions():
    clock = FakeClock()
    applied = []
    events = (
        runner.CapacityEvent(0, 100),
        runner.CapacityEvent(10, 40),
        runner.CapacityEvent(20, 100),
    )

    runner.wait_for_schedule(
        events,
        start_time=5,
        set_capacity=applied.append,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert applied == [100, 40, 100]
    assert clock.value == 25
    assert clock.sleeps == [5, 10, 10]


def test_unique_output_paths_never_overwrite_existing_files(tmp_path):
    paths = runner._unique_output_paths(tmp_path, "run-1")
    assert len({path.name for path in paths}) == len(paths)
    paths[1].write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner._unique_output_paths(tmp_path, "run-1")


def test_collector_invocation_is_independent_of_gateway_api(tmp_path):
    command = runner._collector_command(
        output_path=tmp_path / "run.csv",
        run_id="run-shared",
        scenario_id="scenario-1",
        scenario="constant",
        seed=17,
        sampling_interval=1,
        sampling_tolerance=0.25,
        duration=60,
    )

    assert command[command.index("-m") + 1] == (
        "experiments.capacity_forecasting.collect_gateway_telemetry"
    )
    assert command[command.index("--run-id") + 1] == "run-shared"
    assert "gateway.api" not in inspect.getsource(runner)
    assert "--random-seed" in command
    assert command[command.index("--random-seed") + 1] == "17"
    assert "--sampling-tolerance" in command


def test_interruption_cleanup_stops_traffic_collector_server_and_owned_qdisc():
    fixture = FakeBottleneck()
    fixture.manager.set_capacity(100, initial=True)
    traffic = FakeProcess()
    collector = FakeProcess()
    server = FakeProcess()

    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        error = runner._cleanup_resources(
            [traffic], collector, server, fixture.manager
        )

    assert error is None
    assert traffic.status == 0
    assert collector.status == 130
    assert collector.signals
    assert server.status == 0
    assert fixture.state["kind"] == "noqueue"
    assert fixture.manager.expected_capacity_mbps is None


def test_cleanup_refuses_to_delete_unexpected_qdisc():
    fixture = FakeBottleneck()
    fixture.manager.set_capacity(100, initial=True)
    fixture.state = {"kind": "tbf", "rate": 40}

    error = runner._cleanup_resources([], None, None, fixture.manager)

    assert "expected runner TBF 100 Mbps, found 40 Mbps" in error
    assert fixture.state == {"kind": "tbf", "rate": 40}
