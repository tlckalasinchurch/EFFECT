#include "metrics.hpp"

#include <algorithm>
#include <cmath>
#include <vector>

namespace hack_effect {

namespace {
float linear_to_dbfs(float peak) noexcept {
    if (peak <= 1e-6f || !std::isfinite(peak)) {
        return -120.0f;
    }
    return 20.0f * std::log10(peak);
}

double compute_percentile(const std::vector<float>& sorted, double pct) noexcept {
    if (sorted.empty()) return 0.0;
    if (sorted.size() == 1) return static_cast<double>(sorted[0]);
    const double idx = (pct / 100.0) * static_cast<double>(sorted.size() - 1);
    const std::size_t lo = static_cast<std::size_t>(std::floor(idx));
    const std::size_t hi = static_cast<std::size_t>(std::ceil(idx));
    const double frac = idx - static_cast<double>(lo);
    return static_cast<double>(sorted[lo]) * (1.0 - frac) + static_cast<double>(sorted[hi]) * frac;
}
} // namespace

MetricsCollector::MetricsCollector() {
    reset();
}

void MetricsCollector::configure(uint32_t sample_rate, uint32_t buffer_size) noexcept {
    sample_rate_.store(sample_rate > 0 ? sample_rate : 48000, std::memory_order_relaxed);
    buffer_size_.store(buffer_size > 0 ? buffer_size : 128, std::memory_order_relaxed);
    reset();
}

void MetricsCollector::reset() noexcept {
    callback_count_.store(0, std::memory_order_relaxed);
    ring_pos_.store(0, std::memory_order_relaxed);
    ring_count_.store(0, std::memory_order_relaxed);
    for (auto& slot : ms_ring_) {
        slot.store(0.0f, std::memory_order_relaxed);
    }
    max_ms_.store(0.0, std::memory_order_relaxed);
    warmup_max_ms_.store(0.0, std::memory_order_relaxed);
    avg_ms_.store(0.0, std::memory_order_relaxed);
    window_sum_ms_ = 0.0;
    window_blocks_ = 0;

    over_half_deadline_blocks_.store(0, std::memory_order_relaxed);
    over_deadline_blocks_.store(0, std::memory_order_relaxed);
    nonfinite_blocks_.store(0, std::memory_order_relaxed);
    clipped_blocks_.store(0, std::memory_order_relaxed);
    callback_errors_.store(0, std::memory_order_relaxed);

    input_underflow_.store(0, std::memory_order_relaxed);
    input_overflow_.store(0, std::memory_order_relaxed);
    output_underflow_.store(0, std::memory_order_relaxed);
    output_overflow_.store(0, std::memory_order_relaxed);

    input_peak_linear_.store(0.0f, std::memory_order_relaxed);
    output_peak_linear_.store(0.0f, std::memory_order_relaxed);
}

void MetricsCollector::record_callback(double elapsed_ms,
                                       float in_peak,
                                       float out_peak,
                                       bool had_nonfinite,
                                       bool had_clip,
                                       uint32_t in_underflow,
                                       uint32_t in_overflow,
                                       uint32_t out_underflow,
                                       uint32_t out_overflow) noexcept {
    if (in_underflow) input_underflow_.fetch_add(in_underflow, std::memory_order_relaxed);
    if (in_overflow) input_overflow_.fetch_add(in_overflow, std::memory_order_relaxed);
    if (out_underflow) output_underflow_.fetch_add(out_underflow, std::memory_order_relaxed);
    if (out_overflow) output_overflow_.fetch_add(out_overflow, std::memory_order_relaxed);

    if (had_nonfinite) {
        nonfinite_blocks_.fetch_add(1, std::memory_order_relaxed);
    }
    if (had_clip) {
        clipped_blocks_.fetch_add(1, std::memory_order_relaxed);
    }

    // Smooth peak meters with ballistic decay so 60fps UI gets natural VU motion
    const float prev_in = input_peak_linear_.load(std::memory_order_relaxed);
    const float next_in = std::max(in_peak, prev_in * 0.92f);
    input_peak_linear_.store(next_in, std::memory_order_relaxed);

    const float prev_out = output_peak_linear_.load(std::memory_order_relaxed);
    const float next_out = std::max(out_peak, prev_out * 0.92f);
    output_peak_linear_.store(next_out, std::memory_order_relaxed);

    const uint64_t cb_num = callback_count_.fetch_add(1, std::memory_order_relaxed) + 1;
    if (cb_num <= kWarmupCallbacks) {
        double cur_warm = warmup_max_ms_.load(std::memory_order_relaxed);
        if (elapsed_ms > cur_warm) {
            warmup_max_ms_.store(elapsed_ms, std::memory_order_relaxed);
        }
        return;
    }

    double cur_max = max_ms_.load(std::memory_order_relaxed);
    if (elapsed_ms > cur_max) {
        max_ms_.store(elapsed_ms, std::memory_order_relaxed);
    }

    const uint32_t sr = sample_rate_.load(std::memory_order_relaxed);
    const uint32_t bs = buffer_size_.load(std::memory_order_relaxed);
    const double deadline = (static_cast<double>(bs) / static_cast<double>(sr)) * 1000.0;

    if (elapsed_ms > deadline) {
        over_deadline_blocks_.fetch_add(1, std::memory_order_relaxed);
    }
    if (elapsed_ms > deadline * 0.5) {
        over_half_deadline_blocks_.fetch_add(1, std::memory_order_relaxed);
    }

    const uint64_t pos = ring_pos_.fetch_add(1, std::memory_order_relaxed) % kRingSize;
    ms_ring_[pos].store(static_cast<float>(elapsed_ms), std::memory_order_relaxed);

    const uint64_t cnt = ring_count_.load(std::memory_order_relaxed);
    if (cnt < kRingSize) {
        ring_count_.store(cnt + 1, std::memory_order_release);
    }

    window_sum_ms_ += elapsed_ms;
    window_blocks_ += 1;
    if (window_blocks_ >= kWindowBlocks) {
        avg_ms_.store(window_sum_ms_ / static_cast<double>(window_blocks_), std::memory_order_relaxed);
        window_sum_ms_ = 0.0;
        window_blocks_ = 0;
    }
}

MetricsSnapshot MetricsCollector::snapshot() const {
    MetricsSnapshot s{};
    const uint32_t sr = sample_rate_.load(std::memory_order_relaxed);
    const uint32_t bs = buffer_size_.load(std::memory_order_relaxed);
    s.deadline_ms = (static_cast<double>(bs) / static_cast<double>(sr)) * 1000.0;
    s.callback_count = callback_count_.load(std::memory_order_relaxed);

    const uint64_t count = std::min<uint64_t>(ring_count_.load(std::memory_order_acquire), kRingSize);
    s.percentile_blocks = count;

    if (count > 0) {
        std::vector<float> samples;
        samples.reserve(static_cast<std::size_t>(count));
        double sum = 0.0;
        for (uint64_t i = 0; i < count; ++i) {
            const float v = ms_ring_[static_cast<std::size_t>(i)].load(std::memory_order_relaxed);
            samples.push_back(v);
            sum += static_cast<double>(v);
        }
        std::sort(samples.begin(), samples.end());
        s.p50_ms = compute_percentile(samples, 50.0);
        s.p95_ms = compute_percentile(samples, 95.0);
        s.p99_ms = compute_percentile(samples, 99.0);
        s.p99_9_ms = compute_percentile(samples, 99.9);

        const double win_avg = avg_ms_.load(std::memory_order_relaxed);
        s.avg_ms = (win_avg > 0.0) ? win_avg : (sum / static_cast<double>(count));
    }

    s.max_ms = max_ms_.load(std::memory_order_relaxed);
    s.warmup_max_ms = warmup_max_ms_.load(std::memory_order_relaxed);

    s.over_half_deadline_blocks = over_half_deadline_blocks_.load(std::memory_order_relaxed);
    s.over_deadline_blocks = over_deadline_blocks_.load(std::memory_order_relaxed);
    s.nonfinite_blocks = nonfinite_blocks_.load(std::memory_order_relaxed);
    s.clipped_blocks = clipped_blocks_.load(std::memory_order_relaxed);
    s.callback_errors = callback_errors_.load(std::memory_order_relaxed);

    s.input_underflow = input_underflow_.load(std::memory_order_relaxed);
    s.input_overflow = input_overflow_.load(std::memory_order_relaxed);
    s.output_underflow = output_underflow_.load(std::memory_order_relaxed);
    s.output_overflow = output_overflow_.load(std::memory_order_relaxed);

    s.input_peak_linear = input_peak_linear_.load(std::memory_order_relaxed);
    s.output_peak_linear = output_peak_linear_.load(std::memory_order_relaxed);
    s.input_dbfs = linear_to_dbfs(s.input_peak_linear);
    s.output_dbfs = linear_to_dbfs(s.output_peak_linear);

    const uint64_t total_xruns = s.input_underflow + s.input_overflow + s.output_underflow + s.output_overflow;
    s.xrun_zero = (total_xruns == 0);
    s.p99_under_50pct = (count == 0) || (s.p99_ms < s.deadline_ms * 0.50);
    s.p99_9_under_80pct = (count == 0) || (s.p99_9_ms < s.deadline_ms * 0.80);
    s.finite_clean = (s.nonfinite_blocks == 0 && s.callback_errors == 0);
    s.passed_phase1_gate = s.xrun_zero && s.p99_under_50pct && s.p99_9_under_80pct && s.finite_clean;

    return s;
}

} // namespace hack_effect
