#include "asio_driver.hpp"

#include <iostream>

namespace hack_effect {

AsioDriverHost* AsioDriverHost::active_instance_ = nullptr;

AsioDriverHost::AsioDriverHost() = default;

AsioDriverHost::~AsioDriverHost() {
    stop();
    unload_driver();
}

std::vector<AsioDriverDesc> AsioDriverHost::enumerate_drivers() {
    std::vector<AsioDriverDesc> drivers;
#ifdef _WIN32
    HKEY hKey = nullptr;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, "SOFTWARE\\ASIO", 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        char subkey_name[256];
        DWORD index = 0;
        DWORD name_len = sizeof(subkey_name);
        while (RegEnumKeyExA(hKey, index, subkey_name, &name_len, nullptr, nullptr, nullptr, nullptr) == ERROR_SUCCESS) {
            HKEY hSub = nullptr;
            if (RegOpenKeyExA(hKey, subkey_name, 0, KEY_READ, &hSub) == ERROR_SUCCESS) {
                char clsid_buf[128] = {0};
                char desc_buf[256] = {0};
                DWORD sz = sizeof(clsid_buf);
                RegQueryValueExA(hSub, "CLSID", nullptr, nullptr, reinterpret_cast<LPBYTE>(clsid_buf), &sz);
                sz = sizeof(desc_buf);
                if (RegQueryValueExA(hSub, "Description", nullptr, nullptr, reinterpret_cast<LPBYTE>(desc_buf), &sz) != ERROR_SUCCESS) {
                    std::strncpy(desc_buf, subkey_name, sizeof(desc_buf) - 1);
                }
                RegCloseKey(hSub);

                std::string name = subkey_name;
                bool is_ux1 = (name.find("UX1") != std::string::npos || name.find("Line 6") != std::string::npos);
                drivers.push_back({name, clsid_buf, desc_buf, is_ux1});
            }
            name_len = sizeof(subkey_name);
            ++index;
        }
        RegCloseKey(hKey);
    }
#endif
    return drivers;
}

bool AsioDriverHost::load_driver(const std::string& driver_name_or_clsid) {
#ifdef _WIN32
    unload_driver();

    std::string target_clsid = driver_name_or_clsid;
    std::string target_name = driver_name_or_clsid;

    if (target_clsid.empty() || target_clsid.front() != '{') {
        const auto all = enumerate_drivers();
        const AsioDriverDesc* chosen = nullptr;
        if (!target_name.empty()) {
            for (const auto& d : all) {
                if (d.name == target_name || d.description == target_name) {
                    chosen = &d;
                    break;
                }
            }
        }
        if (!chosen) {
            // Prefer UX1
            for (const auto& d : all) {
                if (d.is_ux1) {
                    chosen = &d;
                    break;
                }
            }
        }
        if (!chosen && !all.empty()) {
            chosen = &all.front();
        }
        if (!chosen) {
            return false;
        }
        target_clsid = chosen->clsid;
        target_name = chosen->name;
    }

    std::wstring wclsid(target_clsid.begin(), target_clsid.end());
    CLSID clsid{};
    if (FAILED(CLSIDFromString(wclsid.c_str(), &clsid))) {
        return false;
    }

    CoInitialize(nullptr);

    IASIO* asio_ptr = nullptr;
    // Steinberg ASIO COM convention: the interface ID passed is the driver's own CLSID
    const HRESULT hr = CoCreateInstance(clsid, nullptr, CLSCTX_INPROC_SERVER, clsid, reinterpret_cast<void**>(&asio_ptr));
    if (FAILED(hr) || !asio_ptr) {
        return false;
    }

    if (!asio_ptr->init(nullptr)) {
        asio_ptr->Release();
        return false;
    }

    char name_buf[64] = {0};
    asio_ptr->getDriverName(name_buf);
    driver_ = asio_ptr;
    driver_name_ = name_buf[0] ? name_buf : target_name;
    return true;
#else
    (void)driver_name_or_clsid;
    return false;
#endif
}

void AsioDriverHost::unload_driver() {
#ifdef _WIN32
    stop();
    if (driver_) {
        driver_->Release();
        driver_ = nullptr;
    }
#endif
    driver_name_.clear();
}

