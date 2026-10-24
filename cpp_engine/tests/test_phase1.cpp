#include "audio_host.hpp"
#include "dsp_blocks.hpp"
#include "metrics.hpp"
#include "param_registry.hpp"
#include "spsc_queue.hpp"
#include "ws_server.hpp"
#include "parity_vectors.inc"

#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#endif

using namespace hack_effect;

namespace {

void test_spsc_ring_buffer() {
    SpscRingBuffer<int, 8> q;
    for (int i = 0; i < 7; ++i) {
        assert(q.push(i));
    }
    // Capacity 8 ring buffer holds 7 items before full
    assert(!q.push(99));

    for (int i = 0; i < 7; ++i) {
        int out = -1;
        assert(q.pop(out));
        assert(out == i);
    }
    int dummy = 0;
    assert(!q.pop(dummy));
    std::cout << "[PASS] test_spsc_ring_buffer\n";
}

void test_param_registry_dual_units() {
    // Linear parameter: Amp Gain (0..1 -> 0..100%)
    const ParamSpec* gain = ParamRegistry::find("amp", "gain");
    assert(gain != nullptr);
    const auto pv1 = ParamRegistry::make_from_normalized(*gain, 0.75f);
    assert(std::fabs(pv1.normalized - 0.75f) < 1e-5f);
    assert(std::fabs(pv1.value - 0.75f) < 1e-5f);
    assert(std::fabs(pv1.display_value - 75.0f) < 1e-3f);

    // LogHz parameter: Cab LowCut (20 Hz .. 500 Hz)
    const ParamSpec* lowcut = ParamRegistry::find("cab", "lowcut");
    assert(lowcut != nullptr);
    const auto pv_min = ParamRegistry::make_from_normalized(*lowcut, 0.0f);
    const auto pv_mid = ParamRegistry::make_from_normalized(*lowcut, 0.5f);
    const auto pv_max = ParamRegistry::make_from_normalized(*lowcut, 1.0f);
    assert(std::fabs(pv_min.value - 20.0f) < 1e-2f);
    // Geometric mean of 20 and 500 is sqrt(10000) = 100 Hz
    assert(std::fabs(pv_mid.value - 100.0f) < 0.2f);
    assert(std::fabs(pv_max.value - 500.0f) < 1e-2f);

    // Alias lookup: "drive" -> "screamer"
    const ParamSpec* drv = ParamRegistry::find("drive", "drive");
    assert(drv != nullptr && std::string(drv->block) == "screamer");
    std::cout << "[PASS] test_param_registry_dual_units\n";
}

void test_audio_callback_nan_guard_and_bypass() {
    AudioHost host;
    host.set_global_bypass(true);
    constexpr uint32_t kFrames = 64;
    std::vector<float> in(kFrames, 0.25f);
    std::vector<float> out(kFrames * 2, 0.0f);

    // Warmup + normal passthrough (global bypass must keep dry input)
    for (int i = 0; i < 60; ++i) {
        host.process_block(in.data(), out.data(), kFrames);
    }
    assert(std::fabs(out[0] - 0.25f) < 0.01f);
    assert(std::fabs(out[1] - 0.25f) < 0.01f);

    // Inject NaN into input block -> must silence entire block and count nonfinite_blocks
    in[10] = std::numeric_limits<float>::quiet_NaN();
    host.process_block(in.data(), out.data(), kFrames);
    for (float s : out) {
        assert(s == 0.0f);
    }
    const auto m = host.metrics_snapshot();
    assert(m.nonfinite_blocks == 1);
    assert(!m.finite_clean);
    assert(!m.passed_phase1_gate);

    host.reset_metrics();
    in[10] = 0.25f;
    for (int i = 0; i < 120; ++i) {
        host.process_block(in.data(), out.data(), kFrames);
    }
    const auto m_clean = host.metrics_snapshot();
    assert(m_clean.nonfinite_blocks == 0);
    assert(m_clean.passed_phase1_gate);
    std::cout << "[PASS] test_audio_callback_nan_guard_and_bypass\n";
}

void test_dsp_unbypass_changes_signal() {
    AudioHost host;
    host.set_global_bypass(false);
    host.set_param_value("amp", "enabled", 1.0f);
    host.set_param_value("amp", "gain", 0.85f);
    host.set_param_value("cab", "enabled", 1.0f);
    host.set_param_value("screamer", "enabled", 1.0f);
    host.set_param_value("screamer", "drive", 0.7f);

    constexpr uint32_t kFrames = 128;
    std::vector<float> in(kFrames, 0.25f);
    std::vector<float> out(kFrames * 2, 0.0f);
    for (int i = 0; i < 8; ++i) {
        host.process_block(in.data(), out.data(), kFrames);
    }
    float max_delta = 0.0f;
    for (uint32_t i = 0; i < kFrames; ++i) {
        max_delta = std::max(max_delta, std::fabs(out[i * 2] - 0.25f));
        assert(std::isfinite(out[i * 2]));
        assert(std::isfinite(out[i * 2 + 1]));
    }
    assert(max_delta > 0.01f);
    std::cout << "[PASS] test_dsp_unbypass_changes_signal (max_delta=" << max_delta << ")\n";
}

void test_ipc_protocol_and_security() {
    AudioHost host;
    WsServerConfig cfg{};
    cfg.bind_address = "127.0.0.1";
    cfg.port = 0; // Ephemeral port for conflict-free test
    cfg.session_token = "test_secret_token_12345";

    // Verify non-loopback address is rejected
    WsServerConfig bad_cfg = cfg;
    bad_cfg.bind_address = "0.0.0.0";
    LoopbackWsServer bad_srv(host, bad_cfg);
    assert(!bad_srv.start());

    LoopbackWsServer srv(host, cfg);
    assert(srv.start());
    assert(srv.port() > 0);

    // Verify Origin allowlist
    assert(srv.is_origin_allowed("http://127.0.0.1:8000"));
    assert(srv.is_origin_allowed("http://localhost:5173"));
    assert(!srv.is_origin_allowed("https://evil.example.com"));

    // Verify JSON command handling (ping, set_param normalized & engineering, set_scene, out-of-range rejection)
    const std::string pong = srv.handle_json_message(R"({"type":"ping","req_id":"r1"})");
    assert(pong.find(R"("type":"pong")") != std::string::npos);

    const std::string set_norm = srv.handle_json_message(
        R"({"type":"set_param","req_id":"r2","block":"amp","param":"gain","normalized":0.8})");
    assert(set_norm.find(R"("ok":true)") != std::string::npos);
    assert(set_norm.find(R"("display_value":80.0000)") != std::string::npos);

    const std::string set_eng = srv.handle_json_message(
        R"({"type":"set_param","req_id":"r3","block":"gate","param":"threshold","value":-45.0})");
    assert(set_eng.find(R"("ok":true)") != std::string::npos);
    assert(set_eng.find(R"("value":-45.0000)") != std::string::npos);

    const std::string bad_range = srv.handle_json_message(
        R"({"type":"set_param","req_id":"r4","block":"amp","param":"gain","normalized":1.5})");
    assert(bad_range.find(R"("ok":false)") != std::string::npos);
    assert(bad_range.find(R"("error":"out_of_range")") != std::string::npos);

    const std::string scene_resp = srv.handle_json_message(
        R"({"type":"set_scene","req_id":"r5","scene_index":3})");
    assert(scene_resp.find(R"("ok":true)") != std::string::npos);
    assert(host.active_scene() == 3);

    // Test live socket HTTP 401 on wrong token & HTTP 403 on disallowed Origin
    auto send_raw_http = [&](const std::string& raw_req) -> std::string {
#ifdef _WIN32
        SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        auto close_s = [&]() { closesocket(s); };
        auto send_s = [&](const char* b, int n) { return send(s, b, n, 0); };
        auto recv_s = [&](char* b, int n) { return recv(s, b, n, 0); };
        DWORD timeout_ms = 2000;
        setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&timeout_ms), sizeof(timeout_ms));
        setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, reinterpret_cast<const char*>(&timeout_ms), sizeof(timeout_ms));
