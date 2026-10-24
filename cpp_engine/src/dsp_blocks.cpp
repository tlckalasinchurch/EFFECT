#include "dsp_blocks.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#endif

namespace hack_effect {

namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr double kSqrt2 = 1.41421356237309504880;
} // namespace

void IirFilter::design_butter1_low(double norm_cutoff, IirFilter& f, bool reset) noexcept {
    f.order = 1;
    const double wc = std::tan(kPi * std::clamp(norm_cutoff, 1e-4, 0.99) * 0.5);
    const double a0 = 1.0 + wc;
    f.b0 = wc / a0;
    f.b1 = wc / a0;
    f.b2 = 0.0;
    f.a1 = (wc - 1.0) / a0;
    f.a2 = 0.0;
    if (reset) f.reset_state();
}

void IirFilter::design_butter2_high(double norm_cutoff, IirFilter& f, bool reset) noexcept {
    f.order = 2;
    const double wc = std::tan(kPi * std::clamp(norm_cutoff, 1e-4, 0.99) * 0.5);
    const double wc2 = wc * wc;
    const double a0 = 1.0 + kSqrt2 * wc + wc2;
    f.b0 = 1.0 / a0;
    f.b1 = -2.0 / a0;
    f.b2 = 1.0 / a0;
    f.a1 = 2.0 * (wc2 - 1.0) / a0;
    f.a2 = (1.0 - kSqrt2 * wc + wc2) / a0;
    if (reset) f.reset_state();
}

void IirFilter::design_butter2_low(double norm_cutoff, IirFilter& f, bool reset) noexcept {
    f.order = 2;
    const double wc = std::tan(kPi * std::clamp(norm_cutoff, 1e-4, 0.99) * 0.5);
    const double wc2 = wc * wc;
    const double a0 = 1.0 + kSqrt2 * wc + wc2;
    f.b0 = wc2 / a0;
    f.b1 = 2.0 * wc2 / a0;
    f.b2 = wc2 / a0;
    f.a1 = 2.0 * (wc2 - 1.0) / a0;
    f.a2 = (1.0 - kSqrt2 * wc + wc2) / a0;
    if (reset) f.reset_state();
}

void IirFilter::design_amp_shelf1(double norm_freq, double gain_db, bool is_low, IirFilter& f) noexcept {
    f.order = 1;
    const double A = std::pow(10.0, gain_db / 40.0);
    const double w0 = std::tan(kPi * norm_freq * 0.5);
    if (is_low) {
        const double a0 = w0 + 1.0;
        f.b0 = (A * w0 + 1.0) / a0;
        f.b1 = (A * w0 - 1.0) / a0;
        f.b2 = 0.0;
        f.a1 = (w0 - 1.0) / a0;
        f.a2 = 0.0;
    } else {
        const double a0 = 1.0 + w0;
        f.b0 = (A + w0) / a0;
        f.b1 = (A - w0) / a0;
        f.b2 = 0.0;
        f.a1 = (1.0 - w0) / a0;
        f.a2 = 0.0;
    }
}

void IirFilter::design_amp_peak2(double norm_freq, double gain_db, double Q, IirFilter& f) noexcept {
    f.order = 2;
    const double A = std::pow(10.0, gain_db / 40.0);
    const double w0 = 2.0 * kPi * norm_freq * 0.5;
    const double alpha = std::sin(w0) / (2.0 * Q);
    const double cw = std::cos(w0);
    const double a0 = 1.0 + alpha / A;
    f.b0 = (1.0 + alpha * A) / a0;
    f.b1 = (-2.0 * cw) / a0;
    f.b2 = (1.0 - alpha * A) / a0;
    f.a1 = (-2.0 * cw) / a0;
    f.a2 = (1.0 - alpha / A) / a0;
}

void IirFilter::design_peaking_biquad(double f0, double gain_db, double Q, double sr, IirFilter& f) noexcept {
    f.order = 2;
    const double w0 = 2.0 * kPi * f0 / sr;
    const double A = std::pow(10.0, gain_db / 40.0);
    const double alpha = std::sin(w0) / (2.0 * Q);
    const double cw = std::cos(w0);
    const double a0 = 1.0 + alpha / A;
    f.b0 = (1.0 + alpha * A) / a0;
    f.b1 = (-2.0 * cw) / a0;
    f.b2 = (1.0 - alpha * A) / a0;
    f.a1 = (-2.0 * cw) / a0;
    f.a2 = (1.0 - alpha / A) / a0;
}

