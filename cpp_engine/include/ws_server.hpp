#pragma once

#include "audio_host.hpp"

#include <atomic>
#include <cstdint>
#include <string>
#include <thread>
#include <vector>

namespace hack_effect {

struct WsServerConfig {
    std::string bind_address{"127.0.0.1"};
    uint16_t port{8765};
    std::string session_token;
    std::vector<std::string> allowed_origins{
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173"
    };
};

class LoopbackWsServer {
public:
    LoopbackWsServer(AudioHost& host, WsServerConfig config);
    ~LoopbackWsServer();

    LoopbackWsServer(const LoopbackWsServer&) = delete;
    LoopbackWsServer& operator=(const LoopbackWsServer&) = delete;

    bool start();
    void stop();

    bool is_running() const noexcept { return running_.load(std::memory_order_acquire); }
    uint16_t port() const noexcept { return bound_port_.load(std::memory_order_acquire); }
    const std::string& session_token() const noexcept { return config_.session_token; }

    // Exposed so unit tests can validate JSON command handling directly in-memory
    // as well as over real loopback WebSocket sockets.
    std::string handle_json_message(const std::string& json_payload);

    static std::string generate_csprng_token();
    bool is_origin_allowed(const std::string& origin) const;

private:
    void accept_loop();
    void handle_client_socket(uintptr_t client_sock);

    AudioHost& host_;
    WsServerConfig config_;
    std::atomic<bool> running_{false};
    std::atomic<bool> stop_requested_{false};
    std::atomic<uint16_t> bound_port_{0};
    uintptr_t listen_sock_{~uintptr_t(0)};
    std::thread accept_thread_;
};

} // namespace hack_effect
