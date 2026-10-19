#include "frame_protocol.h"

#include <cassert>
#include <cstdint>
#include <vector>

static std::vector<uint8_t> cobs(const std::vector<uint8_t> &in) {
    std::vector<uint8_t> out(1U, 0U);
    std::size_t code_at = 0U;
    uint8_t code = 1U;
    for (uint8_t b : in) {
        if (b == 0U) { out[code_at] = code; code_at = out.size(); out.push_back(0U); code = 1U; }
        else { out.push_back(b); if (++code == 0xFFU) { out[code_at] = code; code_at = out.size(); out.push_back(0U); code = 1U; } }
    }
    out[code_at] = code;
    return out;
}

int main() {
    const uint8_t check[] = "123456789";
    assert(gateway::calculate_crc16(check, 9U) == 0x4B37U);
    std::vector<uint8_t> raw{1U, 3U, 0x10U, 0U, 0x20U};
    const uint16_t crc = gateway::calculate_crc16(raw.data(), raw.size());
    raw.push_back(static_cast<uint8_t>(crc)); raw.push_back(static_cast<uint8_t>(crc >> 8U));
    const auto encoded = cobs(raw);
    uint8_t type = 0U; std::vector<uint8_t> payload;
    assert(gateway::decode_frame(encoded, type, payload));
    assert(type == 1U && (payload == std::vector<uint8_t>{0x10U, 0U, 0x20U}));
    auto bad_crc = encoded; bad_crc.back() ^= 1U;
    assert(!gateway::decode_frame(bad_crc, type, payload));
    assert(!gateway::decode_frame(std::vector<uint8_t>{3U, 1U}, type, payload));
    assert(!gateway::decode_frame(std::vector<uint8_t>{0U}, type, payload));
    std::vector<uint8_t> malformed(261U, 0xFFU), decoded;
    assert(!gateway::cobs_decode(malformed, decoded));
}
