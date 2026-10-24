#include "ws_server.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <iomanip>
#include <sstream>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <bcrypt.h>
#endif

namespace hack_effect {

namespace {

std::string json_escape(std::string_view s) {
    std::ostringstream o;
    for (char c : s) {
        switch (c) {
            case '"': o << "\\\""; break;
            case '\\': o << "\\\\"; break;
            case '\b': o << "\\b"; break;
            case '\f': o << "\\f"; break;
            case '\n': o << "\\n"; break;
            case '\r': o << "\\r"; break;
            case '\t': o << "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    o << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                      << static_cast<int>(static_cast<unsigned char>(c));
                } else {
                    o << c;
                }
        }
    }
    return o.str();
}

std::string extract_json_string(const std::string& json, const std::string& key) {
    const std::string pattern = "\"" + key + "\"";
    auto pos = json.find(pattern);
    if (pos == std::string::npos) return {};
    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return {};
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return {};
    std::string out;
    for (std::size_t i = pos + 1; i < json.size(); ++i) {
        if (json[i] == '\\' && i + 1 < json.size()) {
            out.push_back(json[i + 1]);
            ++i;
        } else if (json[i] == '"') {
            return out;
        } else {
            out.push_back(json[i]);
        }
    }
    return {};
}

bool extract_json_number(const std::string& json, const std::string& key, double& out_val) {
    const std::string pattern = "\"" + key + "\"";
    auto pos = json.find(pattern);
    if (pos == std::string::npos) return false;
    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return false;
    ++pos;
    while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {
        ++pos;
    }
    if (pos >= json.size()) return false;
    char* endptr = nullptr;
    const double val = std::strtod(json.c_str() + pos, &endptr);
    if (endptr == json.c_str() + pos || !std::isfinite(val)) {
        return false;
    }
    out_val = val;
    return true;
}

bool extract_json_bool(const std::string& json, const std::string& key, bool& out_val) {
    const std::string pattern = "\"" + key + "\"";
    auto pos = json.find(pattern);
    if (pos == std::string::npos) return false;
    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return false;
    ++pos;
    while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {
        ++pos;
    }
    if (json.compare(pos, 4, "true") == 0) {
        out_val = true;
        return true;
    }
    if (json.compare(pos, 5, "false") == 0) {
        out_val = false;
        return true;
    }
    return false;
}

std::string base64_encode(const uint8_t* data, std::size_t len) {
    static constexpr char kTable[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    out.reserve(((len + 2) / 3) * 4);
    for (std::size_t i = 0; i < len; i += 3) {
        const uint32_t b0 = data[i];
        const uint32_t b1 = (i + 1 < len) ? data[i + 1] : 0;
        const uint32_t b2 = (i + 2 < len) ? data[i + 2] : 0;
        const uint32_t triple = (b0 << 16) | (b1 << 8) | b2;
        out.push_back(kTable[(triple >> 18) & 0x3F]);
        out.push_back(kTable[(triple >> 12) & 0x3F]);
        out.push_back((i + 1 < len) ? kTable[(triple >> 6) & 0x3F] : '=');
        out.push_back((i + 2 < len) ? kTable[triple & 0x3F] : '=');
    }
    return out;
}

std::string compute_ws_accept_key(const std::string& client_key) {
    const std::string magic = client_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    uint8_t digest[20]{};
#ifdef _WIN32
    BCRYPT_ALG_HANDLE alg = nullptr;
    if (BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA1_ALGORITHM, nullptr, 0))) {
        BCryptHash(alg, nullptr, 0,
                   reinterpret_cast<PUCHAR>(const_cast<char*>(magic.data())),
                   static_cast<ULONG>(magic.size()),
                   digest, sizeof(digest));
        BCryptCloseAlgorithmProvider(alg, 0);
    }
#endif
    return base64_encode(digest, sizeof(digest));
}

