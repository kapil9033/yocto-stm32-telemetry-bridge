cmake_minimum_required(VERSION 3.16)
project(stm32f446_freertos_firmware C ASM)

include(FetchContent)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_program(OPENSSL_EXECUTABLE openssl)
if(NOT OPENSSL_EXECUTABLE)
    message(FATAL_ERROR "OpenSSL is required to extract the bootloader public key")
endif()

set(STM32_BOOT_PUBLIC_KEY_PEM "" CACHE FILEPATH
    "Ed25519 public key PEM trusted by the STM32 secure bootloader")
if(NOT EXISTS "${STM32_BOOT_PUBLIC_KEY_PEM}")
    message(FATAL_ERROR
        "Set STM32_BOOT_PUBLIC_KEY_PEM to the Ed25519 public key used to sign firmware packages")
endif()

if(POLICY CMP0169)
    cmake_policy(SET CMP0169 OLD)
endif()

FetchContent_Declare(
    cmsis_core
    GIT_REPOSITORY https://github.com/ARM-software/CMSIS_5.git
    GIT_TAG 5.9.0
    GIT_SHALLOW TRUE
)
FetchContent_Declare(
    cmsis_device_f4
    GIT_REPOSITORY https://github.com/STMicroelectronics/cmsis_device_f4.git
    GIT_TAG v2.6.10
    GIT_SHALLOW TRUE
)
FetchContent_Declare(
    stm32f4xx_hal
    GIT_REPOSITORY https://github.com/STMicroelectronics/stm32f4xx-hal-driver.git
    GIT_TAG v1.8.3
    GIT_SHALLOW TRUE
)
FetchContent_Declare(
    freertos_kernel
    GIT_REPOSITORY https://github.com/FreeRTOS/FreeRTOS-Kernel.git
    GIT_TAG V11.1.0
    GIT_SHALLOW TRUE
)
FetchContent_Declare(
    monocypher
    GIT_REPOSITORY https://github.com/LoupVaillant/Monocypher.git
    GIT_TAG 0d85f98c9d9b0227e42cf795cb527dff372b40a4
)
FetchContent_Declare(
    ed25519_donna
    GIT_REPOSITORY https://github.com/floodyberry/ed25519-donna.git
    GIT_TAG 8757bd4cd209cb032853ece0ce413f122eef212c
)

FetchContent_GetProperties(cmsis_core)
if(NOT cmsis_core_POPULATED)
    FetchContent_Populate(cmsis_core)
endif()
FetchContent_GetProperties(cmsis_device_f4)
if(NOT cmsis_device_f4_POPULATED)
    FetchContent_Populate(cmsis_device_f4)
endif()
FetchContent_GetProperties(stm32f4xx_hal)
if(NOT stm32f4xx_hal_POPULATED)
    FetchContent_Populate(stm32f4xx_hal)
endif()
FetchContent_GetProperties(freertos_kernel)
if(NOT freertos_kernel_POPULATED)
    FetchContent_Populate(freertos_kernel)
endif()
FetchContent_GetProperties(monocypher)
if(NOT monocypher_POPULATED)
    FetchContent_Populate(monocypher)
endif()
FetchContent_GetProperties(ed25519_donna)
if(NOT ed25519_donna_POPULATED)
    FetchContent_Populate(ed25519_donna)
endif()

set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${GENERATED_DIR}")
set(BOOT_PUBLIC_KEY_HEADER "${GENERATED_DIR}/boot_public_key.h")
execute_process(
    COMMAND
        "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/secure_firmware.py"
        export-public-key
        --public-key "${STM32_BOOT_PUBLIC_KEY_PEM}"
        --output "${BOOT_PUBLIC_KEY_HEADER}"
    RESULT_VARIABLE PUBLIC_KEY_RESULT
    OUTPUT_QUIET
    ERROR_VARIABLE PUBLIC_KEY_ERROR
)
if(NOT PUBLIC_KEY_RESULT EQUAL 0)
    message(FATAL_ERROR "Could not generate the bootloader public key header: ${PUBLIC_KEY_ERROR}")
endif()
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${STM32_BOOT_PUBLIC_KEY_PEM}"
)

set(MCU_FLAGS
    -mcpu=cortex-m4
    -mthumb
    -mfpu=fpv4-sp-d16
    -mfloat-abi=hard
)

set(HAL_DIR "${stm32f4xx_hal_SOURCE_DIR}/Src")
set(FREERTOS_DIR "${freertos_kernel_SOURCE_DIR}")
set(CMSIS_CORE_INCLUDE "${cmsis_core_SOURCE_DIR}/CMSIS/Core/Include")
set(CMSIS_DEVICE_INCLUDE "${cmsis_device_f4_SOURCE_DIR}/Include")

set(HAL_SOURCES
    ${HAL_DIR}/stm32f4xx_hal.c
    ${HAL_DIR}/stm32f4xx_hal_adc.c
    ${HAL_DIR}/stm32f4xx_hal_adc_ex.c
    ${HAL_DIR}/stm32f4xx_hal_cortex.c
    ${HAL_DIR}/stm32f4xx_hal_dma.c
    ${HAL_DIR}/stm32f4xx_hal_dma_ex.c
    ${HAL_DIR}/stm32f4xx_hal_flash.c
    ${HAL_DIR}/stm32f4xx_hal_flash_ex.c
    ${HAL_DIR}/stm32f4xx_hal_gpio.c
    ${HAL_DIR}/stm32f4xx_hal_i2c.c
    ${HAL_DIR}/stm32f4xx_hal_i2c_ex.c
    ${HAL_DIR}/stm32f4xx_hal_pwr.c
    ${HAL_DIR}/stm32f4xx_hal_pwr_ex.c
    ${HAL_DIR}/stm32f4xx_hal_rcc.c
    ${HAL_DIR}/stm32f4xx_hal_rcc_ex.c
    ${HAL_DIR}/stm32f4xx_hal_uart.c
)

