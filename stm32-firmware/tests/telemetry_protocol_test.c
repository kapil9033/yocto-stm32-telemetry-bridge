#include "telemetry_protocol.h"
#include <assert.h>
#include <stdint.h>

int main(void) {
    const uint8_t check[] = "123456789";
    assert(calculate_crc16(check, 9U) == 0x4B37U);
    const uint8_t input[] = {0x11U, 0U, 0x22U};
    uint8_t encoded[8]; uint16_t length = 0U;
    assert(telemetry_cobs_encode(input, 3U, encoded, sizeof(encoded), &length));
    assert(length == 5U && encoded[0] == 2U && encoded[1] == 0x11U &&
           encoded[2] == 2U && encoded[3] == 0x22U && encoded[4] == 0U);
    assert(!telemetry_cobs_encode(input, 3U, encoded, 3U, &length));
    return 0;
}
