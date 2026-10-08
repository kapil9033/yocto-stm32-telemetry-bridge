#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#define PROTOCOL_SYNC_MARKER 0xAA55

typedef struct __attribute__((packed)) {
    uint16_t sync;
    uint8_t  msg_type;
    uint8_t  length;
} packet_header_t;

typedef struct __attribute__((packed)) {
    float    temperature;
    float    humidity;
    uint32_t timestamp_ms;
} telemetry_payload_t;

uint16_t calculate_crc16(const uint8_t *data, uint16_t length) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < length; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (uint8_t j = 0; j < 8; j++) {
            if (crc & 0x8000) {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

int main(void) {
    printf("Gateway Receiver: Ready to decode UART telemetry frames.\n");
    return 0;
}
