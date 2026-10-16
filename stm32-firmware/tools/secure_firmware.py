#!/usr/bin/env python3
"""Create, inspect, and verify STM32 signed firmware packages."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

PACKAGE_MAGIC = b"STM32SF1"
PACKAGE_FORMAT = 1
BOARD_FIELD_SIZE = 16
SIGNED_HEADER_FORMAT = "<8sI16sII32s"
SIGNED_HEADER_SIZE = struct.calcsize(SIGNED_HEADER_FORMAT)
SIGNATURE_SIZE = 64
PACKAGE_HEADER_SIZE = 512
STM32F446RE_SLOT_SIZE = 0x60000
MAX_IMAGE_SIZE = STM32F446RE_SLOT_SIZE - PACKAGE_HEADER_SIZE
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


def run_openssl(arguments):
    try:
        subprocess.run(["openssl", *arguments], check=True)
    except FileNotFoundError as error:
        raise RuntimeError("openssl is required but was not found in PATH") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"OpenSSL operation failed (exit {error.returncode})") from error


def board_bytes(board):
    try:
        encoded = board.encode("ascii")
    except UnicodeEncodeError as error:
        raise RuntimeError("board ID must contain ASCII characters") from error
    if not encoded or len(encoded) >= BOARD_FIELD_SIZE:
        raise RuntimeError(f"board ID must be 1 to {BOARD_FIELD_SIZE - 1} ASCII bytes")
    return encoded.ljust(BOARD_FIELD_SIZE, b"\0")


def load_public_key(public_key):
    with tempfile.TemporaryDirectory(prefix="stm32-public-key-") as temp_dir:
        der_path = Path(temp_dir) / "public.der"
        run_openssl([
            "pkey",
            "-pubin",
            "-inform",
            "PEM",
            "-in",
            public_key,
            "-outform",
            "DER",
            "-out",
            str(der_path),
        ])
        der = der_path.read_bytes()
    if len(der) != len(ED25519_SPKI_PREFIX) + 32 or not der.startswith(ED25519_SPKI_PREFIX):
        raise RuntimeError("public key must be an Ed25519 SubjectPublicKeyInfo PEM")
    return der[len(ED25519_SPKI_PREFIX):]


def canonical_signed_header(board, version, image):
    if not 0 <= version <= 0xFFFFFFFF:
        raise RuntimeError("version code must be an unsigned 32-bit integer")
    if not image or len(image) > MAX_IMAGE_SIZE:
        raise RuntimeError(
            f"image size must be between 1 and {MAX_IMAGE_SIZE} bytes for the STM32F446RE slot"
        )
    image_digest = hashlib.blake2b(image, digest_size=32).digest()
    return struct.pack(
        SIGNED_HEADER_FORMAT,
        PACKAGE_MAGIC,
        PACKAGE_FORMAT,
        board_bytes(board),
        version,
        len(image),
        image_digest,
    )


def create_package(args):
    image = Path(args.image).read_bytes()
    signed_header = canonical_signed_header(args.board, args.version_code, image)
    with tempfile.TemporaryDirectory(prefix="stm32-package-") as temp_dir:
        message_path = Path(temp_dir) / "signed-header.bin"
        signature_path = Path(temp_dir) / "signature.bin"
        message_path.write_bytes(signed_header)
        run_openssl([
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            args.private_key,
            "-in",
            str(message_path),
            "-out",
            str(signature_path),
        ])
        signature = signature_path.read_bytes()
    if len(signature) != SIGNATURE_SIZE:
        raise RuntimeError(f"expected a {SIGNATURE_SIZE}-byte Ed25519 signature")
    header = signed_header + signature
    header += bytes(PACKAGE_HEADER_SIZE - len(header))
    package_path = Path(args.package)
    package_path.write_bytes(header + image)
    print(
        f"Created signed package {package_path} for {args.board} version "
        f"{args.version_code} ({len(image)} image bytes)"
    )


def parse_package(package):
    if len(package) < PACKAGE_HEADER_SIZE:
        raise RuntimeError("package is shorter than the fixed header")
    fields = struct.unpack(SIGNED_HEADER_FORMAT, package[:SIGNED_HEADER_SIZE])
    magic, format_version, raw_board, version, image_size, image_digest = fields
    if magic != PACKAGE_MAGIC:
        raise RuntimeError("invalid firmware package magic")
    if format_version != PACKAGE_FORMAT:
        raise RuntimeError(f"unsupported firmware package format {format_version}")
    terminator = raw_board.find(b"\0")
    if terminator <= 0 or any(raw_board[terminator:]):
        raise RuntimeError("invalid board ID encoding in package")
    try:
        board = raw_board[:terminator].decode("ascii")
    except UnicodeDecodeError as error:
        raise RuntimeError("board ID in package is not ASCII") from error
    signature_start = SIGNED_HEADER_SIZE
    signature_end = signature_start + SIGNATURE_SIZE
    signature = package[signature_start:signature_end]
    if any(package[signature_end:PACKAGE_HEADER_SIZE]):
        raise RuntimeError("package reserved header bytes must be zero")
    image = package[PACKAGE_HEADER_SIZE:]
    if image_size == 0 or image_size > MAX_IMAGE_SIZE:
        raise RuntimeError("signed image size is outside the STM32F446RE application slot")
    if image_size != len(image):
        raise RuntimeError("package payload length does not match signed image size")
    return {
        "board": board,
        "version_code": version,
        "image_size": image_size,
        "digest": image_digest,
        "signature": signature,
        "signed_header": package[:SIGNED_HEADER_SIZE],
        "image": image,
    }


def verify_package(args):
    package_path = Path(args.package)
    package = package_path.read_bytes()
    metadata = parse_package(package)
    if metadata["board"] != args.board:
        raise RuntimeError(
            f"board mismatch: package is for {metadata['board']!r}, expected {args.board!r}"
        )
    actual_digest = hashlib.blake2b(metadata["image"], digest_size=32).digest()
    if actual_digest != metadata["digest"]:
        raise RuntimeError("image BLAKE2b-256 digest does not match signed header")
    with tempfile.TemporaryDirectory(prefix="stm32-package-verify-") as temp_dir:
        message_path = Path(temp_dir) / "signed-header.bin"
        signature_path = Path(temp_dir) / "signature.bin"
        message_path.write_bytes(metadata["signed_header"])
        signature_path.write_bytes(metadata["signature"])
        run_openssl([
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            args.public_key,
            "-rawin",
            "-in",
            str(message_path),
            "-sigfile",
            str(signature_path),
        ])
    print(
        f"Signature valid: {package_path} is authorized for {metadata['board']} "
        f"version {metadata['version_code']} ({metadata['image_size']} bytes)"
    )


def export_public_key(args):
    key = load_public_key(args.public_key)
    lines = [
        "#ifndef STM32_BOOT_PUBLIC_KEY_H",
        "#define STM32_BOOT_PUBLIC_KEY_H",
        "",
        "#include <stdint.h>",
        "",
        "static const uint8_t stm32_boot_public_key[32] = {",
    ]
    for offset in range(0, len(key), 8):
        values = ", ".join(f"0x{byte:02x}U" for byte in key[offset:offset + 8])
        lines.append(f"    {values},")
    lines.extend(["};", "", "#endif"])
    Path(args.output).write_text("\n".join(lines) + "\n", encoding="ascii")


def inspect_package(args):
    metadata = parse_package(Path(args.package).read_bytes())
    print(json.dumps({
        "board": metadata["board"],
        "version_code": metadata["version_code"],
        "image_size": metadata["image_size"],
        "digest_blake2b_256": metadata["digest"].hex(),
    }, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser("package", help="create a signed firmware package")
    package_parser.add_argument("--image", required=True)
    package_parser.add_argument("--board", required=True)
    package_parser.add_argument("--version-code", required=True, type=int)
    package_parser.add_argument("--private-key", required=True)
    package_parser.add_argument("--package", required=True)
    package_parser.set_defaults(run=create_package)

    verify_parser = subparsers.add_parser("verify", help="verify a signed firmware package")
    verify_parser.add_argument("--package", required=True)
    verify_parser.add_argument("--public-key", required=True)
    verify_parser.add_argument("--board", required=True)
    verify_parser.set_defaults(run=verify_package)

    inspect_parser = subparsers.add_parser("inspect", help="display signed package metadata")
    inspect_parser.add_argument("--package", required=True)
    inspect_parser.set_defaults(run=inspect_package)

    key_parser = subparsers.add_parser(
        "export-public-key", help="generate a C header containing an Ed25519 public key"
    )
    key_parser.add_argument("--public-key", required=True)
    key_parser.add_argument("--output", required=True)
    key_parser.set_defaults(run=export_public_key)

    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, RuntimeError, ValueError, struct.error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
