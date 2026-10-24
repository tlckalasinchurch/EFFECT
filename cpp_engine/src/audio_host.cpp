#include "audio_host.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>

#ifdef _WIN32
#include <windows.h>
#include <avrt.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>
#endif

namespace hack_effect {

AudioHost::AudioHost() {
    for (std::size_t i = 0; i < kMaxParams; ++i) {
        param_values_[i].store(0.0f, std::memory_order_relaxed);
        param_normalized_[i].store(0.0f, std::memory_order_relaxed);
    }
    for (const auto& spec : ParamRegistry::specs()) {
        if (spec.id < kMaxParams) {
            const auto pv = ParamRegistry::make_from_value(spec, spec.default_val);
            param_values_[spec.id].store(pv.value, std::memory_order_relaxed);
            param_normalized_[spec.id].store(pv.normalized, std::memory_order_relaxed);
        }
    }
    dsp_scratch_.resize(4096, 0.0f);
    init_default_scenes();
}

AudioHost::~AudioHost() {
    stop();
}

void AudioHost::init_default_scenes() {
    static const char* kLabels[kNumScenes] = {
        "Scene A - Clean Crystal",
        "Scene B - Edge of Breakup",
        "Scene C - Tight Rhythm",
        "Scene D - High-Gain Lead",
        "Scene E - Ambient Swell",
        "Scene F - Pitch Harmony",
        "Scene G - Post-Rock Wash",
        "Scene H - Solo Boost"
    };
    static const char* kColors[kNumScenes] = {
        "#38BDF8", "#F59E0B", "#EF4444", "#F43F5E",
        "#A855F7", "#10B981", "#06B6D4", "#EAB308"
    };

    const auto* drive_en = ParamRegistry::find("screamer", "enabled");
    const auto* amp_gain = ParamRegistry::find("amp", "gain");
    const auto* delay_en = ParamRegistry::find("delay", "enabled");
    const auto* reverb_en = ParamRegistry::find("reverb", "enabled");
    const auto* master_vol = ParamRegistry::find("master", "volume");

    for (std::size_t i = 0; i < kNumScenes; ++i) {
        scenes_[i].index = static_cast<uint8_t>(i);
        scenes_[i].label = kLabels[i];
        scenes_[i].color_hex = kColors[i];
        scenes_[i].overrides.clear();

        if (drive_en) {
            scenes_[i].overrides.push_back({drive_en->id, (i >= 1 && i <= 3) ? 1.0f : 0.0f});
        }
        if (amp_gain) {
            const float g = 0.30f + 0.08f * static_cast<float>(i);
            scenes_[i].overrides.push_back({amp_gain->id, std::min(1.0f, g)});
        }
        if (delay_en) {
            scenes_[i].overrides.push_back({delay_en->id, (i == 3 || i == 4 || i == 6 || i == 7) ? 1.0f : 0.0f});
        }
        if (reverb_en) {
            scenes_[i].overrides.push_back({reverb_en->id, (i == 0 || i >= 4) ? 1.0f : 0.0f});
        }
        if (master_vol) {
            scenes_[i].overrides.push_back({master_vol->id, (i == 7) ? 1.15f : 1.0f});
        }
    }
}

bool AudioHost::set_param_normalized(std::string_view block,
                                     std::string_view param,
                                     float norm_val,
                                     ParamValue* out_applied) {
    const ParamSpec* spec = ParamRegistry::find(block, param);
    if (!spec || spec->id >= kMaxParams || !std::isfinite(norm_val)) {
        return false;
    }
    const ParamValue pv = ParamRegistry::make_from_normalized(*spec, norm_val);
    param_values_[spec->id].store(pv.value, std::memory_order_release);
    param_normalized_[spec->id].store(pv.normalized, std::memory_order_release);

    ControlCommand cmd{};
    cmd.type = ControlCommandType::SetParam;
    cmd.param_id = spec->id;
    cmd.normalized = pv.normalized;
    cmd.value = pv.value;
    cmd_queue_.push(cmd);

    if (out_applied) {
        *out_applied = pv;
    }
    return true;
}

bool AudioHost::set_param_value(std::string_view block,
                                std::string_view param,
                                float eng_val,
                                ParamValue* out_applied) {
    const ParamSpec* spec = ParamRegistry::find(block, param);
    if (!spec || spec->id >= kMaxParams || !std::isfinite(eng_val)) {
        return false;
    }
    const ParamValue pv = ParamRegistry::make_from_value(*spec, eng_val);
    param_values_[spec->id].store(pv.value, std::memory_order_release);
    param_normalized_[spec->id].store(pv.normalized, std::memory_order_release);

    ControlCommand cmd{};
    cmd.type = ControlCommandType::SetParam;
    cmd.param_id = spec->id;
    cmd.normalized = pv.normalized;
    cmd.value = pv.value;
    cmd_queue_.push(cmd);

    if (out_applied) {
        *out_applied = pv;
    }
    return true;
}

void AudioHost::set_global_bypass(bool bypass) {
    global_bypass_.store(bypass, std::memory_order_release);
    ControlCommand cmd{};
    cmd.type = ControlCommandType::SetGlobalBypass;
    cmd.bypass = bypass;
    cmd_queue_.push(cmd);
}

bool AudioHost::set_scene(uint8_t scene_index) {
    if (scene_index >= kNumScenes) {
        return false;
    }
    active_scene_.store(scene_index, std::memory_order_release);

    // Apply scene parameter overrides without reallocating DSP or loading files
    for (const auto& [pid, eng_val] : scenes_[scene_index].overrides) {
        const ParamSpec* spec = ParamRegistry::find_by_id(pid);
        if (spec && pid < kMaxParams) {
            const ParamValue pv = ParamRegistry::make_from_value(*spec, eng_val);
            param_values_[pid].store(pv.value, std::memory_order_release);
            param_normalized_[pid].store(pv.normalized, std::memory_order_release);
        }
    }

    ControlCommand cmd{};
    cmd.type = ControlCommandType::SetScene;
    cmd.scene_index = scene_index;
    cmd_queue_.push(cmd);
    return true;
}

std::vector<ParamValue> AudioHost::get_all_params() const {
    std::vector<ParamValue> out;
    const auto& all = ParamRegistry::specs();
    out.reserve(all.size());
    for (const auto& spec : all) {
        const float val = param_values_[spec.id].load(std::memory_order_acquire);
        out.push_back(ParamRegistry::make_from_value(spec, val));
    }
    return out;
}

std::vector<SceneSlot> AudioHost::get_scenes() const {
    std::lock_guard<std::mutex> lock(state_mutex_);
    return std::vector<SceneSlot>(scenes_.begin(), scenes_.end());
}

std::string AudioHost::active_backend() const {
    std::lock_guard<std::mutex> lock(state_mutex_);
    return active_backend_;
}

std::vector<AudioDeviceInfo> AudioHost::enumerate_devices() const {
    std::vector<AudioDeviceInfo> list;
#ifdef _WIN32
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool need_uninit = SUCCEEDED(hr);
    IMMDeviceEnumerator* enumerator = nullptr;
    hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                          __uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(&enumerator));
    if (SUCCEEDED(hr) && enumerator) {
        auto enum_flow = [&](EDataFlow flow, bool is_input) {
            IMMDeviceCollection* col = nullptr;
            if (SUCCEEDED(enumerator->EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE, &col)) && col) {
                UINT count = 0;
                col->GetCount(&count);
                for (UINT i = 0; i < count; ++i) {
                    IMMDevice* dev = nullptr;
                    if (SUCCEEDED(col->Item(i, &dev)) && dev) {
                        IPropertyStore* props = nullptr;
                        std::string friendly = is_input ? "WASAPI Input" : "WASAPI Output";
                        if (SUCCEEDED(dev->OpenPropertyStore(STGM_READ, &props)) && props) {
                            PROPVARIANT varName;
                            PropVariantInit(&varName);
                            if (SUCCEEDED(props->GetValue(PKEY_Device_FriendlyName, &varName)) &&
                                varName.vt == VT_LPWSTR && varName.pwszVal) {
                                int needed = WideCharToMultiByte(CP_UTF8, 0, varName.pwszVal, -1, nullptr, 0, nullptr, nullptr);
                                if (needed > 1) {
                                    std::string utf8(static_cast<std::size_t>(needed - 1), '\0');
                                    WideCharToMultiByte(CP_UTF8, 0, varName.pwszVal, -1, utf8.data(), needed, nullptr, nullptr);
                                    friendly = std::move(utf8);
                                }
                            }
                            PropVariantClear(&varName);
                            props->Release();
                        }
                        AudioDeviceInfo info{};
                        info.id = static_cast<int>(list.size());
                        info.name = friendly;
                        info.backend = "WASAPI";
                        info.max_inputs = is_input ? 2 : 0;
                        info.max_outputs = is_input ? 0 : 2;
                        info.default_sample_rate = 48000;
                        list.push_back(std::move(info));
                        dev->Release();
                    }
                }
                col->Release();
            }
        };
        enum_flow(eCapture, true);
        enum_flow(eRender, false);
        enumerator->Release();
    }
    if (need_uninit) {
        CoUninitialize();
    }
