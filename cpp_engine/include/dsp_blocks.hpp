#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace hack_effect {

/**
 * Exact double-precision state-preserving biquad/1st-order IIR filter matching
 * scipy.signal.lfilter(b, a, x, zi=zi) Direct Form II Transposed.
 */
struct IirFilter {
    int order{0}; // 1 or 2
    double b0{1.0}, b1{0.0}, b2{0.0};
    double a1{0.0}, a2{0.0};
    double z1{0.0}, z2{0.0};

    void reset_state() noexcept {
        z1 = 0.0;
        z2 = 0.0;
    }

    inline double process_sample(double x) noexcept {
        if (order == 1) {
            const double y = b0 * x + z1;
            z1 = b1 * x - a1 * y;
            return y;
        }
        if (order == 2) {
            const double y = b0 * x + z1;
            z1 = b1 * x - a1 * y + z2;
            z2 = b2 * x - a2 * y;
            return y;
        }
        return x;
    }

    void process_block(const float* in, float* out, std::size_t n) noexcept {
        for (std::size_t i = 0; i < n; ++i) {
            out[i] = static_cast<float>(process_sample(static_cast<double>(in[i])));
        }
    }

    void process_block_double(const double* in, double* out, std::size_t n) noexcept {
        for (std::size_t i = 0; i < n; ++i) {
            out[i] = process_sample(in[i]);
        }
    }

    // Exact match to scipy.signal.butter(1, norm_cutoff, btype='low')
    static void design_butter1_low(double norm_cutoff, IirFilter& f, bool reset = false) noexcept;

    // Exact match to scipy.signal.butter(2, norm_cutoff, btype='high' | 'low')
    static void design_butter2_high(double norm_cutoff, IirFilter& f, bool reset = false) noexcept;
    static void design_butter2_low(double norm_cutoff, IirFilter& f, bool reset = false) noexcept;

    // Exact match to AmpHead._shelf(norm_freq, gain_db, btype)
    static void design_amp_shelf1(double norm_freq, double gain_db, bool is_low, IirFilter& f) noexcept;

    // Exact match to AmpHead._peak(norm_freq, gain_db, Q)
    static void design_amp_peak2(double norm_freq, double gain_db, double Q, IirFilter& f) noexcept;

    // Exact match to CabinetSimulator._peaking_biquad(f0, gain_db, Q, sr)
    static void design_peaking_biquad(double f0, double gain_db, double Q, double sr, IirFilter& f) noexcept;
};

/**
 * Exact C++ port of engine/dsp.py :: AmpHead
 */
class DspAmpHead {
public:
    explicit DspAmpHead(uint32_t sample_rate = 48000);

    void set_sample_rate(uint32_t sr);
    void reset();

    void set_params(float gain, float bass, float mid, float treble, float presence, float master, bool bright, bool enabled) noexcept;
    void process(const float* in, float* out, std::size_t n) noexcept;

private:
    uint32_t sample_rate_{48000};
    bool enabled_{true};
    bool bright_{false};
    float gain_{0.65f};
    float bass_{0.55f};
    float mid_{0.50f};
    float treble_{0.60f};
    float presence_{0.60f};
    float master_{0.70f};

    IirFilter lowcut_{};
    IirFilter bass_filter_{};
    IirFilter mid_filter_{};
    IirFilter treble_filter_{};
    IirFilter presence_filter_{};
};

/**
 * Exact C++ port of engine/convolver.py :: PartitionedConvolver
 * Zero-latency partitioned overlap-add convolver.
 */
class DspPartitionedConvolver {
public:
    explicit DspPartitionedConvolver(const std::vector<float>& ir = {1.0f, 0.0f}, std::size_t block_size = 128);

    void set_ir(const std::vector<float>& ir, std::size_t block_size = 128);
    void reset() noexcept;
    void process(const float* in, float* out, std::size_t n) noexcept;

private:
    void complete_block() noexcept;

    std::size_t B_{128};
    std::size_t P_{1};
    std::size_t M_{0};
    std::size_t pos_{0};
    std::size_t w_{0};

    // Time-domain partition blocks (for exact zero-allocation linear block convolution)
    std::vector<double> ir_padded_{};
    std::vector<double> xb_{};
    std::vector<double> f_{};
    std::vector<double> c_{};
    std::vector<double> hist_blocks_{}; // M past blocks of length B
};

/**
 * Exact C++ port of engine/dsp.py :: CabinetSimulator
 */
class DspCabinetSimulator {
public:
    explicit DspCabinetSimulator(uint32_t sample_rate = 48000);

    void set_ir_data(const std::vector<float>& ir);
    void set_cutoffs(float lowcut_hz, float highcut_hz) noexcept;
    void set_params(float level, float mix, float center, float distance, bool enabled) noexcept;
    void reset() noexcept;

    void process(const float* in, float* out, std::size_t n) noexcept;

private:
    void design_cutoffs() noexcept;
    void design_tube_mic_filters() noexcept;

