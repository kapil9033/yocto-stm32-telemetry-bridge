#include "sensors_driver.h"

#include <assert.h>
#include <stddef.h>
#include <stdint.h>

fake_dwt_t fake_dwt;
fake_core_debug_t fake_core_debug;
uint32_t SystemCoreClock = 0U;

static I2C_HandleTypeDef bus;
static uint8_t rtc_registers[7];
static int transmit_status = HAL_OK;
static int receive_status = HAL_OK;
static int mutex_take_status = pdTRUE;
static int receive_calls;
static GPIO_PinState pin_samples[130];
static size_t pin_sample_count;
static size_t pin_sample_index;
static GPIO_PinState idle_pin_level = GPIO_PIN_RESET;

SemaphoreHandle_t xSemaphoreCreateMutex(void)
{
    static int mutexes[2];
    static size_t next_mutex;
    assert(next_mutex < 2U);
    return &mutexes[next_mutex++];
}

int xSemaphoreTake(SemaphoreHandle_t semaphore, unsigned int timeout)
{
    (void)semaphore;
    (void)timeout;
    return mutex_take_status;
}

int xSemaphoreGive(SemaphoreHandle_t semaphore)
{
    (void)semaphore;
    return pdTRUE;
}

int HAL_I2C_Master_Transmit(I2C_HandleTypeDef *handle, uint16_t address,
                            uint8_t *data, uint16_t length, uint32_t timeout)
{
    (void)handle;
    (void)timeout;
    assert(address == DS3231_I2C_ADDR);
    assert(length == 1U && data[0] == 0U);
    return transmit_status;
}

int HAL_I2C_Master_Receive(I2C_HandleTypeDef *handle, uint16_t address,
                           uint8_t *data, uint16_t length, uint32_t timeout)
{
    (void)handle;
    (void)timeout;
    assert(address == DS3231_I2C_ADDR);
    assert(length == sizeof(rtc_registers));
    ++receive_calls;
    if (receive_status == HAL_OK) {
        for (size_t index = 0U; index < sizeof(rtc_registers); ++index) {
            data[index] = rtc_registers[index];
        }
    }
    return receive_status;
}

void HAL_GPIO_Init(void *port, GPIO_InitTypeDef *configuration)
{
    assert(port == GPIOA);
    assert(configuration->Pin == GPIO_PIN_6);
}

void HAL_GPIO_WritePin(void *port, uint32_t pin, GPIO_PinState state)
{
    (void)state;
    assert(port == GPIOA && pin == GPIO_PIN_6);
}

GPIO_PinState HAL_GPIO_ReadPin(void *port, uint32_t pin)
{
    assert(port == GPIOA && pin == GPIO_PIN_6);
    if (pin_sample_index < pin_sample_count) {
        return pin_samples[pin_sample_index++];
    }
    return idle_pin_level;
}

static void set_dht_frame(uint8_t humidity, uint8_t temperature, int valid_checksum)
{
    uint8_t frame[5] = {humidity, 0U, temperature, 0U, 0U};
    frame[4] = (uint8_t)(frame[0] + frame[1] + frame[2] + frame[3]);
    if (!valid_checksum) {
        frame[4] ^= 1U;
    }

    pin_sample_count = 0U;
    pin_sample_index = 0U;
    pin_samples[pin_sample_count++] = GPIO_PIN_RESET;
    pin_samples[pin_sample_count++] = GPIO_PIN_SET;
    pin_samples[pin_sample_count++] = GPIO_PIN_RESET;
    for (size_t byte_index = 0U; byte_index < sizeof(frame); ++byte_index) {
        for (int bit = 7; bit >= 0; --bit) {
            const GPIO_PinState value = (frame[byte_index] & (1U << bit))
                ? GPIO_PIN_SET : GPIO_PIN_RESET;
            pin_samples[pin_sample_count++] = GPIO_PIN_SET;
            pin_samples[pin_sample_count++] = value;
            pin_samples[pin_sample_count++] = GPIO_PIN_RESET;
        }
    }
}

int main(void)
{
    Sensors_Init(&bus);

    uint32_t timestamp = 0U;
    rtc_registers[0] = 0x56U | 0x80U;
    rtc_registers[1] = 0x34U | 0x80U;
    rtc_registers[2] = 0x12U | 0x40U;
    assert(DS3231_Read_Timestamp(&timestamp) == 1U);
    assert(timestamp == (12U * 3600U + 34U * 60U + 56U));

    timestamp = 99U;
    assert(DS3231_Read_Timestamp(NULL) == 0U);
    mutex_take_status = pdFALSE;
    assert(DS3231_Read_Timestamp(&timestamp) == 0U);
    assert(timestamp == 99U);
    mutex_take_status = pdTRUE;
    transmit_status = 1;
    assert(DS3231_Read_Timestamp(&timestamp) == 0U);
    transmit_status = HAL_OK;
    receive_status = 1;
    const int before_failed_receive = receive_calls;
    assert(DS3231_Read_Timestamp(&timestamp) == 0U);
    assert(receive_calls == before_failed_receive + 1);
    receive_status = HAL_OK;

    uint8_t temperature = 0U;
    uint8_t humidity = 0U;
    assert(DHT11_Read_Data(NULL, &humidity) == 0U);
    assert(DHT11_Read_Data(&temperature, NULL) == 0U);

    set_dht_frame(61U, 24U, 1);
    assert(DHT11_Read_Data(&temperature, &humidity) == 1U);
    assert(temperature == 24U && humidity == 61U);

    temperature = 0xAAU;
    humidity = 0xBBU;
    set_dht_frame(61U, 24U, 0);
    assert(DHT11_Read_Data(&temperature, &humidity) == 0U);
    assert(temperature == 0xAAU && humidity == 0xBBU);

    pin_sample_count = 0U;
    pin_sample_index = 0U;
    idle_pin_level = GPIO_PIN_SET;
    assert(DHT11_Read_Data(&temperature, &humidity) == 0U);
    idle_pin_level = GPIO_PIN_RESET;
    return 0;
}
