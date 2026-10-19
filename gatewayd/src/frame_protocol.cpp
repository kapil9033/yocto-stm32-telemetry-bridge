#include "frame_protocol.h"

namespace gateway {

uint16_t calculate_crc16(const uint8_t *data, std::size_t length) {
    uint16_t crc = 0xFFFFU;
    for (std::size_t i = 0U; i < length; ++i) {
        crc ^= data[i];
        for (unsigned j = 0U; j < 8U; ++j) {
            crc = (crc & 1U) != 0U ? static_cast<uint16_t>((crc >> 1U) ^ 0xA001U)
                                  : static_cast<uint16_t>(crc >> 1U);
        }
    }
    return crc;
}

bool cobs_decode(const std::vector<uint8_t> &encoded, std::vector<uint8_t> &decoded) {
    decoded.clear();
    std::size_t index = 0U;
    while (index < encoded.size()) {
        const uint8_t code = encoded[index++];
        if (code == 0U) return false;
        const std::size_t count = static_cast<std::size_t>(code - 1U);
        if (count > encoded.size() - index || count > kMaxRawFrameSize - decoded.size()) return false;
        decoded.insert(decoded.end(), encoded.begin() + static_cast<std::ptrdiff_t>(index),
                       encoded.begin() + static_cast<std::ptrdiff_t>(index + count));
        index += count;
        if (code != 0xFFU && index < encoded.size()) {
            if (decoded.size() >= kMaxRawFrameSize) return false;
            decoded.push_back(0U);
        }
    }
    return true;
}

bool validate_frame(const std::vector<uint8_t> &raw, uint8_t &message_type,
                    std::vector<uint8_t> &payload) {
    if (raw.size() < 4U) return false;
    const std::size_t size = static_cast<std::size_t>(raw[1]) + 4U;
    if (raw.size() != size) return false;
    const std::size_t crc_index = raw.size() - 2U;
    const uint16_t received = static_cast<uint16_t>(raw[crc_index]) |
        static_cast<uint16_t>(static_cast<uint16_t>(raw[crc_index + 1U]) << 8U);
    if (calculate_crc16(raw.data(), crc_index) != received) return false;
    message_type = raw[0];
    payload.assign(raw.begin() + 2, raw.begin() + static_cast<std::ptrdiff_t>(crc_index));
    return true;
}

bool decode_frame(const std::vector<uint8_t> &encoded, uint8_t &message_type,
                  std::vector<uint8_t> &payload) {
    std::vector<uint8_t> raw;
    return cobs_decode(encoded, raw) && validate_frame(raw, message_type, payload);
}

} // namespace gateway