#endif
    if (list.empty()) {
        list.push_back(AudioDeviceInfo{0, "Null Realtime Loopback Pacer", "null_realtime", 1, 2, 48000});
    }
    return list;
}

void AudioHost::drain_control_queue() noexcept {
    ControlCommand cmd{};
    while (cmd_queue_.pop(cmd)) {
        // Commands are already reflected in atomic arrays; queue draining ensures
        // ordered deterministic acknowledgement inside the audio callback.
        (void)cmd;
    }
}

void AudioHost::process_block(const float* mono_in,
                              float* stereo_out,
                              uint32_t frames,
                              uint32_t in_underflow,
                              uint32_t out_underflow) noexcept {
    const auto t0 = std::chrono::steady_clock::now();

    drain_control_queue();

    // Fetch target parameters lock-free
    const float trim_db = param_values_[0].load(std::memory_order_relaxed);
    const float master_vol = param_values_[47].load(std::memory_order_relaxed);
    const float target_in_gain = std::pow(10.0f, trim_db / 20.0f);
    const float target_master_gain = master_vol;

    float in_peak = 0.0f;
    float out_peak = 0.0f;
    bool had_nonfinite = false;
    bool had_clip = false;

    const float coeff = smooth_coeff_;
    const float one_minus_coeff = 1.0f - coeff;

    for (uint32_t i = 0; i < frames; ++i) {
        smooth_input_gain_ = coeff * smooth_input_gain_ + one_minus_coeff * target_in_gain;

        const float raw_in = mono_in ? mono_in[i] : 0.0f;
        if (!std::isfinite(raw_in)) {
            had_nonfinite = true;
            dsp_scratch_[i] = 0.0f;
            stereo_out[i * 2 + 0] = 0.0f;
            stereo_out[i * 2 + 1] = 0.0f;
            continue;
        }

        const float abs_in = std::fabs(raw_in);
        if (abs_in > in_peak) in_peak = abs_in;

        // Phase 1 Bypass / Phase 2 DSP Amp + Cab chain when global_bypass_ is false
        float sample = raw_in * smooth_input_gain_;
        dsp_scratch_[i] = sample;
    }

    if (!global_bypass_.load(std::memory_order_relaxed) && frames <= dsp_scratch_.size()) {
        // 1. Screamer Overdrive
        const bool screamer_en = param_values_[10].load(std::memory_order_relaxed) >= 0.5f;
        const float screamer_drive = param_values_[11].load(std::memory_order_relaxed);
        const float screamer_tone = param_values_[12].load(std::memory_order_relaxed);
        const float screamer_level = param_values_[13].load(std::memory_order_relaxed);
        dsp_screamer_.set_params(screamer_drive, screamer_tone, screamer_level, screamer_en);
        dsp_screamer_.process(dsp_scratch_.data(), dsp_scratch_.data(), frames);

        // 2. Amp Head or NAM Neural Model
        if (use_nam_.load(std::memory_order_relaxed) && dsp_nam_.is_loaded() && dsp_nam_.is_enabled()) {
            dsp_nam_.process(dsp_scratch_.data(), dsp_scratch_.data(), frames);
        } else {
            const bool amp_en = param_values_[14].load(std::memory_order_relaxed) >= 0.5f;
            const float amp_gain = param_values_[15].load(std::memory_order_relaxed);
            const float amp_bass = param_values_[16].load(std::memory_order_relaxed);
            const float amp_mid = param_values_[17].load(std::memory_order_relaxed);
            const float amp_treble = param_values_[18].load(std::memory_order_relaxed);
            const float amp_pres = param_values_[19].load(std::memory_order_relaxed);
            const float amp_master = param_values_[20].load(std::memory_order_relaxed);
            dsp_amp_.set_params(amp_gain, amp_bass, amp_mid, amp_treble, amp_pres, amp_master, false, amp_en);
            dsp_amp_.process(dsp_scratch_.data(), dsp_scratch_.data(), frames);
        }

        // 3. Cabinet Simulator
        const bool cab_en = param_values_[28].load(std::memory_order_relaxed) >= 0.5f;
        const float cab_lvl = param_values_[29].load(std::memory_order_relaxed);
        const float cab_mix = param_values_[32].load(std::memory_order_relaxed);
        const float cab_ctr = param_values_[33].load(std::memory_order_relaxed);
        const float cab_dst = param_values_[34].load(std::memory_order_relaxed);
        dsp_cab_.set_params(cab_lvl, cab_mix, cab_ctr, cab_dst, cab_en);
        dsp_cab_.process(dsp_scratch_.data(), dsp_scratch_.data(), frames);

        // 4. Ducking Delay
        const bool delay_en = param_values_[39].load(std::memory_order_relaxed) >= 0.5f;
        const float delay_time = param_values_[40].load(std::memory_order_relaxed) * 0.001f;
        const float delay_fb = param_values_[41].load(std::memory_order_relaxed);
        const float delay_mix = param_values_[42].load(std::memory_order_relaxed);
        dsp_delay_.set_params(delay_time, delay_fb, delay_mix, true, 0.6f, delay_en);
        dsp_delay_.process(dsp_scratch_.data(), dsp_scratch_.data(), frames);
    }

    for (uint32_t i = 0; i < frames; ++i) {
        if (had_nonfinite) break;
        smooth_master_gain_ = coeff * smooth_master_gain_ + one_minus_coeff * target_master_gain;
        float sample = dsp_scratch_[i] * smooth_master_gain_;
        if (!std::isfinite(sample)) {
            had_nonfinite = true;
            sample = 0.0f;
        }

        const float abs_out = std::fabs(sample);
        if (abs_out >= 0.999f) {
            had_clip = true;
        }
        if (abs_out > out_peak) {
            out_peak = abs_out;
        }

        stereo_out[i * 2 + 0] = sample;
        stereo_out[i * 2 + 1] = sample;
    }

    if (had_nonfinite) {
        std::fill(stereo_out, stereo_out + (frames * 2), 0.0f);
        out_peak = 0.0f;
    }

    const auto t1 = std::chrono::steady_clock::now();
    const double elapsed_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    metrics_.record_callback(elapsed_ms, in_peak, out_peak, had_nonfinite, had_clip,
                             in_underflow, 0, out_underflow, 0);
}

