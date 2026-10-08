# Heterogeneous Industrial Edge Gateway

An embedded system connecting a real-time STM32 microcontroller running
FreeRTOS to a Raspberry Pi Linux gateway built with Yocto. The system acquires
multi-sensor telemetry, displays local status, and communicates framed data
between the target and host.

## Project Overview

Industrial edge devices divide deterministic, real-time work—such as sensor
sampling, safety monitoring, and interrupt handling—from higher-level host
work, such as networking, data persistence, and user interfaces.

This project brings those roles together:

- **Real-time MCU — STM32F446RE:** FreeRTOS firmware for ADC sampling with DMA,
  DS3231 RTC access over I2C, DHT11 single-wire sensing, button input, LCD
  output, and telemetry communication.
- **Linux gateway — Raspberry Pi 3 Model B:** A Yocto-based Linux system,
  booted over NFS, that hosts a C++ daemon for serial parsing, CRC validation,
  and network-facing telemetry services.
- **Host-target protocol:** A binary packet format with framing, byte-stuffing,
  and CRC error checking over a USB CDC-ACM virtual COM port.

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
                 Photocell   LCD1602
```

### MCU Task Structure

The firmware task structure is organized around acquisition, display, and
communication:

| Task | Priority | Period / Trigger | Responsibility |
| :--- | :--- | :--- | :--- |
| `Task_AnalogDMA` | High | 50 ms | Runs four-channel ADC scans into a circular DMA buffer; calculates filtered acceleration and ambient-light values. |
| `Task_DigitalSens` | Medium | 500 ms | Reads the DS3231 over mutex-protected I2C and samples DHT11 temperature and humidity. |
| `Task_DisplayUI` | Low | 200 ms | Formats telemetry for the LCD and switches pages based on button input. |
| `Task_CommParser` | High | Asynchronous / event-driven | Packs telemetry into framed binary packets with CRC16 and transmits it to the gateway. |

FreeRTOS queues are used to share data between tasks. Additional planned
responsibilities described for the target include a sensor-acquisition task
running at a fixed interval, command parsing and dispatch, safety monitoring
against configurable thresholds, and local display updates.

## Hardware

The system is intended to run from USB bus power supplied by the host.

### Bill of Materials

| Component | Function | Interface | Voltage |
| :--- | :--- | :--- | :--- |
| Raspberry Pi 3 Model B (Rev 1.2) | Embedded Linux host gateway | Ethernet / NFS boot | USB 5 V |
| NUCLEO-F446RE (STM32F446RE) | Real-time microcontroller node | USB CDC-ACM / UART | USB 5 V (ST-LINK) |
| ADXL335 module | Three-axis analog accelerometer | Three ADC channels | 3.3 V |
| Photoresistor (photocell) | Ambient-light sensor | ADC voltage divider | 3.3 V |
| DS3231 RTC module | Real-time clock and timestamping | I2C1 | 3.3 V |
| DHT11 module | Temperature and humidity | Single-wire GPIO | 3.3 V |
| HC-SR501 PIR module | Motion detection | Digital GPIO output | 5 V |
| MAX7219 LED matrix | Local status and telemetry display | SPI1 | 5 V |
| LCD1602 display | Local telemetry and status UI | I2C1 adapter or 4-bit GPIO | 5 V / 3.3 V |
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

#### Photoresistor (Photocell)

| Sensor connection | Connect to | Notes |
| --- | --- | --- |
| Voltage-divider output | PB0 (ADC1_IN8 / CN8 A3) | Connect the photocell in a voltage divider between 3.3 V and GND. Keep the ADC input within 0–3.3 V. |
| Divider supply / ground | 3.3 V / common ground | Connect ground to the NUCLEO ground. |

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

#### LCD1602 Display (I2C Adapter)

| Display pin | Connect to | Notes |
| --- | --- | --- |
| VCC | Supply supported by the display adapter | Check both module supply and I2C logic-level requirements. |
| GND | Common ground | Connect to NUCLEO ground. |
| SCL | PB8 (I2C1_SCL) | Shared I2C1 bus with the DS3231. |
| SDA | PB9 (I2C1_SDA) | Shared I2C1 bus with the DS3231. |

#### User Button

| Button connection | Connect to | Notes |
| --- | --- | --- |
| Onboard NUCLEO user button | PC13 | This is the button input configured by the current firmware; active-low. |
| External button, optional | GPIO input to GND | Only use a pin configured by the firmware and its matching pull-up. |

#### Raspberry Pi Gateway Serial Connection

| Connection | Connect to | Notes |
| --- | --- | --- |
| NUCLEO USB connector | Raspberry Pi USB port | ST-LINK USB virtual COM port; Linux typically exposes `/dev/ttyACM0`. |

**Pin-use note:** The documented photocell connection is PB0 (ADC1_IN8), but
the current firmware configures PA5 (ADC1_IN5) for the photocell. PA5 is also
the MAX7219 clock pin, so update the firmware ADC configuration to PB0 before
using the MAX7219 and photocell together. The firmware configures DHT11 on
PA6, the PIR input is PA8, and the onboard button is PC13.

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
|  5: VDD                6: E5V        |    |  5: PB9                6: PC5        |
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
| 33: VBAT              34: PB0 [PHOTO]|    | 33: PA10              34: PC4        |
| 35: PC2               36: PC1         |    | 35: PA2               36: NC         |
| 37: PC3               38: PC0         |    | 37: PA3               38: NC         |
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
gateway). Frames use the following layout:

| Byte offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| `0x00` | Header / SOF | `uint8_t` | Frame start identifier, `0xAA` |
| `0x01` | Message type | `uint8_t` | `0x01` telemetry, `0x02` alarm, or `0x03` command |
| `0x02` | Payload length | `uint8_t` | Payload length, N bytes |
| `0x03` to `N+2` | Payload | `uint8_t[]` | Sensor structure or configuration command |
| `N+3` to `N+4` | CRC16 | `uint16_t` | Modbus/CCITT checksum over header, type, length, and payload |
| `N+5` | Tail / EOF | `uint8_t` | Frame end identifier, `0x55` |

### Telemetry Payload

For message type `0x01`, the documented telemetry payload is 15 bytes:

| Payload offset | Field | Type | Unit / description |
| :--- | :--- | :--- | :--- |
| `0x00` to `0x03` | `timestamp_sec` | `uint32_t` | DS3231 RTC timestamp in seconds |
| `0x04` to `0x05` | `accel_x_mg` | `int16_t` | X-axis acceleration in milli-g |
| `0x06` to `0x07` | `accel_y_mg` | `int16_t` | Y-axis acceleration in milli-g |
| `0x08` to `0x09` | `accel_z_mg` | `int16_t` | Z-axis acceleration in milli-g |
| `0x0A` to `0x0B` | `light_lux_raw` | `uint16_t` | Photoresistor ADC value (0–4095) |
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

The complete frame is 21 bytes: 1-byte header, 1-byte message type, 1-byte
payload length, 15-byte payload, 2-byte CRC16, and 1-byte tail.

## Software Components

### STM32 Target

- **Sensor acquisition:** Reads DHT11 temperature and humidity, DS3231 time,
  and accelerometer data. The documented design uses DMA-based acquisition.
- **Communication parser:** Monitors incoming USB CDC-ACM bytes, recognizes
  frames, validates CRC16, and updates runtime configuration or dispatches
  commands to other tasks.
- **Safety monitor:** Evaluates readings against configurable thresholds
  (such as tilt angle or over-temperature) and can trigger alarms without
  blocking sensor sampling.
- **Display task:** Updates the LCD1602 or 7-segment display with system status,
  IP flags, and sensor values.

### Yocto Linux Gateway

- **Custom BSP layer (`meta-hetero-gateway`):** Provides an image recipe with
  kernel configuration for CDC-ACM devices and network boot, plus systemd
  units to start the gateway daemon.
- **Gateway daemon (`gatewayd`):** A C++17 user-space application with a
  POSIX termios serial wrapper, asynchronous non-blocking I/O, and a frame
  decoder that validates checksums and formats telemetry as logs or JSON.

## Building the STM32 Firmware

The firmware build requires CMake, `arm-none-eabi-gcc`, and network access for
the first configure. CMake downloads pinned versions of STM32 HAL, CMSIS, and
FreeRTOS into the build directory; third-party source is not copied into the
project tree.

From the repository root:

```sh
cmake -S stm32-firmware -B stm32-firmware/build \
  -DCMAKE_TOOLCHAIN_FILE=stm32-firmware/arm-gcc-toolchain.cmake
cmake --build stm32-firmware/build
```

The ELF, BIN, and HEX firmware images are written to `stm32-firmware/build`.

## Implementation Notes

- **Thread-safe I2C access:** The sensor driver uses `xI2cMutex` to prevent
  concurrent access to the shared I2C bus.
- **DHT11 timing protection:** `DHT11_Read_Data()` uses a FreeRTOS critical
  section to prevent scheduler preemption from disrupting single-wire timing.



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