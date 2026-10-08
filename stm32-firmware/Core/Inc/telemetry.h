#ifndef TELEMETRY_H
#define TELEMETRY_H

#include <stdint.h>

#define FRAME_SOF      0xAA
#define FRAME_EOF      0x55
#define MSG_TELEMETRY  0x01
#define MSG_ALARM      0x02
#define MSG_COMMAND    0x03

typedef struct __attribute__((packed)) {
    uint32_t timestamp_sec;  // DS3231 RTC Unix Timestamp
    int16_t  accel_x_mg;     // ADXL335 X-axis Acceleration (milli-g)
    int16_t  accel_y_mg;     // ADXL335 Y-axis Acceleration (milli-g)
    int16_t  accel_z_mg;     // ADXL335 Z-axis Acceleration (milli-g)
    uint16_t light_lux_raw;  // Photocell ADC Raw Value
    int8_t   temp_celsius;   // DHT11 Ambient Temperature (°C)
    uint8_t  humidity_pct;   // DHT11 Relative Humidity (%)
    uint8_t  button_state;   // EXTI Push Button Toggle Flag
} TelemetryPayload_t;

typedef struct __attribute__((packed)) {
    uint8_t  sof;
    uint8_t  msg_type;
    uint8_t  payload_len;
    TelemetryPayload_t payload;
    uint16_t crc16;
    uint8_t  eof;
} TelemetryFrame_t;

uint16_t calculate_crc16(const uint8_t *data, uint16_t length);

#endif // TELEMETRY_H
