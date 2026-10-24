#include "audio_host.hpp"
#include "ws_server.hpp"

#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

using namespace hack_effect;

namespace {

void print_usage() {
    std::cout << "Hack-Effect Native C++ Engine Host (Phase 1)\n"
              << "Usage:\n"
              << "  hack_effect_host [--port <port>] [--token <token>] [--sr <48000>] [--buffer <128>]\n"
              << "  hack_effect_host --benchmark-live [--duration-sec <60>] [--buffers 64,128,256]\n";
}

int run_live_benchmark(int duration_sec, const std::vector<uint32_t>& buffers) {
    AudioHost host;
    const uint32_t sr = 48000;
    bool all_passed = true;

    std::cout << "================================================================================\n";
    std::cout << " HACK-EFFECT C++ ENGINE — PHASE 1 LIVE BENCHMARK (@ " << sr << " Hz)\n";
    std::cout << " Gate Criteria: XRUN = 0 | p99 < 50% deadline | p99.9 < 80% deadline | No NaN\n";
    std::cout << "================================================================================\n";

    for (uint32_t bs : buffers) {
        std::cout << "\n[RUN] Buffer Size: " << bs << " samples ("
                  << std::fixed << std::setprecision(3) << (static_cast<double>(bs) / sr * 1000.0)
                  << " ms deadline) for " << duration_sec << "s...\n";

        host.start(sr, bs, "wasapi");
        std::this_thread::sleep_for(std::chrono::seconds(duration_sec));
        const MetricsSnapshot m = host.metrics_snapshot();
        host.stop();

        const uint64_t xruns = m.input_underflow + m.input_overflow + m.output_underflow + m.output_overflow;
        std::cout << "  Callbacks:        " << m.callback_count << " (ring samples: " << m.percentile_blocks << ")\n"
                  << "  Deadline:         " << m.deadline_ms << " ms\n"
                  << "  p50 / p95:        " << m.p50_ms << " ms / " << m.p95_ms << " ms\n"
                  << "  p99   (<50% lim): " << m.p99_ms << " ms (limit: " << (m.deadline_ms * 0.50) << " ms)\n"
                  << "  p99.9 (<80% lim): " << m.p99_9_ms << " ms (limit: " << (m.deadline_ms * 0.80) << " ms)\n"
                  << "  Max / Warmup Max: " << m.max_ms << " ms / " << m.warmup_max_ms << " ms\n"
                  << "  XRUNs / NonFinite:" << xruns << " / " << m.nonfinite_blocks << "\n"
                  << "  Gate Verdict:     " << (m.passed_phase1_gate ? "PASS" : "FAIL") << "\n";

        if (!m.passed_phase1_gate) {
            all_passed = false;
        }
    }

    std::cout << "\n================================================================================\n";
    std::cout << " OVERALL PHASE 1 GATE VERDICT: " << (all_passed ? "PASSED ALL BUFFERS" : "FAILED") << "\n";
    std::cout << "================================================================================\n";
    return all_passed ? 0 : 1;
}

} // namespace

int main(int argc, char** argv) {
    uint16_t port = 8765;
    std::string token;
    std::string backend = "auto";
    uint32_t sr = 48000;
    uint32_t bs = 128;
    bool benchmark_mode = false;
    int duration_sec = 5;
    std::vector<uint32_t> bench_buffers = {64, 128, 256};

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            print_usage();
            return 0;
        } else if (arg == "--port" && i + 1 < argc) {
            port = static_cast<uint16_t>(std::atoi(argv[++i]));
        } else if (arg == "--token" && i + 1 < argc) {
            token = argv[++i];
        } else if (arg == "--backend" && i + 1 < argc) {
            backend = argv[++i];
        } else if (arg == "--sr" && i + 1 < argc) {
            sr = static_cast<uint32_t>(std::atoi(argv[++i]));
        } else if (arg == "--buffer" && i + 1 < argc) {
            bs = static_cast<uint32_t>(std::atoi(argv[++i]));
        } else if (arg == "--benchmark-live") {
            benchmark_mode = true;
        } else if (arg == "--duration-sec" && i + 1 < argc) {
            duration_sec = std::atoi(argv[++i]);
        }
    }

    if (benchmark_mode) {
        return run_live_benchmark(duration_sec, bench_buffers);
    }

    AudioHost host;
    host.start(sr, bs, backend);

    WsServerConfig cfg{};
    cfg.bind_address = "127.0.0.1";
    cfg.port = port;
    cfg.session_token = token;

    LoopbackWsServer server(host, cfg);
    if (!server.start()) {
        std::cerr << "[ERROR] Failed to bind LoopbackWsServer on 127.0.0.1:" << port << "\n";
        return 1;
    }

    std::cout << "[HACK-EFFECT C++ HOST] Listening on ws://127.0.0.1:" << server.port()
              << "/ws?token=" << server.session_token() << "\n";
    std::cout.flush();

    // Run until interrupted
    while (server.is_running()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    return 0;
}