// ---------------------------------------------------------------------------
// DspAmpHead (exact parity with engine/dsp.py :: AmpHead)
// ---------------------------------------------------------------------------

DspAmpHead::DspAmpHead(uint32_t sample_rate) {
    set_sample_rate(sample_rate);
}

void DspAmpHead::set_sample_rate(uint32_t sr) {
    sample_rate_ = sr > 0 ? sr : 48000;
    const double nyq = static_cast<double>(sample_rate_) * 0.5;
    IirFilter::design_butter2_high(80.0 / nyq, lowcut_, true);
    bass_filter_.reset_state();
    mid_filter_.reset_state();
    treble_filter_.reset_state();
    presence_filter_.reset_state();
}

void DspAmpHead::reset() {
    lowcut_.reset_state();
    bass_filter_.reset_state();
    mid_filter_.reset_state();
    treble_filter_.reset_state();
    presence_filter_.reset_state();
}

void DspAmpHead::set_params(float gain, float bass, float mid, float treble, float presence, float master, bool bright, bool enabled) noexcept {
    gain_ = gain;
    bass_ = bass;
    mid_ = mid;
    treble_ = treble;
    presence_ = presence;
    master_ = master;
    bright_ = bright;
    enabled_ = enabled;
}

void DspAmpHead::process(const float* in, float* out, std::size_t n) noexcept {
    if (!enabled_ || n == 0) {
        if (in != out) {
            std::copy(in, in + n, out);
        }
        return;
    }

    const double nyq = static_cast<double>(sample_rate_) * 0.5;
    const double bass_gain_db = (static_cast<double>(bass_) - 0.5) * 24.0;
    const double mid_gain_db = (static_cast<double>(mid_) - 0.5) * 18.0;
    const double treble_gain_db = (static_cast<double>(treble_) - 0.5) * 22.0;
    const double presence_gain_db = (static_cast<double>(presence_) - 0.5) * 15.0;

    // Update coefficients without resetting filter states (F2 fix parity)
    IirFilter::design_amp_shelf1(150.0 / nyq, bass_gain_db, true, bass_filter_);
    IirFilter::design_amp_peak2(800.0 / nyq, mid_gain_db, 1.0, mid_filter_);
    IirFilter::design_amp_shelf1(3500.0 / nyq, treble_gain_db, false, treble_filter_);
    IirFilter::design_amp_shelf1(5500.0 / nyq, presence_gain_db, false, presence_filter_);

    const double pre_gain = 1.0 + std::pow(static_cast<double>(gain_), 2.2) * 60.0;
    const double dc_bias = 0.15 * std::min(static_cast<double>(gain_), 0.8);
    const double dc_bias_tanh = std::tanh(dc_bias * 1.8);
    const double power_mult = 0.8 + static_cast<double>(master_) * 0.7;
    const double master_out_mult = static_cast<double>(master_) * 1.2;

    // First pass: lowcut filter across block (so bright switch can match np.roll(x, 1) if needed)
    std::vector<double> x_vec(n);
    for (std::size_t i = 0; i < n; ++i) {
        x_vec[i] = lowcut_.process_sample(static_cast<double>(in[i]));
    }

    if (bright_ && n > 0) {
        const double last_val = x_vec[n - 1];
        for (std::size_t i = n - 1; i > 0; --i) {
            x_vec[i] = x_vec[i] + 0.35 * (x_vec[i] - x_vec[i - 1]);
        }
        x_vec[0] = x_vec[0] + 0.35 * (x_vec[0] - last_val);
    }

    for (std::size_t i = 0; i < n; ++i) {
        const double x = x_vec[i];
        const double s1 = std::tanh(x * pre_gain);
        const double s2 = std::tanh((s1 + dc_bias) * 1.8) - dc_bias_tanh;
        const double pd = std::clamp(s2 * power_mult, -1.2, 1.2);
        const double s3 = (3.0 * pd - pd * pd * pd) * 0.5;

        double y = bass_filter_.process_sample(s3);
        y = mid_filter_.process_sample(y);
        y = treble_filter_.process_sample(y);
        y = presence_filter_.process_sample(y);

        out[i] = static_cast<float>(y * master_out_mult);
    }
}

// ---------------------------------------------------------------------------
// DspPartitionedConvolver (exact parity with engine/convolver.py)
// ---------------------------------------------------------------------------

