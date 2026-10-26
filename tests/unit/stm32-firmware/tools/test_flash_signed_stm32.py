import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "stm32-firmware/tools/flash_signed_stm32.sh"
)


def _executable(path, body):
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _run(package, public_key, env):
    return subprocess.run(
        [str(SCRIPT), str(package), str(public_key)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


@pytest.mark.unit
def test_flash_script_requires_two_arguments():
    result = subprocess.run([str(SCRIPT)], text=True, capture_output=True, check=False)
    assert result.returncode == 2
    assert "Usage:" in result.stderr


@pytest.mark.unit
def test_flash_script_rejects_non_absolute_or_unsafe_paths(tmp_path):
    package = tmp_path / "package.sfu"
    public_key = tmp_path / "public.pem"
    package.touch()
    public_key.touch()
    result = subprocess.run(
        [str(SCRIPT), str(package), "relative.pem"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Paths must be absolute" in result.stderr


@pytest.mark.unit
def test_flash_script_rejects_missing_files(tmp_path):
    result = subprocess.run(
        [str(SCRIPT), str(tmp_path / "missing.sfu"), str(tmp_path / "missing.pem")],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Required file does not exist" in result.stderr


@pytest.mark.unit
def test_flash_script_verifies_before_programming(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    package = tmp_path / "package.sfu"
    public_key = tmp_path / "public.pem"
    package.touch()
    public_key.touch()
    log = tmp_path / "calls.log"
    _executable(
        bindir / "python3",
        'printf "verify" >> "$FLASH_TEST_LOG"\nprintf " <%s>" "$@" >> "$FLASH_TEST_LOG"\nprintf "\\n" >> "$FLASH_TEST_LOG"',
    )
    _executable(
        bindir / "openocd",
        'printf "flash" >> "$FLASH_TEST_LOG"\nprintf " <%s>" "$@" >> "$FLASH_TEST_LOG"\nprintf "\\n" >> "$FLASH_TEST_LOG"',
    )
    env = os.environ.copy()
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["FLASH_TEST_LOG"] = str(log)
    env["OPENOCD_SCRIPTS"] = "/safe/openocd/scripts"

    result = _run(package, public_key, env)
    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2
    assert calls[0].startswith("verify <")
    assert "secure_firmware.py> <verify>" in calls[0]
    assert f"--package> <{package}>" in calls[0]
    assert f"--public-key> <{public_key}>" in calls[0]
    assert "--board> <STM32F446RE>" in calls[0]
    assert calls[1].startswith("flash <")
    assert "-s> </safe/openocd/scripts>" in calls[1]
    assert f"program {package} 0x08020000 verify reset exit" in calls[1]
