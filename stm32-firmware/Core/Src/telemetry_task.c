#include "telemetry_task.h"
#include "sensors_driver.h"
#include <string.h>

/* External Handles */
extern ADC_HandleTypeDef hadc1;
extern UART_HandleTypeDef huart2;
extern I2C_HandleTypeDef hi2c1;

/* Shared DMA Buffer & Synchronization Semaphore */
extern volatile uint16_t adc_dma_buffer[ADC_CHANNELS_NUM];
extern SemaphoreHandle_t xAdcDmaSemaphore;

/**
  * @brief Calculates Modbus CRC-16 Checksum over frame data.
  */
uint16_t Calculate_CRC16(const uint8_t *data, uint16_t length)
{
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (uint8_t j = 0; j < 8; ++j) {
            if (crc & 0x0001) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

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

    TelemetryPayload payload;
    uint8_t tx_frame_buffer[64];

    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(1000); // 1Hz Telemetry Rate (matches DHT11 refresh rate)

    for (;;)
    {
        /* Wait for ADC DMA conversion frame complete */
        if (xSemaphoreTake(xAdcDmaSemaphore, xFrequency) == pdTRUE)
        {
            /* 1. Extract Analog Accelerometer & Photocell Data */
            uint16_t raw_x = adc_dma_buffer[0];
            uint16_t raw_y = adc_dma_buffer[1];
            uint16_t raw_z = adc_dma_buffer[2];
            
            payload.accel_x_mg   = (int16_t)(((int32_t)raw_x - 2048) * 8058 / 3300);
            payload.accel_y_mg   = (int16_t)(((int32_t)raw_y - 2048) * 8058 / 3300);
            payload.accel_z_mg   = (int16_t)(((int32_t)raw_z - 2048) * 8058 / 3300);
            payload.light_lux_raw = adc_dma_buffer[3];

            /* 2. Read DS3231 RTC Timestamp (Fallback to FreeRTOS Uptime if read fails) */
            uint32_t rtc_epoch = 0;
            if (DS3231_Read_Timestamp(&rtc_epoch)) {
                payload.timestamp_sec = rtc_epoch;
            } else {
                payload.timestamp_sec = xTaskGetTickCount() / configTICK_RATE_HZ;
            }

            /* 3. Read DHT11 Temperature & Humidity (Fallback to defaults if read fails) */
            uint8_t temp = 0, humidity = 0;
            if (DHT11_Read_Data(&temp, &humidity)) {
                payload.temp_celsius = (int8_t)temp;
                payload.humidity_pct = humidity;
            } else {
                payload.temp_celsius = 25; // Default safe fallback
                payload.humidity_pct = 50; // Default safe fallback
            }

            /* 4. Read User Button State (PC13, active LOW on NUCLEO boards) */
            payload.button_state = (HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_13) == GPIO_PIN_RESET) ? 1 : 0;

            /* 5. Assemble Binary Telemetry Frame */
            uint16_t idx = 0;
            tx_frame_buffer[idx++] = FRAME_SOF;                 /* 0xAA Header */
            tx_frame_buffer[idx++] = MSG_TYPE_TELEMETRY;         /* 0x01 Type   */
            tx_frame_buffer[idx++] = sizeof(TelemetryPayload); /* Payload Length (16 bytes) */

            /* Copy Packed Struct into Frame Buffer */
            memcpy(&tx_frame_buffer[idx], &payload, sizeof(TelemetryPayload));
            idx += sizeof(TelemetryPayload);

            /* 6. Compute CRC16 over SOF + TYPE + LENGTH + PAYLOAD */
            uint16_t crc = Calculate_CRC16(tx_frame_buffer, idx);
            tx_frame_buffer[idx++] = (uint8_t)(crc & 0xFF);         /* CRC Low Byte  */
            tx_frame_buffer[idx++] = (uint8_t)((crc >> 8) & 0xFF);  /* CRC High Byte */
            tx_frame_buffer[idx++] = FRAME_EOF;                    /* 0x55 Footer   */

            /* 7. Transmit Binary Protocol Frame over UART */
            HAL_UART_Transmit(&huart2, tx_frame_buffer, idx, HAL_MAX_DELAY);
        }

        /* Maintain steady 1Hz execution frequency */
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}
