import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def run_script(name: str, *args: str, env: dict[str, str] | None = None):
    values = os.environ.copy()
    values.pop("EB_LAB_CLIENTS", None)
    if env:
        values.update(env)
    return subprocess.run(
        ["bash", str(SCRIPTS / name), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=values,
        check=False,
    )


@pytest.mark.parametrize("count", ("1", "3", "5"))
def test_setup_check_accepts_supported_client_counts(count):
    result = run_script("setup_gateway.sh", "--check", count)

    assert result.returncode == 0, result.stderr
    assert f"{count} client(s)" in result.stdout
    assert f"client{count}" in result.stdout
    assert f"veth-c{count}-br" in result.stdout


def test_setup_check_defaults_to_three_and_honours_environment():
    default = run_script("setup_gateway.sh", "--check")
    five = run_script("setup_gateway.sh", "--check", env={"EB_LAB_CLIENTS": "5"})

    assert default.returncode == 0, default.stderr
    assert "3 client(s)" in default.stdout
    assert five.returncode == 0, five.stderr
    assert "5 client(s)" in five.stdout


@pytest.mark.parametrize("count", ("0", "-1", "abc", "1.5", "100"))
def test_setup_check_rejects_invalid_client_counts_before_privileged_work(count):
    result = run_script("setup_gateway.sh", "--check", count)

    assert result.returncode != 0
    assert "client count" in result.stderr


def test_cleanup_check_accepts_three_and_five_clients():
    three = run_script("cleanup_gateway.sh", "--check", "3")
    five = run_script("cleanup_gateway.sh", "--check", "5")

    assert three.returncode == 0, three.stderr
    assert "3 client(s)" in three.stdout
    assert five.returncode == 0, five.stderr
    assert "5 client(s)" in five.stdout


def test_cleanup_check_rejects_invalid_count():
    result = run_script("cleanup_gateway.sh", "--check", "0")

    assert result.returncode != 0
    assert "client count" in result.stderr
