#ifndef TELEMETRY_H
#define TELEMETRY_H

#include <cstdint>

#pragma pack(push, 1)
struct TelemetryPayload {
    uint32_t timestamp_sec;
    int16_t  accel_x_mg;
    int16_t  accel_y_mg;
    int16_t  accel_z_mg;
    uint16_t light_lux_raw;
    int8_t   temp_celsius;
    uint8_t  humidity_pct;
    uint8_t  button_state;
};

struct TelemetryFrame {
    uint8_t          sof;
    uint8_t          msg_type;
    uint8_t          payload_len;
    TelemetryPayload payload;
    uint16_t         crc16;
    uint8_t          eof;
};
#pragma pack(pop)

#endif // TELEMETRY_H
