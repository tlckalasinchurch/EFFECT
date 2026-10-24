#include "param_registry.hpp"

#include <algorithm>
#include <cmath>

namespace hack_effect {

const std::vector<ParamSpec>& ParamRegistry::specs() {
    static const std::vector<ParamSpec> kSpecs = {
        // Input
        {0,  "input",    "trim",      "Input Trim", "dB",   TaperKind::Linear,       -24.0f,   24.0f,    0.0f,   1.0f},
        // Gate
        {1,  "gate",     "enabled",   "Gate On",    "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    1.0f,   1.0f},
        {2,  "gate",     "threshold", "Threshold",  "dB",   TaperKind::Linear,       -80.0f,  -20.0f,  -55.0f,   1.0f},
        {3,  "gate",     "release",   "Release",    "ms",   TaperKind::Linear,        10.0f,  500.0f,   50.0f,   1.0f},
        {4,  "gate",     "hold",      "Hold",       "ms",   TaperKind::Linear,         0.0f,  200.0f,   50.0f,   1.0f},
        {5,  "gate",     "range",     "Range",      "dB",   TaperKind::Linear,       -90.0f,  -20.0f,  -60.0f,   1.0f},
        // Pitch
        {6,  "pitch",    "enabled",   "Pitch On",   "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    0.0f,   1.0f},
        {7,  "pitch",    "semitones", "Pitch",      "st",   TaperKind::Linear,       -24.0f,   24.0f,    0.0f,   1.0f},
        {8,  "pitch",    "glide",     "Glide",      "%",    TaperKind::Linear,         0.0f,  100.0f,    0.0f,   1.0f},
        {9,  "pitch",    "mix",       "Mix",        "%",    TaperKind::Linear,         0.0f,    1.0f,    1.0f, 100.0f},
        // Screamer (Drive)
        {10, "screamer", "enabled",   "Drive On",   "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    0.0f,   1.0f},
        {11, "screamer", "drive",     "Drive",      "%",    TaperKind::Linear,         0.0f,    1.0f,    0.4f, 100.0f},
        {12, "screamer", "tone",      "Tone",       "%",    TaperKind::Linear,         0.0f,    1.0f,    0.6f, 100.0f},
        {13, "screamer", "level",     "Level",      "%",    TaperKind::Linear,         0.0f,    1.0f,    0.7f, 100.0f},
        // Amp
        {14, "amp",      "enabled",   "Amp On",     "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    1.0f,   1.0f},
        {15, "amp",      "gain",      "Gain",       "%",    TaperKind::Linear,         0.0f,    1.0f,   0.65f, 100.0f},
        {16, "amp",      "bass",      "Bass",       "%",    TaperKind::Linear,         0.0f,    1.0f,   0.55f, 100.0f},
        {17, "amp",      "mid",       "Middle",     "%",    TaperKind::Linear,         0.0f,    1.0f,   0.50f, 100.0f},
        {18, "amp",      "treble",    "Treble",     "%",    TaperKind::Linear,         0.0f,    1.0f,   0.60f, 100.0f},
        {19, "amp",      "presence",  "Presence",   "%",    TaperKind::Linear,         0.0f,    1.0f,   0.60f, 100.0f},
        {20, "amp",      "master",    "Master",     "%",    TaperKind::Linear,         0.0f,    1.0f,   0.70f, 100.0f},
        // EQ
        {21, "eq",       "enabled",   "EQ On",      "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    0.0f,   1.0f},
        {22, "eq",       "band0",     "Band 1",     "dB",   TaperKind::Linear,       -16.0f,   16.0f,    0.0f,   1.0f},
        {23, "eq",       "band1",     "Band 2",     "dB",   TaperKind::Linear,       -16.0f,   16.0f,    0.0f,   1.0f},
        {24, "eq",       "band2",     "Band 3",     "dB",   TaperKind::Linear,       -16.0f,   16.0f,    0.0f,   1.0f},
        {25, "eq",       "band3",     "Band 4",     "dB",   TaperKind::Linear,       -16.0f,   16.0f,    0.0f,   1.0f},
        {26, "eq",       "band4",     "Band 5",     "dB",   TaperKind::Linear,       -16.0f,   16.0f,    0.0f,   1.0f},
        {27, "eq",       "band5",     "Band 6",     "dB",   TaperKind::Linear,       -16.0f,   16.0f,    0.0f,   1.0f},
        // Cab
        {28, "cab",      "enabled",   "Cab On",     "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    1.0f,   1.0f},
        {29, "cab",      "level",     "Level",      "%",    TaperKind::Linear,         0.0f,    2.0f,    1.0f, 100.0f},
        {30, "cab",      "lowcut",    "Low Cut",    "Hz",   TaperKind::LogHz,         20.0f,  500.0f,   20.0f,   1.0f},
        {31, "cab",      "highcut",   "High Cut",   "Hz",   TaperKind::LogHz,       1000.0f,20000.0f,20000.0f,   1.0f},
        {32, "cab",      "mix",       "Mix",        "%",    TaperKind::Linear,         0.0f,    1.0f,    1.0f, 100.0f},
        {33, "cab",      "center",    "Axis Center","%",    TaperKind::Linear,         0.0f,  100.0f,   50.0f,   1.0f},
        {34, "cab",      "distance",  "Distance",   "%",    TaperKind::Linear,         0.0f,  100.0f,   20.0f,   1.0f},
        // Mod
        {35, "mod",      "enabled",   "Mod On",     "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    0.0f,   1.0f},
        {36, "mod",      "rate",      "Rate",       "%",    TaperKind::Linear,         0.0f,    1.0f,    0.5f, 100.0f},
        {37, "mod",      "depth",     "Depth",      "%",    TaperKind::Linear,         0.0f,    1.0f,    0.5f, 100.0f},
        {38, "mod",      "mix",       "Mix",        "%",    TaperKind::Linear,         0.0f,    1.0f,    0.5f, 100.0f},
        // Delay
        {39, "delay",    "enabled",   "Delay On",   "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    0.0f,   1.0f},
        {40, "delay",    "time",      "Time",       "ms",   TaperKind::Linear,        20.0f, 2000.0f,  360.0f,   1.0f},
        {41, "delay",    "feedback",  "Feedback",   "%",    TaperKind::Linear,         0.0f,   0.95f,   0.35f, 100.0f},
        {42, "delay",    "mix",       "Mix",        "%",    TaperKind::Linear,         0.0f,    1.0f,   0.25f, 100.0f},
        // Reverb
        {43, "reverb",   "enabled",   "Reverb On",  "bool", TaperKind::DiscreteBool,   0.0f,    1.0f,    0.0f,   1.0f},
        {44, "reverb",   "decay",     "Decay",      "%",    TaperKind::Linear,         0.0f,    1.0f,    0.5f, 100.0f},
        {45, "reverb",   "tone",      "Tone",       "%",    TaperKind::Linear,         0.0f,    1.0f,    0.5f, 100.0f},
        {46, "reverb",   "mix",       "Mix",        "%",    TaperKind::Linear,         0.0f,    1.0f,    0.2f, 100.0f},
        // Master
        {47, "master",   "volume",    "Master Vol", "%",    TaperKind::Linear,         0.0f,    2.0f,    1.0f, 100.0f}
    };
    return kSpecs;
}

const ParamSpec* ParamRegistry::find(std::string_view block, std::string_view param) {
    // Support UI alias "drive" -> "screamer" and "output" -> "master"
    std::string_view canonical_block = block;
    if (block == "drive") canonical_block = "screamer";
    else if (block == "output") canonical_block = "master";

    for (const auto& s : specs()) {
        if (canonical_block == s.block && param == s.param) {
            return &s;
        }
    }
    return nullptr;
}

const ParamSpec* ParamRegistry::find_by_id(uint16_t id) {
    const auto& all = specs();
    if (id < all.size()) {
        return &all[id];
    }
    return nullptr;
}

float ParamRegistry::value_to_normalized(const ParamSpec& spec, float engineering_val) noexcept {
    if (!std::isfinite(engineering_val)) {
        engineering_val = spec.default_val;
    }
    const float clamped = std::clamp(engineering_val, spec.min_val, spec.max_val);
    if (spec.taper == TaperKind::DiscreteBool) {
        return clamped >= 0.5f ? 1.0f : 0.0f;
    }
    if (spec.taper == TaperKind::LogHz && spec.min_val > 0.0f && spec.max_val > spec.min_val) {
        const float log_min = std::log(spec.min_val);
        const float log_max = std::log(spec.max_val);
        return std::clamp((std::log(clamped) - log_min) / (log_max - log_min), 0.0f, 1.0f);
    }
    const float span = spec.max_val - spec.min_val;
    if (span <= 0.0f) return 0.0f;
    return std::clamp((clamped - spec.min_val) / span, 0.0f, 1.0f);
}

float ParamRegistry::normalized_to_value(const ParamSpec& spec, float norm_val) noexcept {
    if (!std::isfinite(norm_val)) {
        return spec.default_val;
    }
    const float n = std::clamp(norm_val, 0.0f, 1.0f);
    if (spec.taper == TaperKind::DiscreteBool) {
        return n >= 0.5f ? 1.0f : 0.0f;
    }
    if (spec.taper == TaperKind::LogHz && spec.min_val > 0.0f && spec.max_val > spec.min_val) {
        const float log_min = std::log(spec.min_val);
        const float log_max = std::log(spec.max_val);
        return std::clamp(std::exp(log_min + n * (log_max - log_min)), spec.min_val, spec.max_val);
    }
    return spec.min_val + n * (spec.max_val - spec.min_val);
}

ParamValue ParamRegistry::make_from_normalized(const ParamSpec& spec, float norm_val) noexcept {
    const float clamped_norm = std::clamp(std::isfinite(norm_val) ? norm_val : 0.0f, 0.0f, 1.0f);
    const float eng = normalized_to_value(spec, clamped_norm);
    const float final_norm = value_to_normalized(spec, eng);
    return ParamValue{
        spec.id,
        final_norm,
        eng,
        eng * spec.display_scale
    };
}

ParamValue ParamRegistry::make_from_value(const ParamSpec& spec, float engineering_val) noexcept {
    const float norm = value_to_normalized(spec, engineering_val);
    const float clamped_eng = normalized_to_value(spec, norm);
    return ParamValue{
        spec.id,
        norm,
        clamped_eng,
        clamped_eng * spec.display_scale
    };
}

} // namespace hack_effect
