#include "frame_protocol.h"
#include "telemetry.h"

#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <string>
#include <termios.h>
#include <unistd.h>
#include <vector>

namespace {
constexpr std::size_t kMaxEncodedFrameSize = 512U;

int configure_serial_port(const char *name) {
    const int fd = open(name, O_RDWR | O_NOCTTY | O_NDELAY);
    if (fd < 0) {
        std::cerr << "[gatewayd] ERROR: Unable to open " << name << " - " << std::strerror(errno) << std::endl;
        return -1;
    }
    (void)fcntl(fd, F_SETFL, 0);
    termios options{};
    if (tcgetattr(fd, &options) != 0) {
        std::cerr << "[gatewayd] ERROR: Unable to read serial settings: " << std::strerror(errno) << std::endl;
        close(fd);
        return -1;
    }
    cfsetispeed(&options, B115200);
    cfsetospeed(&options, B115200);
    options.c_cflag &= static_cast<tcflag_t>(~(PARENB | CSTOPB | CSIZE));
    options.c_cflag |= CS8;
    options.c_lflag &= static_cast<tcflag_t>(~(ICANON | ECHO | ECHOE | ISIG));
    options.c_iflag &= static_cast<tcflag_t>(~(IXON | IXOFF | IXANY));
    options.c_cflag &= static_cast<tcflag_t>(~CRTSCTS);
    options.c_oflag &= static_cast<tcflag_t>(~OPOST);
    options.c_cc[VMIN] = 0;
    options.c_cc[VTIME] = 1;
    tcflush(fd, TCIFLUSH);
    if (tcsetattr(fd, TCSANOW, &options) != 0) {
        std::cerr << "[gatewayd] ERROR: Failed to apply serial settings: " << std::strerror(errno) << std::endl;
        close(fd);
        return -1;
    }
    return fd;
}

void print_telemetry(const std::vector<uint8_t> &payload) {
    if (payload.size() != sizeof(TelemetryPayload)) return;
    TelemetryPayload telemetry{};
    std::memcpy(&telemetry, payload.data(), sizeof(telemetry));
    std::cout << "[TELEMETRY] Timestamp=" << telemetry.timestamp_sec
              << " Accel_mg=" << telemetry.accel_x_mg << ',' << telemetry.accel_y_mg << ',' << telemetry.accel_z_mg
              << " ADC=" << telemetry.light_lux_raw;
    if (telemetry.humidity_pct == UINT8_MAX) std::cout << " DHT11=READ_ERROR";
    else std::cout << " Temperature_C=" << static_cast<int>(telemetry.temp_celsius)
                   << " Humidity_pct=" << static_cast<unsigned>(telemetry.humidity_pct);
    std::cout << " Button=" << static_cast<unsigned>(telemetry.button_state) << std::endl;
}
}

int main(int argc, char **argv) {
    std::string serial_dev = "/dev/ttyACM0";
    if (argc == 3 && std::string(argv[1]) == "--serial") serial_dev = argv[2];
    else if (argc != 1) {
        std::cerr << "Usage: gatewayd [--serial DEVICE]" << std::endl;
        return 2;
    }
    std::cout << "[gatewayd] Starting; serial=" << serial_dev << std::endl;
    int fd = configure_serial_port(serial_dev.c_str());
    while (fd < 0) {
        std::cout << "[gatewayd] Retrying connection to " << serial_dev << " in 2 seconds..." << std::endl;
        sleep(2);
        fd = configure_serial_port(serial_dev.c_str());
    }
    std::cout << "[gatewayd] Connected to " << serial_dev << std::endl;

    std::vector<uint8_t> encoded;
    encoded.reserve(64U);
    bool discard_until_delimiter = false;
    uint8_t byte = 0U;
    for (;;) {
        const ssize_t count = read(fd, &byte, 1U);
        if (count <= 0) { usleep(1000U); continue; }
        if (byte == 0U) {
            if (discard_until_delimiter) { discard_until_delimiter = false; encoded.clear(); continue; }
            if (encoded.empty()) continue;
            uint8_t message_type = 0U;
            std::vector<uint8_t> payload;
            if (!gateway::decode_frame(encoded, message_type, payload)) {
                std::cerr << "[gatewayd] ERROR: Invalid frame" << std::endl;
            } else if (message_type == 0x01U) {
                print_telemetry(payload);
            }
            encoded.clear();
        } else if (!discard_until_delimiter && encoded.size() >= kMaxEncodedFrameSize) {
            std::cerr << "[gatewayd] ERROR: Encoded frame exceeds maximum size" << std::endl;
            encoded.clear();
            discard_until_delimiter = true;
        } else if (!discard_until_delimiter) encoded.push_back(byte);
    }
}
