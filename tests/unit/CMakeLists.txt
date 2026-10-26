cmake_minimum_required(VERSION 3.16)
project(project_unit_tests LANGUAGES C CXX)

enable_testing()

option(ENABLE_MCDC_COVERAGE "Instrument native unit tests for MC/DC coverage" OFF)
if(ENABLE_MCDC_COVERAGE)
    if(NOT CMAKE_C_COMPILER_ID STREQUAL "GNU"
       OR NOT CMAKE_CXX_COMPILER_ID STREQUAL "GNU"
       OR CMAKE_C_COMPILER_VERSION VERSION_LESS 14)
        message(FATAL_ERROR "MC/DC reporting requires GCC 14 or newer for C and C++")
    endif()
    add_compile_options(--coverage -fcondition-coverage)
    add_link_options(--coverage)
endif()

add_executable(gateway_protocol_test
    gatewayd/src/frame_protocol_test.cpp
    ../../gatewayd/src/frame_protocol.cpp
)
target_include_directories(gateway_protocol_test PRIVATE ../../gatewayd/inc)
add_test(NAME gateway_protocol_test COMMAND gateway_protocol_test)

add_executable(telemetry_protocol_test
    stm32-firmware/Core/Src/telemetry_protocol_test.c
    ../../stm32-firmware/Core/Src/telemetry_protocol.c
)
target_include_directories(telemetry_protocol_test PRIVATE ../../stm32-firmware/Core/Inc)
add_test(NAME telemetry_protocol_test COMMAND telemetry_protocol_test)

add_executable(firmware_package_test
    stm32-firmware/Core/Src/firmware_package_test.c
    ../../stm32-firmware/Core/Src/firmware_package.c
)
target_include_directories(firmware_package_test BEFORE PRIVATE
    stm32-firmware/test-support/fakes
    ../../stm32-firmware/Core/Inc
)
add_test(NAME firmware_package_test COMMAND firmware_package_test)

add_executable(sensors_driver_test
    stm32-firmware/Core/Src/sensors_driver_test.c
    ../../stm32-firmware/Core/Src/sensors_driver.c
)
target_include_directories(sensors_driver_test BEFORE PRIVATE
    stm32-firmware/test-support/fakes
)
add_test(NAME sensors_driver_test COMMAND sensors_driver_test)
