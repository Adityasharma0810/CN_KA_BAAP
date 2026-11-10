"""Bounded, shell-free command execution for Linux traffic control."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence

from qos.models import CommandError, CommandTimeoutError


DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_CAPTURE_CHARS = 64 * 1024


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandRunner(Protocol):
    def run(
        self,
        args: Sequence[str],
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> CommandResult: ...


class SubprocessRunner:
    """Run a fixed argument vector without a shell.

    Capture is bounded so a misbehaving tool cannot exhaust memory here. Error
    text is intentionally kept off public API boundaries by the enforcement
    layer.
    """

    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if not 0.1 <= default_timeout <= 120:
            raise ValueError("default_timeout must be between 0.1 and 120 seconds")
        self.default_timeout = default_timeout

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> CommandResult:
        command = tuple(str(item) for item in args)
        if not command or any(not item for item in command):
            raise CommandError("empty command")
        effective_timeout = timeout if timeout is not None else self.default_timeout
        try:
            completed = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
                shell=False,
                env={
                    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                    "LC_ALL": "C",
                },
            )
        except subprocess.TimeoutExpired as error:
            raise CommandTimeoutError("traffic-control command timed out") from error
        except OSError as error:
            raise CommandError("traffic-control command could not be executed") from error
        return CommandResult(
            args=command,
            returncode=completed.returncode,
            stdout=(completed.stdout or "")[:_MAX_CAPTURE_CHARS],
            stderr=(completed.stderr or "")[:_MAX_CAPTURE_CHARS],
        )


def require_success(result: CommandResult) -> CommandResult:
    """Raise a safe command error when a tool reports failure."""

    if not result.ok:
        raise CommandError(
            f"traffic-control command failed with status {result.returncode}"
        )
    return result