    uint32_t sample_rate_{48000};
    bool enabled_{true};
    bool conv_dirty_{false};
    float level_{1.0f};
    float mix_{1.0f};
    float lowcut_hz_{20.0f};
    float highcut_hz_{20000.0f};
    float center_{50.0f};
    float distance_{20.0f};

    DspPartitionedConvolver conv_;
    IirFilter hp_filter_{};
    IirFilter lp_filter_{};
    std::vector<IirFilter> tube_mic_sections_{};
};

/**
 * Cloned MOOER GE150 / TS-808 Asymmetric Tube Screamer Overdrive
 */
class DspOverdrive {
public:
    explicit DspOverdrive(uint32_t sample_rate = 48000);
    void set_params(float drive, float tone, float level, bool enabled) noexcept;
    void process(const float* in, float* out, std::size_t n) noexcept;

private:
    uint32_t sample_rate_{48000};
    bool enabled_{false};
    float drive_{0.4f};
    float tone_{0.6f};
    float level_{0.7f};
    IirFilter tone_filter_{};
};

/**
 * Cloned Neural DSP Archetype Petrucci / Plini Stereo Haas Doubler & Micro-Detune Widener
 */
class DspStereoDoubler {
public:
    explicit DspStereoDoubler(uint32_t sample_rate = 48000);
    void set_params(float width_ms, float detune_depth, float mix, bool enabled) noexcept;
    void process_stereo(const float* mono_in, float* left_out, float* right_out, std::size_t n) noexcept;

private:
    uint32_t sample_rate_{48000};
    bool enabled_{true};
    float width_ms_{14.0f};
    float detune_depth_{0.35f};
    float mix_{1.0f};
    double lfo_phase_{0.0};
    std::vector<float> ring_{};
    std::size_t write_pos_{0};
};

/**
 * Cloned Quad Cortex Dynamic Ducking Delay
 */
class DspDuckingDelay {
public:
    explicit DspDuckingDelay(uint32_t sample_rate = 48000);
    void set_params(float time_sec, float feedback, float mix, bool ducking, float duck_depth, bool enabled) noexcept;
    void process(const float* in, float* out, std::size_t n) noexcept;

private:
    uint32_t sample_rate_{48000};
    bool enabled_{false};
    bool ducking_{true};
    float time_sec_{0.36f};
    float feedback_{0.35f};
    float mix_{0.25f};
    float duck_depth_{0.6f};
    float duck_gain_{1.0f};
    std::vector<float> buffer_{};
    std::size_t write_pos_{0};
};

/**
 * Cloned Kemper Continuous Morph A<->B Interpolator (Zero-Allocation Lock-Free)
 */
struct MorphSnapshot {
    float amp_gain{0.40f};
    float amp_master{0.70f};
    float screamer_drive{0.20f};
    float screamer_level{0.70f};
    float delay_mix{0.15f};
    float reverb_mix{0.18f};
};

class DspKemperMorph {
public:
    static MorphSnapshot interpolate(const MorphSnapshot& a, const MorphSnapshot& b, float pos) noexcept {
        const float t = pos < 0.0f ? 0.0f : (pos > 1.0f ? 1.0f : pos);
        const float inv = 1.0f - t;
        return MorphSnapshot{
            inv * a.amp_gain + t * b.amp_gain,
            inv * a.amp_master + t * b.amp_master,
            inv * a.screamer_drive + t * b.screamer_drive,
            inv * a.screamer_level + t * b.screamer_level,
            inv * a.delay_mix + t * b.delay_mix,
            inv * a.reverb_mix + t * b.reverb_mix
        };
    }
};

/**
 * Native Neural Amp Modeler (NAM) C99 Engine Bridge.
 * Binds to engine/nam_c99.dll for zero-allocation real-time WaveNet inference.
 */
class DspNamEngine {
public:
    DspNamEngine();
    ~DspNamEngine();

    bool load_dll(const char* dll_path = nullptr);
    bool load_model_binary(const void* buf, uint32_t size, std::string* error_out = nullptr);
    bool load_weights(const float* weights, std::size_t weight_count, double sample_rate = 48000.0, double loudness = -18.0, std::string* error_out = nullptr);
    void reset() noexcept;
    void process(const float* in, float* out, std::size_t n) noexcept;

    bool is_loaded() const noexcept { return is_loaded_; }
    const char* model_name() const noexcept { return model_name_.c_str(); }
    void set_enabled(bool enabled) noexcept { enabled_ = enabled; }
    bool is_enabled() const noexcept { return enabled_; }

private:
    void* dll_handle_{nullptr};
    bool is_loaded_{false};
    bool enabled_{true};
    std::string model_name_{"None"};

    using FnLoad = int (*)(const void*, uint32_t, int, const char**);
    using FnReset = void (*)();
    using FnProcess = void (*)(const float*, float*, int);
    using FnModel = int (*)();
    using FnModelName = const char* (*)();

    FnLoad fn_load_{nullptr};
    FnReset fn_reset_{nullptr};
    FnProcess fn_process_{nullptr};
    FnModel fn_model_{nullptr};
    FnModelName fn_model_name_{nullptr};
};

} // namespace hack_effect
