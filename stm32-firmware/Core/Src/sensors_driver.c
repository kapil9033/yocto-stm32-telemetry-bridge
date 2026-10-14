#include "sensors_driver.h"

static I2C_HandleTypeDef *p_hi2c = NULL;
static SemaphoreHandle_t xI2cMutex = NULL;
static SemaphoreHandle_t xDht11Mutex = NULL;

#define DHT11_EDGE_TIMEOUT_US 100U

/* Helper: BCD to Decimal Conversion */
static uint8_t BCD2DEC(uint8_t val) {
    return (uint8_t)(((val >> 4) * 10) + (val & 0x0F));
}

/**
  * @brief Initialize Mutexes and I2C peripheral handle
  */
void Sensors_Init(I2C_HandleTypeDef *hi2c)
{
    p_hi2c = hi2c;

    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0U;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

    if (xI2cMutex == NULL) {
        xI2cMutex = xSemaphoreCreateMutex();
    }
    if (xDht11Mutex == NULL) {
        xDht11Mutex = xSemaphoreCreateMutex();
    }
}

/**
  * @brief Reads UNIX Epoch timestamp from DS3231 over I2C with Mutex Protection
  */
uint8_t DS3231_Read_Timestamp(uint32_t *epoch_sec)
{
    if (p_hi2c == NULL || epoch_sec == NULL) return 0;

    uint8_t reg = 0x00;
    uint8_t buffer[7];
    uint8_t status = 0;

    /* Acquire I2C Bus Mutex (Wait up to 100ms) */
    if (xSemaphoreTake(xI2cMutex, pdMS_TO_TICKS(100)) == pdTRUE)
    {
        if (HAL_I2C_Master_Transmit(p_hi2c, DS3231_I2C_ADDR, &reg, 1, 100) == HAL_OK) {
            if (HAL_I2C_Master_Receive(p_hi2c, DS3231_I2C_ADDR, buffer, 7, 100) == HAL_OK) {
                status = 1;
            }
        }
        xSemaphoreGive(xI2cMutex);
    }

    if (status) {
        uint8_t sec  = BCD2DEC(buffer[0] & 0x7F);
        uint8_t min  = BCD2DEC(buffer[1] & 0x7F);
        uint8_t hour = BCD2DEC(buffer[2] & 0x3F);

        /* Approximate seconds calculation for payload timestamp */
        *epoch_sec = (uint32_t)(hour * 3600 + min * 60 + sec);
        return 1;
    }

    return 0;
}

/* Microsecond Delay Helper for Single-Wire Protocol */
static void delay_us(uint32_t us) {
    uint32_t cycles = (SystemCoreClock / 1000000U) * us;
    uint32_t start = DWT->CYCCNT;
    while ((DWT->CYCCNT - start) < cycles) {
    }
}

static uint8_t DHT11_WaitForLevel(GPIO_PinState level, uint32_t timeout_us)
{
    uint32_t timeout_cycles = (SystemCoreClock / 1000000U) * timeout_us;
    uint32_t start = DWT->CYCCNT;

    while (HAL_GPIO_ReadPin(DHT11_PORT, DHT11_PIN) != level) {
        if ((DWT->CYCCNT - start) >= timeout_cycles) {
            return 0U;
        }
    }

    return 1U;
}

static void DHT11_Set_Pin_Output(void) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    GPIO_InitStruct.Pin = DHT11_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(DHT11_PORT, &GPIO_InitStruct);
}

static void DHT11_Set_Pin_Input(void) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    GPIO_InitStruct.Pin = DHT11_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(DHT11_PORT, &GPIO_InitStruct);
}

/**
  * @brief Reads Temperature & Humidity from DHT11 with Mutex Protection
  */
uint8_t DHT11_Read_Data(uint8_t *temp, uint8_t *humidity)
{
    if (temp == NULL || humidity == NULL || xDht11Mutex == NULL) {
        return 0U;
    }

    uint8_t data[5] = {0};
    uint8_t success = 0;

    /* Lock DHT11 Single-Wire Bus Mutex */
    if (xSemaphoreTake(xDht11Mutex, pdMS_TO_TICKS(1000)) == pdTRUE)
    {
        taskENTER_CRITICAL(); /* Critical section for precise timing */

        /* 1. Host Start Signal */
        DHT11_Set_Pin_Output();
        HAL_GPIO_WritePin(DHT11_PORT, DHT11_PIN, GPIO_PIN_RESET);
        delay_us(18000); // Pull down for 18ms
        HAL_GPIO_WritePin(DHT11_PORT, DHT11_PIN, GPIO_PIN_SET);
        delay_us(30);

        /* 2. Switch to input and bound every response-edge wait. */
        DHT11_Set_Pin_Input();

        if (DHT11_WaitForLevel(GPIO_PIN_RESET, DHT11_EDGE_TIMEOUT_US) &&
            DHT11_WaitForLevel(GPIO_PIN_SET, DHT11_EDGE_TIMEOUT_US) &&
            DHT11_WaitForLevel(GPIO_PIN_RESET, DHT11_EDGE_TIMEOUT_US)) {
            /* 3. Read 40 bits (5 bytes), timing out on missing edges. */
            success = 1U;
            for (uint8_t i = 0U; i < 40U; ++i) {
                if (!DHT11_WaitForLevel(GPIO_PIN_SET, DHT11_EDGE_TIMEOUT_US)) {
                    success = 0U;
                    break;
                }

                delay_us(40U);
                if (HAL_GPIO_ReadPin(DHT11_PORT, DHT11_PIN) == GPIO_PIN_SET) {
                    data[i / 8U] |= (uint8_t)(1U << (7U - (i % 8U)));
                }

                if (!DHT11_WaitForLevel(GPIO_PIN_RESET, DHT11_EDGE_TIMEOUT_US)) {
                    success = 0U;
                    break;
                }
            }

            /* 4. Validate checksum */
            if (success &&
                data[4] == (uint8_t)(data[0] + data[1] + data[2] + data[3])) {
                *humidity = data[0];
                *temp = data[2];
            } else {
                success = 0U;
            }
        }

        taskEXIT_CRITICAL();
        xSemaphoreGive(xDht11Mutex);
    }

    return success;
}
