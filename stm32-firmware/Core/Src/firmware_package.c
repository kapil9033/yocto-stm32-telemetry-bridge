#include "firmware_package.h"

#include <string.h>

#include "ed25519.h"
#include "monocypher.h"
#include "boot_public_key.h"

static const uint8_t package_magic[8] = {
    'S', 'T', 'M', '3', '2', 'S', 'F', '1'
};

static const uint8_t package_board_id[16] = {
    'S', 'T', 'M', '3', '2', 'F', '4', '4',
    '6', 'R', 'E', 0U, 0U, 0U, 0U, 0U
};

static uint32_t read_u32_le(const uint8_t *bytes)
{
    return (uint32_t)bytes[0]
         | ((uint32_t)bytes[1] << 8U)
         | ((uint32_t)bytes[2] << 16U)
         | ((uint32_t)bytes[3] << 24U);
}

static int bytes_are_zero(const uint8_t *bytes, size_t length)
{
    uint8_t aggregate = 0U;
    for (size_t index = 0U; index < length; ++index) {
        aggregate |= bytes[index];
    }
    return aggregate == 0U;
}

stm32_package_status_t stm32_package_verify(
    const uint8_t *package,
    size_t package_size,
    uint32_t *initial_stack_pointer,
    uint32_t *reset_handler)
{
    if (package == NULL || initial_stack_pointer == NULL || reset_handler == NULL
        || package_size < STM32_PACKAGE_HEADER_SIZE
        || package_size > STM32_PACKAGE_SLOT_SIZE) {
        return STM32_PACKAGE_INVALID_HEADER;
    }

    const uint8_t *header = package;
    if (memcmp(header, package_magic, sizeof(package_magic)) != 0
        || read_u32_le(&header[8]) != STM32_PACKAGE_FORMAT_VERSION
        || memcmp(&header[12], package_board_id, sizeof(package_board_id)) != 0
        || !bytes_are_zero(&header[132], STM32_PACKAGE_HEADER_SIZE - 132U)) {
        return STM32_PACKAGE_INVALID_HEADER;
    }

    const uint32_t image_size = read_u32_le(&header[32]);
    const size_t actual_payload_size = package_size - STM32_PACKAGE_PAYLOAD_OFFSET;
    if (image_size == 0U
        || image_size > STM32_PACKAGE_MAX_IMAGE_SIZE
        || (size_t)image_size != actual_payload_size) {
        return STM32_PACKAGE_INVALID_HEADER;
    }

    if (ed25519_sign_open(
            header,
            STM32_PACKAGE_SIGNED_HEADER_SIZE,
            stm32_boot_public_key,
            &header[STM32_PACKAGE_SIGNATURE_OFFSET]) != 0) {
        return STM32_PACKAGE_INVALID_SIGNATURE;
    }

    uint8_t calculated_digest[32];
    crypto_blake2b(
        calculated_digest,
        sizeof(calculated_digest),
        &package[STM32_PACKAGE_PAYLOAD_OFFSET],
        image_size);
    const int digest_matches = crypto_verify32(calculated_digest, &header[36]) == 0;
    memset(calculated_digest, 0, sizeof(calculated_digest));
    if (!digest_matches) {
        return STM32_PACKAGE_INVALID_DIGEST;
    }

    const uint8_t *vectors = &package[STM32_PACKAGE_PAYLOAD_OFFSET];
    uint32_t stack_pointer;
    uint32_t vector_reset_handler;
    memcpy(&stack_pointer, &vectors[0], sizeof(stack_pointer));
    memcpy(&vector_reset_handler, &vectors[4], sizeof(vector_reset_handler));
    const uint32_t reset_address = vector_reset_handler & ~1U;
    const uint32_t image_start = STM32_PACKAGE_APP_VECTOR_ADDRESS;
    const uint32_t image_end = image_start + image_size;
    if (stack_pointer < 0x20000000U
        || stack_pointer > 0x20020000U
        || (stack_pointer & 0x7U) != 0U
        || (vector_reset_handler & 1U) == 0U
        || reset_address < image_start
        || reset_address >= image_end) {
        return STM32_PACKAGE_INVALID_VECTOR;
    }

    *initial_stack_pointer = stack_pointer;
    *reset_handler = vector_reset_handler;
    return STM32_PACKAGE_VALID;
}
