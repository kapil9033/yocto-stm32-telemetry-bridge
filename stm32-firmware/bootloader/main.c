#include <stdint.h>

#include "firmware_package.h"
#include "stm32f446xx.h"

extern uint32_t _estack;
void SystemInit(void);

static void boot_fail_closed(void)
{
    for (;;) {
        __NOP();
    }
}

static uint32_t read_image_size(const uint8_t *package)
{
    return (uint32_t)package[32]
         | ((uint32_t)package[33] << 8U)
         | ((uint32_t)package[34] << 16U)
         | ((uint32_t)package[35] << 24U);
}

__attribute__((noreturn))
static void jump_to_application(uint32_t initial_stack_pointer, uint32_t reset_handler)
{
    __disable_irq();
    SysTick->CTRL = 0U;
    SysTick->LOAD = 0U;
    SysTick->VAL = 0U;

    const uint32_t interrupt_bank_count =
        (SCnSCB->ICTR & SCnSCB_ICTR_INTLINESNUM_Msk) + 1U;
    for (uint32_t bank = 0U; bank < interrupt_bank_count; ++bank) {
        NVIC->ICER[bank] = 0xFFFFFFFFU;
        NVIC->ICPR[bank] = 0xFFFFFFFFU;
    }

    SCB->VTOR = STM32_PACKAGE_APP_VECTOR_ADDRESS;
    __DSB();
    __ISB();
    __set_BASEPRI(0U);
    __set_FAULTMASK(0U);
    __set_CONTROL(0U);
    __ISB();
    __asm volatile(
        "msr msp, %0\n"
        "cpsie i\n"
        "bx %1\n"
        :
        : "r" (initial_stack_pointer), "r" (reset_handler)
        : "memory");

    __builtin_unreachable();
}

int main(void)
{
    (void)&_estack;

    const uint8_t *const package =
        (const uint8_t *)STM32_PACKAGE_APP_SLOT_ADDRESS;
    uint32_t initial_stack_pointer = 0U;
    uint32_t reset_handler = 0U;
    const uint32_t image_size = read_image_size(package);
    if (image_size == 0U || image_size > STM32_PACKAGE_MAX_IMAGE_SIZE) {
        boot_fail_closed();
    }

    if (stm32_package_verify(
            package,
            STM32_PACKAGE_HEADER_SIZE + (size_t)image_size,
            &initial_stack_pointer,
            &reset_handler) != STM32_PACKAGE_VALID) {
        boot_fail_closed();
    }

    jump_to_application(initial_stack_pointer, reset_handler);
}
