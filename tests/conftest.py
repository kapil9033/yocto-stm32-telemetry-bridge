import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def gateway_binary(tmp_path_factory):
    configured = os.environ.get("GATEWAYD_BIN")
    if configured:
        binary = pathlib.Path(configured)
        if not binary.is_file():
            pytest.fail(f"GATEWAYD_BIN does not exist: {binary}")
        return binary
    build = tmp_path_factory.mktemp("gateway-build")
    subprocess.run(["cmake", "-S", str(ROOT / "gatewayd"), "-B", str(build)], check=True)
    subprocess.run(["cmake", "--build", str(build), "--target", "gatewayd"], check=True)
    return build / "gatewayd"