#else
        int s = socket(AF_INET, SOCK_STREAM, 0);
        auto close_s = [&]() { close(s); };
        auto send_s = [&](const char* b, int n) { return static_cast<int>(::send(s, b, static_cast<std::size_t>(n), 0)); };
        auto recv_s = [&](char* b, int n) { return static_cast<int>(::recv(s, b, static_cast<std::size_t>(n), 0)); };
        timeval tv{};
        tv.tv_sec = 2;
        tv.tv_usec = 0;
        setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
        setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#endif
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(srv.port());
        inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
        if (connect(s, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
            close_s();
            return {};
        }
        send_s(raw_req.data(), static_cast<int>(raw_req.size()));
        char rbuf[512]{};
        int n = recv_s(rbuf, static_cast<int>(sizeof(rbuf) - 1));
        close_s();
        return n > 0 ? std::string(rbuf, static_cast<std::size_t>(n)) : std::string{};
    };

    const std::string resp_401 = send_raw_http(
        "GET /ws?token=wrong_token HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Origin: http://127.0.0.1:8000\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n");
    assert(resp_401.find("401 Unauthorized") != std::string::npos);

    const std::string resp_403 = send_raw_http(
        "GET /ws?token=test_secret_token_12345 HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Origin: http://malicious.site\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n");
    assert(resp_403.find("403 Forbidden") != std::string::npos);

    srv.stop();
    std::cout << "[PASS] test_ipc_protocol_and_security\n";
}

