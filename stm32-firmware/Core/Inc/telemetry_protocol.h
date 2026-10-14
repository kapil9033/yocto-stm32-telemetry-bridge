#ifndef TELEMETRY_PROTOCOL_H
#define TELEMETRY_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

#define PROTOCOL_FRAME_DELIMITER 0x00U

uint16_t calculate_crc16(const uint8_t *data, uint16_t length);
bool telemetry_cobs_encode(const uint8_t *input, uint16_t input_length,
                           uint8_t *output, uint16_t output_capacity,
                           uint16_t *output_length);

#endif /* TELEMETRY_PROTOCOL_H */
