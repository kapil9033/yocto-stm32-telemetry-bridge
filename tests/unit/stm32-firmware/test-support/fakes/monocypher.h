#ifndef TEST_MONOCYPHER_H
#define TEST_MONOCYPHER_H

#include <stddef.h>
#include <stdint.h>

void crypto_blake2b(uint8_t *hash, size_t hash_size,
                    const uint8_t *message, size_t message_size);
int crypto_verify32(const uint8_t a[32], const uint8_t b[32]);

#endif