std::string extract_http_header(const std::string& req, const std::string& header_name) {
    std::string lower_req = req;
    std::string lower_hdr = header_name + ":";
    std::transform(lower_req.begin(), lower_req.end(), lower_req.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    std::transform(lower_hdr.begin(), lower_hdr.end(), lower_hdr.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });

    auto pos = lower_req.find(lower_hdr);
    if (pos == std::string::npos) return {};
    pos += lower_hdr.size();
    while (pos < req.size() && (req[pos] == ' ' || req[pos] == '\t')) ++pos;
    auto end = req.find("\r\n", pos);
    if (end == std::string::npos) end = req.size();
    return req.substr(pos, end - pos);
}

std::string extract_query_token(const std::string& req) {
    auto line_end = req.find("\r\n");
    if (line_end == std::string::npos) return {};
    const std::string first_line = req.substr(0, line_end);
    auto qpos = first_line.find("token=");
    if (qpos == std::string::npos) return {};
    qpos += 6;
    std::size_t end = qpos;
    while (end < first_line.size() && first_line[end] != ' ' && first_line[end] != '&') {
        ++end;
    }
    return first_line.substr(qpos, end - qpos);
}

} // namespace

std::string LoopbackWsServer::generate_csprng_token() {
    uint8_t bytes[32]{};
#ifdef _WIN32
    BCryptGenRandom(nullptr, bytes, sizeof(bytes), BCRYPT_USE_SYSTEM_PREFERRED_RNG);
#endif
    std::ostringstream oss;
    for (uint8_t b : bytes) {
        oss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(b);
    }
    return oss.str();
}

LoopbackWsServer::LoopbackWsServer(AudioHost& host, WsServerConfig config)
    : host_(host), config_(std::move(config)) {
    if (config_.session_token.empty()) {
        config_.session_token = generate_csprng_token();
    }
}

LoopbackWsServer::~LoopbackWsServer() {
    stop();
}

bool LoopbackWsServer::is_origin_allowed(const std::string& origin) const {
    if (origin.empty()) {
        // Non-browser test/CLI clients without Origin are allowed when authenticated by token on loopback
        return true;
    }
    for (const auto& allowed : config_.allowed_origins) {
        if (origin == allowed) return true;
    }
    return false;
}

