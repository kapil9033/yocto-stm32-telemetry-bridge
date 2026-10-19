#ifndef FRAME_PROTOCOL_H
#define FRAME_PROTOCOL_H

#include <cstddef>
#include <cstdint>
#include <vector>

namespace gateway {

constexpr std::size_t kMaxRawFrameSize = 259U;
uint16_t calculate_crc16(const uint8_t *data, std::size_t length);
bool cobs_decode(const std::vector<uint8_t> &encoded, std::vector<uint8_t> &decoded);
bool validate_frame(const std::vector<uint8_t> &raw, uint8_t &message_type,
                    std::vector<uint8_t> &payload);
bool decode_frame(const std::vector<uint8_t> &encoded, uint8_t &message_type,
                  std::vector<uint8_t> &payload);

} // namespace gateway
#endif
