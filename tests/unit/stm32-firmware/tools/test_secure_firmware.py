import importlib.util
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "stm32-firmware/tools/secure_firmware.py"
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
    with pytest.raises(RuntimeError):
        secure.board_bytes("")


@pytest.mark.unit
def test_signed_header_size_boundaries():
    with pytest.raises(RuntimeError):
        secure.canonical_signed_header("STM32F446RE", 1, b"")
    with pytest.raises(RuntimeError):
        secure.canonical_signed_header("STM32F446RE", 1, b"x" * (secure.MAX_IMAGE_SIZE + 1))
    with pytest.raises(RuntimeError):
        secure.canonical_signed_header("STM32F446RE", -1, b"x")
    assert len(secure.canonical_signed_header("STM32F446RE", 1, b"x")) == secure.SIGNED_HEADER_SIZE
    assert len(secure.canonical_signed_header("STM32F446RE", 0xFFFFFFFF, b"x")) == secure.SIGNED_HEADER_SIZE
    with pytest.raises(RuntimeError, match="unsigned 32-bit"):
        secure.canonical_signed_header("STM32F446RE", 0x100000000, b"x")


@pytest.mark.unit
def test_canonical_header_contains_expected_fields():
    image = b"firmware image"
    header = secure.canonical_signed_header("STM32F446RE", 42, image)
    magic, fmt, board, version, image_size, digest = struct.unpack(
        secure.SIGNED_HEADER_FORMAT, header
    )
    assert (magic, fmt, board, version, image_size, digest) == (
        secure.PACKAGE_MAGIC,
        secure.PACKAGE_FORMAT,
        b"STM32F446RE".ljust(secure.BOARD_FIELD_SIZE, b"\0"),
        42,
        len(image),
        hashlib.blake2b(image, digest_size=32).digest(),
    )


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
def test_package_parser_rejects_invalid_fields_and_reserved_bytes():
    image = b"payload"
    valid_header = secure.canonical_signed_header("STM32F446RE", 3, image)
    signature = b"s" * secure.SIGNATURE_SIZE

    invalid_format = bytearray(valid_header + signature + bytes(
        secure.PACKAGE_HEADER_SIZE - len(valid_header) - len(signature)
    ) + image)
    struct.pack_into("<I", invalid_format, 8, secure.PACKAGE_FORMAT + 1)
    with pytest.raises(RuntimeError, match="unsupported firmware package format"):
        secure.parse_package(bytes(invalid_format))

    invalid_board = bytearray(valid_header + signature + bytes(
        secure.PACKAGE_HEADER_SIZE - len(valid_header) - len(signature)
    ) + image)
    invalid_board[12:28] = b"\0" * secure.BOARD_FIELD_SIZE
    with pytest.raises(RuntimeError, match="board ID encoding"):
        secure.parse_package(bytes(invalid_board))

    reserved_byte = bytearray(valid_header + signature + bytes(
        secure.PACKAGE_HEADER_SIZE - len(valid_header) - len(signature)
    ) + image)
    reserved_byte[secure.PACKAGE_HEADER_SIZE - 1] = 1
    with pytest.raises(RuntimeError, match="reserved header bytes"):
        secure.parse_package(bytes(reserved_byte))

    zero_size_header = bytearray(valid_header)
    struct.pack_into("<I", zero_size_header, secure.SIGNED_HEADER_SIZE - 36, 0)
    with pytest.raises(RuntimeError, match="image size"):
        secure.parse_package(bytes(zero_size_header + signature + bytes(
            secure.PACKAGE_HEADER_SIZE - len(zero_size_header) - len(signature)
        )))


@pytest.mark.unit
def test_package_parser_returns_metadata():
    image = b"payload"
    signed_header = secure.canonical_signed_header("STM32F446RE", 9, image)
    signature = bytes(range(secure.SIGNATURE_SIZE))
    package = signed_header + signature + bytes(
        secure.PACKAGE_HEADER_SIZE - len(signed_header) - len(signature)
    ) + image
    metadata = secure.parse_package(package)
    assert metadata["board"] == "STM32F446RE"
    assert metadata["version_code"] == 9
    assert metadata["image_size"] == len(image)
    assert metadata["image"] == image
    assert metadata["signature"] == signature
    assert metadata["signed_header"] == signed_header


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