void AsioDriverHost::buffer_switch_thunk(int32_t double_buffer_index, ASIOBool /*direct_process*/) {
    if (active_instance_) {
        active_instance_->handle_buffer_switch(double_buffer_index);
    }
}

namespace {
void convert_from_asio(const void* src, float* dst, uint32_t frames, ASIOSampleType type) {
    if (type == ASIOSTInt24LSB) {
        const uint8_t* b = reinterpret_cast<const uint8_t*>(src);
        for (uint32_t i = 0; i < frames; ++i) {
            const int32_t val = (static_cast<int32_t>(b[0])) |
                                (static_cast<int32_t>(b[1]) << 8) |
                                (static_cast<int32_t>(static_cast<int8_t>(b[2])) << 16);
            dst[i] = static_cast<float>(val) * (1.0f / 8388608.0f);
            b += 3;
        }
    } else if (type == ASIOSTInt32LSB) {
        const int32_t* s32 = reinterpret_cast<const int32_t*>(src);
        for (uint32_t i = 0; i < frames; ++i) {
            dst[i] = static_cast<float>(s32[i]) * (1.0f / 2147483648.0f);
        }
    } else if (type == ASIOSTFloat32LSB) {
        std::memcpy(dst, src, frames * sizeof(float));
    } else if (type == ASIOSTInt16LSB) {
        const int16_t* s16 = reinterpret_cast<const int16_t*>(src);
        for (uint32_t i = 0; i < frames; ++i) {
            dst[i] = static_cast<float>(s16[i]) * (1.0f / 32768.0f);
        }
    } else {
        std::fill_n(dst, frames, 0.0f);
    }
}

void convert_to_asio_deinterleaved(const float* stereo_src, void* dst_l, void* dst_r, uint32_t frames, ASIOSampleType type) {
    if (type == ASIOSTInt24LSB) {
        uint8_t* bl = reinterpret_cast<uint8_t*>(dst_l);
        uint8_t* br = reinterpret_cast<uint8_t*>(dst_r);
        for (uint32_t i = 0; i < frames; ++i) {
            const float fl = stereo_src[i * 2 + 0];
            const float fr = stereo_src[i * 2 + 1];
            const int32_t vl = static_cast<int32_t>(std::clamp(fl * 8388607.0f, -8388608.0f, 8388607.0f));
            const int32_t vr = static_cast<int32_t>(std::clamp(fr * 8388607.0f, -8388608.0f, 8388607.0f));

            bl[0] = static_cast<uint8_t>(vl & 0xFF);
            bl[1] = static_cast<uint8_t>((vl >> 8) & 0xFF);
            bl[2] = static_cast<uint8_t>((vl >> 16) & 0xFF);
            bl += 3;

            br[0] = static_cast<uint8_t>(vr & 0xFF);
            br[1] = static_cast<uint8_t>((vr >> 8) & 0xFF);
            br[2] = static_cast<uint8_t>((vr >> 16) & 0xFF);
            br += 3;
        }
    } else if (type == ASIOSTInt32LSB) {
        int32_t* sl = reinterpret_cast<int32_t*>(dst_l);
        int32_t* sr = reinterpret_cast<int32_t*>(dst_r);
        for (uint32_t i = 0; i < frames; ++i) {
            sl[i] = static_cast<int32_t>(std::clamp(stereo_src[i * 2 + 0] * 2147483647.0f, -2147483648.0f, 2147483647.0f));
            sr[i] = static_cast<int32_t>(std::clamp(stereo_src[i * 2 + 1] * 2147483647.0f, -2147483648.0f, 2147483647.0f));
        }
    } else if (type == ASIOSTFloat32LSB) {
        float* fl = reinterpret_cast<float*>(dst_l);
        float* fr = reinterpret_cast<float*>(dst_r);
        for (uint32_t i = 0; i < frames; ++i) {
            fl[i] = stereo_src[i * 2 + 0];
            fr[i] = stereo_src[i * 2 + 1];
        }
    }
}
} // namespace

