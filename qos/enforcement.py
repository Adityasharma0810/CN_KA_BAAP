"""Linux traffic-enforcement lifecycle: apply, verify, update, rollback, remove.

The enforcer only touches interfaces the project owns. Ownership is established
from the ``experience-budget-lab`` link alias or the project lab state file, not
from interface naming alone.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Protocol

from qos.capabilities import LinuxCapabilityDetector
from qos.commands import (
    build_download_commands,
    build_upload_commands,
    delete_ifb_command,
    ensure_ifb_command,
    set_ifb_alias_command,
    set_ifb_up_command,
)
from qos.models import (
    AllocationPlan,
    CapabilityError,
    CapabilityReport,
    ClientAllocation,
    Direction,
    EnforcementError,
    EnforcementMode,
    EnforcementState,
    EnforcementStatus,
    LabLink,
    RollbackError,
    UnsafeResourceError,
    VerificationError,
    RequestedMode,
    utc_now,
    validate_link_coverage,
)
from qos.rollback import (
    InterfaceSnapshot,
    capture_snapshots,
    remove_project_qdiscs,
    restore_snapshots,
)
from qos.runner import CommandRunner, SubprocessRunner, require_success
from qos.verifier import read_interface_state, verify_plan


LAB_MARKER = "experience-budget-lab"
DEFAULT_STATE_FILE = Path("/run/experience-budget/lab.state")
DEFAULT_SYS_CLASS_NET = Path("/sys/class/net")


class OwnershipPolicy(Protocol):
    def exists(self, interface: str) -> bool: ...

    def is_owned(self, interface: str) -> bool: ...


class DefaultOwnership:
    """Read project ownership markers without modifying kernel state."""

    def __init__(
        self,
        *,
        sys_class_net: Path = DEFAULT_SYS_CLASS_NET,
        state_file: Path = DEFAULT_STATE_FILE,
        marker: str = LAB_MARKER,
    ):
        self.sys_class_net = Path(sys_class_net)
        self.state_file = Path(state_file)
        self.marker = marker

    def exists(self, interface: str) -> bool:
        return (self.sys_class_net / interface).exists()

    def is_owned(self, interface: str) -> bool:
        try:
            alias = (
                self.sys_class_net / interface / "ifalias"
            ).read_text(encoding="utf-8", errors="replace").strip()
        except (FileNotFoundError, PermissionError, OSError):
            alias = ""
        if alias == self.marker:
            return True
        try:
            lines = self.state_file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except (FileNotFoundError, PermissionError, OSError):
            return False
        return any(
            line.split() == [kind, interface]
            for line in lines
            for kind in ("veth", "ifb", "bridge")
            if line.strip()
        )


class LinuxTrafficEnforcer:
    """A testable, idempotent façade over project-owned ``tc`` state."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        detector: LinuxCapabilityDetector | None = None,
        ownership: OwnershipPolicy | None = None,
        clock: Callable[[], datetime] = utc_now,
        marker: str = LAB_MARKER,
    ):
        self.runner = runner or SubprocessRunner()
        self.detector = detector or LinuxCapabilityDetector(runner=self.runner)
        self.ownership = ownership or DefaultOwnership(marker=marker)
        self.clock = clock
        self.marker = marker
        self._capabilities: CapabilityReport | None = None
        self._mode = EnforcementMode.NONE
        self._status = EnforcementStatus(
            state=EnforcementState.UNCONFIGURED,
            mode=EnforcementMode.NONE,
            requested_mode=RequestedMode.AUTO,
            reason="not_applied",
            applied_at=None,
            verified=False,
            client_count=0,
        )
        self._last_plan: AllocationPlan | None = None
        self._last_links: tuple[LabLink, ...] = ()
        self._created_ifbs: set[str] = set()

    @property
    def status(self) -> EnforcementStatus:
        return self._status

    @property
    def mode(self) -> EnforcementMode:
        return self._mode

    def capabilities(self, *, refresh: bool = False) -> CapabilityReport:
        if self._capabilities is None or refresh:
            self._capabilities = self.detector.detect()
        return self._capabilities

    def _detect_for(self, requested: RequestedMode) -> CapabilityReport:
        report = self.detector.detect(requested=requested)
        self._capabilities = report
        return report

    def _require_owned(self, interface: str) -> None:
        if not self.ownership.exists(interface):
            raise UnsafeResourceError("required lab interface does not exist")
        if not self.ownership.is_owned(interface):
            raise UnsafeResourceError("lab interface is not project-owned")

    def _prepare_ifbs(
        self,
        links: Iterable[LabLink],
        *,
        upload_required: set[str],
    ) -> list[str]:
        created: list[str] = []
        for link in links:
            if link.client_id not in upload_required:
                continue
            if self.ownership.exists(link.ifb_interface):
                if not self.ownership.is_owned(link.ifb_interface):
                    raise UnsafeResourceError("IFB interface is not project-owned")
                require_success(
                    self.runner.run(set_ifb_up_command(link))
                )
                continue
            require_success(self.runner.run(ensure_ifb_command(link)))
            self._created_ifbs.add(link.ifb_interface)
            created.append(link.ifb_interface)
            require_success(self.runner.run(set_ifb_alias_command(link, self.marker)))
            require_success(self.runner.run(set_ifb_up_command(link)))
        return created

    def _execute_direction(
        self,
        *,
        link: LabLink,
        allocation: ClientAllocation,
        mode: EnforcementMode,
    ) -> None:
        if allocation.download_mbps is not None:
            for command in build_download_commands(link, allocation, mode):
                require_success(self.runner.run(command))
        else:
            self._clear_download(link)

        if allocation.upload_mbps is not None:
            for command in build_upload_commands(link, allocation, mode):
                require_success(self.runner.run(command))
        else:
            self._clear_upload(link)

    def _clear_download(self, link: LabLink) -> None:
        state = read_interface_state(
            self.runner,
            link.download_interface,
            include_classes=False,
            include_filters=False,
        )
        if state.root_kind not in (None, "noqueue"):
            if state.root_kind not in ("cake", "htb", "tbf"):
                raise UnsafeResourceError("download qdisc is not a known lab mode")
            require_success(
                self.runner.run(
                    ("tc", "qdisc", "del", "dev", link.download_interface, "root")
                )
            )
        actual = read_interface_state(
            self.runner,
            link.download_interface,
            include_classes=False,
            include_filters=False,
        )
        if actual.root_kind not in (None, "noqueue"):
            raise VerificationError("download qdisc cleanup did not verify")

    def _clear_upload(self, link: LabLink) -> None:
        ingress = read_interface_state(
            self.runner,
            link.upload_interface,
            include_classes=False,
            include_filters=True,
        )
        if ingress.ingress_present:
            if link.ifb_interface not in ingress.redirect_targets:
                raise UnsafeResourceError("upload filter does not target the lab IFB")
            require_success(
                self.runner.run(
                    (
                        "tc",
                        "qdisc",
                        "del",
                        "dev",
                        link.upload_interface,
                        "handle",
                        "ffff:",
                        "ingress",
                    )
                )
            )
        actual_ingress = read_interface_state(
            self.runner,
            link.upload_interface,
            include_classes=False,
            include_filters=True,
        )
        if actual_ingress.ingress_present or actual_ingress.redirect_targets:
            raise VerificationError("upload redirect cleanup did not verify")
        if not self.ownership.exists(link.ifb_interface):
            return
        if not self.ownership.is_owned(link.ifb_interface):
            if ingress.ingress_present:
                raise UnsafeResourceError("upload IFB is not project-owned")
            return
        ifb_state = read_interface_state(
            self.runner,
            link.ifb_interface,
            include_classes=False,
            include_filters=False,
        )
        if ifb_state.root_kind not in (None, "noqueue"):
            if ifb_state.root_kind not in ("cake", "htb", "tbf"):
                raise UnsafeResourceError("upload qdisc is not a known lab mode")
            require_success(
                self.runner.run(
                    ("tc", "qdisc", "del", "dev", link.ifb_interface, "root")
                )
            )
        actual_ifb = read_interface_state(
            self.runner,
            link.ifb_interface,
            include_classes=False,
            include_filters=False,
        )
        if actual_ifb.root_kind not in (None, "noqueue"):
            raise VerificationError("upload qdisc cleanup did not verify")

    def _remove_links(self, links: Iterable[LabLink]) -> None:
        materialized = tuple(links)
        owned = {
            interface
            for link in materialized
            for interface in (
                link.download_interface,
                link.upload_interface,
                link.ifb_interface,
            )
            if self.ownership.is_owned(interface)
        }
        active_links = tuple(
            link
            for link in materialized
            if any(
                self.ownership.exists(interface)
                for interface in (
                    link.download_interface,
                    link.upload_interface,
                    link.ifb_interface,
                )
            )
        )
        removed, failures = remove_project_qdiscs(
            self.runner,
            active_links,
            owned_interfaces=owned,
            delete_ifb=False,
        )
        removal_errors = list(failures)
        for link in materialized:
            if link.ifb_interface in self._created_ifbs:
                if self.ownership.exists(link.ifb_interface):
                    try:
                        require_success(self.runner.run(delete_ifb_command(link)))
                    except Exception:
                        removal_errors.append("ifb_removal_failed")
                self._created_ifbs.discard(link.ifb_interface)
        if not removed or removal_errors:
            raise EnforcementError(
                f"project-owned qdisc cleanup failed: {removal_errors[0]}"
            )

    def _verify_removed(self, links: Iterable[LabLink]) -> tuple[bool, tuple[str, ...]]:
        errors: list[str] = []
        for link in links:
            for interface in (link.download_interface, link.upload_interface):
                if not self.ownership.exists(interface):
                    continue
                state = read_interface_state(
                    self.runner,
                    interface,
                    include_classes=False,
                    include_filters=False,
                )
                if state.root_kind not in (None, "noqueue"):
                    errors.append("client_qdisc_still_present")
                if state.ingress_present:
                    errors.append("client_ingress_still_present")
            if self.ownership.exists(link.ifb_interface):
                ifb = read_interface_state(
                    self.runner,
                    link.ifb_interface,
                    include_classes=False,
                    include_filters=False,
                )
                if ifb.root_kind not in (None, "noqueue"):
                    errors.append("ifb_qdisc_still_present")
        return not errors, tuple(errors)

    def _rollback(
        self,
        *,
        previous_plan: AllocationPlan | None,
        previous_links: tuple[LabLink, ...],
        current_links: tuple[LabLink, ...],
        snapshots: dict[str, InterfaceSnapshot],
        touched: tuple[str, ...],
    ) -> None:
        removal_failed = False
        try:
            self._remove_links(current_links)
        except Exception:
            removal_failed = True

        if previous_plan is not None and previous_links:
            try:
                if removal_failed:
                    raise RollbackError("project-owned cleanup failed")
                self._apply_without_rollback(
                    previous_plan,
                    previous_links,
                    mode=self._mode,
                )
                verification = verify_plan(
                    links=previous_links,
                    allocations=previous_plan.allocations,
                    mode=self._mode,
                    runner=self.runner,
                )
                if not verification.ok:
                    raise RollbackError("previous configuration did not verify")
            except Exception as error:
                self._status = EnforcementStatus(
                    state=EnforcementState.UNHEALTHY,
                    mode=self._mode,
                    requested_mode=previous_plan.requested_mode,
                    reason="rollback_failed",
                    applied_at=self._status.applied_at,
                    verified=False,
                    client_count=self._status.client_count,
                    rollback_ok=False,
                    rolled_back_at=self.clock(),
                    last_error="rollback_failed",
                )
                raise RollbackError("rollback to previous state failed") from error
            self._status = EnforcementStatus(
                state=EnforcementState.ROLLED_BACK,
                mode=self._mode,
                requested_mode=previous_plan.requested_mode,
                reason="restored_previous_configuration",
                applied_at=self._status.applied_at,
                verified=True,
                client_count=len(previous_plan.allocations),
                rollback_ok=True,
                rolled_back_at=self.clock(),
            )
            return

        own = {
            interface
            for interface in touched
            if self.ownership.exists(interface) and self.ownership.is_owned(interface)
        }
        ok, failures = restore_snapshots(
            self.runner, snapshots.values(), owned_interfaces=own
        )
        ok = ok and not removal_failed
        self._status = EnforcementStatus(
            state=EnforcementState.ROLLED_BACK if ok else EnforcementState.UNHEALTHY,
            mode=EnforcementMode.NONE,
            requested_mode=RequestedMode.AUTO,
            reason="restored_original_state" if ok else "rollback_failed",
            applied_at=None,
            verified=ok,
            client_count=0,
            rollback_ok=ok,
            rolled_back_at=self.clock(),
            last_error=None if ok else failures[0] if failures else "rollback_failed",
        )
        if not ok:
            raise RollbackError("restore of original interface state failed")

    def _apply_without_rollback(
        self,
        plan: AllocationPlan,
        links: tuple[LabLink, ...],
        *,
        mode: EnforcementMode,
    ) -> None:
        by_client = validate_link_coverage(plan, links)
        upload_required = {
            allocation.client_id
            for allocation in plan.allocations
            if allocation.upload_mbps is not None
        }
        self._prepare_ifbs(links, upload_required=upload_required)
        allocations = plan.by_client()
        for link in links:
            allocation = allocations.get(link.client_id)
            if allocation is None:
                self._clear_download(link)
                self._clear_upload(link)
                continue
            self._execute_direction(
                link=by_client[allocation.client_id],
                allocation=allocation,
                mode=mode,
            )

    def apply(
        self,
        plan: AllocationPlan,
        links: Iterable[LabLink],
    ) -> EnforcementStatus:
        """Apply a plan idempotently, verify kernel readback, and roll back on failure."""

        materialized = tuple(links)
        validate_link_coverage(plan, materialized)

        report = self._detect_for(plan.requested_mode)
        if plan.requested_mode == RequestedMode.CAKE:
            if not report.supports(EnforcementMode.CAKE):
                raise CapabilityError("CAKE was requested but is not available")
            mode = EnforcementMode.CAKE
        elif plan.requested_mode == RequestedMode.HTB_FQ_CODEL:
            if not report.supports(EnforcementMode.HTB_FQ_CODEL):
                raise CapabilityError("HTB + fq_codel was requested but is not available")
            mode = EnforcementMode.HTB_FQ_CODEL
        else:
            mode = report.selected_mode
            if mode == EnforcementMode.NONE:
                raise CapabilityError("no supported shaping architecture is available")

        upload_required = {
            allocation.client_id
            for allocation in plan.allocations
            if allocation.upload_mbps is not None
        }
        if upload_required and not (
            report.ifb and report.matchall and report.mirred
        ):
            raise CapabilityError(
                "upload shaping requires IFB, matchall, and mirred support"
            )

        for link in materialized:
            self._require_owned(link.download_interface)
            if link.client_id in upload_required:
                self._require_owned(link.upload_interface)
                if self.ownership.exists(link.ifb_interface) and not self.ownership.is_owned(
                    link.ifb_interface
                ):
                    raise UnsafeResourceError("IFB interface is not project-owned")

        previous_plan = self._last_plan
        previous_links = self._last_links
        current_links_by_client = {
            link.client_id: link for link in materialized
        }
        stale_links = tuple(
            link
            for link in previous_links
            if current_links_by_client.get(link.client_id) != link
        )

        previous_interfaces = {
            interface
            for link in previous_links
            for interface in (
                link.download_interface,
                link.upload_interface,
                link.ifb_interface,
            )
        }
        if previous_plan is not None and previous_links:
            previous_readback = verify_plan(
                links=previous_links,
                allocations=previous_plan.allocations,
                mode=self._mode,
                runner=self.runner,
            )
            if not previous_readback.ok:
                self._status = EnforcementStatus(
                    state=EnforcementState.UNHEALTHY,
                    mode=self._mode,
                    requested_mode=previous_plan.requested_mode,
                    reason="pre_update_readback_mismatch",
                    applied_at=self._status.applied_at,
                    verified=False,
                    client_count=len(previous_plan.allocations),
                    last_error=previous_readback.errors[0],
                )
                raise VerificationError(
                    "existing enforcement state does not match the previous plan"
                )

        interfaces_to_snapshot = {
            link.download_interface for link in (*materialized, *stale_links)
        } | {
            link.upload_interface for link in (*materialized, *stale_links)
        } | {
            link.ifb_interface
            for link in materialized
            if link.client_id in upload_required
            and self.ownership.exists(link.ifb_interface)
        }
        snapshots = capture_snapshots(self.runner, interfaces_to_snapshot)
        for snapshot in snapshots.values():
            if (
                snapshot.interface not in previous_interfaces
                and not snapshot.restorable
            ):
                raise UnsafeResourceError(
                    "existing qdisc state cannot be safely restored"
                )

        touched = tuple(sorted(interfaces_to_snapshot))
        try:
            self._remove_links(stale_links)
            self._apply_without_rollback(plan, materialized, mode=mode)
            verification = verify_plan(
                links=materialized,
                allocations=plan.allocations,
                mode=mode,
                runner=self.runner,
            )
            if not verification.ok:
                raise VerificationError(
                    "kernel traffic-control readback did not match the request"
                )
            if stale_links:
                removed, removed_errors = self._verify_removed(stale_links)
                if not removed:
                    raise VerificationError("stale enforcement was not removed")
        except Exception as error:
            try:
                self._rollback(
                    previous_plan=previous_plan,
                    previous_links=previous_links,
                    current_links=materialized,
                    snapshots=snapshots,
                    touched=touched,
                )
            except RollbackError:
                raise
            raise error

        self._mode = mode
        self._last_plan = plan
        self._last_links = materialized
        self._status = EnforcementStatus(
            state=EnforcementState.HEALTHY,
            mode=mode,
            requested_mode=plan.requested_mode,
            reason=report.reason,
            applied_at=self.clock(),
            verified=True,
            client_count=len(plan.allocations),
            rollback_ok=None,
        )
        return self._status

    def update(self, plan: AllocationPlan, links: Iterable[LabLink]) -> EnforcementStatus:
        return self.apply(plan, links)

    def remove(self, links: Iterable[LabLink] | None = None) -> EnforcementStatus:
        """Remove project-owned shaping state. Safe to call repeatedly."""

        materialized = tuple(links) if links is not None else self._last_links
        try:
            self._remove_links(materialized)
            removed, errors = self._verify_removed(materialized)
            if not removed:
                raise VerificationError("traffic-control state was not removed")
        except Exception as error:
            self._status = EnforcementStatus(
                state=EnforcementState.UNHEALTHY,
                mode=self._mode,
                requested_mode=self._status.requested_mode,
                reason="remove_failed",
                applied_at=self._status.applied_at,
                verified=False,
                client_count=0,
                last_error=getattr(error, "code", "remove_failed"),
            )
            raise
        self._mode = EnforcementMode.NONE
        self._last_plan = None
        self._last_links = ()
        self._status = EnforcementStatus(
            state=EnforcementState.REMOVED,
            mode=EnforcementMode.NONE,
            requested_mode=RequestedMode.AUTO,
            reason="removed",
            applied_at=None,
            verified=True,
            client_count=0,
        )
        return self._status

    def health(self) -> EnforcementStatus:
        """Verify current kernel state without changing it."""

        if self._last_plan is None or not self._last_links:
            if self._status.state != EnforcementState.UNCONFIGURED:
                return self._status
            return EnforcementStatus(
                state=EnforcementState.UNCONFIGURED,
                mode=EnforcementMode.NONE,
                requested_mode=RequestedMode.AUTO,
                reason="not_applied",
                applied_at=None,
                verified=False,
                client_count=0,
            )
        verification = verify_plan(
            links=self._last_links,
            allocations=self._last_plan.allocations,
            mode=self._mode,
            runner=self.runner,
        )
        if verification.ok:
            self._status = EnforcementStatus(
                state=EnforcementState.HEALTHY,
                mode=self._mode,
                requested_mode=self._last_plan.requested_mode,
                reason="readback_verified",
                applied_at=self._status.applied_at,
                verified=True,
                client_count=len(self._last_plan.allocations),
            )
        else:
            self._status = EnforcementStatus(
                state=EnforcementState.DEGRADED,
                mode=self._mode,
                requested_mode=self._last_plan.requested_mode,
                reason="readback_mismatch",
                applied_at=self._status.applied_at,
                verified=False,
                client_count=len(self._last_plan.allocations),
                last_error=verification.errors[0] if verification.errors else "readback_mismatch",
            )
        return self._status
