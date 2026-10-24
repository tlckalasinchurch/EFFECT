#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace hack_effect {

enum class TaperKind : uint8_t {
    Linear = 0,
    LogHz = 1,
    DiscreteBool = 2,
    DiscreteInt = 3
};

struct ParamSpec {
    uint16_t id;
    const char* block;
    const char* param;
    const char* label;
    const char* unit;
    TaperKind taper;
    float min_val;
    float max_val;
    float default_val;
    float display_scale; // e.g., 100.0f when internal 0..1 is shown as 0..100%
};

struct ParamValue {
    uint16_t id{0};
    float normalized{0.0f};    // 0.0 .. 1.0
    float value{0.0f};         // Engineering value in native DSP range
    float display_value{0.0f}; // Value scaled for digital readout (e.g. % or Hz)
};

class ParamRegistry {
public:
    static const std::vector<ParamSpec>& specs();
    static const ParamSpec* find(std::string_view block, std::string_view param);
    static const ParamSpec* find_by_id(uint16_t id);

    static float value_to_normalized(const ParamSpec& spec, float engineering_val) noexcept;
    static float normalized_to_value(const ParamSpec& spec, float norm_val) noexcept;
    static ParamValue make_from_normalized(const ParamSpec& spec, float norm_val) noexcept;
    static ParamValue make_from_value(const ParamSpec& spec, float engineering_val) noexcept;
};

} // namespace hack_effect