std::string LoopbackWsServer::handle_json_message(const std::string& json_payload) {
    if (json_payload.size() > 65536) {
        return R"({"type":"error","ok":false,"error":"payload_too_large"})";
    }

    const std::string type = extract_json_string(json_payload, "type");
    const std::string req_id = extract_json_string(json_payload, "req_id");

    auto make_err = [&](std::string_view code, std::string_view detail) {
        std::ostringstream o;
        o << R"({"type":"error","req_id":")" << json_escape(req_id)
          << R"(","ok":false,"error":")" << json_escape(code)
          << R"(","detail":")" << json_escape(detail) << R"("})";
        return o.str();
    };

    if (type.empty()) {
        return make_err("missing_type", "Message must include a valid 'type' string");
    }

    if (type == "ping") {
        std::ostringstream o;
        o << R"({"type":"pong","req_id":")" << json_escape(req_id)
          << R"(","ok":true,"engine_version":"0.1.0-phase1"})";
        return o.str();
    }

    if (type == "start_stream") {
        double sr = 48000.0;
        double bs = 128.0;
        extract_json_number(json_payload, "sample_rate", sr);
        extract_json_number(json_payload, "buffer_size", bs);
        std::string backend = extract_json_string(json_payload, "backend");
        if (backend.empty()) backend = "auto";

        if (sr < 8000.0 || sr > 192000.0 || bs < 16.0 || bs > 4096.0) {
            return make_err("invalid_audio_config", "sample_rate or buffer_size out of allowed bounds");
        }
        const bool ok = host_.start(static_cast<uint32_t>(sr), static_cast<uint32_t>(bs), backend);
        std::ostringstream o;
        o << R"({"type":"stream_started","req_id":")" << json_escape(req_id)
          << R"(","ok":)" << (ok ? "true" : "false")
          << R"(,"sample_rate":)" << host_.sample_rate()
          << R"(,"buffer_size":)" << host_.buffer_size()
          << R"(,"backend":")" << json_escape(host_.active_backend()) << R"("})";
        return o.str();
    }

    if (type == "stop_stream") {
        host_.stop();
        std::ostringstream o;
        o << R"({"type":"stream_stopped","req_id":")" << json_escape(req_id)
          << R"(","ok":true,"is_running":false})";
        return o.str();
    }

    if (type == "set_bypass") {
        bool gb = false;
        if (extract_json_bool(json_payload, "global_bypass", gb)) {
            host_.set_global_bypass(gb);
        }
        const std::string blk = extract_json_string(json_payload, "block");
        bool blk_en = true;
        if (!blk.empty() && extract_json_bool(json_payload, "enabled", blk_en)) {
            if (!host_.set_param_value(blk, "enabled", blk_en ? 1.0f : 0.0f)) {
                return make_err("unknown_block", "Block does not support bypass");
            }
        }
        std::ostringstream o;
        o << R"({"type":"bypass_updated","req_id":")" << json_escape(req_id)
          << R"(","ok":true,"global_bypass":)" << (host_.global_bypass() ? "true" : "false") << "}";
        return o.str();
    }

    if (type == "set_param") {
        const std::string block = extract_json_string(json_payload, "block");
        const std::string param = extract_json_string(json_payload, "param");
        const ParamSpec* spec = ParamRegistry::find(block, param);
        if (!spec) {
            return make_err("unknown_param", "Parameter not found in registry");
        }

        ParamValue applied{};
        double norm_d = 0.0;
        double val_d = 0.0;
        if (extract_json_number(json_payload, "normalized", norm_d)) {
            if (norm_d < 0.0 || norm_d > 1.0) {
                return make_err("out_of_range", "normalized value must be between 0.0 and 1.0");
            }
            if (!host_.set_param_normalized(block, param, static_cast<float>(norm_d), &applied)) {
                return make_err("apply_failed", "Failed to apply normalized parameter");
            }
        } else if (extract_json_number(json_payload, "value", val_d)) {
            if (val_d < static_cast<double>(spec->min_val) || val_d > static_cast<double>(spec->max_val)) {
                return make_err("out_of_range", "engineering value out of registered min/max range");
            }
            if (!host_.set_param_value(block, param, static_cast<float>(val_d), &applied)) {
                return make_err("apply_failed", "Failed to apply engineering parameter");
            }
        } else {
            return make_err("missing_value", "Provide either 'normalized' (0..1) or 'value'");
        }

        std::ostringstream o;
        o << std::fixed << std::setprecision(4);
        o << R"({"type":"param_updated","req_id":")" << json_escape(req_id)
          << R"(","ok":true,"block":")" << json_escape(spec->block)
          << R"(","param":")" << json_escape(spec->param)
          << R"(","normalized":)" << applied.normalized
          << R"(,"value":)" << applied.value
          << R"(,"display_value":)" << applied.display_value
          << R"(,"unit":")" << json_escape(spec->unit) << R"("})";
        return o.str();
    }

    if (type == "set_scene") {
        double idx = -1.0;
        if (!extract_json_number(json_payload, "scene_index", idx) || idx < 0.0 || idx > 7.0) {
            return make_err("invalid_scene", "scene_index must be 0..7 (Scenes A..H)");
        }
        const uint8_t sidx = static_cast<uint8_t>(idx);
        host_.set_scene(sidx);
        const auto scenes = host_.get_scenes();
        std::ostringstream o;
        o << R"({"type":"scene_updated","req_id":")" << json_escape(req_id)
          << R"(","ok":true,"scene_index":)" << static_cast<int>(sidx)
          << R"(,"label":")" << json_escape(scenes[sidx].label)
          << R"(","color_hex":")" << json_escape(scenes[sidx].color_hex) << R"("})";
        return o.str();
    }

    if (type == "reset_metrics") {
        host_.reset_metrics();
        std::ostringstream o;
        o << R"({"type":"metrics_reset","req_id":")" << json_escape(req_id) << R"(","ok":true})";
        return o.str();
    }

    if (type == "get_metrics") {
        const auto m = host_.metrics_snapshot();
        const uint64_t total_xruns = m.input_underflow + m.input_overflow + m.output_underflow + m.output_overflow;
        std::ostringstream o;
        o << std::fixed << std::setprecision(4);
        o << R"({"type":"metrics","req_id":")" << json_escape(req_id)
          << R"(","ok":true,"is_running":)" << (host_.is_running() ? "true" : "false")
          << R"(,"backend":")" << json_escape(host_.active_backend())
          << R"(","sample_rate":)" << host_.sample_rate()
          << R"(,"buffer_size":)" << host_.buffer_size()
          << R"(,"deadline_ms":)" << m.deadline_ms
          << R"(,"callback_count":)" << m.callback_count
          << R"(,"percentile_blocks":)" << m.percentile_blocks
          << R"(,"p50_ms":)" << m.p50_ms
          << R"(,"p95_ms":)" << m.p95_ms
          << R"(,"p99_ms":)" << m.p99_ms
          << R"(,"p99_9_ms":)" << m.p99_9_ms
          << R"(,"avg_ms":)" << m.avg_ms
          << R"(,"max_ms":)" << m.max_ms
          << R"(,"warmup_max_ms":)" << m.warmup_max_ms
          << R"(,"xruns":{"input_underflow":)" << m.input_underflow
          << R"(,"input_overflow":)" << m.input_overflow
          << R"(,"output_underflow":)" << m.output_underflow
          << R"(,"output_overflow":)" << m.output_overflow
          << R"(,"total":)" << total_xruns << "}"
          << R"(,"over_half_deadline_blocks":)" << m.over_half_deadline_blocks
          << R"(,"over_deadline_blocks":)" << m.over_deadline_blocks
          << R"(,"nonfinite_blocks":)" << m.nonfinite_blocks
          << R"(,"clipped_blocks":)" << m.clipped_blocks
          << R"(,"callback_errors":)" << m.callback_errors
          << R"(,"meters":{"input_dbfs":)" << m.input_dbfs
          << R"(,"output_dbfs":)" << m.output_dbfs
          << R"(,"input_linear":)" << m.input_peak_linear
          << R"(,"output_linear":)" << m.output_peak_linear << "}"
          << R"(,"gate_check":{"xrun_zero":)" << (m.xrun_zero ? "true" : "false")
          << R"(,"p99_under_50pct":)" << (m.p99_under_50pct ? "true" : "false")
          << R"(,"p99_9_under_80pct":)" << (m.p99_9_under_80pct ? "true" : "false")
          << R"(,"finite_clean":)" << (m.finite_clean ? "true" : "false")
          << R"(,"passed":)" << (m.passed_phase1_gate ? "true" : "false") << "}}";
        return o.str();
    }

    if (type == "get_state") {
        const auto params = host_.get_all_params();
        const auto& specs = ParamRegistry::specs();
        const auto scenes = host_.get_scenes();
        std::ostringstream o;
        o << std::fixed << std::setprecision(4);
        o << R"({"type":"state","req_id":")" << json_escape(req_id)
          << R"(","ok":true,"is_running":)" << (host_.is_running() ? "true" : "false")
          << R"(,"backend":")" << json_escape(host_.active_backend()) << R"(")"
          << R"(,"global_bypass":)" << (host_.global_bypass() ? "true" : "false")
          << R"(,"active_scene":)" << static_cast<int>(host_.active_scene())
          << R"(,"sample_rate":)" << host_.sample_rate()
          << R"(,"buffer_size":)" << host_.buffer_size()
          << R"(,"scenes":[)";
        for (std::size_t i = 0; i < scenes.size(); ++i) {
            if (i > 0) o << ",";
            o << R"({"index":)" << static_cast<int>(scenes[i].index)
              << R"(,"label":")" << json_escape(scenes[i].label)
              << R"(","color_hex":")" << json_escape(scenes[i].color_hex) << R"("})";
        }
        o << R"(],"params":[)";
        for (std::size_t i = 0; i < params.size() && i < specs.size(); ++i) {
            if (i > 0) o << ",";
            o << R"({"block":")" << json_escape(specs[i].block)
              << R"(","param":")" << json_escape(specs[i].param)
              << R"(","label":")" << json_escape(specs[i].label)
              << R"(","normalized":)" << params[i].normalized
              << R"(,"value":)" << params[i].value
              << R"(,"display_value":)" << params[i].display_value
              << R"(,"min":)" << specs[i].min_val
              << R"(,"max":)" << specs[i].max_val
              << R"(,"default":)" << specs[i].default_val
              << R"(,"unit":")" << json_escape(specs[i].unit) << R"("})";
        }
        o << "]}";
        return o.str();
    }

    return make_err("unknown_command", "Unsupported command type: " + type);
}