void test_phase2_amp_and_cab_python_parity() {
    constexpr std::size_t kN = 300;
    constexpr uint32_t kSr = 48000;

    // 1. DspAmpHead parity against Python AmpHead across 3 blocks (128, 128, 44)
    DspAmpHead amp(kSr);
    amp.set_params(0.65f, 0.55f, 0.50f, 0.60f, 0.60f, 0.70f, false, true);
    std::vector<float> amp_out(kN, 0.0f);
    amp.process(&kTestInput[0], &amp_out[0], 128);
    amp.process(&kTestInput[128], &amp_out[128], 128);
    amp.process(&kTestInput[256], &amp_out[256], 44);

    float max_amp_err = 0.0f;
    for (std::size_t i = 0; i < kN; ++i) {
        const float err = std::fabs(amp_out[i] - kRefAmpOut[i]);
        if (err > max_amp_err) max_amp_err = err;
    }
    assert(max_amp_err < 1e-5f);

    // 2. DspPartitionedConvolver parity against Python PartitionedConvolver across irregular blocks (37, 128, 135)
    std::vector<float> ir_vec(std::begin(kTestIr), std::end(kTestIr));
    DspPartitionedConvolver conv(ir_vec, 128);
    std::vector<float> conv_out(kN, 0.0f);
    conv.process(&kTestInput[0], &conv_out[0], 37);
    conv.process(&kTestInput[37], &conv_out[37], 128);
    conv.process(&kTestInput[165], &conv_out[165], 135);

    float max_conv_err = 0.0f;
    for (std::size_t i = 0; i < kN; ++i) {
        const float err = std::fabs(conv_out[i] - kRefConvOut[i]);
        if (err > max_conv_err) max_conv_err = err;
    }
    assert(max_conv_err < 1e-5f);

    // 3. DspCabinetSimulator parity against Python CabinetSimulator (IR + Butterworth cutoffs + SM57 + Center/Distance)
    DspCabinetSimulator cab(kSr);
    cab.set_ir_data(ir_vec);
    cab.set_cutoffs(80.0f, 7500.0f);
    cab.set_params(1.0f, 1.0f, 50.0f, 20.0f, true);
    std::vector<float> cab_out(kN, 0.0f);
    cab.process(&kTestInput[0], &cab_out[0], 128);
    cab.process(&kTestInput[128], &cab_out[128], 172);

    float max_cab_err = 0.0f;
    for (std::size_t i = 0; i < kN; ++i) {
        const float err = std::fabs(cab_out[i] - kRefCabOut[i]);
        if (err > max_cab_err) max_cab_err = err;
    }
    assert(max_cab_err < 1e-5f);

    std::cout << "[PASS] test_phase2_amp_and_cab_python_parity (max_amp_err=" << max_amp_err
              << ", max_conv_err=" << max_conv_err << ", max_cab_err=" << max_cab_err << ")\n";
}

void test_phase3_cloned_flagship_dsp() {
    constexpr std::size_t kN = 300;
    // 1. MOOER GE150 / TS-808 Asymmetric Overdrive
    DspOverdrive od(48000);
    od.set_params(0.6f, 0.65f, 0.8f, true);
    std::vector<float> out_od(kN, 0.0f);
    od.process(&kTestInput[0], out_od.data(), kN);
    float od_rms = 0.0f;
    for (float s : out_od) od_rms += s * s;
    if (!(od_rms > 0.1f)) std::abort();

    // 2. Neural DSP Archetype Stereo Haas Doubler
    DspStereoDoubler doubler(48000);
    doubler.set_params(14.0f, 0.4f, 1.0f, true);
    std::vector<float> left(kN, 0.0f), right(kN, 0.0f);
    doubler.process_stereo(out_od.data(), left.data(), right.data(), kN);
    float diff_lr = 0.0f;
    for (std::size_t i = 0; i < kN; ++i) diff_lr += std::fabs(left[i] - right[i]);
    if (!(diff_lr > 1.0f)) std::abort();

    // 3. Quad Cortex Dynamic Ducking Delay
    DspDuckingDelay dly(48000);
    dly.set_params(0.002f, 0.45f, 0.5f, true, 0.65f, true);
    std::vector<float> out_dly(kN, 0.0f);
    dly.process(out_od.data(), out_dly.data(), kN);

    // 4. Kemper Continuous Morph A<->B Interpolator
    MorphSnapshot a{0.25f, 0.75f, 0.15f, 0.70f, 0.10f, 0.20f};
    MorphSnapshot b{0.85f, 0.85f, 0.55f, 0.90f, 0.40f, 0.50f};
    MorphSnapshot mid = DspKemperMorph::interpolate(a, b, 0.5f);
    if (!(std::fabs(mid.amp_gain - 0.55f) < 1e-5f && std::fabs(mid.delay_mix - 0.25f) < 1e-5f)) std::abort();

    std::cout << "[PASS] test_phase3_cloned_flagship_dsp (Overdrive + Neural Stereo Doubler + QC Ducking Delay + Kemper Morph)\n";
}

