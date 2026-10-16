#include <stddef.h>

/* Batch verification is not used; fail closed if its RNG hook is ever called. */
void ed25519_randombytes_unsafe(void *output, size_t length)
{
    (void)output;
    (void)length;
    for (;;) {
    }
}