@pytest.mark.unit
def test_verify_rejects_board_mismatch_before_openssl(tmp_path, monkeypatch):
    image = b"payload"
    signed_header = secure.canonical_signed_header("STM32F446RE", 1, image)
    package = signed_header + bytes(secure.SIGNATURE_SIZE) + bytes(
        secure.PACKAGE_HEADER_SIZE - len(signed_header) - secure.SIGNATURE_SIZE
    ) + image
    package_path = tmp_path / "firmware.sfu"
    package_path.write_bytes(package)
    run_openssl = Mock(side_effect=AssertionError("should not verify a mismatched board"))
    monkeypatch.setattr(secure, "run_openssl", run_openssl)

    with pytest.raises(RuntimeError, match="board mismatch"):
        secure.verify_package(SimpleNamespace(
            package=str(package_path), board="OTHER", public_key="unused.pem"
        ))
    run_openssl.assert_not_called()


@pytest.mark.unit
def test_export_public_key_writes_formatted_header(tmp_path, monkeypatch):
    key = bytes(range(32))
    monkeypatch.setattr(secure, "load_public_key", lambda _: key)
    output = tmp_path / "stm32_boot_public_key.h"
    secure.export_public_key(SimpleNamespace(public_key="key.pem", output=str(output)))

    text = output.read_text(encoding="ascii")
    assert text.startswith("#ifndef STM32_BOOT_PUBLIC_KEY_H\n#define STM32_BOOT_PUBLIC_KEY_H\n")
    assert "0x00U, 0x01U, 0x02U, 0x03U, 0x04U, 0x05U, 0x06U, 0x07U," in text
    assert "0x18U, 0x19U, 0x1aU, 0x1bU, 0x1cU, 0x1dU, 0x1eU, 0x1fU," in text
    assert text.endswith("};\n\n#endif\n")


@pytest.mark.unit
def test_inspect_package_outputs_json_metadata(tmp_path, capsys):
    image = b"payload"
    signed_header = secure.canonical_signed_header("STM32F446RE", 11, image)
    package = signed_header + bytes(secure.SIGNATURE_SIZE) + bytes(
        secure.PACKAGE_HEADER_SIZE - len(signed_header) - secure.SIGNATURE_SIZE
    ) + image
    package_path = tmp_path / "firmware.sfu"
    package_path.write_bytes(package)

    secure.inspect_package(SimpleNamespace(package=str(package_path)))
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "board": "STM32F446RE",
        "version_code": 11,
        "image_size": len(image),
        "digest_blake2b_256": hashlib.blake2b(image, digest_size=32).hexdigest(),
    }


@pytest.mark.unit
def test_run_openssl_wraps_missing_executable_and_failure(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(secure.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="required but was not found"):
        secure.run_openssl(["pkey", "-version"])

    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(2, args[0])

    monkeypatch.setattr(secure.subprocess, "run", failed)
    with pytest.raises(RuntimeError, match="exit 2"):
        secure.run_openssl(["pkey", "-version"])


@pytest.mark.unit
def test_load_public_key_extracts_raw_ed25519_key(tmp_path, monkeypatch):
    raw_key = bytes(range(32))
    der = secure.ED25519_SPKI_PREFIX + raw_key

    def write_der(arguments):
        output = Path(arguments[arguments.index("-out") + 1])
        output.write_bytes(der)

    monkeypatch.setattr(secure, "run_openssl", write_der)
    assert secure.load_public_key("public.pem") == raw_key

    def write_invalid_der(arguments):
        output = Path(arguments[arguments.index("-out") + 1])
        output.write_bytes(b"not an Ed25519 key")

    monkeypatch.setattr(secure, "run_openssl", write_invalid_der)
    with pytest.raises(RuntimeError, match="Ed25519 SubjectPublicKeyInfo"):
        secure.load_public_key("non-ed25519.pem")


@pytest.mark.unit
def test_main_reports_user_facing_error(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv", ["secure_firmware.py", "inspect", "--package", "missing.sfu"]
    )
    assert secure.main() == 1
    assert "ERROR:" in capsys.readouterr().err