bool AudioHost::try_start_asio(uint32_t sr, uint32_t bs) {
    auto cb = [this](const float* in, float* stereo_out, uint32_t frames) {
        this->process_block(in, stereo_out, frames, 0, 0);
    };
    return asio_host_.start(sr, bs, cb);
}

bool AudioHost::try_start_wasapi(uint32_t sr, uint32_t bs) {
    (void)sr;
    (void)bs;
    // Exclusive WASAPI device open is not implemented. The production path is
    // ASIO; otherwise the host falls back to the timed realtime pacer.
    return false;
}

bool AudioHost::start(uint32_t sample_rate,
                      uint32_t buffer_size,
                      const std::string& backend_pref,
                      int /*input_device_id*/,
                      int /*output_device_id*/) {
    stop();

    if (sample_rate == 0) sample_rate = 48000;
    if (buffer_size == 0) buffer_size = 128;

    sample_rate_.store(sample_rate, std::memory_order_relaxed);
    buffer_size_.store(buffer_size, std::memory_order_relaxed);

    // 5 ms exponential smoothing time constant
    smooth_coeff_ = std::exp(-1.0f / (0.005f * static_cast<float>(sample_rate)));
    metrics_.configure(sample_rate, buffer_size);
    cmd_queue_.clear();

    stop_requested_.store(false, std::memory_order_release);

    if (backend_pref == "asio" || backend_pref == "auto") {
        if (try_start_asio(sample_rate, buffer_size)) {
            running_.store(true, std::memory_order_release);
            std::lock_guard<std::mutex> lock(state_mutex_);
            active_backend_ = "asio: " + asio_host_.driver_name();
            return true;
        }
        if (backend_pref == "asio") {
            running_.store(false, std::memory_order_release);
            std::lock_guard<std::mutex> lock(state_mutex_);
            active_backend_ = "asio_init_failed";
            return false;
        }
    }

    running_.store(true, std::memory_order_release);
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        active_backend_ = (backend_pref == "wasapi") ? "wasapi_shared_pacer" : "realtime_pacer";
    }

    audio_thread_ = std::thread(&AudioHost::run_realtime_pacer_loop, this);
    return true;
}

