# Heterogeneous Industrial Edge Gateway

## Yocto Linux Gateway and STM32 FreeRTOS Telemetry Bridge

An embedded system connecting a real-time STM32 microcontroller running
FreeRTOS to a Raspberry Pi Linux gateway built with Yocto. The system acquires
multi-sensor telemetry, displays local status, and communicates framed data
between the target and host.

## Table of Contents

- [Initial Project Scope](#initial-project-scope)
- [Project Overview](#project-overview)
- [System Architecture](#system-architecture)
  - [Implemented Data Flow](#implemented-data-flow)
  - [STM32 Task Structure](#stm32-task-structure)
- [Hardware](#hardware)
  - [Bill of Materials](#bill-of-materials)
  - [Hardware Connections and Pinouts](#hardware-connections-and-pinouts)
  - [STM32F446RE Board Pinout Reference](#stm32f446re-board-pinout-reference)
- [Communication Protocol](#communication-protocol)
  - [Telemetry Payload](#telemetry-payload)
- [Software Components](#software-components)
- [Building the STM32 Firmware](#building-the-stm32-firmware)
- [Testing Strategy](#testing-strategy)
  - [Test Levels](#test-levels)
  - [Recommended Repository Layout](#recommended-repository-layout)
  - [Test Execution and CI](#test-execution-and-ci)
  - [Testing Rollout Plan](#testing-rollout-plan)
- [EU Cyber Resilience Act (CRA) Readiness](#eu-cyber-resilience-act-cra-readiness)
  - [Phased Security Checklist](#phased-security-checklist)
    - [Phase 0: Product Scope and Threat Model](#phase-0-product-scope-and-threat-model)
    - [Phase 1: Release and Pi Flashing Controls](#phase-1-release-and-pi-flashing-controls)
    - [Phase 2: STM32 Boot-Time Firmware Enforcement](#phase-2-stm32-boot-time-firmware-enforcement)
    - [Phase 3: Production Hardware and Trust Protection](#phase-3-production-hardware-and-trust-protection)
    - [Phase 4: Communications and Data Protection](#phase-4-communications-and-data-protection)
    - [Phase 5: Vulnerability Handling and Security Support](#phase-5-vulnerability-handling-and-security-support)
    - [Phase 6: Security Verification and Release Evidence](#phase-6-security-verification-and-release-evidence)
  - [Signed STM32 Firmware Flashing](#signed-stm32-firmware-flashing)
    - [Why Boot-Time Verification Is Necessary](#why-boot-time-verification-is-necessary)
    - [Flash Layout and Recovery](#flash-layout-and-recovery)
    - [Bench Test: STM32 Boot-Time Signature Enforcement](#bench-test-stm32-boot-time-signature-enforcement)
- [Implementation Notes](#implementation-notes)

## Initial Project Scope

The project was initially conceived as a full-stack heterogeneous system:

- **Target platform:** Raspberry Pi 3 Model B running a custom Yocto Linux image,
  paired with an STM32F446RE running FreeRTOS.
- **Host-to-target link:** USB CDC-ACM or UART for telemetry and commands.
- **Network and root filesystem:** Ethernet, including an NFS-root development
  environment for the Raspberry Pi.
- **Software stack:** Yocto/BitBake, a C++ Linux user-space daemon, FreeRTOS,
  and Linux device interfaces.

The project goals are to:

1. Build the Yocto image and required software on the development host, then
   flash/deploy that image to the Raspberry Pi using the existing setup. The Pi
   is the runtime target, not the build machine.
2. Design a reliable binary protocol between Linux and the STM32, with framing,
   COBS byte stuffing, and CRC16 verification.
3. Observe system and sensor telemetry while running the Raspberry Pi in an
   Ethernet/NFS-root setup.

The current protocol implementation and its frame layout are documented in
[Communication Protocol](#communication-protocol). Frames use COBS encoding,
a `0x00` delimiter, and CRC-16/MODBUS.

## Project Overview

Industrial edge devices divide deterministic, real-time work—such as sensor
sampling, safety monitoring, and interrupt handling—from higher-level host
work, such as networking, data persistence, and user interfaces.

This project brings those roles together:

- **STM32F446RE:** Runs the FreeRTOS firmware, samples configured sensors,
  updates the local LCD, and sends telemetry over USART2.
- **Raspberry Pi 3 Model B:** Runs the Yocto Linux image and `gatewayd`, which
  reads the STM32 serial stream, validates telemetry frames, and writes decoded
  readings to the system journal.
- **`meta-telemetry-bridge`:** A Yocto build layer on the development host. Its
  BitBake recipe builds and packages `gatewayd` and its systemd unit into the
  target image; the layer itself is not a runtime process on the Pi.
- **NFS:** Used by the development setup to provide or deploy the Pi root
  filesystem. It does not carry live STM32 telemetry.

## System Architecture

```text
                   +-----------------------------------+
                   |    Host System (Ubuntu / macOS)   |
                   |       NFS Server / Build Host     |
                   +-----------------+-----------------+
                                     | Ethernet (NFS rootfs)
                                     v
                   +-----------------------------------+
                   |    Raspberry Pi 3 Model B (Yocto) |
                   |        Linux Edge Gateway         |
                   +-----------------+-----------------+
                                     |
                                     | USB CDC-ACM (/dev/ttyACM0)
                                     v
                   +-----------------------------------+
                   |    STM32F446RE (NUCLEO Board)     |
                   |       FreeRTOS Target Firmware    |
                   +--+---------+---------+---------+--+
                      |         |         |         |
                 ADC1 + DMA    I2C1      GPIO      EXTI
                      v         v         v         v
                 ADXL335     DS3231     DHT11    Button
                            LCD1602
```

### Implemented Data Flow

In the current implementation, telemetry flows one way from the STM32 to the
Pi:

```text
Development host
  └─ BitBake + meta-telemetry-bridge
       └─ builds gatewayd and includes it in the Yocto image
             └─ image/rootfs deployed to or booted by the Raspberry Pi

STM32 sensors and button
  └─ FreeRTOS telemetry task
       └─ USART2, 115200 baud, 8N1
            └─ NUCLEO ST-LINK USB virtual COM port
                 └─ Raspberry Pi /dev/ttyACM0
                      └─ gatewayd COBS decode + CRC check
                           └─ decoded readings in systemd journal
```

The Pi's USB serial device is the **live telemetry link**. The `gatewayd`
systemd service reads it at 115200 baud, separates frames at `0x00`, COBS
decodes each frame, checks its payload length and CRC-16/MODBUS, then prints
valid telemetry to standard output, which systemd records in the journal. The
daemon does not currently publish readings over MQTT, HTTP, or another network
API.

NFS is a separate **boot/deployment path** between the development host and
the Pi. It supplies or receives the Pi root filesystem; it is not between
`gatewayd` and the STM32 and does not transport telemetry.

The STM32 also emits the plain-text `STM32 UART READY` startup marker before
binary telemetry begins. This marker is diagnostic text, not a protocol frame;
the current gateway parser expects COBS frames and can report an invalid COBS
frame for those startup bytes before it reaches the first `0x00` delimiter.

### STM32 Task Structure

The current firmware creates one application FreeRTOS task, which performs
acquisition, display updates, and transmission in sequence once per second:

| Task | Priority | Period / Trigger | Responsibility |
| :--- | :--- | :--- | :--- |
| `TelemetryTask` | `tskIDLE_PRIORITY + 2` | 1 s | Starts ADC circular DMA, reads the accelerometer ADC slots, DS3231 timestamp and DHT11, samples the onboard button, updates the LCD, and sends a telemetry frame over USART2. |

The current telemetry path is transmit-only from STM32 to Pi. The gateway
does not send commands back, and the firmware does not currently implement
the separate command parser, alarm dispatcher, safety-monitor task, or
multiple-task queue architecture described in earlier plans. The fourth ADC
payload slot remains in the protocol even though no photoresistor is connected;
its raw value should not be interpreted as a light measurement.

## Hardware

The system is intended to run from USB bus power supplied by the host.

### Bill of Materials

| Component | Function | Interface | Voltage |
| :--- | :--- | :--- | :--- |
| Raspberry Pi 3 Model B (Rev 1.2) | Embedded Linux host gateway | Ethernet / NFS boot | USB 5 V |
| NUCLEO-F446RE (STM32F446RE) | Real-time microcontroller node | USB CDC-ACM / UART | USB 5 V (ST-LINK) |
| ADXL335 module | Three-axis analog accelerometer | Three ADC channels | 3.3 V |
| DS3231 RTC module | Real-time clock and timestamping | I2C1 | 3.3 V |
| DHT11 module | Temperature and humidity | Single-wire GPIO | 3.3 V |
| HC-SR501 PIR module | Motion detection | Digital GPIO output | 5 V |
| MAX7219 LED matrix | Local status and telemetry display | SPI1 | 5 V |
| LCD1602 display | Local telemetry and status UI | Parallel GPIO, 4-bit mode | 5 V |
| Push-button switch | Display mode and command input | GPIO / EXTI | 3.3 V |
| Breadboard and DuPont wires | Prototyping interconnect | N/A | N/A |

### Hardware Connections and Pinouts

The STM32F446RE uses 3.3 V GPIO logic. Use an external supply for 5 V
peripherals and connect its ground to a NUCLEO ground pin. Check peripheral
signal levels before connecting them to STM32 GPIO.

#### ADXL335 Accelerometer

| Sensor pin | Connect to | Notes |
| --- | --- | --- |
| VCC | 3.3 V rail | Use the sensor module's supported supply voltage. |
| GND | Common ground | Connect to NUCLEO ground. |
| X-OUT | PA0 (ADC1_IN0) | ADC1 circular DMA channel 1. |
| Y-OUT | PA1 (ADC1_IN1) | ADC1 circular DMA channel 2. |
| Z-OUT | PA4 (ADC1_IN4) | ADC1 circular DMA channel 3. |

#### DS3231 RTC Module

| Module pin | Connect to | Notes |
| --- | --- | --- |
| VCC | 3.3 V rail | Confirm the module supports 3.3 V operation. |
| GND | Common ground | Connect to NUCLEO ground. |
| SCL | PB8 (I2C1_SCL / CN5 SCL, D15) | I2C1 bus. |
| SDA | PB9 (I2C1_SDA / CN5 SDA, D14) | I2C1 bus. |

#### DHT11 Temperature and Humidity Sensor

| Sensor pin | Connect to | Notes |
| --- | --- | --- |
| VCC | 3.3 V rail | Use 3.3 V logic. |
| GND | Common ground | Connect to NUCLEO ground. |
| DATA | PA6 (CN10 pin 13) | Single-wire GPIO; use the module's pull-up or a suitable pull-up to 3.3 V. |

#### HC-SR501 PIR Motion Sensor

| Sensor pin | Connect to | Board header position / notes |
| --- | --- | --- |
| VCC | External 5 V rail | Allow the module to stabilize after power-up. |
| GND | Common ground | Connect to the NUCLEO and external-supply ground. |
| OUT | PA8 | CN9 D7 / pin 8 or CN10 pin 23. Verify OUT is 3.3 V-safe; use level shifting if required. |

#### MAX7219 LED Matrix

| Matrix pin | Connect to | Notes |
| --- | --- | --- |
| VCC | External 5 V supply | Do not power the matrix from the NUCLEO 3.3 V rail. |
| GND | Common ground | Connect to NUCLEO and external-supply ground. |
| DIN | PA7 (SPI1_MOSI / CN5 D11) | SPI data output. |
| CS | PB6 (CN5 D10) | GPIO output used as chip select. |
| CLK | PA5 (SPI1_SCK / CN5 D13) | SPI clock. |

#### LCD1602 Display (Native Parallel, 4-Bit Mode)

This mapping uses the LCD's D4-D7 data pins; D0-D3 are not connected. The
chosen STM32 pins are available in the current project pinout and do not
overlap the listed sensor or MAX7219 connections. Configure them as GPIO
outputs and initialize the LCD in 4-bit mode in firmware.

| LCD pin | Connect to | Notes |
| --- | --- | --- |
| VSS | Common ground | Standard HD44780-compatible LCD ground pin. |
| VDD (sometimes labeled VCC) | +5 V rail | A standard 16-pin LCD has VDD as its supply pin. If your board exposes separate VCC and VDD pins, check its datasheet before wiring both. |
| V0 / VO | Wiper of a 10 kOhm contrast potentiometer | Connect the potentiometer's two outer terminals to +5 V and GND. Adjust for readable contrast. |
| RS | PC0 (CN7 pin 38) | Register select GPIO output. |
| RW | GND | Write-only operation; tie low. |
| E | PC1 (CN7 pin 36) | Enable GPIO output. |
| D0-D3 | Not connected | Unused in 4-bit mode. |
| D4 | PC2 (CN7 pin 35) | LCD data bit 4. |
| D5 | PC3 (CN7 pin 37) | LCD data bit 5. |
| D6 | PC4 (CN10 pin 34) | LCD data bit 6. |
| D7 | PC5 (CN10 pin 6) | LCD data bit 7. |
| A (LED+) | +5 V through the backlight current-limiting resistor | Some LCD modules include this resistor; check the module documentation. |
| K (LED-) | GND | Backlight cathode. |

Connect LCD ground, NUCLEO ground, and external-supply ground together. STM32
GPIO outputs are 3.3 V; check that the LCD accepts 3.3 V logic-high inputs when
powered from 5 V, and use a level shifter if its datasheet requires one. Do not
connect the LCD's 5 V supply or contrast voltage to an STM32 GPIO.

#### User Button

| Button connection | Connect to | Notes |
| --- | --- | --- |
| Onboard NUCLEO user button | PC13 | This is the button input configured by the current firmware; active-low. |
| External button, optional | GPIO input to GND | Only use a pin configured by the firmware and its matching pull-up. |

#### Raspberry Pi Gateway Serial Connection

| Connection | Connect to | Notes |
| --- | --- | --- |
| NUCLEO USB connector | Raspberry Pi USB port | ST-LINK USB virtual COM port; Linux typically exposes `/dev/ttyACM0`. |

**Pin-use note:** The firmware configures DHT11 on PA6, the PIR input is PA8,
and the onboard button is PC13. LCD pins are configured in firmware; the LCD
is initialized and updated when connected.

The DHT11 driver bounds its signal-edge waits. If the sensor read fails,
telemetry still continues and reports temperature `-128` and humidity `255`
as error sentinels; these values are not sensor measurements.

### STM32F446RE Board Pinout Reference

The numbers below identify physical header positions on the NUCLEO-F446RE.
CN7 and CN10 Morpho headers are shown side by side.

#### CN5 Digital Header

| Pin | Signal | STM32 pin / peripheral |
| ---: | --- | --- |
| 1 | D8 | PA9 |
| 2 | D9 | PC7 (TIM3_CH2 / TIM8_CH2) |
| 3 | CS / D10 | PB6 (SPI1 chip select) |
| 4 | MOSI / D11 | PA7 (SPI1_MOSI / PWM) |
| 5 | MISO / D12 | PA6 (SPI1_MISO) |
| 6 | SCK / D13 | PA5 (SPI1_SCK / onboard LD2) |
| 7 | GND | Ground |
| 8 | AVDD | Analog VDD reference |
| 9 | SDA / D14 | PB9 (I2C1_SDA) |
| 10 | SCL / D15 | PB8 (I2C1_SCL) |

#### CN6 Power Header

| Pin | Signal | Description |
| ---: | --- | --- |
| 1 | NC | Not connected |
| 2 | IOREF | 3.3 V reference |
| 3 | RESET | NRST MCU reset |
| 4 | +3.3 V | 3.3 V power rail |
| 5 | +5 V | 5 V power rail |
| 6 | GND | Ground |
| 7 | GND | Ground |
| 8 | VIN | External input voltage (7–12 V) |

#### CN7 and CN10 Morpho Headers

The rows pair adjacent pin numbers on each connector.

```text
CN7 (Left Morpho Header)                               CN10 (Right Morpho Header)
+--------------------------------------+    +--------------------------------------+
|  1: PC10               2: PC11       |    |  1: PC9                2: PC8        |
|  3: PC12               4: PD2        |    |  3: PB8                4: PC6        |
|  5: VDD                6: E5V        |    |  5: PB9                6: PC5 [LCD D7]|
|  7: BOOT0              8: GND        |    |  7: AVDD               8: U5V        |
|  9: NC                10: NC         |    |  9: GND               10: NC         |
| 11: NC                12: IOREF      |    | 11: PA5               12: PA12       |
| 13: PA13*             14: NRST       |    | 13: PA6 [DHT11 DATA]   14: PA11       |
| 15: PA14*             16: +3V3       |    | 15: PA7 [MAX DIN]      16: PB12       |
| 17: PA15              18: +5V        |    | 17: PB6 [MAX CS]       18: PB11       |
| 19: GND               20: GND        |    | 19: PC7               20: GND        |
| 21: PB7               22: GND        |    | 21: PA9               22: PB2        |
| 23: PC13 [USER]       24: VIN        |    | 23: PA8 [PIR OUT]      24: PB1        |
| 25: PC14              26: NC         |    | 25: PB10              26: PB15       |
| 27: PC15              28: PA0        |    | 27: PB4               28: PB14       |
| 29: PH0               30: PA1        |    | 29: PB5               30: PB13       |
| 31: PH1               32: PA4        |    | 31: PB3               32: AGND       |
| 33: VBAT              34: PB0         |    | 33: PA10              34: PC4 [LCD D6]|
| 35: PC2 [LCD D4]      36: PC1 [LCD E] |   | 35: PA2               36: NC         |
| 37: PC3 [LCD D5]      38: PC0 [LCD RS]|   | 37: PA3               38: NC         |
+--------------------------------------+    +--------------------------------------+
```

`*` PA13 and PA14 are SWD debug pins. Header positions shown for the PIR are
CN10 pin 23 and CN9 pin 8 (PA8).

#### CN8 Analog Header

| Pin | Signal | STM32 pin / peripheral |
| ---: | --- | --- |
| 1 | A0 | PA0 (ADC1_IN0) |
| 2 | A1 | PA1 (ADC1_IN1) |
| 3 | A2 | PA4 (ADC1_IN4) |
| 4 | A3 | PB0 (ADC1_IN8) |
| 5 | A4 | PC1 (ADC1_IN11) |
| 6 | A5 | PC0 (ADC1_IN10) |

#### CN9 Digital Header

| Pin | Signal | STM32 pin / peripheral |
| ---: | --- | --- |
| 1 | D0 (RX) | PA3 (USART2_RX / ST-LINK VCP) |
| 2 | D1 (TX) | PA2 (USART2_TX / ST-LINK VCP) |
| 3 | D2 | PA10 |
| 4 | D3 | PB3 (TIM2_CH2) |
| 5 | D4 | PB5 |
| 6 | D5 | PB4 (TIM3_CH1) |
| 7 | D6 | PB10 (TIM2_CH3) |
| 8 | D7 | PA8 |

## Communication Protocol

Telemetry is sent over the serial interface (shown as `/dev/ttyACM0` on the
gateway). Each frame is COBS-encoded and terminated by a `0x00` delimiter. After
COBS decoding, the frame has this layout:

| Byte offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| `0x00` | Message type | `uint8_t` | `0x01` telemetry, `0x02` alarm, or `0x03` command |
| `0x01` | Payload length | `uint8_t` | Payload length, N bytes |
| `0x02` to `N+1` | Payload | `uint8_t[]` | Sensor structure or configuration command |
| `N+2` to `N+3` | CRC16 | `uint16_t` | CRC-16/MODBUS over message type, length, and payload; low byte first |

The CRC uses initial value `0xFFFF` and reflected polynomial `0xA001`. Numeric
fields in the payload are transmitted little-endian. COBS removes zero bytes
from the encoded frame body, so `0x00` safely marks the end of each frame.

### Telemetry Payload

For message type `0x01`, the telemetry payload is 15 bytes:

| Payload offset | Field | Type | Unit / description |
| :--- | :--- | :--- | :--- |
| `0x00` to `0x03` | `timestamp_sec` | `uint32_t` | DS3231 RTC timestamp in seconds |
| `0x04` to `0x05` | `accel_x_mg` | `int16_t` | X-axis acceleration in milli-g |
| `0x06` to `0x07` | `accel_y_mg` | `int16_t` | Y-axis acceleration in milli-g |
| `0x08` to `0x09` | `accel_z_mg` | `int16_t` | Z-axis acceleration in milli-g |
| `0x0A` to `0x0B` | `light_lux_raw` | `uint16_t` | Raw ADC input value (0–4095) |
| `0x0C` | `temp_celsius` | `int8_t` | DHT11 temperature in degrees Celsius |
| `0x0D` | `humidity_pct` | `uint8_t` | DHT11 relative humidity in percent |
| `0x0E` | `button_state` | `uint8_t` | EXTI button state (0 or 1) |

The corresponding packed C structure is:

```c
typedef struct __attribute__((packed)) {
    uint32_t timestamp_sec;
    int16_t  accel_x_mg;
    int16_t  accel_y_mg;
    int16_t  accel_z_mg;
    uint16_t light_lux_raw;
    int8_t   temp_celsius;
    uint8_t  humidity_pct;
    uint8_t  button_state;
} TelemetryPayload_t;
```

The decoded frame is 19 bytes: 1-byte message type, 1-byte payload length,
15-byte payload, and 2-byte CRC16. COBS encoding and the terminating delimiter
add framing overhead.

## Software Components

### STM32 Target

- **Runtime:** STM32F446RE running FreeRTOS firmware flashed to MCU flash.
- **Current telemetry task:** Acquires ADC data using DMA, reads the DS3231
  and DHT11, samples the onboard button, updates the LCD1602, and transmits
  telemetry once per second.
- **Serial output:** USART2 is configured for 115200 baud, 8 data bits, no
  parity, one stop bit (8N1), with no hardware flow control. The NUCLEO
  ST-LINK USB virtual COM port presents this stream to Linux as
  `/dev/ttyACM0`.

### Yocto Linux Gateway

- **Build-time layer (`meta-telemetry-bridge`):** Contains the `gatewayd`
  BitBake recipe and systemd unit. BitBake cross-compiles the daemon for the
  configured Raspberry Pi machine and installs it as `/usr/bin/gatewayd`.
  The layer is used during image builds; it is not a running component on the
  Pi.
- **Runtime (`gatewayd`):** A C++17 Linux daemon started by systemd. It reads
  `/dev/ttyACM0`, validates COBS framing, payload length, and CRC-16/MODBUS,
  then prints decoded telemetry to the system journal. It currently does not
  provide a network API or persist readings to a database.

## Building the STM32 Firmware

The firmware build requires CMake, `arm-none-eabi-gcc`, OpenSSL, the release
public key, and network access for the first configure. CMake downloads pinned
versions of STM32 HAL, CMSIS, FreeRTOS, Monocypher (BLAKE2b), and Ed25519-donna
(standard Ed25519 verification) into the build directory; third-party source
is not copied into the project tree. Create or retrieve the signing key pair
as described in [Signed STM32 Firmware Flashing](#signed-stm32-firmware-flashing)
before configuring the build.

From the repository root:

```sh
cmake -S stm32-firmware -B stm32-firmware/build \
  -DCMAKE_TOOLCHAIN_FILE=stm32-firmware/arm-gcc-toolchain.cmake \
  -DSTM32_BOOT_PUBLIC_KEY_PEM="$HOME/.config/telemetry-bridge/stm32-signing-public.pem"
cmake --build stm32-firmware/build
```

The application ELF/BIN/HEX and `stm32f446_secure_bootloader.elf`,
`stm32f446_secure_bootloader.bin`, and `.hex` are written to
`stm32-firmware/build`. The public key is embedded in the bootloader at
configure time; the private key is used only on the trusted release host.

### Flashing the STM32 from the Raspberry Pi

The NUCLEO-F446RE ST-LINK USB connector is attached to the Raspberry Pi. The
release host builds and signs firmware; the Pi receives only a signed package,
the matching public key, and the tools needed to verify and program it. **Never
copy the private signing key or its passphrase to the Pi, NFS root, or source
repository.**

#### Why Boot-Time Verification Is Necessary

The earlier Pi-side wrapper checked firmware before running OpenOCD, but it
could be bypassed by running OpenOCD directly or replacing the Pi's software.
That check therefore protected the normal update procedure, not the firmware
execution boundary. A device-side bootloader is necessary because it runs
before the application and validates the image from flash itself. It rejects
an unsigned, altered, malformed, or wrong-board image even if that image was
written through a path that bypassed the Pi wrapper.

#### Flash Layout and Recovery

The STM32F446RE flash is divided into these regions:

| Address range | Size | Contents |
| --- | ---: | --- |
| `0x08000000`–`0x0801FFFF` | 128 KiB | First-stage secure bootloader |
| `0x08020000`–`0x0807FFFF` | 384 KiB | One application package slot |
| `0x08020000`–`0x080201FF` | 512 bytes | Package header: signed metadata and Ed25519 signature |
| `0x08020200`–`0x0807FFFF` | Up to 392,704 bytes | Application image, including its vector table |

The package binds the `STM32F446RE` board ID, an unsigned numeric version
code, image length, and BLAKE2b-256 image digest into a signed 68-byte metadata
record. The bootloader verifies the standard Ed25519 signature, digest, image
bounds, and initial vector values before setting VTOR/MSP and entering the
application. The release host uses OpenSSL for Ed25519 and the same BLAKE2b
digest algorithm. The verifier uses the pinned, portable C Ed25519-donna
implementation and Monocypher's BLAKE2b implementation.

This is a **single application slot**, chosen to preserve the existing
ST-LINK/OpenOCD workflow and avoid reserving flash for A/B images. A failed or
interrupted application write can leave the application unbootable, but the
bootloader remains in its separate flash sectors. Recover by programming a
known-good signed package to the application slot using ST-LINK/OpenOCD. There
is no automatic rollback or recovery image.

The bootloader must be provisioned first in a controlled environment. The
current build does not enable STM32 write protection or readout/debug
protection: someone with physical debug-port access can still replace the
bootloader itself. Do not claim resistance to an attacker with direct debug
access until an option-byte policy and its manufacturing/service recovery
process are designed and tested.

#### Create a Release Package

Run host commands from the repository root:

```sh
cd ~/Desktop/YoctoProject/yocto-stm32-telemetry-bridge
```

Generate an encrypted Ed25519 key pair once in a controlled release
environment. If the pair already exists, retain it: a replacement public key
will not match a provisioned bootloader. Keep the private key access-restricted
with a protected offline backup:

```sh
install -d -m 700 "$HOME/.config/telemetry-bridge"
openssl genpkey -algorithm ED25519 -aes-256-cbc \
  -out "$HOME/.config/telemetry-bridge/stm32-signing-private.pem"
chmod 600 "$HOME/.config/telemetry-bridge/stm32-signing-private.pem"
openssl pkey \
  -in "$HOME/.config/telemetry-bridge/stm32-signing-private.pem" \
  -pubout \
  -out "$HOME/.config/telemetry-bridge/stm32-signing-public.pem"
```

OpenSSL prompts for the private-key passphrase; do not put it in a command
argument or script. Configure with the matching public key and build both
images:

```sh
cmake -S stm32-firmware -B stm32-firmware/build \
  -DCMAKE_TOOLCHAIN_FILE=stm32-firmware/arm-gcc-toolchain.cmake \
  -DSTM32_BOOT_PUBLIC_KEY_PEM="$HOME/.config/telemetry-bridge/stm32-signing-public.pem"
cmake --build stm32-firmware/build
```

Package the application after each build. `--version-code` is a signed
32-bit integer (not a semantic version string); assign larger values to later
releases. Version codes are authenticated but **not yet enforced as an
anti-rollback policy**:

```sh
python3 stm32-firmware/tools/secure_firmware.py package \
  --image stm32-firmware/build/stm32f446_freertos_firmware.bin \
  --board STM32F446RE \
  --version-code 10000 \
  --private-key "$HOME/.config/telemetry-bridge/stm32-signing-private.pem" \
  --package stm32-firmware/build/stm32f446_freertos_firmware.sfu

python3 stm32-firmware/tools/secure_firmware.py verify \
  --package stm32-firmware/build/stm32f446_freertos_firmware.sfu \
  --public-key "$HOME/.config/telemetry-bridge/stm32-signing-public.pem" \
  --board STM32F446RE
```

For the Pi-side verifier, include `openssl`, `python3-core`, `python3-crypt`,
`python3-io`, and `python3-json` in the Yocto image. The Yocto configuration
for this project was updated with these packages; rebuild/deploy the image if
they are not present.

#### Provision the Bootloader and Flash a Release

Copy the bootloader image, `.sfu` release package, public key, verifier, and
flash wrapper into the exported NFS root. Run this on the development host
after building and packaging:

```sh
sudo install -d -m 755 /srv/nfs/rpi-rootfs/home/stm32-update
sudo install -m 644 \
  stm32-firmware/build/stm32f446_secure_bootloader.bin \
  stm32-firmware/build/stm32f446_freertos_firmware.sfu \
  stm32-firmware/tools/secure_firmware.py \
  "$HOME/.config/telemetry-bridge/stm32-signing-public.pem" \
  /srv/nfs/rpi-rootfs/home/stm32-update/
sudo install -m 755 stm32-firmware/tools/flash_signed_stm32.sh \
  /srv/nfs/rpi-rootfs/home/stm32-update/
```

After the Pi boots from that NFS root, check the files:

```sh
ls -l /home/stm32-update/
```

For first-time provisioning (or intentional bootloader replacement), stop the
gateway service and program the bootloader at `0x08000000`. This direct command
is for controlled provisioning only; OpenOCD does not authenticate the
bootloader binary:

```sh
systemctl stop gatewayd
openocd \
  -f interface/stlink.cfg \
  -f target/stm32f4x.cfg \
  -c "program /home/stm32-update/stm32f446_secure_bootloader.bin 0x08000000 verify reset exit"
```

For normal application releases, first verify the `.sfu` package on the Pi as
`root`. This checks its board ID, digest, and signature:

```sh
python3 /home/stm32-update/secure_firmware.py verify \
  --package /home/stm32-update/stm32f446_freertos_firmware.sfu \
  --public-key /home/stm32-update/stm32-signing-public.pem \
  --board STM32F446RE
```

Stop `gatewayd` if it is running, then use the wrapper for the application
update. It repeats verification immediately before OpenOCD writes the package
at `0x08020000`; do not substitute a direct OpenOCD command for routine
releases:

```sh
systemctl stop gatewayd
/home/stm32-update/flash_signed_stm32.sh \
  /home/stm32-update/stm32f446_freertos_firmware.sfu \
  /home/stm32-update/stm32-signing-public.pem
systemctl start gatewayd
```

Successful output includes `** Programming Finished **`, `** Verified OK **`,
and `** Resetting Target **`. OpenOCD's read-back `verify` confirms that flash
matches the input package; signature authenticity is enforced by the
bootloader at startup.

#### Verify Host-Side Package Rejection

On the Pi, test that the host wrapper blocks a modified package before
OpenOCD starts. This only changes a temporary copy:

```sh
cp /home/stm32-update/stm32f446_freertos_firmware.sfu \
  /tmp/stm32f446_freertos_firmware-tampered.sfu
python3 -c 'from pathlib import Path; p=Path("/tmp/stm32f446_freertos_firmware-tampered.sfu"); b=bytearray(p.read_bytes()); b[612] ^= 1; p.write_bytes(b)'

/home/stm32-update/flash_signed_stm32.sh \
  /tmp/stm32f446_freertos_firmware-tampered.sfu \
  /home/stm32-update/stm32-signing-public.pem
```

Byte 612 is in the package payload (512-byte header plus payload offset 100).
The wrapper must exit with a digest error and show **no OpenOCD banner or
programming output**. Do not flash the tampered file during this host-side
test. Delete the temporary file afterward:

```sh
rm -f /tmp/stm32f446_freertos_firmware-tampered.sfu
```

#### Bench Test: STM32 Boot-Time Signature Enforcement

This hardware test was performed on the NUCLEO-F446RE on 2026-10-16:

1. Programmed `stm32f446_secure_bootloader.bin` at `0x08000000`.
2. Flashed the valid signed `.sfu` package at `0x08020000`; telemetry resumed.
3. Changed one byte in a temporary package and programmed it directly with
   OpenOCD at `0x08020000`, bypassing the Pi wrapper. OpenOCD reported
   `**Verified OK**`, which only confirms byte-for-byte flash programming.
4. After reset, `gatewayd` connected to the serial port but emitted no
   telemetry frames while the tampered image was installed.
5. Reflashed the original signed package through the verification wrapper;
   telemetry resumed.

This confirms the bootloader rejected the tampered application on the tested
board and that a valid signed image recovered it. The OpenOCD success message
for the tampered package is expected: OpenOCD does not verify the package
signature. The bootloader currently provides no rejection log, so lack of
telemetry after reset is the observable fail-closed behavior.

To repeat on a **bench board only**, first ensure the valid package is present
at `/home/stm32-update/stm32f446_freertos_firmware.sfu`. Stop `gatewayd`,
make a modified copy, and directly flash it to the application slot. This
intentionally bypasses host-side checks:

```sh
systemctl stop gatewayd
cp /home/stm32-update/stm32f446_freertos_firmware.sfu \
  /tmp/stm32f446_freertos_firmware-tampered.sfu
python3 -c 'from pathlib import Path; p=Path("/tmp/stm32f446_freertos_firmware-tampered.sfu"); b=bytearray(p.read_bytes()); b[612] ^= 1; p.write_bytes(b)'

openocd \
  -f interface/stlink.cfg \
  -f target/stm32f4x.cfg \
  -c "program /tmp/stm32f446_freertos_firmware-tampered.sfu 0x08020000 verify reset exit"

systemctl start gatewayd
journalctl -u gatewayd -f
```

Allow about 10 seconds for telemetry. `gatewayd` may report that it connected,
but there should be no `[TELEMETRY FRAME RECEIVED]` lines. Stop the journal
with Ctrl+C, then recover immediately by restoring the valid package:

```sh
systemctl stop gatewayd
/home/stm32-update/flash_signed_stm32.sh \
  /home/stm32-update/stm32f446_freertos_firmware.sfu \
  /home/stm32-update/stm32-signing-public.pem
systemctl start gatewayd
journalctl -u gatewayd -f
```

Confirm valid telemetry frames resume, then stop the journal with Ctrl+C and
remove the temporary test package:

```sh
rm -f /tmp/stm32f446_freertos_firmware-tampered.sfu
```

Do not conduct destructive rejection tests on field devices. This bench test
covers a modified payload; unsigned, wrong-board, malformed, and interrupted
updates should also be included in a controlled verification plan before
production.

### Checking STM32 UART Output on the Raspberry Pi

The current firmware configures USART2 for 115200 baud, 8 data bits, no parity,
and one stop bit (8N1). The NUCLEO ST-LINK virtual COM port should appear on
the Pi as `/dev/ttyACM0`.

#### Viewing Gateway Daemon Output

The `gatewayd` systemd service writes its standard output and errors to the
system journal. As `root` on the Pi, check the service and follow its logs:

```sh
systemctl status gatewayd --no-pager
journalctl -u gatewayd -f
```

At startup, expect a line similar to:

```text
gatewayd[258]: [gatewayd] Starting Industrial Gateway Daemon...
gatewayd[258]: [gatewayd] Connected to /dev/ttyACM0 successfully!
```

The process ID and exact messages may differ. Once valid telemetry frames
arrive, the journal prints decoded values, for example:

```text
gatewayd[258]: ================ [TELEMETRY FRAME RECEIVED] ================
gatewayd[258]:  Timestamp (RTC)  : 33399 s
gatewayd[258]:  Accel X / Y / Z  : 12 mg | -65 mg | 952 mg
gatewayd[258]:  Photocell Raw    : 1753 / 4095
gatewayd[258]:  Temperature      : 21 °C
gatewayd[258]:  Humidity         : 46 %
gatewayd[258]:  EXTI Button State: RELEASED
gatewayd[258]: ========================================================
```

Values change as telemetry arrives. If no photoresistor is connected, the
reported raw ADC value is not a meaningful light measurement.

#### Capturing Raw STM32 UART Bytes

To inspect the bytes sent by the STM32 directly, stop `gatewayd` first so it
does not compete with the capture command for `/dev/ttyACM0`. As `root` on the
Pi:

```sh
systemctl stop gatewayd
stty -F /dev/ttyACM0 115200 cs8 -parenb -cstopb raw -echo
dd if=/dev/ttyACM0 bs=1 count=1000 2>/dev/null | hexdump -C
```

`stty` configures `/dev/ttyACM0` for 115200 baud, 8 data bits (`cs8`), no
parity (`-parenb`), one stop bit (`-cstopb`), raw byte handling, and no echo.
`dd` reads 1000 bytes (`bs=1 count=1000`); `2>/dev/null` hides its transfer
summary, and `hexdump -C` displays hexadecimal bytes alongside printable
characters. Start the capture, then press the STM32 RESET button once.

The output begins with the ASCII startup marker `STM32 UART READY`, whose
hexadecimal bytes are `53 54 4d 33 32 20 55 41 52 54 20 52 45 41 44 59 0d 0a`.
It is followed by binary COBS-encoded telemetry frames terminated by `00`.
Frame bytes and decoded values vary, so the full output will not be identical
each time. For example, the beginning should look like:

```text
00000000  53 54 4d 33 32 20 55 41 52 54 20 52 45 41 44 59  |STM32 UART READY|
00000010  0d 0a ...                                        |..|
```

The `...` represents variable binary telemetry bytes; it is not literal
`hexdump` output. `dd` exits after reading 1000 bytes. If it has not received
enough data yet, it waits; press Ctrl+C to stop early. Keep `gatewayd` stopped
and this as the only process reading `/dev/ttyACM0` during the test. Restart
the daemon afterwards:

```sh
systemctl start gatewayd
```

Useful Raspberry Pi checks:

```sh
ls -l /dev/ttyACM0
dmesg | grep -E 'ttyACM|cdc_acm'
systemctl status gatewayd --no-pager
journalctl -u gatewayd -b --no-pager -n 50
```

The service and journal commands apply to images that include `gatewayd` and
systemd. The serial device appearing confirms USB enumeration only; valid COBS
frames must still be captured and decoded to confirm end-to-end telemetry.

## Testing Strategy

Use **pytest as the top-level runner for Python tests and host-side scenarios**,
while keeping C and C++ unit tests in native CTest targets. This provides one
convenient command for host checks without forcing embedded or gateway code into
a Python-only testing model. Pytest can also coordinate target and hardware
tests, but those should require explicit selection because they need deployed
devices or a dedicated bench.

The repository currently has no checked-in test suite or CTest targets. The
layout and commands below describe the recommended architecture; they become
available as their corresponding milestones are implemented.

### Test Levels

| Level | What it verifies here | Representative cases | Typical runner |
| --- | --- | --- | --- |
| **Unit** | A function or module in isolation | `secure_firmware.py` package parsing, signing and verification; firmware CRC/COBS; gateway frame validation and payload decoding; bootloader package checks | pytest for Python; CTest for C/C++ |
| **Integration** | Components working across an interface on the host | Firmware-compatible frame bytes accepted by the gateway; gateway consumes serial input from a pseudo-terminal (PTY); partial reads, multiple frames, malformed-frame recovery | pytest orchestrating host binaries and PTYs, plus native protocol tests |
| **System** | The deployed Yocto image and services | `gatewayd` starts under systemd, opens the configured serial device, logs valid telemetry, and recovers after disconnect/reconnect | pytest over SSH or a target test interface |
| **HIL** | Firmware, gateway and real hardware together | Board startup and telemetry cadence; sensor success/error paths; button response; reset recovery; secure boot accepts valid packages and rejects tampered or wrong-board packages | pytest coordinating a dedicated bench |

These levels answer different questions. Host integration cannot prove
electrical behavior or sensor accuracy, and a successful firmware cross-build
cannot prove that the image works on a Raspberry Pi.

### Recommended Repository Layout

```text
tests/
  conftest.py                 # Shared fixtures and opt-in target/bench setup
  pytest.ini                  # Markers and default selection
  fixtures/
    protocol_vectors.json     # Independently specified wire-format examples
  unit/
    python/test_secure_firmware.py
  integration/
    test_gateway_serial.py
  system/
    test_gateway_service.py
  hil/
    test_stm32_telemetry.py

gatewayd/
  tests/                      # Host C++ tests registered with CTest

stm32-firmware/
  tests/                      # Native C tests for portable firmware modules
```

Keep protocol vectors language-neutral and specify expected bytes, CRC values,
payload fields, and edge cases. Avoid relying only on an encoder/decoder
round-trip from the same implementation: matching defects can cancel each
other out. Use independent expected vectors in firmware, gateway, and
Python-facing tests.

To make this architecture practical, first separate portable logic from
hardware and process entry points:

- Extract gateway COBS decoding, CRC checking, frame validation, and telemetry
  decoding from `gatewayd/src/main.cpp` into a host-buildable module. Keep serial
  I/O and logging in the daemon layer.
- Add a serial-device configuration option to `gatewayd` (using the current
  device as the deployment default) so a PTY can be injected during host tests.
- Keep firmware protocol and package-verification code callable without HAL,
  flash, or bootloader startup dependencies where practical; compile native
  tests separately from ARM firmware targets.
- Use temporary directories and generated test signing keys for package tests.
  Never check a release private key into the repository or CI artifacts.

### Test Execution and CI

Register pytest markers for `unit`, `integration`, `system`, `hil`, and, if
needed, `destructive`. Default local and pull-request runs should include only
host-safe unit and integration coverage. Require explicit marker selection and
a bench/target configuration for system and HIL tests. Destructive flash,
erase, or recovery checks belong only on an identified bench device.

Use a project-local virtual environment for pytest so this repository's Python
tools stay separate from the system Python and other projects. Create it and
install the test dependency once:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

The test runner automatically uses `.venv/bin/python` when it exists; it falls
back to `python3` otherwise. Run the suite from the repository root:

```sh
./run_host_tests.sh
```

The system test is skipped unless `YOCTO_SSH_HOST` is set to an SSH target
where the test account can run `systemctl`, read the journal, and inspect
`/dev/ttyACM0`. For example: `YOCTO_SSH_HOST=pi@raspberrypi`. To build the
gateway separately, the integration test accepts `GATEWAYD_BIN=/path/to/gatewayd`.
HIL tests are added alongside an identified bench fixture; they are not part of
the host runner until that fixture is available.

CI should initially run pytest host tests, both native CTest suites, and the
firmware cross-build. Run Yocto image builds on suitable runners because they
are resource-intensive; run system and HIL suites on dedicated self-hosted
hardware or an explicitly triggered bench job. Preserve logs, test reports,
firmware/package hashes, and target identity as artifacts, excluding signing
secrets.

### Testing Rollout Plan

1. **Lock down contracts:** document frame and payload layout, byte order,
   CRC-16/MODBUS parameters, timestamp meaning, startup-marker handling, and
   expected telemetry cadence. Resolve the mismatch between the README's Unix
   timestamp description and the current RTC implementation before asserting
   timestamp semantics.
2. **Start with Python unit tests:** cover package creation, inspection, and
   verification, including malformed headers, board mismatches, image-size
   boundaries, changed payloads, invalid signatures, and missing OpenSSL.
3. **Add native portable-code tests:** test firmware CRC/COBS and package
   verification, plus gateway frame validation. Include known CRC vectors,
   zero-heavy inputs, truncation, length errors, CRC failures, capacity limits,
   and recovery at a delimiter.
4. **Add PTY integration coverage:** exercise the gateway with partial reads,
   concatenated frames, invalid input followed by a valid frame, and
   disconnect/reconnect. Specify expected handling for the firmware's current
   `STM32 UART READY` text marker, which is not a COBS frame.
5. **Add target system checks:** verify the Yocto image, systemd behavior,
   serial access, journal output, and bounded reconnect behavior on the Pi.
6. **Add bench HIL checks:** measure board startup and telemetry, exercise
   sensor error paths and reset recovery, and test secure-boot acceptance and
   rejection using controlled packages.

Two repository questions should be settled in the first milestone. The README
documents the RTC value as a Unix timestamp, but the current
`DS3231_Read_Timestamp` implementation appears to derive seconds from the
time-of-day fields only. Also, `linux-gateway/src/gateway_receiver.c` appears
to be a separate stub with a different CRC formulation from `gatewayd`; decide
whether it is supported or legacy before treating it as a second implementation
under test. Test vectors and coverage should follow the intended production
path.

## EU Cyber Resilience Act (CRA) Readiness

This roadmap tracks product-security work relevant to the EU Cyber Resilience
Act (CRA); it is not legal advice, a conformity assessment, or a claim that
the product currently complies. The CRA sets outcome-oriented cybersecurity
requirements. Controls such as a dedicated secure element, encryption on every
interface, or disabling every debug port are not automatically the only
acceptable solution in every product: select proportionate controls from the
documented product scope, threat model, and risk assessment. Confirm applicable
obligations and dates for the product before placing it on the EU market. See
the [official CRA text](https://eur-lex.europa.eu/eli/reg/2024/2847/oj).

### Phased Security Checklist

Keep this checklist stable and update item status as implementation and
verification are completed. A checked item records completed engineering work;
it does not by itself establish production readiness or CRA compliance.

#### Phase 0: Product Scope and Threat Model

**Why:** Security controls should follow the product's intended use, interfaces,
deployment environment, and likely attackers. This also establishes which CRA
obligations and conformity steps apply, instead of treating example controls as
universal legal requirements.

- [ ] Define the product boundary, intended use, deployment and service
  environments, users, external interfaces, expected service life, and whether
  the product will be placed on the EU market.
- [ ] Map assets, data flows, trust boundaries, and attack paths, including
  unauthorized firmware updates, Pi compromise, physical debug access, and
  recovery/service procedures.
- [ ] Determine applicable CRA requirements and product classification with
  appropriate compliance expertise; turn applicable requirements into
  verifiable security requirements and release criteria.

#### Phase 1: Release and Pi Flashing Controls

**Why:** A signed release prevents unnoticed alteration, while access controls
on the Pi reduce accidental or unauthorized use of OpenOCD and ST-LINK. A
wrapper alone is not an access-control boundary: a Pi administrator can bypass
it, replace the verifier or public key, or invoke programming tools directly.

- [ ] Sign a canonical manifest with Ed25519. It binds the STM32F446RE board
  ID, release version, binary size, and SHA-256 image digest.
- [ ] Verify the manifest signature, expected board ID, image size, and digest
  on the Pi before the flash wrapper invokes OpenOCD.
- [x] Keep normal ST-LINK/OpenOCD programming; retain OpenOCD read-back
  verification as a separate integrity check.
- [x] Keep the private signing key out of the repository and Pi; distribute
  only the public verification key.
- [x] Verify the signed firmware package in the Pi flash wrapper before it
  invokes OpenOCD.
- [ ] Restrict access to ST-LINK, OpenOCD, release packages, and update
  commands to authorized accounts or a narrowly scoped update service; do not
  grant the runtime gateway service unnecessary flashing privileges.
- [ ] Harden the Pi update path: protect the verifier and trusted public key
  from unauthorized replacement, authenticate and log update requests, and
  assess secure/verified boot and recovery options supported by the exact Pi
  hardware and boot configuration.
- [ ] Document the remaining Pi administrator and physical-access bypasses,
  and define what additional controls are required for the product's threat
  model.

The current release tool signs a fixed-header `.sfu` package using Ed25519 and
BLAKE2b-256 rather than a separate canonical SHA-256 manifest. The package
does bind the board ID, version, image length, and digest, and the Pi wrapper
verifies it before flashing. The manifest/hash-format items above remain
unchecked until the documented format and implementation are aligned.

#### Phase 2: STM32 Boot-Time Firmware Enforcement

**Why:** Host-side checks cannot stop a directly programmed unauthorized
application. A device-side bootloader makes the STM32 verify the application
before execution, independently of whether the Pi wrapper was used.

- [x] Define a flash layout that reserves space for a first-stage bootloader
  and places the application at a non-zero flash address.
- [x] Select and integrate a maintained signature-verification implementation
  that fits STM32F446RE flash/RAM limits; embed only the public key in the
  bootloader.
- [x] Verify application board ID, image length, digest, and signature before
  jumping to the application; fail closed on invalid images.
- [x] Update linker and OpenOCD programming addresses. Keep ST-LINK/OpenOCD for
  routine programming, but make the bootloader reject unauthorized images even
  when they are written directly.
- [ ] Decide how version rollback is prevented, how signing keys are rotated
  or revoked, and how failed updates are recovered. The signed version field
  is currently recorded but no anti-rollback state is enforced.

The bootloader region is reserved by the flash layout but is not hardware
write-protected. Bench testing has covered valid signed-image boot, rejection
of a directly programmed payload-tampered image, and ST-LINK recovery on a
NUCLEO-F446RE. See
[Bench Test: STM32 Boot-Time Signature Enforcement](#bench-test-stm32-boot-time-signature-enforcement).

#### Phase 3: Production Hardware and Trust Protection

**Why:** Application signature checks depend on the bootloader and its
verification key remaining trustworthy. Exposed debug/programming access or
replaceable trust anchors can undermine that boundary. Protection settings
also affect manufacturing, development, field service, and recovery, so they
must be designed and tested before production.

- [ ] Assess STM32 readout/debug protection and its impact on development,
  manufacturing, field service, and recovery before enabling any option bytes.
- [ ] Define and test a production policy for SWD/JTAG, UART boot paths, unused
  debug interfaces, and physical access; disable or restrict interfaces that
  are not needed in shipped units.
- [ ] Decide whether the product threat model requires hardware-backed secret
  storage (for example, a secure element); document the choice and its
  manufacturing and recovery implications. The STM32 bootloader currently
  contains a public verification key, not a private signing key.
- [ ] Inventory credentials and cryptographic assets; ensure there are no
  universal default passwords or shared device secrets, and define provisioning,
  storage, rotation, and revocation for any secrets that are required.

#### Phase 4: Communications and Data Protection

**Why:** Integrity checks such as the telemetry CRC detect transmission errors,
not malicious modification or eavesdropping. The right protection depends on
whether a link crosses an untrusted boundary and whether its data or commands
need confidentiality, integrity, or peer authentication.

- [ ] Inventory communication links and data handled by the product; document
  confidentiality, integrity, and authentication needs for each link.
- [ ] For links exposed to untrusted networks or carrying sensitive data or
  security-relevant commands, select and implement suitable authenticated
  protection, including secure key provisioning and rotation.
- [ ] Document the risk decision for local STM32-to-Pi UART telemetry. The
  current COBS/CRC protocol provides framing and error detection, not
  cryptographic confidentiality or authenticity.
- [ ] Minimize collected/stored data and protect any sensitive data at rest
  using controls supported by the hardware and product threat model.

#### Phase 5: Vulnerability Handling and Security Support

**Why:** Secure design cannot prevent every future vulnerability. A maintained
product needs a way to receive reports, assess affected components, issue
security fixes, and tell users how long support will continue.

- [ ] Define and publish a product security support period based on expected
  product use and applicable CRA requirements. The CRA generally sets a
  five-year minimum unless the product's expected use period is shorter; confirm
  the rule applicable to this product and provide security updates throughout
  the declared period.
- [ ] Establish a vulnerability intake and response process, including a
  security contact, triage, severity assessment, remediation targets, and
  coordinated disclosure.
- [ ] Maintain an inventory of firmware, Yocto, gateway, and third-party
  components with versions and a process to monitor advisories and assess
  vulnerabilities.
- [ ] Define how security updates are built, signed, delivered, documented,
  and made available to users without charge during the applicable support
  period.

#### Phase 6: Security Verification and Release Evidence

**Why:** Tests demonstrate that controls work in failure cases, while retained
design and release evidence supports maintenance, incident response, and any
applicable conformity assessment.

- [ ] Test accepted and rejected firmware cases: valid image, unsigned image,
  modified image, wrong-board image, interrupted programming, and older signed
  image.
- [ ] Test that unauthorized Pi users cannot invoke the update path, replace
  trusted verification material, or program the target through available
  interfaces; explicitly test and document administrator/physical-access
  boundaries.
- [ ] Verify production debug-interface settings, credential provisioning,
  update recovery, and communications protections on representative hardware.
- [ ] Keep the threat model, security decisions, test results, component
  inventory, update/recovery instructions, and release records together for
  engineering and conformity-readiness review.

### Outcome After All Phases

Completing and verifying these phases should provide a documented security
lifecycle: authorized releases are checked on the Pi and independently enforced
by the STM32 at boot; routine Pi flashing is restricted and auditable; production
interfaces and trust anchors have an assessed protection policy; sensitive
communications and data receive proportionate safeguards; and vulnerabilities
can be handled with security updates throughout a published support period.
This materially reduces risks from accidental or unauthorized updates and
common software attacks, but does not make the product invulnerable or prevent
every attack by a compromised administrator or person with physical access.
The result is engineering evidence toward CRA readiness, not automatic legal
compliance or product certification.

### Production Firmware Release Bundle

For normal customer updates, provide:

- `stm32f446_freertos_firmware.sfu` — application, signed board/version/image
  metadata, payload digest, and Ed25519 signature in one package.
- The matching `stm32-signing-public.pem` and its fingerprint, delivered or
  confirmed through a trusted channel.
- `secure_firmware.py`, `flash_signed_stm32.sh`, and instructions for package
  verification, supported hardware, ST-LINK/OpenOCD use, recovery, and release
  identification.

The bootloader binary is needed only for controlled initial provisioning or
an authorized bootloader replacement; it must be built with the matching
public key. Never distribute the private signing key, its passphrase, or a copy
of the signing environment.

The package binds authorization to the `STM32F446RE` board family, not an
individual MCU serial number or unique device ID. Per-device authorization
would require a separately designed and tested device-ID policy.

The Pi-side verifier requires `python3-core`, `python3-crypt`, `python3-io`,
`python3-json`, and `openssl` in the deployed Yocto image. These dependencies
were added to the project's Yocto image configuration; rebuild/deploy that
image if they are not present.

## Implementation Notes

- **Thread-safe I2C access:** The sensor driver uses `xI2cMutex` to prevent
  concurrent access to the shared I2C bus.
- **DHT11 timing protection:** `DHT11_Read_Data()` uses a FreeRTOS critical
  section to prevent scheduler preemption from disrupting single-wire timing.
- **Shared system tick:** The startup `SysTick_Handler` advances the STM32 HAL
  tick before the FreeRTOS scheduler starts, then forwards ticks to FreeRTOS
  after scheduler initialization. This avoids calling the kernel tick handler
  while its task lists are not initialized.



Quick Comparison
Approach                    Best Used For                               Version Control Target

Distro/Image        RecipeProduction features, package      meta-telemetry-bridge/recipes-core/
                     sets, systemd configs

Template Configs    Developer onboarding &                  meta-telemetry-bridge/conf/templates/
                    reproducible local builds

Kas Tool            Automated CI/CD pipelines &             Top-level kas.yml in project root
                    automated docker builds


Strategy 1: The Distro & Machine Layer Pattern (Recommended)
Embed system-wide defaults into your custom layer (meta-telemetry-bridge). Configurations inside layers are automatically version-controlled and override Yocto defaults cleanly.

Configuration variables (e.g., systemd init, package managers, custom distro features) belong in a custom distro configuration (meta-telemetry-bridge/conf/distro/telemetry-distro.conf).

Hardware settings (e.g., overlay trees, console settings) belong in a machine configuration or machine append file (meta-telemetry-bridge/conf/machine/include/).

Default Packages belong inside image recipes (meta-telemetry-bridge/recipes-core/images/telemetry-image.bb), NOT in IMAGE_INSTALL:append inside local.conf.


Strategy 2: Template Configurations (conf/templates/)
Yocto provides a built-in mechanism to generate standardized local.conf and bblayers.conf files whenever a developer sources oe-init-build-env.

Place your base configuration templates inside your custom layer:

meta-telemetry-bridge/
└── conf/
    └── templates/
        └── default/
            ├── bblayers.conf.sample
            ├── local.conf.sample
            └── README.conf.template

How it works in practice:
When setting up a build, set the TEMPLATECONF environment variable:

Bash
export TEMPLATECONF=meta-telemetry-bridge/conf/templates/default
source poky/oe-init-build-env Rasp_Build
BitBake automatically copies .sample files to create Rasp_Build/conf/local.conf and Rasp_Build/conf/bblayers.conf.


Strategy 3: Multi-Layer Management Tools (Kas / Android Repo)

For enterprise CI/CD systems, companies use top-level build orchestrators that generate the build folder dynamically from declarative YAML or XML files.

Tool                             Usage Pattern                                      Primary Benefit        
Kas (Siemens)           Single kas-project.yml defining repos                   Industry standard for Yocto CI/CD
                        revisions, local.conf snippets, and target images.          (GitLab CI/   GitHub Actions).


Google Repo             XML manifest defining Git submodules                    Used by Automotive Grade Linux (AGL) 
                        and layer repositories.                                     and Yocto board vendors.




To maintain project-specific settings in version control without polluting your global `conf/local.conf`, store those configurations inside your custom layer (`meta-telemetry-bridge`) instead of manually editing files in `build/conf/`.

Here are the **three standard Yocto methods** to track and apply project-specific configurations automatically:




---

### Option 1: Store in `meta-telemetry-bridge/conf/layer.conf` *(Recommended for Layer-Level Settings)*

Variables defined in a layer's `conf/layer.conf` apply automatically to any build that includes `meta-telemetry-bridge` in `bblayers.conf`.

Append your hardware and package requirements directly to your layer's configuration file:

```bash
cat << 'EOF' >> meta-telemetry-bridge/conf/layer.conf

# =================================================================
# STM32 Telemetry Bridge - Hardware & Build Configuration
# =================================================================

# Enable hardware interfaces required by the gateway
ENABLE_UART = "1"
ENABLE_I2C = "1"
ENABLE_SPI = "1"

# Raspberry Pi Device Tree Overlay for Telemetry UART
RPI_EXTRA_CONFIG:append = "\ndtoverlay=uart1\n"

EOF

```

* **Version Controlled:** Lives inside your git repository (`meta-telemetry-bridge/`).
* **Zero Manual Setup:** Anyone who adds the layer automatically inherits these settings without modifying `local.conf`.
* Keep package selection in the image recipe, rather than `layer.conf`, so
  unrelated images that include this layer do not inherit gateway packages.

---

### Option 2: Put Configurations in Image Recipes *(Recommended for Software Selection)*

Instead of adding packages to `IMAGE_INSTALL:append` inside `local.conf`, define them directly inside a custom image recipe (e.g., `meta-telemetry-bridge/recipes-core/images/telemetry-gateway-image.bb`):

```bitbake
SUMMARY = "Custom Gateway Image for STM32 Telemetry Bridge"
LICENSE = "MIT"

inherit core-image

# Include base packages and hardware drivers directly in the recipe
IMAGE_INSTALL:append = " \
    gatewayd \
    telemetry-daemon \
    sensor-gateway-app \
    openocd \
    libgpiod \
    libgpiod-tools \
    wireless-regdb-static \
    wpa-supplicant \
"

# Hardware-specific features tied to this image
EXTRA_IMAGE_FEATURES += "ssh-server-dropbear tools-debug debug-tweaks"

```

Then build your dedicated image:

```bash
bitbake telemetry-gateway-image

```

---

### Option 3: Use an Include File (`conf/telemetry-bridge.conf`)

If you want to keep the configuration organized as a distinct file that can be conditionally included in `local.conf`:

1. **Create the configuration file in your layer:**

```bash
mkdir -p meta-telemetry-bridge/conf/include
cat << 'EOF' > meta-telemetry-bridge/conf/include/telemetry-bridge.conf
# Hardware interface settings
ENABLE_UART = "1"
RPI_EXTRA_CONFIG:append = "\ndtoverlay=uart1\n"

EOF

```

2. **Add a single `include` line to your `build/conf/local.conf`:**

```bitbake
include conf/include/telemetry-bridge.conf

```

---
