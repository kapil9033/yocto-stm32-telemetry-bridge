#ifndef TELEMETRY_PROTOCOL_H
#define TELEMETRY_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

#define PROTOCOL_SYNC_MARKER  0xAA55
#define MSG_TYPE_TELEMETRY    0x01
#define MSG_TYPE_COMMAND      0x02

#pragma pack(push, 1)
typedef struct {
    uint16_t sync;
    uint8_t  msg_type;
    uint8_t  length;
} packet_header_t;

typedef struct {
    float    temperature;
    float    humidity;
    uint32_t timestamp_ms;
} telemetry_payload_t;

typedef struct {
    packet_header_t header;
    telemetry_payload_t payload;
    uint16_t crc16;
} telemetry_packet_t;
#pragma pack(pop)

uint16_t calculate_crc16(const uint8_t *data, uint16_t length);

#endif /* TELEMETRY_PROTOCOL_H */
