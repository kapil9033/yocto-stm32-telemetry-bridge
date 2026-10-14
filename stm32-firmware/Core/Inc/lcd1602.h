#ifndef LCD1602_H
#define LCD1602_H

#include <stdint.h>

void LCD1602_Init(void);
void LCD1602_WriteLine(uint8_t row, const char *text);

#endif
