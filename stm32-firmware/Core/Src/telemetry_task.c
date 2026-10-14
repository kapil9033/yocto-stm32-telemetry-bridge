#include "telemetry_task.h"
#include "telemetry_protocol.h"
#include "sensors_driver.h"
#include "lcd1602.h"
#include <limits.h>
#include <stdio.h>
#include <string.h>

/* External Handles */
extern ADC_HandleTypeDef hadc1;
extern UART_HandleTypeDef huart2;
extern I2C_HandleTypeDef hi2c1;

/* Shared DMA Buffer & Synchronization Semaphore */
extern volatile uint16_t adc_dma_buffer[ADC_CHANNELS_NUM];
extern SemaphoreHandle_t xAdcDmaSemaphore;

/**
  * @brief FreeRTOS Task: Acquires ADC DMA measurements, DS3231 RTC timestamp, 
  *        and DHT11 temperature/humidity values, then transmits framed telemetry over UART.
  */
void StartTelemetryTask(void *argument)
{
    (void)argument;

    /* Initialize Thread-Safe Sensor Driver Mutexes & Handles */
    Sensors_Init(&hi2c1);

    /* Start ADC1 in Scan Mode with Circular DMA Transfer */
    HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_dma_buffer, ADC_CHANNELS_NUM);

    TelemetryPayload payload = {0};
    uint8_t raw_frame[sizeof(TelemetryPayload) + 4U];
    uint8_t tx_frame_buffer[64];

    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(1000); // 1Hz Telemetry Rate (matches DHT11 refresh rate)

    for (;;)
    {
        /* Keep telemetry flowing even if ADC DMA has not produced a frame. */
        if (xSemaphoreTake(xAdcDmaSemaphore, xFrequency) == pdTRUE) {
            /* 1. Extract Analog Accelerometer & Photocell Data */
            uint16_t raw_x = adc_dma_buffer[0];
            uint16_t raw_y = adc_dma_buffer[1];
            uint16_t raw_z = adc_dma_buffer[2];
            
            payload.accel_x_mg   = (int16_t)(((int32_t)raw_x - 2048) * 8058 / 3300);
            payload.accel_y_mg   = (int16_t)(((int32_t)raw_y - 2048) * 8058 / 3300);
            payload.accel_z_mg   = (int16_t)(((int32_t)raw_z - 2048) * 8058 / 3300);
            payload.light_lux_raw = adc_dma_buffer[3];
        }

        /* 2. Read DS3231 RTC Timestamp (Fallback to FreeRTOS Uptime if read fails) */
        uint32_t rtc_epoch = 0;
        if (DS3231_Read_Timestamp(&rtc_epoch)) {
            payload.timestamp_sec = rtc_epoch;
        } else {
            payload.timestamp_sec = xTaskGetTickCount() / configTICK_RATE_HZ;
        }

        /* 3. Read DHT11; sentinel values make failed reads visible in output. */
        uint8_t temp = 0U;
        uint8_t humidity = 0U;
        if (DHT11_Read_Data(&temp, &humidity)) {
            payload.temp_celsius = (int8_t)temp;
            payload.humidity_pct = humidity;
        } else {
            payload.temp_celsius = INT8_MIN;
            payload.humidity_pct = UINT8_MAX;
        }

        /* 4. Read User Button State (PC13, active LOW on NUCLEO boards) */
        payload.button_state = (HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_13) == GPIO_PIN_RESET) ? 1U : 0U;

        char display_line[17];
        if (payload.humidity_pct == UINT8_MAX) {
            (void)snprintf(display_line, sizeof(display_line), "DHT11 READ ERR");
        } else {
            (void)snprintf(display_line, sizeof(display_line), "T:%dC H:%u%%",
                           (int)payload.temp_celsius,
                           (unsigned int)payload.humidity_pct);
        }
        LCD1602_WriteLine(0U, display_line);

        (void)snprintf(display_line, sizeof(display_line), "L:%u B:%u",
                       (unsigned int)payload.light_lux_raw,
                       (unsigned int)payload.button_state);
        LCD1602_WriteLine(1U, display_line);

        /* 5. Build type + length + payload + little-endian Modbus CRC16. */
        uint16_t raw_length = 0U;
        raw_frame[raw_length++] = MSG_TYPE_TELEMETRY;
        raw_frame[raw_length++] = (uint8_t)sizeof(TelemetryPayload);
        memcpy(&raw_frame[raw_length], &payload, sizeof(TelemetryPayload));
        raw_length += (uint16_t)sizeof(TelemetryPayload);

        uint16_t crc = calculate_crc16(raw_frame, raw_length);
        raw_frame[raw_length++] = (uint8_t)(crc & 0xFFU);
        raw_frame[raw_length++] = (uint8_t)((crc >> 8) & 0xFFU);

        /* 6. COBS-encode the raw frame and terminate it with 0x00. */
        uint16_t encoded_length = 0U;
        if (!telemetry_cobs_encode(raw_frame, raw_length, tx_frame_buffer,
                                   (uint16_t)sizeof(tx_frame_buffer), &encoded_length)) {
            Error_Handler();
        }

        /* 7. Transmit the encoded frame over UART. */
        HAL_UART_Transmit(&huart2, tx_frame_buffer, encoded_length, HAL_MAX_DELAY);

        /* Maintain steady 1Hz execution frequency */
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}
