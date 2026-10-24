#pragma once

#ifdef _WIN32
#include <windows.h>
#include <objbase.h>
#endif

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

namespace hack_effect {

using ASIOBool = int32_t;
using ASIOError = int32_t;
using ASIOSampleRate = double;

enum ASIOErrorCodes : ASIOError {
    ASE_OK = 0,
    ASE_SUCCESS = 0x3f484c27,
    ASE_NotPresent = -1000,
    ASE_HWMalfunction = -999,
    ASE_InvalidParameter = -998,
    ASE_InvalidMode = -997,
    ASE_SPNotAdvancing = -996,
    ASE_NoClock = -995,
    ASE_NoMemory = -994
};

enum ASIOSampleType : int32_t {
    ASIOSTInt16MSB = 0,
    ASIOSTInt24MSB = 1,
    ASIOSTInt32MSB = 2,
    ASIOSTFloat32MSB = 3,
    ASIOSTFloat64MSB = 4,
    ASIOSTInt32MSB16 = 8,
    ASIOSTInt32MSB18 = 9,
    ASIOSTInt32MSB20 = 10,
    ASIOSTInt32MSB24 = 11,
    ASIOSTInt16LSB = 16,
    ASIOSTInt24LSB = 17, // Line 6 UX1 native sample format
    ASIOSTInt32LSB = 18,
    ASIOSTFloat32LSB = 19,
    ASIOSTFloat64LSB = 20,
    ASIOSTInt32LSB16 = 24,
    ASIOSTInt32LSB18 = 25,
    ASIOSTInt32LSB20 = 26,
    ASIOSTInt32LSB24 = 27
};

struct ASIOClockSource {
    int32_t index;
    int32_t associatedChannel;
    int32_t associatedGroup;
    ASIOBool isCurrentSource;
    char name[32];
};

struct ASIOChannelInfo {
    int32_t channel;
    ASIOBool isInput;
    ASIOBool isActive;
    int32_t channelGroup;
    ASIOSampleType type;
    char name[32];
};

struct ASIOBufferInfo {
    ASIOBool isInput;
    int32_t channelNum;
    void* buffers[2];
};

struct ASIOSamples {
    uint32_t lo;
    uint32_t hi;
};

struct ASIOTimeStamp {
    uint32_t lo;
    uint32_t hi;
};

struct ASIOTimeCode {
    double speed;
    ASIOSamples timeCodeSamples;
    uint32_t flags;
    char future[64];
};

struct ASIOTimeInfo {
    double speed;
    ASIOTimeStamp systemTime;
    ASIOSamples samplePosition;
    ASIOSampleRate sampleRate;
    uint32_t flags;
    char reserved[12];
};

struct ASIOTime {
    int32_t reserved[4];
    ASIOTimeInfo timeInfo;
    ASIOTimeCode timeCode;
};

struct ASIOCallbacks {
    void (*bufferSwitch)(int32_t doubleBufferIndex, ASIOBool directProcess);
    void (*sampleRateDidChange)(ASIOSampleRate sRate);
    int32_t (*asioMessage)(int32_t selector, int32_t value, void* message, double* opt);
    ASIOTime* (*bufferSwitchTimeInfo)(ASIOTime* params, int32_t doubleBufferIndex, ASIOBool directProcess);
};

#ifdef _WIN32
// COM interface layout for IASIO (matches Steinberg ASIO SDK specification)
struct IASIO : public IUnknown {
    virtual ASIOBool init(void* sysHandle) = 0;
    virtual void getDriverName(char* name) = 0;
    virtual int32_t getDriverVersion() = 0;
    virtual void getErrorMessage(char* string) = 0;
    virtual ASIOError start() = 0;
    virtual ASIOError stop() = 0;
    virtual ASIOError getChannels(int32_t* numInputChannels, int32_t* numOutputChannels) = 0;
    virtual ASIOError getLatencies(int32_t* inputLatency, int32_t* outputLatency) = 0;
    virtual ASIOError getBufferSize(int32_t* minSize, int32_t* maxSize, int32_t* preferredSize, int32_t* granularity) = 0;
    virtual ASIOError canSampleRate(ASIOSampleRate sampleRate) = 0;
    virtual ASIOError getSampleRate(ASIOSampleRate* sampleRate) = 0;
    virtual ASIOError setSampleRate(ASIOSampleRate sampleRate) = 0;
    virtual ASIOError getClockSources(ASIOClockSource* clocks, int32_t* numSources) = 0;
    virtual ASIOError setClockSource(int32_t reference) = 0;
    virtual ASIOError getSamplePosition(ASIOSamples* sPos, ASIOTimeStamp* tStamp) = 0;
    virtual ASIOError getChannelInfo(ASIOChannelInfo* info) = 0;
    virtual ASIOError createBuffers(ASIOBufferInfo* bufferInfos, int32_t numChannels, int32_t bufferSize, ASIOCallbacks* callbacks) = 0;
    virtual ASIOError disposeBuffers() = 0;
    virtual ASIOError controlPanel() = 0;
    virtual ASIOError future(int32_t selector, void* opt) = 0;
    virtual ASIOError outputReady() = 0;
};
#endif

struct AsioDriverDesc {
    std::string name;
    std::string clsid;
    std::string description;
    bool is_ux1{false};
};

class AsioDriverHost {
public:
    using AudioCallback = std::function<void(const float* in, float* stereo_out, uint32_t frames)>;

    AsioDriverHost();
    ~AsioDriverHost();

    static std::vector<AsioDriverDesc> enumerate_drivers();
    bool load_driver(const std::string& driver_name_or_clsid = "");
    void unload_driver();

    bool start(uint32_t sample_rate, uint32_t buffer_size, AudioCallback callback);
    void stop();

    bool is_loaded() const noexcept { return driver_ != nullptr; }
    bool is_running() const noexcept { return is_running_; }
    const std::string& driver_name() const noexcept { return driver_name_; }
    uint32_t sample_rate() const noexcept { return sample_rate_; }
    uint32_t buffer_size() const noexcept { return buffer_size_; }
    int32_t input_latency_samples() const noexcept { return input_latency_; }
    int32_t output_latency_samples() const noexcept { return output_latency_; }
    double roundtrip_latency_ms() const noexcept {
        return (sample_rate_ > 0) ? (static_cast<double>(input_latency_ + output_latency_) / sample_rate_ * 1000.0) : 0.0;
    }

private:
    static void buffer_switch_thunk(int32_t double_buffer_index, ASIOBool direct_process);
    void handle_buffer_switch(int32_t double_buffer_index);

    static AsioDriverHost* active_instance_;

#ifdef _WIN32
    IASIO* driver_{nullptr};
#else
    void* driver_{nullptr};
#endif
    std::string driver_name_;
    uint32_t sample_rate_{48000};
    uint32_t buffer_size_{128};
    int32_t input_latency_{0};
    int32_t output_latency_{0};
    bool is_running_{false};
    bool buffers_created_{false};

    ASIOSampleType in_type_{ASIOSTInt24LSB};
    ASIOSampleType out_type_{ASIOSTInt24LSB};
    std::vector<ASIOBufferInfo> buffer_infos_;
    ASIOCallbacks callbacks_{};

    AudioCallback audio_callback_;
    std::vector<float> in_scratch_;
    std::vector<float> out_scratch_;
};

} // namespace hack_effect