set(FREERTOS_SOURCES
    ${FREERTOS_DIR}/tasks.c
    ${FREERTOS_DIR}/queue.c
    ${FREERTOS_DIR}/list.c
    ${FREERTOS_DIR}/portable/GCC/ARM_CM4F/port.c
    ${FREERTOS_DIR}/portable/MemMang/heap_4.c
)

add_executable(${PROJECT_NAME}.elf
    Core/Src/main.c
    Core/Src/lcd1602.c
    Core/Src/sensors_driver.c
    Core/Src/telemetry_protocol.c
    Core/Src/telemetry_task.c
    Core/Src/stm32f4xx_hal_msp.c
    ${HAL_SOURCES}
    ${FREERTOS_SOURCES}
    ${cmsis_device_f4_SOURCE_DIR}/Source/Templates/system_stm32f4xx.c
    ${cmsis_device_f4_SOURCE_DIR}/Source/Templates/gcc/startup_stm32f446xx.s
)

target_include_directories(${PROJECT_NAME}.elf PRIVATE
    Core/Inc
    ${FREERTOS_DIR}/include
    ${FREERTOS_DIR}/portable/GCC/ARM_CM4F
    ${CMSIS_CORE_INCLUDE}
    ${CMSIS_DEVICE_INCLUDE}
    ${stm32f4xx_hal_SOURCE_DIR}/Inc
    "${GENERATED_DIR}"
    "${monocypher_SOURCE_DIR}/src"
)

target_compile_definitions(${PROJECT_NAME}.elf PRIVATE
    STM32F446xx
    USE_HAL_DRIVER
)

target_compile_options(${PROJECT_NAME}.elf PRIVATE
    ${MCU_FLAGS}
    -Wall
    -Wextra
    -Wpedantic
    -fdata-sections
    -ffunction-sections
    -O2
)

target_link_options(${PROJECT_NAME}.elf PRIVATE
    ${MCU_FLAGS}
    -T${CMAKE_CURRENT_SOURCE_DIR}/STM32F446RETx_FLASH.ld
    -Wl,--gc-sections
    -Wl,-Map=${PROJECT_NAME}.map
    -Wl,--print-memory-usage
)

set_target_properties(${PROJECT_NAME}.elf PROPERTIES
    SUFFIX ""
    LINK_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/STM32F446RETx_FLASH.ld"
)

add_executable(stm32f446_secure_bootloader.elf
    bootloader/main.c
    bootloader/ed25519_randombytes.c
    Core/Src/firmware_package.c
    "${monocypher_SOURCE_DIR}/src/monocypher.c"
    "${ed25519_donna_SOURCE_DIR}/ed25519.c"
    ${cmsis_device_f4_SOURCE_DIR}/Source/Templates/system_stm32f4xx.c
    ${cmsis_device_f4_SOURCE_DIR}/Source/Templates/gcc/startup_stm32f446xx.s
)

target_include_directories(stm32f446_secure_bootloader.elf PRIVATE
    Core/Inc
    "${CMSIS_CORE_INCLUDE}"
    "${CMSIS_DEVICE_INCLUDE}"
    "${GENERATED_DIR}"
    "${monocypher_SOURCE_DIR}/src"
    "${ed25519_donna_SOURCE_DIR}"
)

target_compile_definitions(stm32f446_secure_bootloader.elf PRIVATE
    STM32F446xx
    ED25519_NO_INLINE_ASM
    ED25519_CUSTOMRANDOM
    ED25519_REFHASH
)

target_compile_options(stm32f446_secure_bootloader.elf PRIVATE
    ${MCU_FLAGS}
    -Wall
    -Wextra
    -Wpedantic
    -ffunction-sections
    -fdata-sections
    -Os
)

target_link_options(stm32f446_secure_bootloader.elf PRIVATE
    ${MCU_FLAGS}
    -T${CMAKE_CURRENT_SOURCE_DIR}/STM32F446RETx_BOOTLOADER.ld
    -Wl,--gc-sections
    -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/stm32f446_secure_bootloader.map
    -Wl,--print-memory-usage
)

set_target_properties(stm32f446_secure_bootloader.elf PROPERTIES
    SUFFIX ""
    LINK_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/STM32F446RETx_BOOTLOADER.ld"
)

add_custom_command(TARGET ${PROJECT_NAME}.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:${PROJECT_NAME}.elf> ${PROJECT_NAME}.bin
    COMMAND ${CMAKE_OBJCOPY} -O ihex $<TARGET_FILE:${PROJECT_NAME}.elf> ${PROJECT_NAME}.hex
    COMMAND ${CMAKE_SIZE} --format=berkeley $<TARGET_FILE:${PROJECT_NAME}.elf>
    COMMENT "Generating firmware binary and HEX images"
)

add_custom_command(TARGET stm32f446_secure_bootloader.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary
        $<TARGET_FILE:stm32f446_secure_bootloader.elf>
        stm32f446_secure_bootloader.bin
    COMMAND ${CMAKE_OBJCOPY} -O ihex
        $<TARGET_FILE:stm32f446_secure_bootloader.elf>
        stm32f446_secure_bootloader.hex
    COMMAND ${CMAKE_SIZE} --format=berkeley
        $<TARGET_FILE:stm32f446_secure_bootloader.elf>
    COMMENT "Generating secure bootloader binary and HEX images"
)
