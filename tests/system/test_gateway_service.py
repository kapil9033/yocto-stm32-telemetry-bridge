import os
import shlex
import subprocess
import time

import pytest


def ssh(host, remote_command, timeout=15):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, remote_command],
                          check=True, text=True, capture_output=True, timeout=timeout)


@pytest.mark.system
def test_yocto_gateway_service_and_serial_device():
    host = os.environ.get("YOCTO_SSH_HOST")
    if not host:
        pytest.skip("Set YOCTO_SSH_HOST to run deployed Raspberry Pi system tests")

    serial_device = os.environ.get("YOCTO_SERIAL_DEVICE", "/dev/ttyACM0")
    status = ssh(host, "systemctl is-active gatewayd")
    assert status.stdout.strip() == "active"
    device = ssh(host, f"test -c {shlex.quote(serial_device)} && echo present")
    assert device.stdout.strip() == "present"
    logs = ssh(host, "journalctl -u gatewayd -b --no-pager -n 100 -o cat")
    assert any(
        marker in logs.stdout
        for marker in ("Starting", "Connected", "TELEMETRY FRAME RECEIVED", "[TELEMETRY]")
    )


@pytest.mark.system
def test_yocto_gateway_service_is_enabled_and_restart_configured():
    host = os.environ.get("YOCTO_SSH_HOST")
    if not host:
        pytest.skip("Set YOCTO_SSH_HOST to run deployed Raspberry Pi system tests")

    properties = ssh(
        host,
        "systemctl show gatewayd --property=UnitFileState "
        "--property=Restart --property=RestartUSec --no-pager",
    )
    values = dict(line.split("=", 1) for line in properties.stdout.splitlines() if "=" in line)
    assert values.get("UnitFileState") == "enabled"
    assert values.get("Restart") == "always"
    assert values.get("RestartUSec", "0") != "0"


@pytest.mark.system
def test_yocto_gateway_journal_contains_decoded_telemetry():
    host = os.environ.get("YOCTO_SSH_HOST")
    if not host:
        pytest.skip("Set YOCTO_SSH_HOST to run deployed Raspberry Pi system tests")

    timeout = int(os.environ.get("YOCTO_TELEMETRY_TIMEOUT", "30"))
    deadline = time.monotonic() + timeout
    last_logs = ""
    while time.monotonic() < deadline:
        result = ssh(host, "journalctl -u gatewayd -b --no-pager -n 100 -o cat")
        last_logs = result.stdout
        if "[TELEMETRY] Timestamp=" in last_logs or "Timestamp (RTC)" in last_logs:
            return
        time.sleep(min(2, max(0, deadline - time.monotonic())))

    pytest.fail(
        f"No decoded telemetry appeared in gatewayd journal within {timeout}s. "
        f"Recent service output:\n{last_logs}"
    )
