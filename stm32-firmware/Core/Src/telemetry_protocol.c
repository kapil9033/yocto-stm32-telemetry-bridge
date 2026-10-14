#include "telemetry_protocol.h"

uint16_t calculate_crc16(const uint8_t *data, uint16_t length) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (uint8_t j = 0; j < 8; j++) {
            if ((crc & 0x0001U) != 0U) {
                crc = (crc >> 1) ^ 0xA001U;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

bool telemetry_cobs_encode(const uint8_t *input, uint16_t input_length,
                           uint8_t *output, uint16_t output_capacity,
                           uint16_t *output_length) {
    if (input == 0 || output == 0 || output_length == 0 || output_capacity < 2U) {
        return false;
    }

    uint16_t code_index = 0U;
    uint16_t write_index = 1U;
    uint8_t code = 1U;

    for (uint16_t read_index = 0U; read_index < input_length; read_index++) {
        if (input[read_index] == PROTOCOL_FRAME_DELIMITER) {
            output[code_index] = code;
            code_index = write_index;
            if (write_index >= output_capacity) {
                return false;
            }
            write_index++;
            code = 1U;
        } else {
            if (write_index >= output_capacity) {
                return false;
            }
            output[write_index++] = input[read_index];
            code++;

            if (code == 0xFFU) {
                output[code_index] = code;
                code_index = write_index;
                if (write_index >= output_capacity) {
                    return false;
                }
                write_index++;
                code = 1U;
            }
        }
    }

    if (code_index >= output_capacity || write_index >= output_capacity) {
        return false;
    }
    output[code_index] = code;
    output[write_index++] = PROTOCOL_FRAME_DELIMITER;
    *output_length = write_index;
    return true;
}
