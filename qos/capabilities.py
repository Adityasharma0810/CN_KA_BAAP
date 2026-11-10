"""Kernel and tool capability detection for Linux shaping.

Detection is deliberately read-only. It never applies a qdisc to an
unowned interface. Module presence is checked through sysfs and the kernel's
``modules.builtin`` index before falling back to ``modinfo``.
"""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from qos.models import (
    CapabilityReport,
    EnforcementMode,
    RequestedMode,
    utc_now,
)
from qos.runner import CommandRunner, SubprocessRunner


_MODULES = {
    "cake": ("sch_cake",),
    "htb": ("sch_htb",),
    "fq_codel": ("sch_fq_codel",),
    "ifb": ("ifb",),
    "matchall": ("cls_matchall",),
    "mirred": ("act_mirred",),
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, PermissionError, OSError):
        return ""


class ModuleProbe:
    """Best-effort, read-only kernel module availability probe."""

    def __init__(
        self,
        *,
        kernel_release: str | None = None,
        modules_root: Path = Path("/lib/modules"),
        sys_module_root: Path = Path("/sys/module"),
        modinfo: Callable[[str], bool] | None = None,
    ):
        self.kernel_release = kernel_release or platform.release()
        self.modules_root = modules_root
        self.sys_module_root = sys_module_root
        self._modinfo = modinfo
        self._builtin_text: str | None = None

    def available(self, names: tuple[str, ...]) -> bool:
        for name in names:
            if (self.sys_module_root / name).exists():
                return True
            if self._is_builtin(name):
                return True
            if self._modinfo is not None and self._modinfo(name):
                return True
            if self._modinfo is None and self._module_file_exists(name):
                return True
        return False

    def _is_builtin(self, name: str) -> bool:
        if self._builtin_text is None:
            path = self.modules_root / self.kernel_release / "modules.builtin"
            self._builtin_text = _read_text(path)
        wanted = f"/{name}.ko"
        return any(
            line.endswith(wanted) or line.endswith("/" + name + ".ko.zst")
            for line in self._builtin_text.splitlines()
        )

    def _module_file_exists(self, name: str) -> bool:
        module_root = self.modules_root / self.kernel_release
        dependency_index = _read_text(module_root / "modules.dep")
        suffixes = (".ko", ".ko.xz", ".ko.zst", ".ko.gz")
        return any(
            line.split(":", 1)[0].endswith(f"/{name}{suffix}")
            for line in dependency_index.splitlines()
            for suffix in suffixes
        )


class LinuxCapabilityDetector:
    """Detect which shaping architectures the current kernel/tooling supports."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        module_probe: ModuleProbe | None = None,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.runner = runner or SubprocessRunner()
        self.module_probe = module_probe or ModuleProbe()
        self.clock = clock

    def detect(
        self,
        *,
        requested: RequestedMode = RequestedMode.AUTO,
    ) -> CapabilityReport:
        tc_version: str | None = None
        try:
            result = self.runner.run(["tc", "-V"])
            if result.returncode == 0:
                tc_version = (result.stdout or result.stderr).strip()[:200] or "unknown"
        except Exception:
            tc_version = None

        cake = self.module_probe.available(_MODULES["cake"])
        htb = self.module_probe.available(_MODULES["htb"])
        fq_codel = self.module_probe.available(_MODULES["fq_codel"])
        ifb = self.module_probe.available(_MODULES["ifb"])
        matchall = self.module_probe.available(_MODULES["matchall"])
        mirred = self.module_probe.available(_MODULES["mirred"])

        if tc_version is None:
            mode = EnforcementMode.NONE
            reason = "tc_unavailable"
        elif requested == RequestedMode.CAKE:
            if cake:
                mode = EnforcementMode.CAKE
                reason = "requested_cake_supported"
            else:
                mode = EnforcementMode.NONE
                reason = "requested_cake_unsupported"
        elif requested == RequestedMode.HTB_FQ_CODEL:
            if htb and fq_codel:
                mode = EnforcementMode.HTB_FQ_CODEL
                reason = "requested_htb_fq_codel_supported"
            else:
                mode = EnforcementMode.NONE
                reason = "requested_htb_fq_codel_unsupported"
        elif cake:
            mode = EnforcementMode.CAKE
            reason = "cake_preferred"
        elif htb and fq_codel:
            mode = EnforcementMode.HTB_FQ_CODEL
            reason = "cake_unavailable_htb_fq_codel_fallback"
        else:
            mode = EnforcementMode.NONE
            reason = "no_supported_qdisc"

        return CapabilityReport(
            checked_at=self.clock().astimezone(timezone.utc),
            kernel_release=self.module_probe.kernel_release,
            tc_version=tc_version,
            cake=cake,
            htb=htb,
            fq_codel=fq_codel,
            ifb=ifb,
            matchall=matchall,
            mirred=mirred,
            selected_mode=mode,
            reason=reason,
        )