DspPartitionedConvolver::DspPartitionedConvolver(const std::vector<float>& ir, std::size_t block_size) {
    set_ir(ir, block_size);
}

void DspPartitionedConvolver::set_ir(const std::vector<float>& ir, std::size_t block_size) {
    B_ = block_size > 0 ? block_size : 128;
    const std::size_t ir_len = std::max<std::size_t>(1, ir.size());
    P_ = (ir_len + B_ - 1) / B_;
    M_ = P_ - 1;

    ir_padded_.assign(P_ * B_, 0.0);
    for (std::size_t i = 0; i < ir.size(); ++i) {
        ir_padded_[i] = static_cast<double>(ir[i]);
    }

    xb_.assign(B_, 0.0);
    f_.assign(B_, 0.0);
    c_.assign(B_, 0.0);
    hist_blocks_.assign(M_ * B_, 0.0);
    pos_ = 0;
    w_ = 0;
}

void DspPartitionedConvolver::reset() noexcept {
    std::fill(xb_.begin(), xb_.end(), 0.0);
    std::fill(f_.begin(), f_.end(), 0.0);
    std::fill(c_.begin(), c_.end(), 0.0);
    std::fill(hist_blocks_.begin(), hist_blocks_.end(), 0.0);
    pos_ = 0;
    w_ = 0;
}

void DspPartitionedConvolver::process(const float* in, float* out, std::size_t n) noexcept {
    std::size_t i = 0;
    while (i < n) {
        const std::size_t pos = pos_;
        const std::size_t m = std::min(n - i, B_ - pos);
        for (std::size_t k = 0; k < m; ++k) {
            xb_[pos + k] = static_cast<double>(in[i + k]);
        }
        // Direct convolution of xb_[0 .. pos + m - 1] with partition 0 (h0 = ir_padded_[0 .. B_-1])
        for (std::size_t k = 0; k < m; ++k) {
            const std::size_t idx = pos + k;
            double sum = 0.0;
            for (std::size_t j = 0; j <= idx; ++j) {
                sum += xb_[idx - j] * ir_padded_[j];
            }
            out[i + k] = static_cast<float>(sum + f_[idx] + c_[idx]);
        }
        i += m;
        pos_ = pos + m;
        if (pos_ == B_) {
            complete_block();
            pos_ = 0;
        }
    }
}

