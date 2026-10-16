#!/usr/bin/env python3
"""Create and verify signed STM32 firmware manifests using OpenSSL Ed25519."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def canonical_manifest(data):
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def run_openssl(arguments):
    try:
        subprocess.run(["openssl", "pkeyutl", *arguments], check=True)
    except FileNotFoundError as error:
        raise RuntimeError("openssl is required but was not found in PATH") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"OpenSSL signature operation failed (exit {error.returncode})") from error


def sign(args):
    image = Path(args.image)
    image_bytes = image.read_bytes()
    manifest = {
        "board": args.board,
        "format": 1,
        "image_size": len(image_bytes),
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
        "version": args.version,
    }
    manifest_bytes = canonical_manifest(manifest)
    manifest_path = Path(args.manifest)
    signature_path = Path(args.signature)

    with tempfile.TemporaryDirectory(prefix="stm32-sign-") as temporary_directory:
        temporary_manifest = Path(temporary_directory) / "manifest.json"
        temporary_signature = Path(temporary_directory) / "manifest.sig"
        temporary_manifest.write_bytes(manifest_bytes)
        run_openssl([
            "-sign",
            "-rawin",
            "-inkey",
            args.private_key,
            "-in",
            str(temporary_manifest),
            "-out",
            str(temporary_signature),
        ])
        manifest_path.write_bytes(manifest_bytes)
        signature_path.write_bytes(temporary_signature.read_bytes())

    print(f"Signed {image} ({manifest['image_size']} bytes, {manifest['sha256']})")
    print(f"Manifest: {manifest_path}")
    print(f"Signature: {signature_path}")


def verify(args):
    image_bytes = Path(args.image).read_bytes()
    manifest_path = Path(args.manifest)
    manifest_bytes = manifest_path.read_bytes()

    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid manifest JSON: {error}") from error

    expected_keys = {"board", "format", "image_size", "sha256", "version"}
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise RuntimeError("manifest has missing or unexpected fields")
    if canonical_manifest(manifest) != manifest_bytes:
        raise RuntimeError("manifest is not in canonical format")
    if type(manifest["format"]) is not int or manifest["format"] != 1:
        raise RuntimeError("unsupported manifest format")
    if manifest["board"] != args.board:
        raise RuntimeError(
            f"board mismatch: image is for {manifest['board']!r}, expected {args.board!r}"
        )
    if type(manifest["image_size"]) is not int or manifest["image_size"] != len(image_bytes):
        raise RuntimeError("image size does not match signed manifest")
    image_digest = hashlib.sha256(image_bytes).hexdigest()
    if manifest["sha256"] != image_digest:
        raise RuntimeError("image SHA-256 does not match signed manifest")

    with tempfile.TemporaryDirectory(prefix="stm32-verify-") as temporary_directory:
        temporary_manifest = Path(temporary_directory) / "manifest.json"
        temporary_manifest.write_bytes(manifest_bytes)
        run_openssl([
            "-verify",
            "-pubin",
            "-inkey",
            args.public_key,
            "-rawin",
            "-in",
            str(temporary_manifest),
            "-sigfile",
            args.signature,
        ])

    print(
        f"Signature valid: {args.image} is authorized for {manifest['board']} "
        f"version {manifest['version']} ({manifest['image_size']} bytes)"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sign_parser = subparsers.add_parser("sign", help="sign an image manifest")
    sign_parser.add_argument("--image", required=True)
    sign_parser.add_argument("--board", required=True)
    sign_parser.add_argument("--version", required=True)
    sign_parser.add_argument("--private-key", required=True)
    sign_parser.add_argument("--manifest", required=True)
    sign_parser.add_argument("--signature", required=True)
    sign_parser.set_defaults(run=sign)

    verify_parser = subparsers.add_parser("verify", help="verify image and manifest")
    verify_parser.add_argument("--image", required=True)
    verify_parser.add_argument("--manifest", required=True)
    verify_parser.add_argument("--signature", required=True)
    verify_parser.add_argument("--public-key", required=True)
    verify_parser.add_argument("--board", required=True)
    verify_parser.set_defaults(run=verify)

    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
