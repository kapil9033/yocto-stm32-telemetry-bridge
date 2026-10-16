#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 2 ]]; then
    printf 'Usage: %s SIGNED_PACKAGE PUBLIC_KEY\n' "$0" >&2
    exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE="$1"
PUBLIC_KEY="$2"
OPENOCD_SCRIPTS="${OPENOCD_SCRIPTS:-/usr/share/openocd/scripts}"

for path in "${PACKAGE}" "${PUBLIC_KEY}"; do
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
    --package "${PACKAGE}" \
    --public-key "${PUBLIC_KEY}" \
    --board STM32F446RE

openocd \
    -s "${OPENOCD_SCRIPTS}" \
    -f interface/stlink.cfg \
    -f target/stm32f4x.cfg \
    -c "program ${PACKAGE} 0x08020000 verify reset exit"