void DspPartitionedConvolver::complete_block() noexcept {
    // 1. Tail of current block xb_ with h0, plus second half of U (from previous history)
    std::vector<double> c_new(B_, 0.0);
    for (std::size_t k = 0; k < B_; ++k) {
        const std::size_t n_idx = B_ + k;
        double sum = 0.0;
        // xb_[i] * h0[n_idx - i] for i in [k + 1 .. B_ - 1]
        for (std::size_t i = k + 1; i < B_; ++i) {
            sum += xb_[i] * ir_padded_[n_idx - i];
        }
        // Add second half [B_ .. 2B_-1] of previous partitions' convolutions stored in hist_blocks_
        for (std::size_t p = 1; p <= M_; ++p) {
            const std::size_t slot = (w_ + M_ - p) % M_;
            const double* x_old = &hist_blocks_[slot * B_];
            const double* hp = &ir_padded_[p * B_];
            for (std::size_t i = k + 1; i < B_; ++i) {
                sum += x_old[i] * hp[n_idx - i];
            }
        }
        c_new[k] = sum;
    }
    c_ = std::move(c_new);

    // 2. Push current xb_ into history ring and compute f_ (first half [0 .. B_-1] of later partitions)
    if (M_ > 0) {
        std::copy(xb_.begin(), xb_.end(), &hist_blocks_[w_ * B_]);
        w_ = (w_ + 1) % M_;

        std::fill(f_.begin(), f_.end(), 0.0);
        for (std::size_t p = 1; p <= M_; ++p) {
            const std::size_t slot = (w_ + M_ - p) % M_;
            const double* x_old = &hist_blocks_[slot * B_];
            const double* hp = &ir_padded_[p * B_];
            for (std::size_t k = 0; k < B_; ++k) {
                double sum = 0.0;
                for (std::size_t i = 0; i <= k; ++i) {
                    sum += x_old[k - i] * hp[i];
                }
                f_[k] += sum;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// DspCabinetSimulator (exact parity with engine/dsp.py :: CabinetSimulator)
// ---------------------------------------------------------------------------

DspCabinetSimulator::DspCabinetSimulator(uint32_t sample_rate)
    : sample_rate_(sample_rate > 0 ? sample_rate : 48000),
      conv_({1.0f, 0.0f}, 128) {
    design_cutoffs();
    design_tube_mic_filters();
}

void DspCabinetSimulator::set_ir_data(const std::vector<float>& ir) {
    conv_.set_ir(ir, 128);
    design_cutoffs();
}

void DspCabinetSimulator::set_cutoffs(float lowcut_hz, float highcut_hz) noexcept {
    lowcut_hz_ = lowcut_hz;
    highcut_hz_ = highcut_hz;
    design_cutoffs();
}

void DspCabinetSimulator::set_params(float level, float mix, float center, float distance, bool enabled) noexcept {
    level_ = level;
    mix_ = std::clamp(mix, 0.0f, 1.0f);
    const bool rebuild_mic = (std::fabs(center - center_) > 1e-4f || std::fabs(distance - distance_) > 1e-4f);
    center_ = center;
    distance_ = distance;
    enabled_ = enabled;
    if (rebuild_mic) {
        design_tube_mic_filters();
    }
}

void DspCabinetSimulator::reset() noexcept {
    conv_.reset();
    hp_filter_.reset_state();
    lp_filter_.reset_state();
    for (auto& s : tube_mic_sections_) {
        s.reset_state();
    }
}

void DspCabinetSimulator::design_cutoffs() noexcept {
    const double nyq = static_cast<double>(sample_rate_) * 0.5;
    const double low = std::min(std::max(static_cast<double>(lowcut_hz_), 10.0), nyq * 0.90);
    const double high = std::min(std::max(static_cast<double>(highcut_hz_), low * 1.5), nyq * 0.95);
    IirFilter::design_butter2_high(low / nyq, hp_filter_, true);
    IirFilter::design_butter2_low(high / nyq, lp_filter_, true);
}

void DspCabinetSimulator::design_tube_mic_filters() noexcept {
    std::vector<IirFilter> next;
    const double sr = static_cast<double>(sample_rate_);

    // Default SM57 voicing (matches CabinetSimulator._design_tube_mic_filters when tube="OFF", mic="SM57")
    {
        IirFilter f1{}, f2{};
        IirFilter::design_peaking_biquad(3800.0, 4.0, 1.6, sr, f1);
        IirFilter::design_peaking_biquad(85.0, -2.0, 0.7, sr, f2);
        next.push_back(f1);
        next.push_back(f2);
    }

    const double center_norm = std::clamp(static_cast<double>(center_), 0.0, 100.0) / 100.0;
    if (center_norm > 0.05) {
        IirFilter fc{};
        IirFilter::design_peaking_biquad(5000.0, -center_norm * 7.0, 0.8, sr, fc);
        next.push_back(fc);
    }

    const double dist_norm = std::clamp(static_cast<double>(distance_), 0.0, 100.0) / 100.0;
    const double prox_db = 3.0 - dist_norm * 4.5;
    if (std::fabs(prox_db) > 0.1) {
        IirFilter fd{};
        IirFilter::design_peaking_biquad(120.0, prox_db, 0.7, sr, fd);
        next.push_back(fd);
    }

    if (tube_mic_sections_.size() == next.size()) {
        for (std::size_t i = 0; i < next.size(); ++i) {
            next[i].z1 = tube_mic_sections_[i].z1;
            next[i].z2 = tube_mic_sections_[i].z2;
        }
    }
    tube_mic_sections_ = std::move(next);
}

void DspCabinetSimulator::process(const float* in, float* out, std::size_t n) noexcept {
    if (!enabled_) {
        conv_dirty_ = true;
        if (in != out) {
            std::copy(in, in + n, out);
        }
        return;
    }

    if (conv_dirty_) {
        conv_.reset();
        conv_dirty_ = false;
    }

    std::vector<float> wet_f(n);
    conv_.process(in, wet_f.data(), n);

    for (std::size_t i = 0; i < n; ++i) {
        double w = hp_filter_.process_sample(static_cast<double>(wet_f[i]));
        w = lp_filter_.process_sample(w);
        for (auto& sec : tube_mic_sections_) {
            w = sec.process_sample(w);
        }
        w *= static_cast<double>(level_);
        if (mix_ >= 0.999f) {
            out[i] = static_cast<float>(w);
        } else {
            out[i] = static_cast<float>(static_cast<double>(in[i]) * (1.0 - mix_) + w * mix_);
        }
    }
}

// ---------------------------------------------------------------------------
// DspOverdrive (MOOER GE150 / TS-808 Asymmetric Tube Screamer Overdrive)
// ---------------------------------------------------------------------------

DspOverdrive::DspOverdrive(uint32_t sample_rate)
    : sample_rate_(sample_rate > 0 ? sample_rate : 48000) {
    set_params(drive_, tone_, level_, enabled_);
}

void DspOverdrive::set_params(float drive, float tone, float level, bool enabled) noexcept {
    drive_ = std::clamp(drive, 0.0f, 1.0f);
    const bool tone_changed = std::fabs(tone - tone_) > 1e-5f || tone_filter_.order == 0;
    tone_ = std::clamp(tone, 0.0f, 1.0f);
    level_ = std::clamp(level, 0.0f, 1.0f);
    enabled_ = enabled;
    if (tone_changed) {
        const double cutoff = 800.0 + static_cast<double>(tone_) * 3500.0;
        const double nyq = static_cast<double>(sample_rate_) * 0.5;
        const double norm_cutoff = std::min(std::max(cutoff / nyq, 0.01), 0.95);
        IirFilter::design_butter1_low(norm_cutoff, tone_filter_, true);
    }
}

void DspOverdrive::process(const float* in, float* out, std::size_t n) noexcept {
    if (!enabled_) {
        if (in != out) std::copy(in, in + n, out);
        return;
    }
    const double gain = 1.0 + static_cast<double>(drive_ * drive_) * 39.0;
    const double out_gain = static_cast<double>(level_) * 1.5;
    for (std::size_t i = 0; i < n; ++i) {
        const double x = static_cast<double>(in[i]) * gain;
        const double y_clip = (x > 0.0) ? (std::tanh(x * 1.2) * 0.85) : (std::tanh(x * 0.9) * 0.95);
        const double y_filt = tone_filter_.process_sample(y_clip);
        out[i] = static_cast<float>(y_filt * out_gain);
    }
}

// ---------------------------------------------------------------------------
// DspStereoDoubler (Neural DSP Archetype Petrucci / Plini Stereo Haas Widener)
// ---------------------------------------------------------------------------

DspStereoDoubler::DspStereoDoubler(uint32_t sample_rate)
    : sample_rate_(sample_rate > 0 ? sample_rate : 48000),
      ring_(static_cast<std::size_t>(sample_rate_ / 10), 0.0f) {}

void DspStereoDoubler::set_params(float width_ms, float detune_depth, float mix, bool enabled) noexcept {
    width_ms_ = std::clamp(width_ms, 0.0f, 40.0f);
    detune_depth_ = std::clamp(detune_depth, 0.0f, 1.0f);
    mix_ = std::clamp(mix, 0.0f, 1.0f);
    enabled_ = enabled;
}

void DspStereoDoubler::process_stereo(const float* mono_in, float* left_out, float* right_out, std::size_t n) noexcept {
    if (!enabled_ || width_ms_ <= 0.1f || ring_.empty()) {
        for (std::size_t i = 0; i < n; ++i) {
            left_out[i] = mono_in[i];
            right_out[i] = mono_in[i];
        }
        return;
    }
    const std::size_t cap = ring_.size();
    const double base_samples = (static_cast<double>(width_ms_) * 0.001) * static_cast<double>(sample_rate_);
    const double mod_samples = (0.8 * static_cast<double>(detune_depth_) * 0.001) * static_cast<double>(sample_rate_);
    const double lfo_inc = (2.0 * 3.14159265358979323846 * 0.65) / static_cast<double>(sample_rate_);

    for (std::size_t i = 0; i < n; ++i) {
        const float s = mono_in[i];
        left_out[i] = s;
        ring_[write_pos_] = s;

        const double d = std::clamp(base_samples + mod_samples * std::sin(lfo_phase_), 1.0, static_cast<double>(cap - 2));
        lfo_phase_ += lfo_inc;
        if (lfo_phase_ > 6.283185307179586) lfo_phase_ -= 6.283185307179586;

        const double rpos = static_cast<double>((write_pos_ + cap) % cap) - d;
        const double rwrap = rpos < 0.0 ? (rpos + static_cast<double>(cap)) : rpos;
        const std::size_t idx0 = static_cast<std::size_t>(rwrap) % cap;
        const std::size_t idx1 = (idx0 + 1) % cap;
        const float frac = static_cast<float>(rwrap - std::floor(rwrap));
        const float delayed = ring_[idx0] * (1.0f - frac) + ring_[idx1] * frac;

        right_out[i] = (1.0f - mix_) * s + mix_ * delayed;
        write_pos_ = (write_pos_ + 1) % cap;
    }
}

// ---------------------------------------------------------------------------
// DspDuckingDelay (Quad Cortex Dynamic Ducking Delay)
// ---------------------------------------------------------------------------

DspDuckingDelay::DspDuckingDelay(uint32_t sample_rate)
    : sample_rate_(sample_rate > 0 ? sample_rate : 48000),
      buffer_(static_cast<std::size_t>(sample_rate_ * 2), 0.0f) {}

void DspDuckingDelay::set_params(float time_sec, float feedback, float mix, bool ducking, float duck_depth, bool enabled) noexcept {
    time_sec_ = std::clamp(time_sec, 0.01f, 1.95f);
    feedback_ = std::clamp(feedback, 0.0f, 0.95f);
    mix_ = std::clamp(mix, 0.0f, 1.0f);
    ducking_ = ducking;
    duck_depth_ = std::clamp(duck_depth, 0.0f, 0.95f);
    enabled_ = enabled;
}

void DspDuckingDelay::process(const float* in, float* out, std::size_t n) noexcept {
    if (!enabled_ || mix_ <= 0.001f || buffer_.empty()) {
        if (in != out) std::copy(in, in + n, out);
        return;
    }
    const std::size_t max_samples = buffer_.size();
    const std::size_t delay_samples = std::clamp<std::size_t>(
        static_cast<std::size_t>(time_sec_ * static_cast<float>(sample_rate_)), 1, max_samples - 1);

    double sum_sq = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        sum_sq += static_cast<double>(in[i]) * static_cast<double>(in[i]);
    }
    const float rms = static_cast<float>(std::sqrt(sum_sq / static_cast<double>(n > 0 ? n : 1) + 1e-9));
    if (ducking_) {
        const float target_duck = (rms > 0.035f) ? std::max(0.05f, 1.0f - duck_depth_) : 1.0f;
        duck_gain_ = duck_gain_ * 0.88f + target_duck * 0.12f;
    } else {
        duck_gain_ = 1.0f;
    }

    for (std::size_t i = 0; i < n; ++i) {
        const float x = in[i];
        const std::size_t r_idx = (write_pos_ + max_samples - delay_samples) % max_samples;
        const float delayed = buffer_[r_idx];
        buffer_[write_pos_] = x + delayed * feedback_;
        write_pos_ = (write_pos_ + 1) % max_samples;
        const float wet = delayed * duck_gain_;
        out[i] = (1.0f - mix_) * x + mix_ * wet;
    }
}

namespace {
uint32_t calc_nam_crc32(const uint8_t* data, size_t length) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1));
        }
    }
    return ~crc;
}
} // namespace

