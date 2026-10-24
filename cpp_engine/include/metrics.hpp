#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace hack_effect {

struct MetricsSnapshot {
    uint64_t callback_count{0};
    uint64_t percentile_blocks{0};
    double deadline_ms{0.0};
    double avg_ms{0.0};
    double max_ms{0.0};
    double warmup_max_ms{0.0};
    double p50_ms{0.0};
    double p95_ms{0.0};
    double p99_ms{0.0};
    double p99_9_ms{0.0};

    uint64_t over_half_deadline_blocks{0};
    uint64_t over_deadline_blocks{0};
    uint64_t nonfinite_blocks{0};
    uint64_t clipped_blocks{0};
    uint64_t callback_errors{0};

    uint64_t input_underflow{0};
    uint64_t input_overflow{0};
    uint64_t output_underflow{0};
    uint64_t output_overflow{0};

    float input_peak_linear{0.0f};
    float output_peak_linear{0.0f};
    float input_dbfs{-120.0f};
    float output_dbfs{-120.0f};

    bool xrun_zero{true};
    bool p99_under_50pct{true};
    bool p99_9_under_80pct{true};
    bool finite_clean{true};
    bool passed_phase1_gate{true};
};

class MetricsCollector {
public:
    static constexpr std::size_t kRingSize = 8192;
    static constexpr uint64_t kWarmupCallbacks = 50;
    static constexpr std::size_t kWindowBlocks = 500;

    MetricsCollector();

    void configure(uint32_t sample_rate, uint32_t buffer_size) noexcept;
    void reset() noexcept;

    // Called exclusively on the real-time audio callback thread (zero allocation, zero lock)
    void record_callback(double elapsed_ms,
                         float in_peak,
                         float out_peak,
                         bool had_nonfinite,
                         bool had_clip,
                         uint32_t in_underflow = 0,
                         uint32_t in_overflow = 0,
                         uint32_t out_underflow = 0,
                         uint32_t out_overflow = 0) noexcept;

    void record_error() noexcept {
        callback_errors_.fetch_add(1, std::memory_order_relaxed);
    }

    // Called from IPC / telemetry thread
    MetricsSnapshot snapshot() const;

private:
    std::atomic<uint32_t> sample_rate_{48000};
    std::atomic<uint32_t> buffer_size_{128};

    std::atomic<uint64_t> callback_count_{0};
    std::atomic<uint64_t> ring_pos_{0};
    std::atomic<uint64_t> ring_count_{0};
    std::array<std::atomic<float>, kRingSize> ms_ring_{};

    std::atomic<double> max_ms_{0.0};
    std::atomic<double> warmup_max_ms_{0.0};
    std::atomic<double> avg_ms_{0.0};
    double window_sum_ms_{0.0};
    std::size_t window_blocks_{0};

    std::atomic<uint64_t> over_half_deadline_blocks_{0};
    std::atomic<uint64_t> over_deadline_blocks_{0};
    std::atomic<uint64_t> nonfinite_blocks_{0};
    std::atomic<uint64_t> clipped_blocks_{0};
    std::atomic<uint64_t> callback_errors_{0};

    std::atomic<uint64_t> input_underflow_{0};
    std::atomic<uint64_t> input_overflow_{0};
    std::atomic<uint64_t> output_underflow_{0};
    std::atomic<uint64_t> output_overflow_{0};

    std::atomic<float> input_peak_linear_{0.0f};
    std::atomic<float> output_peak_linear_{0.0f};
};

} // namespace hack_effect
