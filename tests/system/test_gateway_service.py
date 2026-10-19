import os
import subprocess

import pytest


def ssh(host, remote_command, timeout=15):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, remote_command],
                          check=True, text=True, capture_output=True, timeout=timeout)


@pytest.mark.system
def test_yocto_gateway_service_and_serial_device():
    host = os.environ.get("YOCTO_SSH_HOST")
    if not host:
        pytest.skip("Set YOCTO_SSH_HOST to run deployed Raspberry Pi system tests")
    status = ssh(host, "systemctl is-active gatewayd")
    assert status.stdout.strip() == "active"
    device = ssh(host, "test -c /dev/ttyACM0 && echo present")
    assert device.stdout.strip() == "present"
    logs = ssh(host, "journalctl -u gatewayd -b --no-pager -n 100")
    assert "Starting" in logs.stdout or "Connected" in logs.stdout
