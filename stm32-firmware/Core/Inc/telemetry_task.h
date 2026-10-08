#ifndef TELEMETRY_TASK_H
#define TELEMETRY_TASK_H

#include "main.h"
#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"

/* Protocol Frame Marker Definitions */
#define FRAME_SOF         0xAA
#define FRAME_EOF         0x55
#define MSG_TYPE_TELEMETRY 0x01

#define ADC_CHANNELS_NUM  4

/* Telemetry Binary Payload (Packed, 16 Bytes Total) */
typedef struct __attribute__((packed)) {
    uint32_t timestamp_sec;   /* RTC/System Uptime Seconds */
    int16_t  accel_x_mg;      /* ADXL335 X-Axis Acceleration */
    int16_t  accel_y_mg;      /* ADXL335 Y-Axis Acceleration */
    int16_t  accel_z_mg;      /* ADXL335 Z-Axis Acceleration */
    uint16_t light_lux_raw;   /* Photocell 12-bit ADC Value  */
    int8_t   temp_celsius;    /* Temperature Sensor Value    */
    uint8_t  humidity_pct;    /* Humidity Sensor Value       */
    uint8_t  button_state;    /* EXTI GPIO User Button State */
} TelemetryPayload;

/* Function Declarations */
void StartTelemetryTask(void *argument);
uint16_t Calculate_CRC16(const uint8_t *data, uint16_t length);

#endif /* TELEMETRY_TASK_H */
