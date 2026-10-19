import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "stm32-firmware/tools/secure_firmware.py"
spec = importlib.util.spec_from_file_location("secure_firmware", SCRIPT)
secure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(secure)


@pytest.mark.unit
def test_board_id_encoding_and_validation():
    assert secure.board_bytes("STM32F446RE") == b"STM32F446RE".ljust(16, b"\0")
    with pytest.raises(RuntimeError):
        secure.board_bytes("é")
    with pytest.raises(RuntimeError):
        secure.board_bytes("X" * 16)


@pytest.mark.unit
def test_signed_header_size_boundaries():
    with pytest.raises(RuntimeError):
        secure.canonical_signed_header("STM32F446RE", 1, b"")
    with pytest.raises(RuntimeError):
        secure.canonical_signed_header("STM32F446RE", 1, b"x" * (secure.MAX_IMAGE_SIZE + 1))
    with pytest.raises(RuntimeError):
        secure.canonical_signed_header("STM32F446RE", -1, b"x")
    assert len(secure.canonical_signed_header("STM32F446RE", 1, b"x")) == secure.SIGNED_HEADER_SIZE


@pytest.mark.unit
def test_package_parser_rejects_malformed_and_size_mismatch():
    with pytest.raises(RuntimeError, match="shorter"):
        secure.parse_package(b"too short")
    package = bytearray(secure.PACKAGE_HEADER_SIZE + 2)
    package[:secure.SIGNED_HEADER_SIZE] = secure.canonical_signed_header("STM32F446RE", 1, b"x")
    package[0] ^= 1
    with pytest.raises(RuntimeError, match="magic"):
        secure.parse_package(bytes(package))
    package[0] ^= 1
    with pytest.raises(RuntimeError, match="payload length"):
        secure.parse_package(bytes(package))


@pytest.mark.unit
def test_create_verify_and_tamper_rejection(tmp_path):
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    package = tmp_path / "firmware.sfu"
    image = tmp_path / "image.bin"
    try:
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("OpenSSL Ed25519 support unavailable")
    subprocess.run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)], check=True)
    image.write_bytes(bytes(range(1, 64)))
    args = type("Args", (), {"image": str(image), "board": "STM32F446RE", "version_code": 7, "private_key": str(private_key), "package": str(package)})()
    secure.create_package(args)
    parsed = secure.parse_package(package.read_bytes())
    assert parsed["board"] == "STM32F446RE" and parsed["version_code"] == 7
    verify_args = type("Args", (), {"package": str(package), "board": "STM32F446RE", "public_key": str(public_key)})()
    secure.verify_package(verify_args)
    tampered = bytearray(package.read_bytes())
    tampered[-1] ^= 1
    package.write_bytes(tampered)
    with pytest.raises(RuntimeError, match="digest"):
        secure.verify_package(verify_args)
