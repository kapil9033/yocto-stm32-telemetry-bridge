#include "telemetry_protocol.h"
#include <assert.h>
#include <stdint.h>

int main(void) {
    const uint8_t check[] = "123456789";
    assert(calculate_crc16(check, 9U) == 0x4B37U);
    assert(calculate_crc16(check, 0U) == 0xFFFFU);

    const uint8_t input[] = {0x11U, 0U, 0x22U};
    uint8_t encoded[8]; uint16_t length = 0U;
    assert(telemetry_cobs_encode(input, 3U, encoded, sizeof(encoded), &length));
    assert(length == 5U && encoded[0] == 2U && encoded[1] == 0x11U &&
           encoded[2] == 2U && encoded[3] == 0x22U && encoded[4] == 0U);
    assert(!telemetry_cobs_encode(input, 3U, encoded, 3U, &length));

    const uint8_t no_delimiters[] = {0x01U, 0x02U, 0x03U};
    assert(telemetry_cobs_encode(no_delimiters, sizeof(no_delimiters),
                                 encoded, sizeof(encoded), &length));
    assert(length == 5U && encoded[0] == 4U && encoded[1] == 1U &&
           encoded[2] == 2U && encoded[3] == 3U && encoded[4] == 0U);

    assert(!telemetry_cobs_encode(input, sizeof(input), 0, sizeof(encoded), &length));
    assert(!telemetry_cobs_encode(input, sizeof(input), encoded, sizeof(encoded), 0));
    assert(!telemetry_cobs_encode(input, sizeof(input), encoded, 1U, &length));
    assert(!telemetry_cobs_encode(0, 0U, encoded, sizeof(encoded), &length));
    assert(telemetry_cobs_encode(input, 0U, encoded, sizeof(encoded), &length));
    assert(length == 2U && encoded[0] == 1U && encoded[1] == 0U);
    return 0;
}