DspNamEngine::DspNamEngine() = default;

DspNamEngine::~DspNamEngine() {
#ifdef _WIN32
    if (dll_handle_) {
        FreeLibrary(reinterpret_cast<HMODULE>(dll_handle_));
        dll_handle_ = nullptr;
    }
#endif
}

bool DspNamEngine::load_dll(const char* dll_path) {
#ifdef _WIN32
    if (dll_handle_) {
        return true;
    }
    const char* candidates[] = {
        dll_path,
        "engine/nam_c99.dll",
        "../../engine/nam_c99.dll",
        "../engine/nam_c99.dll",
        "nam_c99.dll"
    };
    HMODULE h = nullptr;
    for (const char* path : candidates) {
        if (!path) continue;
        h = LoadLibraryA(path);
        if (h) break;
    }
    if (!h) {
        return false;
    }
    dll_handle_ = reinterpret_cast<void*>(h);
    fn_load_ = reinterpret_cast<FnLoad>(GetProcAddress(h, "nam_dll_load"));
    fn_reset_ = reinterpret_cast<FnReset>(GetProcAddress(h, "nam_dll_reset"));
    fn_process_ = reinterpret_cast<FnProcess>(GetProcAddress(h, "nam_dll_process"));
    fn_model_ = reinterpret_cast<FnModel>(GetProcAddress(h, "nam_dll_model"));
    fn_model_name_ = reinterpret_cast<FnModelName>(GetProcAddress(h, "nam_dll_model_name"));

    if (!fn_load_ || !fn_reset_ || !fn_process_) {
        FreeLibrary(h);
        dll_handle_ = nullptr;
        fn_load_ = nullptr;
        fn_reset_ = nullptr;
        fn_process_ = nullptr;
        return false;
    }
    return true;
#else
    return false;
#endif
}