bool LoopbackWsServer::start() {
    stop();

    // Enforce loopback-only binding
    if (config_.bind_address != "127.0.0.1" && config_.bind_address != "localhost") {
        return false;
    }

#ifdef _WIN32
    WSADATA wsa{};
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        return false;
    }

    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) {
        return false;
    }

    int opt = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&opt), sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(config_.port);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    if (bind(s, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == SOCKET_ERROR) {
        closesocket(s);
        return false;
    }

    sockaddr_in bound{};
    int bound_len = sizeof(bound);
    if (getsockname(s, reinterpret_cast<sockaddr*>(&bound), &bound_len) == 0) {
        bound_port_.store(ntohs(bound.sin_port), std::memory_order_release);
    } else {
        bound_port_.store(config_.port, std::memory_order_release);
    }

    if (listen(s, SOMAXCONN) == SOCKET_ERROR) {
        closesocket(s);
        return false;
    }

    listen_sock_ = static_cast<uintptr_t>(s);
    stop_requested_.store(false, std::memory_order_release);
    running_.store(true, std::memory_order_release);
    accept_thread_ = std::thread(&LoopbackWsServer::accept_loop, this);
    return true;
#else
    return false;
#endif
}

void LoopbackWsServer::stop() {
    stop_requested_.store(true, std::memory_order_release);
#ifdef _WIN32
    if (listen_sock_ != ~uintptr_t(0)) {
        closesocket(static_cast<SOCKET>(listen_sock_));
        listen_sock_ = ~uintptr_t(0);
    }
#endif
    if (accept_thread_.joinable()) {
        accept_thread_.join();
    }
    running_.store(false, std::memory_order_release);
}

