#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace hack_effect {

/**
 * Single-Producer Single-Consumer (SPSC) lock-free ring buffer.
 * Used to pass parameter/scene/bypass updates from the IPC thread to the
 * real-time audio callback without locks or dynamic memory allocation.
 */
template <typename T, std::size_t Capacity>
class SpscRingBuffer {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be a power of two");

public:
    SpscRingBuffer() = default;

    bool push(const T& item) noexcept {
        const std::size_t w = write_idx_.load(std::memory_order_relaxed);
        const std::size_t next_w = (w + 1) & kMask;
        if (next_w == read_idx_.load(std::memory_order_acquire)) {
            return false; // Queue full
        }
        buffer_[w] = item;
        write_idx_.store(next_w, std::memory_order_release);
        return true;
    }

    bool pop(T& out_item) noexcept {
        const std::size_t r = read_idx_.load(std::memory_order_relaxed);
        if (r == write_idx_.load(std::memory_order_acquire)) {
            return false; // Queue empty
        }
        out_item = buffer_[r];
        read_idx_.store((r + 1) & kMask, std::memory_order_release);
        return true;
    }

    void clear() noexcept {
        T dummy{};
        while (pop(dummy)) {}
    }

private:
    static constexpr std::size_t kMask = Capacity - 1;
    alignas(64) std::atomic<std::size_t> write_idx_{0};
    alignas(64) std::atomic<std::size_t> read_idx_{0};
    T buffer_[Capacity]{};
};

} // namespace hack_effect
