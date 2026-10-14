#include "lcd1602.h"
#include "main.h"
#include <stddef.h>

#define LCD_RS_PIN GPIO_PIN_0
#define LCD_E_PIN  GPIO_PIN_1

static const uint16_t lcd_data_pins[] = {
    GPIO_PIN_2,
    GPIO_PIN_3,
    GPIO_PIN_4,
    GPIO_PIN_5
};

static void LCD1602_DelayUs(uint32_t microseconds)
{
    uint32_t cycles = (SystemCoreClock / 1000000U) * microseconds;
    uint32_t start = DWT->CYCCNT;
    while ((DWT->CYCCNT - start) < cycles) {
    }
}

static void LCD1602_PulseEnable(void)
{
    HAL_GPIO_WritePin(GPIOC, LCD_E_PIN, GPIO_PIN_SET);
    LCD1602_DelayUs(1U);
    HAL_GPIO_WritePin(GPIOC, LCD_E_PIN, GPIO_PIN_RESET);
    LCD1602_DelayUs(1U);
}

static void LCD1602_WriteNibble(uint8_t nibble)
{
    for (size_t i = 0; i < sizeof(lcd_data_pins) / sizeof(lcd_data_pins[0]); ++i) {
        GPIO_PinState state = ((nibble & (uint8_t)(1U << i)) != 0U)
            ? GPIO_PIN_SET
            : GPIO_PIN_RESET;
        HAL_GPIO_WritePin(GPIOC, lcd_data_pins[i], state);
    }
    LCD1602_PulseEnable();
}

static void LCD1602_Send(uint8_t value, GPIO_PinState register_select)
{
    HAL_GPIO_WritePin(GPIOC, LCD_RS_PIN, register_select);
    LCD1602_WriteNibble((uint8_t)(value >> 4));
    LCD1602_WriteNibble((uint8_t)(value & 0x0FU));
    LCD1602_DelayUs(50U);
}

static void LCD1602_Command(uint8_t command)
{
    LCD1602_Send(command, GPIO_PIN_RESET);
    if (command == 0x01U || command == 0x02U) {
        LCD1602_DelayUs(2000U);
    }
}

void LCD1602_Init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0U;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    HAL_GPIO_WritePin(GPIOC, LCD_RS_PIN | LCD_E_PIN, GPIO_PIN_RESET);
    LCD1602_DelayUs(40000U);

    LCD1602_WriteNibble(0x03U);
    LCD1602_DelayUs(5000U);
    LCD1602_WriteNibble(0x03U);
    LCD1602_DelayUs(1000U);
    LCD1602_WriteNibble(0x03U);
    LCD1602_DelayUs(1000U);
    LCD1602_WriteNibble(0x02U);

    LCD1602_Command(0x28U);
    LCD1602_Command(0x08U);
    LCD1602_Command(0x01U);
    LCD1602_Command(0x06U);
    LCD1602_Command(0x0CU);
}

void LCD1602_WriteLine(uint8_t row, const char *text)
{
    if (row > 1U || text == NULL) {
        return;
    }

    size_t text_length = 0U;
    while (text_length < 16U && text[text_length] != '\0') {
        ++text_length;
    }

    LCD1602_Command(row == 0U ? 0x80U : 0xC0U);

    for (size_t i = 0; i < 16U; ++i) {
        uint8_t character = (i < text_length) ? (uint8_t)text[i] : (uint8_t)' ';
        LCD1602_Send(character, GPIO_PIN_SET);
    }
}
