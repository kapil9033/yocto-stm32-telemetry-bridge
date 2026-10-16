#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 4 ]]; then
    printf 'Usage: %s IMAGE MANIFEST SIGNATURE PUBLIC_KEY\n' "$0" >&2
    exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="$1"
MANIFEST="$2"
SIGNATURE="$3"
PUBLIC_KEY="$4"
OPENOCD_SCRIPTS="${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}"

for path in "${IMAGE}" "${MANIFEST}" "${SIGNATURE}" "${PUBLIC_KEY}"; do
    if [[ ! "${path}" =~ ^/[A-Za-z0-9_./-]+$ ]]; then
        printf 'ERROR: Paths must be absolute and contain only letters, digits, "/", ".", "_", or "-": %s\n' \
            "${path}" >&2
        exit 2
    fi
    if [[ ! -f "${path}" ]]; then
        printf 'ERROR: Required file does not exist: %s\n' "${path}" >&2
        exit 1
    fi
done

if ! command -v python3 >/dev/null 2>&1; then
    printf 'ERROR: python3 is required for firmware signature verification.\n' >&2
    exit 1
fi
if ! command -v openocd >/dev/null 2>&1; then
    printf 'ERROR: openocd is required to program the STM32.\n' >&2
    exit 1
fi

python3 "${SCRIPT_DIR}/secure_firmware.py" verify \
    --image "${IMAGE}" \
    --manifest "${MANIFEST}" \
    --signature "${SIGNATURE}" \
    --public-key "${PUBLIC_KEY}" \
    --board STM32F446RE

openocd \
    -s "${OPENOCD_SCRIPTS}" \
    -f interface/stlink.cfg \
    -f target/stm32f4x.cfg \
    -c "program ${IMAGE} 0x08000000 verify reset exit"
