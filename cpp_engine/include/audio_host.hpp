#pragma once

#include "asio_driver.hpp"
#include "dsp_blocks.hpp"
#include "metrics.hpp"
#include "param_registry.hpp"
#include "spsc_queue.hpp"

#include <array>
#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace hack_effect {

enum class ControlCommandType : uint8_t {
    SetParam = 0,
    SetGlobalBypass = 1,
    SetScene = 2
};

struct ControlCommand {
    ControlCommandType type{ControlCommandType::SetParam};
    uint16_t param_id{0};
    float normalized{0.0f};
    float value{0.0f};
    uint8_t scene_index{0};
    bool bypass{false};
};

struct SceneSlot {
    uint8_t index{0};
    std::string label;
    std::string color_hex;
    // Per-parameter override: (param_id, engineering_value)
    std::vector<std::pair<uint16_t, float>> overrides;
};

struct AudioDeviceInfo {
    int id{-1};
    std::string name;
    std::string backend;
    int max_inputs{0};
    int max_outputs{0};
    uint32_t default_sample_rate{48000};
};

class AudioHost {
public:
    static constexpr std::size_t kMaxParams = 64;
    static constexpr std::size_t kNumScenes = 8;

    AudioHost();
    ~AudioHost();

    AudioHost(const AudioHost&) = delete;
    AudioHost& operator=(const AudioHost&) = delete;

    bool start(uint32_t sample_rate = 48000,
               uint32_t buffer_size = 128,
               const std::string& backend_pref = "auto",
               int input_device_id = -1,
               int output_device_id = -1);

    void stop();

    bool is_running() const noexcept { return running_.load(std::memory_order_acquire); }
    uint32_t sample_rate() const noexcept { return sample_rate_.load(std::memory_order_relaxed); }
    uint32_t buffer_size() const noexcept { return buffer_size_.load(std::memory_order_relaxed); }
    std::string active_backend() const;

    // Control API (called from IPC/UI thread, pushes into lock-free SPSC queue)
    bool set_param_normalized(std::string_view block, std::string_view param, float norm_val, ParamValue* out_applied = nullptr);
    bool set_param_value(std::string_view block, std::string_view param, float eng_val, ParamValue* out_applied = nullptr);
    void set_global_bypass(bool bypass);
    bool global_bypass() const noexcept { return global_bypass_.load(std::memory_order_acquire); }
    bool set_scene(uint8_t scene_index);
    uint8_t active_scene() const noexcept { return active_scene_.load(std::memory_order_acquire); }

    std::vector<ParamValue> get_all_params() const;
    std::vector<SceneSlot> get_scenes() const;
    std::vector<AudioDeviceInfo> enumerate_devices() const;

    MetricsSnapshot metrics_snapshot() const { return metrics_.snapshot(); }
    void reset_metrics() noexcept { metrics_.reset(); }

    DspNamEngine& nam_engine() noexcept { return dsp_nam_; }
    void set_use_nam(bool use_nam) noexcept { use_nam_.store(use_nam, std::memory_order_release); }
    bool is_using_nam() const noexcept { return use_nam_.load(std::memory_order_acquire); }

    // Exposed for deterministic offline/unit testing of callback behavior
    void process_block(const float* mono_in, float* stereo_out, uint32_t frames,
                       uint32_t in_underflow = 0, uint32_t out_underflow = 0) noexcept;

private:
    void drain_control_queue() noexcept;
    void init_default_scenes();
    void run_realtime_pacer_loop();
    bool try_start_asio(uint32_t sr, uint32_t bs);
    bool try_start_wasapi(uint32_t sr, uint32_t bs);

    mutable std::mutex state_mutex_; // Protects non-RT metadata (backend string, scene definitions)
    std::string active_backend_{"stopped"};

    std::atomic<bool> running_{false};
    std::atomic<bool> stop_requested_{false};
    std::atomic<uint32_t> sample_rate_{48000};
    std::atomic<uint32_t> buffer_size_{128};
    std::atomic<bool> global_bypass_{true};
    std::atomic<uint8_t> active_scene_{0};

    // Lock-free parameter storage shared between control plane and audio callback
    std::array<std::atomic<float>, kMaxParams> param_values_{};
    std::array<std::atomic<float>, kMaxParams> param_normalized_{};

    // Audio thread internal smoothed state (owned strictly by audio thread)
    float smooth_input_gain_{1.0f};
    float smooth_master_gain_{1.0f};
    float smooth_bypass_mix_{1.0f}; // 1.0 = active, 0.0 = muted
    float smooth_coeff_{0.99f};

    DspAmpHead dsp_amp_{48000};
    DspCabinetSimulator dsp_cab_{48000};
    DspOverdrive dsp_screamer_{48000};
    DspStereoDoubler dsp_doubler_{48000};
    DspDuckingDelay dsp_delay_{48000};
    DspNamEngine dsp_nam_{};
    std::atomic<bool> use_nam_{false};
    std::vector<float> dsp_scratch_{};

    AsioDriverHost asio_host_{};

    SpscRingBuffer<ControlCommand, 256> cmd_queue_{};
    MetricsCollector metrics_{};
    std::array<SceneSlot, kNumScenes> scenes_{};

    std::thread audio_thread_;
};

} // namespace hack_effect