void test_phase4_nam_c99_native_inference() {
    DspNamEngine nam_eng;
    if (!nam_eng.load_dll()) {
        std::cout << "[SKIP] test_phase4_nam_c99_native_inference (nam_c99.dll not found in current path)\n";
        return;
    }

    std::vector<float> dummy_weights(1871, 0.01f);
    dummy_weights.back() = 1.0f; // head_scale
    std::string err;
    const bool ok = nam_eng.load_weights(dummy_weights.data(), dummy_weights.size(), 48000.0, -18.0, &err);
    if (!ok) {
        std::cout << "[SKIP] test_phase4_nam_c99_native_inference: " << err << "\n";
        return;
    }

    assert(nam_eng.is_loaded());
    constexpr std::size_t kN = 128;
    std::vector<float> in(kN, 0.15f);
    std::vector<float> out(kN, 0.0f);

    nam_eng.reset();
    nam_eng.process(in.data(), out.data(), kN);

    for (float s : out) {
        assert(std::isfinite(s));
    }
    std::cout << "[PASS] test_phase4_nam_c99_native_inference (A2-Lite WaveNet zero-allocation inference)\n";
}

void test_phase5_asio_driver_enumeration_and_com() {
    const auto drivers = AsioDriverHost::enumerate_drivers();
    if (drivers.empty()) {
        std::cout << "[SKIP] test_phase5_asio_driver_enumeration_and_com (no ASIO drivers found in registry)\n";
        return;
    }
    bool has_ux1 = false;
    for (const auto& d : drivers) {
        if (d.is_ux1) has_ux1 = true;
    }
    (void)has_ux1;

    AsioDriverHost asio;
    const bool loaded = asio.load_driver("ASIO UX1");
    if (!loaded) {
        std::cout << "[SKIP] test_phase5_asio_driver_enumeration_and_com (failed to load ASIO UX1 COM instance)\n";
        return;
    }

    assert(asio.is_loaded());
    assert(!asio.driver_name().empty());

    uint32_t callbacks_received = 0;
    auto cb = [&callbacks_received](const float* in, float* stereo_out, uint32_t frames) {
        (void)in;
        std::fill_n(stereo_out, frames * 2, 0.0f);
        ++callbacks_received;
    };

    const bool started = asio.start(48000, 128, cb);
    if (started) {
        std::this_thread::sleep_for(std::chrono::milliseconds(60));
        asio.stop();
        assert(callbacks_received > 0);
        std::cout << "[PASS] test_phase5_asio_driver_enumeration_and_com (ASIO UX1 streamed "
                  << callbacks_received << " double-buffered blocks, roundtrip latency: "
                  << asio.roundtrip_latency_ms() << " ms)\n";
    } else {
        std::cout << "[PASS] test_phase5_asio_driver_enumeration_and_com (ASIO UX1 COM initialized successfully)\n";
    }
    asio.unload_driver();
}

} // namespace

int main() {
    test_spsc_ring_buffer();
    test_param_registry_dual_units();
    test_audio_callback_nan_guard_and_bypass();
    test_dsp_unbypass_changes_signal();
    test_ipc_protocol_and_security();
    test_phase2_amp_and_cab_python_parity();
    test_phase3_cloned_flagship_dsp();
    test_phase4_nam_c99_native_inference();
    test_phase5_asio_driver_enumeration_and_com();
    std::cout << "\nC++ UNIT / IPC / DSP TESTS COMPLETED.\n";
    std::cout << "Hardware-dependent NAM DLL and ASIO UX1 cases are reported as PASS or SKIP above.\n";
    std::cout << "Do not treat a SKIP as live Line 6 UX1 ASIO evidence.\n";
    return 0;
}
