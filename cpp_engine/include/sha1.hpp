#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace hack_effect {
namespace sha1 {

inline uint32_t rol(uint32_t value, int bits) noexcept {
    return (value << bits) | (value >> (32 - bits));
}

inline void hash(const uint8_t* data, std::size_t len, uint8_t out[20]) noexcept {
    uint32_t h0 = 0x67452301u;
    uint32_t h1 = 0xEFCDAB89u;
    uint32_t h2 = 0x98BADCFEu;
    uint32_t h3 = 0x10325476u;
    uint32_t h4 = 0xC3D2E1F0u;

    const uint64_t bit_len = static_cast<uint64_t>(len) * 8ull;
    const std::size_t pad_len = ((len % 64) < 56) ? (56 - (len % 64)) : (120 - (len % 64));
    const std::size_t total = len + pad_len + 8;

    uint8_t block[128];
    uint32_t w[80];
    std::size_t offset = 0;
    while (offset < total) {
        std::memset(block, 0, 64);
        const std::size_t remain = total - offset;
        const std::size_t chunk = remain < 64 ? remain : 64;
        for (std::size_t i = 0; i < chunk; ++i) {
            const std::size_t src = offset + i;
            if (src < len) {
                block[i] = data[src];
            } else if (src == len) {
                block[i] = 0x80;
            } else if (src >= len + pad_len) {
                const std::size_t byte_index = src - (len + pad_len);
                block[i] = static_cast<uint8_t>((bit_len >> ((7 - byte_index) * 8)) & 0xFFu);
            }
        }

        for (int i = 0; i < 16; ++i) {
            w[i] = (static_cast<uint32_t>(block[i * 4]) << 24) |
                   (static_cast<uint32_t>(block[i * 4 + 1]) << 16) |
                   (static_cast<uint32_t>(block[i * 4 + 2]) << 8) |
                   (static_cast<uint32_t>(block[i * 4 + 3]));
        }
        for (int i = 16; i < 80; ++i) {
            w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
        }

        uint32_t a = h0, b = h1, c = h2, d = h3, e = h4;
        for (int i = 0; i < 80; ++i) {
            uint32_t f, k;
            if (i < 20) {
                f = (b & c) | ((~b) & d);
                k = 0x5A827999u;
            } else if (i < 40) {
                f = b ^ c ^ d;
                k = 0x6ED9EBA1u;
            } else if (i < 60) {
                f = (b & c) | (b & d) | (c & d);
                k = 0x8F1BBCDCu;
            } else {
                f = b ^ c ^ d;
                k = 0xCA62C1D6u;
            }
            const uint32_t temp = rol(a, 5) + f + e + k + w[i];
            e = d;
            d = c;
            c = rol(b, 30);
            b = a;
            a = temp;
        }
        h0 += a;
        h1 += b;
        h2 += c;
        h3 += d;
        h4 += e;
        offset += 64;
    }

    const uint32_t hs[5] = {h0, h1, h2, h3, h4};
    for (int i = 0; i < 5; ++i) {
        out[i * 4] = static_cast<uint8_t>((hs[i] >> 24) & 0xFFu);
        out[i * 4 + 1] = static_cast<uint8_t>((hs[i] >> 16) & 0xFFu);
        out[i * 4 + 2] = static_cast<uint8_t>((hs[i] >> 8) & 0xFFu);
        out[i * 4 + 3] = static_cast<uint8_t>(hs[i] & 0xFFu);
    }
}

} // namespace sha1
} // namespace hack_effect