void AudioHost::stop() {
    stop_requested_.store(true, std::memory_order_release);
    asio_host_.stop();
    if (audio_thread_.joinable()) {
        audio_thread_.join();
    }
    running_.store(false, std::memory_order_release);
    std::lock_guard<std::mutex> lock(state_mutex_);
    active_backend_ = "stopped";
}

void AudioHost::run_realtime_pacer_loop() {
#ifdef _WIN32
    DWORD task_idx = 0;
    HANDLE mmcss_handle = AvSetMmThreadCharacteristicsW(L"Pro Audio", &task_idx);
    if (!mmcss_handle) {
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
    }
#endif

    const uint32_t sr = sample_rate_.load(std::memory_order_relaxed);
    const uint32_t bs = buffer_size_.load(std::memory_order_relaxed);

    // Preallocate buffers outside the real-time loop
    std::vector<float> in_buf(bs, 0.0f);
    std::vector<float> out_buf(bs * 2, 0.0f);

    // Populate a quiet synthetic guitar DI test tone (-36 dBFS 110 Hz A2)
    double phase = 0.0;
    const double phase_inc = (2.0 * 3.14159265358979323846 * 110.0) / static_cast<double>(sr);

    const auto period_ns = std::chrono::nanoseconds(
        (static_cast<int64_t>(bs) * 1000000000LL) / static_cast<int64_t>(sr));
    auto next_wake = std::chrono::steady_clock::now() + period_ns;

    while (!stop_requested_.load(std::memory_order_acquire)) {
        for (uint32_t i = 0; i < bs; ++i) {
            in_buf[i] = static_cast<float>(std::sin(phase) * 0.0158);
            phase += phase_inc;
            if (phase > 6.283185307179586) phase -= 6.283185307179586;
        }

        process_block(in_buf.data(), out_buf.data(), bs, 0, 0);

        const auto now = std::chrono::steady_clock::now();
        if (next_wake > now) {
            std::this_thread::sleep_until(next_wake);
            next_wake += period_ns;
        } else {
            next_wake = now + period_ns;
        }
    }

#ifdef _WIN32
    if (mmcss_handle) {
        AvRevertMmThreadCharacteristics(mmcss_handle);
    }
#endif
}

} // namespace hack_effect
