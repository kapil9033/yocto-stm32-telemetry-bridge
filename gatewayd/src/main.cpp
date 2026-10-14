#include <iostream>
#include <vector>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cerrno>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <sys/select.h>
#include "../inc/telemetry.h"

namespace {

constexpr uint8_t kFrameDelimiter = 0x00U;
constexpr std::size_t kMaxEncodedFrameSize = 512U;
constexpr std::size_t kMaxRawFrameSize = 259U;

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

bool cobs_decode(const std::vector<uint8_t> &encoded, std::vector<uint8_t> &decoded) {
    decoded.clear();
    size_t index = 0U;

    while (index < encoded.size()) {
        const uint8_t code = encoded[index++];
        if (code == 0U) {
            return false;
        }

        const size_t copy_length = static_cast<size_t>(code - 1U);
        if (copy_length > encoded.size() - index ||
            copy_length > kMaxRawFrameSize - decoded.size()) {
            return false;
        }

        decoded.insert(decoded.end(), encoded.begin() + static_cast<std::ptrdiff_t>(index),
                       encoded.begin() + static_cast<std::ptrdiff_t>(index + copy_length));
        index += copy_length;

        if (code != 0xFFU && index < encoded.size()) {
            if (decoded.size() >= kMaxRawFrameSize) {
                return false;
            }
            decoded.push_back(0U);
        }
    }

    return true;
}

} // namespace

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

    std::vector<uint8_t> encoded_frame;
    std::vector<uint8_t> raw_frame;
    encoded_frame.reserve(64U);
    raw_frame.reserve(sizeof(TelemetryPayload) + 4U);
    bool discard_until_delimiter = false;
    uint8_t byte = 0;

    while (true) {
        ssize_t bytes_read = read(fd, &byte, 1);
        if (bytes_read <= 0) {
            usleep(1000); // 1ms sleep on empty buffer to avoid high CPU load
            continue;
        }

        if (byte == kFrameDelimiter) {
            if (discard_until_delimiter) {
                discard_until_delimiter = false;
                encoded_frame.clear();
                continue;
            }
            if (encoded_frame.empty()) {
                continue;
            }

            if (!cobs_decode(encoded_frame, raw_frame)) {
                std::cerr << "[gatewayd] ERROR: Invalid COBS frame" << std::endl;
                encoded_frame.clear();
                continue;
            }
            encoded_frame.clear();

            if (raw_frame.size() < 4U) {
                std::cerr << "[gatewayd] ERROR: Frame is shorter than its header and CRC" << std::endl;
                continue;
            }

            const uint8_t msg_type = raw_frame[0];
            const uint8_t payload_len = raw_frame[1];
            const size_t expected_size = static_cast<size_t>(payload_len) + 4U;
            if (raw_frame.size() != expected_size) {
                std::cerr << "[gatewayd] ERROR: Frame payload length does not match decoded size" << std::endl;
                continue;
            }

            const size_t crc_data_size = raw_frame.size() - 2U;
            const uint16_t received_crc =
                static_cast<uint16_t>(raw_frame[crc_data_size]) |
                static_cast<uint16_t>(static_cast<uint16_t>(raw_frame[crc_data_size + 1U]) << 8U);
            const uint16_t calculated_crc = calculate_crc16(raw_frame.data(), crc_data_size);
            if (calculated_crc != received_crc) {
                std::cerr << "[gatewayd] ERROR: CRC mismatch! Expected: 0x"
                          << std::hex << calculated_crc << " Received: 0x" << received_crc
                          << std::dec << std::endl;
                continue;
            }

            const uint8_t *payload = &raw_frame[2];
            if (msg_type == 0x01U && payload_len == sizeof(TelemetryPayload)) {
                TelemetryPayload telemetry;
                std::memcpy(&telemetry, payload, sizeof(TelemetryPayload));

                std::cout << "\n================ [TELEMETRY FRAME RECEIVED] ================" << std::endl;
                std::cout << " Timestamp (RTC)  : " << telemetry.timestamp_sec << " s" << std::endl;
                std::cout << " Accel X / Y / Z  : " << telemetry.accel_x_mg << " mg | "
                          << telemetry.accel_y_mg << " mg | "
                          << telemetry.accel_z_mg << " mg" << std::endl;
                std::cout << " Photocell Raw    : " << telemetry.light_lux_raw << " / 4095" << std::endl;
                if (telemetry.humidity_pct == UINT8_MAX) {
                    std::cout << " DHT11            : READ ERROR" << std::endl;
                } else {
                    std::cout << " Temperature      : " << static_cast<int>(telemetry.temp_celsius) << " °C" << std::endl;
                    std::cout << " Humidity         : " << static_cast<int>(telemetry.humidity_pct) << " %" << std::endl;
                }
                std::cout << " EXTI Button State: " << (telemetry.button_state ? "PRESSED" : "RELEASED") << std::endl;
                std::cout << "============================================================\n" << std::endl;
            }
        } else if (discard_until_delimiter) {
            continue;
        } else if (encoded_frame.size() >= kMaxEncodedFrameSize) {
            std::cerr << "[gatewayd] ERROR: Encoded frame exceeds maximum size" << std::endl;
            encoded_frame.clear();
            discard_until_delimiter = true;
        } else {
            encoded_frame.push_back(byte);
        }
    }

    close(fd);
    return 0;
}
