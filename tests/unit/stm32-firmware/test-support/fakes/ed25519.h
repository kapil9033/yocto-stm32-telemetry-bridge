#ifndef TEST_ED25519_H
#define TEST_ED25519_H

#include <stddef.h>

typedef unsigned char ed25519_public_key[32];
typedef unsigned char ed25519_signature[64];

int ed25519_sign_open(const unsigned char *message, size_t message_length,
                      const ed25519_public_key public_key,
                      const ed25519_signature signature);

#endif
