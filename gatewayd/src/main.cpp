#include <iostream>
#include <vector>
#include <cstdint>
#include <cstring>
#include <cerrno>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <sys/select.h>
#include "../inc/telemetry.h"

// Calculate Modbus CRC16 over packet payload/headers
uint16_t calculate_crc16(const uint8_t *data, size_t length) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (int j = 0; j < 8; ++j) {
            if (crc & 0x0001) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

// Configure POSIX serial port termios settings
int configure_serial_port(const char *port_name, speed_t baud_rate) {
    int fd = open(port_name, O_RDWR | O_NOCTTY | O_NDELAY);
    if (fd == -1) {
        std::cerr << "[gatewayd] ERROR: Unable to open " << port_name << " - " << std::strerror(errno) << std::endl;
        return -1;
    }

    // Clear file flags to restore blocking/non-blocking control
    fcntl(fd, F_SETFL, 0);

    struct termios options;
    tcgetattr(fd, &options);

    // Set baud rate (default 115200)
    cfsetispeed(&options, baud_rate);
    cfsetospeed(&options, baud_rate);

    // 8N1 (8 Data bits, No parity, 1 Stop bit)
    options.c_cflag &= static_cast<tcflag_t>(~PARENB);
    options.c_cflag &= static_cast<tcflag_t>(~CSTOPB);
    options.c_cflag &= static_cast<tcflag_t>(~CSIZE);
    options.c_cflag |= CS8;

    // Raw input mode (Disable canonical mode, echo, signals)
    options.c_lflag &= static_cast<tcflag_t>(~(ICANON | ECHO | ECHOE | ISIG));
    
    // Disable software flow control (XON/XOFF) and hardware flow control
    options.c_iflag &= static_cast<tcflag_t>(~(IXON | IXOFF | IXANY));
    options.c_cflag &= static_cast<tcflag_t>(~CRTSCTS);

    // Raw output mode
    options.c_oflag &= static_cast<tcflag_t>(~OPOST);

    // Read timeout configurations (Wait up to 100ms per read call)
    options.c_cc[VMIN]  = 0;
    options.c_cc[VTIME] = 1;

    tcflush(fd, TCIFLUSH);
    if (tcsetattr(fd, TCSANOW, &options) != 0) {
        std::cerr << "[gatewayd] ERROR: Failed to apply termios settings - " << std::strerror(errno) << std::endl;
        close(fd);
        return -1;
    }

    return fd;
}

enum class RxState {
    WAIT_SOF,
    WAIT_TYPE,
    WAIT_LEN,
    WAIT_PAYLOAD,
    WAIT_CRC_LOW,
    WAIT_CRC_HIGH,
    WAIT_EOF
};

int main() {
    const char *serial_dev = "/dev/ttyACM0";
    std::cout << "[gatewayd] Starting Industrial Gateway Daemon..." << std::endl;

    int fd = configure_serial_port(serial_dev, B115200);
    while (fd < 0) {
        std::cout << "[gatewayd] Retrying connection to " << serial_dev << " in 2 seconds..." << std::endl;
        sleep(2);
        fd = configure_serial_port(serial_dev, B115200);
    }

    std::cout << "[gatewayd] Connected to " << serial_dev << " successfully!" << std::endl;

    RxState state = RxState::WAIT_SOF;
    uint8_t msg_type = 0;
    uint8_t payload_len = 0;
    std::vector<uint8_t> payload_buffer;
    uint16_t rx_crc = 0;
    uint8_t byte = 0;

    while (true) {
        ssize_t bytes_read = read(fd, &byte, 1);
        if (bytes_read <= 0) {
            usleep(1000); // 1ms sleep on empty buffer to avoid high CPU load
            continue;
        }

        switch (state) {
            case RxState::WAIT_SOF:
                if (byte == 0xAA) { // Frame Start
                    state = RxState::WAIT_TYPE;
                }
                break;

            case RxState::WAIT_TYPE:
                msg_type = byte;
                state = RxState::WAIT_LEN;
                break;

            case RxState::WAIT_LEN:
                payload_len = byte;
                payload_buffer.clear();
                payload_buffer.reserve(payload_len);
                if (payload_len > 0) {
                    state = RxState::WAIT_PAYLOAD;
                } else {
                    state = RxState::WAIT_CRC_LOW;
                }
                break;

            case RxState::WAIT_PAYLOAD:
                payload_buffer.push_back(byte);
                if (payload_buffer.size() == payload_len) {
                    state = RxState::WAIT_CRC_LOW;
                }
                break;

            case RxState::WAIT_CRC_LOW:
                rx_crc = byte;
                state = RxState::WAIT_CRC_HIGH;
                break;

            case RxState::WAIT_CRC_HIGH:
                rx_crc |= static_cast<uint16_t>(byte << 8);
                state = RxState::WAIT_EOF;
                break;

            case RxState::WAIT_EOF:
                if (byte == 0x55) { // Frame End
                    // Reconstruct header + payload buffer for CRC validation
                    std::vector<uint8_t> crc_check_buf;
                    crc_check_buf.push_back(0xAA);
                    crc_check_buf.push_back(msg_type);
                    crc_check_buf.push_back(payload_len);
                    crc_check_buf.insert(crc_check_buf.end(), payload_buffer.begin(), payload_buffer.end());

                    uint16_t calculated_crc = calculate_crc16(crc_check_buf.data(), crc_check_buf.size());

                    if (calculated_crc == rx_crc) {
                        if (msg_type == 0x01 && payload_buffer.size() == sizeof(TelemetryPayload)) {
                            TelemetryPayload telemetry;
                            std::memcpy(&telemetry, payload_buffer.data(), sizeof(TelemetryPayload));

                            std::cout << "\n================ [TELEMETRY FRAME RECEIVED] ================" << std::endl;
                            std::cout << " Timestamp (RTC)  : " << telemetry.timestamp_sec << " s" << std::endl;
                            std::cout << " Accel X / Y / Z  : " << telemetry.accel_x_mg << " mg | " 
                                      << telemetry.accel_y_mg << " mg | " 
                                      << telemetry.accel_z_mg << " mg" << std::endl;
                            std::cout << " Photocell Raw    : " << telemetry.light_lux_raw << " / 4095" << std::endl;
                            std::cout << " Temperature      : " << static_cast<int>(telemetry.temp_celsius) << " °C" << std::endl;
                            std::cout << " Humidity         : " << static_cast<int>(telemetry.humidity_pct) << " %" << std::endl;
                            std::cout << " EXTI Button State: " << (telemetry.button_state ? "PRESSED" : "RELEASED") << std::endl;
                            std::cout << "============================================================\n" << std::endl;
                        }
                    } else {
                        std::cerr << "[gatewayd] ERROR: CRC mismatch! Expected: 0x" 
                                  << std::hex << calculated_crc << " Received: 0x" << rx_crc 
                                  << std::dec << std::endl;
                    }
                } else {
                    std::cerr << "[gatewayd] ERROR: Missing EOF frame tail (0x55)" << std::endl;
                }
                state = RxState::WAIT_SOF;
                break;

            default:
                state = RxState::WAIT_SOF;
                break;
        }
    }

    close(fd);
    return 0;
}