void AsioDriverHost::handle_buffer_switch(int32_t double_buffer_index) {
    if (!audio_callback_ || buffer_infos_.size() < 3) return;

    void* in_ptr = buffer_infos_[0].buffers[double_buffer_index];
    convert_from_asio(in_ptr, in_scratch_.data(), buffer_size_, in_type_);

    audio_callback_(in_scratch_.data(), out_scratch_.data(), buffer_size_);

    void* out_l = buffer_infos_[1].buffers[double_buffer_index];
    void* out_r = buffer_infos_[2].buffers[double_buffer_index];
    convert_to_asio_deinterleaved(out_scratch_.data(), out_l, out_r, buffer_size_, out_type_);

#ifdef _WIN32
    if (driver_) {
        driver_->outputReady();
    }
#endif
}

bool AsioDriverHost::start(uint32_t sample_rate, uint32_t buffer_size, AudioCallback callback) {
#ifdef _WIN32
    if (!driver_) {
        if (!load_driver()) {
            return false;
        }
    }
    stop();

    sample_rate_ = (sample_rate > 0) ? sample_rate : 48000;
    buffer_size_ = (buffer_size > 0) ? buffer_size : 128;
    audio_callback_ = std::move(callback);

    driver_->canSampleRate(static_cast<double>(sample_rate_));
    driver_->setSampleRate(static_cast<double>(sample_rate_));

    int32_t min_b = 0, max_b = 0, pref_b = 0, gran_b = 0;
    driver_->getBufferSize(&min_b, &max_b, &pref_b, &gran_b);
    if (buffer_size_ < static_cast<uint32_t>(min_b) && min_b > 0) buffer_size_ = min_b;
    if (buffer_size_ > static_cast<uint32_t>(max_b) && max_b > 0) buffer_size_ = max_b;

    ASIOChannelInfo info_in{};
    info_in.channel = 0;
    info_in.isInput = 1;
    driver_->getChannelInfo(&info_in);
    in_type_ = info_in.type;

    ASIOChannelInfo info_out{};
    info_out.channel = 0;
    info_out.isInput = 0;
    driver_->getChannelInfo(&info_out);
    out_type_ = info_out.type;

    buffer_infos_.resize(3);
    // In 0
    buffer_infos_[0].isInput = 1;
    buffer_infos_[0].channelNum = 0;
    buffer_infos_[0].buffers[0] = nullptr;
    buffer_infos_[0].buffers[1] = nullptr;
    // Out 0 (Left)
    buffer_infos_[1].isInput = 0;
    buffer_infos_[1].channelNum = 0;
    buffer_infos_[1].buffers[0] = nullptr;
    buffer_infos_[1].buffers[1] = nullptr;
    // Out 1 (Right)
    buffer_infos_[2].isInput = 0;
    buffer_infos_[2].channelNum = 1;
    buffer_infos_[2].buffers[0] = nullptr;
    buffer_infos_[2].buffers[1] = nullptr;

    callbacks_ = {};
    callbacks_.bufferSwitch = &AsioDriverHost::buffer_switch_thunk;

    in_scratch_.resize(buffer_size_, 0.0f);
    out_scratch_.resize(buffer_size_ * 2, 0.0f);

    active_instance_ = this;

    const ASIOError err_buf = driver_->createBuffers(buffer_infos_.data(), static_cast<int32_t>(buffer_infos_.size()),
                                                     static_cast<int32_t>(buffer_size_), &callbacks_);
    if (err_buf != ASE_OK) {
        active_instance_ = nullptr;
        return false;
    }
    buffers_created_ = true;

    driver_->getLatencies(&input_latency_, &output_latency_);

    const ASIOError err_start = driver_->start();
    if (err_start != ASE_OK) {
        stop();
        return false;
    }

    is_running_ = true;
    return true;
#else
    (void)sample_rate; (void)buffer_size; (void)callback;
    return false;
#endif
}

void AsioDriverHost::stop() {
#ifdef _WIN32
    if (is_running_ && driver_) {
        driver_->stop();
        is_running_ = false;
    }
    if (buffers_created_ && driver_) {
        driver_->disposeBuffers();
        buffers_created_ = false;
    }
    if (active_instance_ == this) {
        active_instance_ = nullptr;
    }
#endif
}

} // namespace hack_effect
