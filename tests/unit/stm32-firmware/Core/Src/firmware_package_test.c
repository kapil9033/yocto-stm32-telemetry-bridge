#include "firmware_package.h"

#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

static int signature_valid = 1;

int ed25519_sign_open(const unsigned char *message, size_t message_length,
                      const unsigned char public_key[32],
                      const unsigned char signature[64])
{
    (void)message;
    (void)message_length;
    (void)public_key;
    (void)signature;
    return signature_valid ? 0 : -1;
}

void crypto_blake2b(uint8_t *hash, size_t hash_size,
                    const uint8_t *message, size_t message_size)
{
    (void)message;
    (void)message_size;
    memset(hash, 0x5AU, hash_size);
}

int crypto_verify32(const uint8_t a[32], const uint8_t b[32])
{
    return memcmp(a, b, 32U);
}

static uint8_t package[STM32_PACKAGE_HEADER_SIZE + 8U];

static void write_u32_le(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)value;
    destination[1] = (uint8_t)(value >> 8U);
    destination[2] = (uint8_t)(value >> 16U);
    destination[3] = (uint8_t)(value >> 24U);
}

static void make_valid_package(void)
{
    memset(package, 0, sizeof(package));
    memcpy(package, "STM32SF1", 8U);
    write_u32_le(&package[8], STM32_PACKAGE_FORMAT_VERSION);
    memcpy(&package[12], "STM32F446RE", 11U);
    write_u32_le(&package[32], 8U);
    memset(&package[36], 0x5A, 32U);
    write_u32_le(&package[STM32_PACKAGE_PAYLOAD_OFFSET], 0x20001000U);
    write_u32_le(&package[STM32_PACKAGE_PAYLOAD_OFFSET + 4U],
                 STM32_PACKAGE_APP_VECTOR_ADDRESS | 1U);
}

int main(void)
{
    uint32_t stack_pointer = 0U;
    uint32_t reset_handler = 0U;

    make_valid_package();
    assert(stm32_package_verify(NULL, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_HEADER);
    assert(stm32_package_verify(package, sizeof(package), NULL,
                                &reset_handler) == STM32_PACKAGE_INVALID_HEADER);
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                NULL) == STM32_PACKAGE_INVALID_HEADER);
    assert(stm32_package_verify(package, STM32_PACKAGE_HEADER_SIZE - 1U,
                                &stack_pointer, &reset_handler) == STM32_PACKAGE_INVALID_HEADER);
    assert(stm32_package_verify(package, STM32_PACKAGE_SLOT_SIZE + 1U,
                                &stack_pointer, &reset_handler) == STM32_PACKAGE_INVALID_HEADER);

    package[0] ^= 1U;
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_HEADER);
    make_valid_package();
    package[140] = 1U;
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_HEADER);
    make_valid_package();
    write_u32_le(&package[32], 0U);
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_HEADER);
    make_valid_package();
    write_u32_le(&package[32], 9U);
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_HEADER);

    make_valid_package();
    signature_valid = 0;
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_SIGNATURE);
    signature_valid = 1;

    make_valid_package();
    package[36] ^= 1U;
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_DIGEST);

    make_valid_package();
    write_u32_le(&package[STM32_PACKAGE_PAYLOAD_OFFSET], 0x20000001U);
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_VECTOR);
    make_valid_package();
    write_u32_le(&package[STM32_PACKAGE_PAYLOAD_OFFSET + 4U],
                 STM32_PACKAGE_APP_VECTOR_ADDRESS);
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_VECTOR);
    make_valid_package();
    write_u32_le(&package[STM32_PACKAGE_PAYLOAD_OFFSET + 4U],
                 STM32_PACKAGE_APP_VECTOR_ADDRESS + 9U);
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_INVALID_VECTOR);

    make_valid_package();
    assert(stm32_package_verify(package, sizeof(package), &stack_pointer,
                                &reset_handler) == STM32_PACKAGE_VALID);
    assert(stack_pointer == 0x20001000U);
    assert(reset_handler == (STM32_PACKAGE_APP_VECTOR_ADDRESS | 1U));
    return 0;
}
