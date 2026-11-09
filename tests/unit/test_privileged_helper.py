import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "privileged" / "eb-priv"


def test_privileged_helper_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(HELPER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["unknown"],
        ["probe"],
        ["probe", "0"],
        ["probe", "10"],
        ["probe", "1;ls"],
        ["probe", "1", "extra"],
        ["traffic"],
        ["traffic", "unknown"],
        ["traffic", "start", "0", "call", "10"],
        ["traffic", "start", "1;ls", "call", "10"],
        ["traffic", "start", "1", "call;ls", "10"],
        ["traffic", "start", "1", "call", "10;ls"],
        ["traffic", "start", "1", "invalid", "10"],
        ["traffic", "start", "1", "call", "4"],
        ["traffic", "start", "1", "call", "121"],
        ["traffic", "start", "1", "call", "10", "extra"],
        ["traffic", "stop", "1", "extra"],
        ["traffic", "stop-all", "extra"],
        ["bottleneck", "7"],
        ["bottleneck", "1;ls"],
        ["bottleneck", "20;ls"],
        ["bottleneck", "off", "extra"],
        ["traffic", "stop", "1;touch /tmp/eb-priv-marker"],
    ],
)
def test_helper_rejects_bad_inputs_unprivileged_with_fixed_output(arguments):
    result = subprocess.run(
        ["bash", str(HELPER), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert re.fullmatch(
        r"fail (?:parse_error|no_namespace)\n",
        result.stdout,
    )
    assert result.stderr == ""
    assert "10.50.0.1" not in result.stdout
    assert "client" not in result.stdout