void LoopbackWsServer::accept_loop() {
#ifdef _WIN32
    while (!stop_requested_.load(std::memory_order_acquire)) {
        sockaddr_in client_addr{};
        int addr_len = sizeof(client_addr);
        SOCKET client = accept(static_cast<SOCKET>(listen_sock_),
                               reinterpret_cast<sockaddr*>(&client_addr),
                               &addr_len);
        if (client == INVALID_SOCKET) {
            break;
        }
        // Verify peer is strictly 127.0.0.1
        if (ntohl(client_addr.sin_addr.s_addr) != INADDR_LOOPBACK) {
            closesocket(client);
            continue;
        }
        handle_client_socket(static_cast<uintptr_t>(client));
    }
#endif
}

void LoopbackWsServer::handle_client_socket(uintptr_t raw_sock) {
#ifdef _WIN32
    SOCKET sock = static_cast<SOCKET>(raw_sock);
    DWORD timeout_ms = 5000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&timeout_ms), sizeof(timeout_ms));

    char buf[4096]{};
    int n = recv(sock, buf, sizeof(buf) - 1, 0);
    if (n <= 0) {
        closesocket(sock);
        return;
    }
    const std::string req(buf, static_cast<std::size_t>(n));

    // Validate Origin allowlist
    const std::string origin = extract_http_header(req, "Origin");
    if (!is_origin_allowed(origin)) {
        const char* forbidden = "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
        send(sock, forbidden, static_cast<int>( std::strlen(forbidden)), 0);
        closesocket(sock);
        return;
    }

    // Validate Session Token (Query param or X-HackEffect-Token header)
    std::string token = extract_query_token(req);
    if (token.empty()) {
        token = extract_http_header(req, "X-HackEffect-Token");
    }
    if (token != config_.session_token) {
        const char* unauth = "HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
        send(sock, unauth, static_cast<int>(std::strlen(unauth)), 0);
        closesocket(sock);
        return;
    }

    const std::string ws_key = extract_http_header(req, "Sec-WebSocket-Key");
    if (ws_key.empty()) {
        const char* bad_req = "HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
        send(sock, bad_req, static_cast<int>(std::strlen(bad_req)), 0);
        closesocket(sock);
        return;
    }

    const std::string accept_key = compute_ws_accept_key(ws_key);
    std::ostringstream hs;
    hs << "HTTP/1.1 101 Switching Protocols\r\n"
       << "Upgrade: websocket\r\n"
       << "Connection: Upgrade\r\n"
       << "Sec-WebSocket-Accept: " << accept_key << "\r\n\r\n";
    const std::string hs_str = hs.str();
    send(sock, hs_str.data(), static_cast<int>(hs_str.size()), 0);

    // WebSocket Frame Loop (RFC 6455)
    while (!stop_requested_.load(std::memory_order_acquire)) {
        uint8_t hdr[2]{};
        int r = recv(sock, reinterpret_cast<char*>(hdr), 2, 0);
        if (r != 2) break;

        const uint8_t opcode = hdr[0] & 0x0F;
        const bool masked = (hdr[1] & 0x80) != 0;
        uint64_t payload_len = hdr[1] & 0x7F;

        if (opcode == 0x8) { // Close frame
            break;
        }

        if (payload_len == 126) {
            uint8_t ext[2]{};
            if (recv(sock, reinterpret_cast<char*>(ext), 2, 0) != 2) break;
            payload_len = (static_cast<uint64_t>(ext[0]) << 8) | ext[1];
        } else if (payload_len == 127) {
            uint8_t ext[8]{};
            if (recv(sock, reinterpret_cast<char*>(ext), 8, 0) != 8) break;
            payload_len = 0;
            for (int i = 0; i < 8; ++i) {
                payload_len = (payload_len << 8) | ext[i];
            }
        }

        if (payload_len > 65536) {
            break; // Frame exceeds safety guard
        }

        uint8_t mask_key[4]{};
        if (masked) {
            if (recv(sock, reinterpret_cast<char*>(mask_key), 4, 0) != 4) break;
        }

        std::string payload(static_cast<std::size_t>(payload_len), '\0');
        std::size_t received = 0;
        while (received < payload_len) {
            int chunk = recv(sock, payload.data() + received,
                             static_cast<int>(payload_len - received), 0);
            if (chunk <= 0) break;
            received += static_cast<std::size_t>(chunk);
        }
        if (received != payload_len) break;

        if (masked) {
            for (std::size_t i = 0; i < payload.size(); ++i) {
                payload[i] ^= static_cast<char>(mask_key[i & 3]);
            }
        }

        const std::string reply = handle_json_message(payload);

        // Send unmasked server text frame
        std::vector<uint8_t> frame;
        frame.push_back(0x81); // FIN + Text opcode
        if (reply.size() < 126) {
            frame.push_back(static_cast<uint8_t>(reply.size()));
        } else if (reply.size() <= 65535) {
            frame.push_back(126);
            frame.push_back(static_cast<uint8_t>((reply.size() >> 8) & 0xFF));
            frame.push_back(static_cast<uint8_t>(reply.size() & 0xFF));
        } else {
            break;
        }
        frame.insert(frame.end(), reply.begin(), reply.end());
        send(sock, reinterpret_cast<const char*>(frame.data()), static_cast<int>(frame.size()), 0);
    }

    closesocket(sock);
#endif
}

} // namespace hack_effect
