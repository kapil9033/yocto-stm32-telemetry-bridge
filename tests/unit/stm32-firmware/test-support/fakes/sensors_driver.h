#ifndef TEST_SENSORS_DRIVER_H
#define TEST_SENSORS_DRIVER_H

#include "main.h"
#include "FreeRTOS.h"
#include "semphr.h"

#define DHT11_PORT GPIOA
#define DHT11_PIN GPIO_PIN_6
#define DS3231_I2C_ADDR (0x68U << 1U)

void Sensors_Init(I2C_HandleTypeDef *hi2c);
uint8_t DS3231_Read_Timestamp(uint32_t *epoch_sec);
uint8_t DHT11_Read_Data(uint8_t *temp, uint8_t *humidity);

#endif