bool DspNamEngine::load_model_binary(const void* buf, uint32_t size, std::string* error_out) {
    if (!dll_handle_ && !load_dll()) {
        if (error_out) *error_out = "Failed to load nam_c99.dll";
        return false;
    }
    const char* err = nullptr;
    const int rc = fn_load_(buf, size, 0, &err);
    if (rc != 0) {
        if (error_out) *error_out = err ? err : "nam_dll_load failed";
        is_loaded_ = false;
        return false;
    }
    is_loaded_ = true;
    if (fn_model_name_) {
        const char* name = fn_model_name_();
        if (name) model_name_ = name;
    }
    return true;
}

bool DspNamEngine::load_weights(const float* weights, std::size_t weight_count, double sample_rate, double loudness, std::string* error_out) {
    if (!dll_handle_ && !load_dll()) {
        if (error_out) *error_out = "Failed to load nam_c99.dll";
        return false;
    }

    const char* template_paths[] = {
        (weight_count == 1871) ? "engine/a2lite_template.bin" : "engine/a2full_template.bin",
        (weight_count == 1871) ? "../../engine/a2lite_template.bin" : "../../engine/a2full_template.bin",
        (weight_count == 1871) ? "../engine/a2lite_template.bin" : "../engine/a2full_template.bin"
    };

    std::vector<uint8_t> hdr;
    for (const char* tpath : template_paths) {
        std::ifstream f(tpath, std::ios::binary | std::ios::ate);
        if (f.is_open()) {
            std::streamsize sz = f.tellg();
            f.seekg(0, std::ios::beg);
            hdr.resize(static_cast<std::size_t>(sz));
            f.read(reinterpret_cast<char*>(hdr.data()), sz);
            break;
        }
    }

    if (hdr.size() < 496) {
        if (error_out) *error_out = "Cannot find template binary for weight count " + std::to_string(weight_count);
        return false;
    }

    const uint32_t weight_bytes = static_cast<uint32_t>(weight_count * sizeof(float));
    const uint32_t tot_size = static_cast<uint32_t>(hdr.size()) + weight_bytes;
    const uint32_t hdr_len = static_cast<uint32_t>(hdr.size());
    const uint32_t count = static_cast<uint32_t>(weight_count);

    std::memcpy(&hdr[8], &tot_size, 4);
    std::memcpy(&hdr[12], &hdr_len, 4);
    std::memcpy(&hdr[16], &count, 4);
    std::memcpy(&hdr[36], &sample_rate, 8);
    std::memcpy(&hdr[44], &loudness, 8);
    const uint32_t zero = 0;
    std::memcpy(&hdr[24], &zero, 4);

    std::vector<uint8_t> body(tot_size);
    std::memcpy(body.data(), hdr.data(), hdr.size());
    std::memcpy(body.data() + hdr.size(), weights, weight_bytes);

    std::vector<uint8_t> crc_buf;
    crc_buf.reserve(tot_size - 4);
    crc_buf.insert(crc_buf.end(), body.begin(), body.begin() + 24);
    crc_buf.insert(crc_buf.end(), body.begin() + 28, body.end());
    const uint32_t crc = calc_nam_crc32(crc_buf.data(), crc_buf.size());
    std::memcpy(&body[24], &crc, 4);

    return load_model_binary(body.data(), tot_size, error_out);
}

void DspNamEngine::reset() noexcept {
    if (fn_reset_) {
        fn_reset_();
    }
}

void DspNamEngine::process(const float* in, float* out, std::size_t n) noexcept {
    if (!is_loaded_ || !enabled_ || !fn_process_) {
        if (in != out) {
            std::memcpy(out, in, n * sizeof(float));
        }
        return;
    }
    std::size_t processed = 0;
    while (processed < n) {
        const std::size_t chunk = std::min<std::size_t>(512, n - processed);
        fn_process_(in + processed, out + processed, static_cast<int>(chunk));
        processed += chunk;
    }
}

} // namespace hack_effect
