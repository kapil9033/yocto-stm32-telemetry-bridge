#ifndef __MAIN_H
#define __MAIN_H

#include <stddef.h>
#include <stdint.h>

typedef struct { volatile uint32_t CYCCNT; volatile uint32_t CTRL; } fake_dwt_t;
typedef struct { volatile uint32_t DEMCR; } fake_core_debug_t;
typedef struct { int unused; } I2C_HandleTypeDef;
typedef struct { uint32_t Pin; uint32_t Mode; uint32_t Speed; uint32_t Pull; } GPIO_InitTypeDef;
typedef enum { GPIO_PIN_RESET = 0, GPIO_PIN_SET = 1 } GPIO_PinState;

extern fake_dwt_t fake_dwt;
extern fake_core_debug_t fake_core_debug;
extern uint32_t SystemCoreClock;

#define DWT (&fake_dwt)
#define CoreDebug (&fake_core_debug)
#define CoreDebug_DEMCR_TRCENA_Msk (1U << 24U)
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define GPIOA ((void *)1)
#define GPIO_PIN_6 (1U << 6U)
#define GPIO_MODE_OUTPUT_PP 1U
#define GPIO_MODE_INPUT 2U
#define GPIO_SPEED_FREQ_LOW 1U
#define GPIO_NOPULL 0U
#define HAL_OK 0

int HAL_I2C_Master_Transmit(I2C_HandleTypeDef *handle, uint16_t address,
                            uint8_t *data, uint16_t length, uint32_t timeout);
int HAL_I2C_Master_Receive(I2C_HandleTypeDef *handle, uint16_t address,
                           uint8_t *data, uint16_t length, uint32_t timeout);
void HAL_GPIO_Init(void *port, GPIO_InitTypeDef *configuration);
void HAL_GPIO_WritePin(void *port, uint32_t pin, GPIO_PinState state);
GPIO_PinState HAL_GPIO_ReadPin(void *port, uint32_t pin);

#endif
