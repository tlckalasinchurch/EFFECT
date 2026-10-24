# Hack-Effect Native C++ Engine — Phase 1 IPC Contract (`v1`)

> **Clean-Room & Isolation Policy:**
> This contract governs the isolated `cpp_engine/` native host, metrics collector, and loopback WebSocket IPC server. Existing Python DSP files (`engine/dsp.py`, `engine/convolver.py`, `server.py`, `config.py`) remain untouched so ongoing F1/F2 listening-gate work is never disturbed.

---

## 1. Security & Transport Boundary

- **Bind Address:** `127.0.0.1` only (IPv4 loopback). Binding to `0.0.0.0` is rejected at startup.
- **Default Port:** `8765` (configurable via CLI `--port <uint16>`).
- **Session Token Authentication:**
  - Generated using CSPRNG (`BCryptGenRandom` on Windows) at process startup (32 bytes -> 64 hex chars), or passed explicitly via `--token <token>` for deterministic automated testing.
  - Clients must supply the token either in the WebSocket request query string (`ws://127.0.0.1:8765/ws?token=<TOKEN>`) or via header `X-HackEffect-Token: <TOKEN>`.
- **Origin Allowlist Validation:**
  - Browser clients that send an `Origin` header must match the explicit allowlist:
    - `http://127.0.0.1:8000`
    - `http://localhost:8000`
    - `http://127.0.0.1:5173`
    - `http://localhost:5173`
  - Non-browser CLI/test clients without an `Origin` header are permitted **only** if they present a valid session token and connect from `127.0.0.1`.
- **Frame Guards:**
  - Maximum incoming frame payload: `65536` bytes (64 KiB).
  - Strictly UTF-8 JSON objects (`type` and `req_id` fields validated). Unknown commands or out-of-range values return structured error responses without crashing or blocking the audio thread.

---

## 2. Threading & Real-Time Audio Safety Model

1. **Audio Thread (Real-Time Priority / WASAPI or ASIO Callback):**
   - **Zero Heap Allocations:** All timing rings (`TIMING_RING_BLOCKS = 8192`) and scratch buffers are preallocated before stream start.
   - **Zero Locks:** Never acquires `std::mutex` or OS locks.
   - **Control Plane -> Audio Thread:** Single-Producer Single-Consumer (SPSC) lock-free ring buffer (`ControlQueue<256>`) plus atomic snapshot state (`std::atomic` fields with `memory_order_acquire` / `memory_order_release`).
   - **Gain / Bypass Smoothing:** Every block bypass and master/trim gain transition uses a per-sample 1-pole exponential smoother ($\tau \approx 5\text{ ms}$) in the audio callback to guarantee **zero-click** switching during Scene changes (`A`–`H`) and rapid knob drags.
   - **NaN / Inf & Clip Guard:** Every output block is scanned for non-finite samples (`!std::isfinite(s)`). If detected, the block is zeroed immediately (`out.fill(0.0f)`) and `nonfinite_blocks` is incremented.

2. **Network / IPC Thread:**
   - Parses incoming JSON frames, validates parameter ranges and taper curves, pushes lightweight `ControlEvent` structs into the lock-free SPSC queue, and broadcasts 60 Hz real-time meter/telemetry frames when subscribed.

---

## 3. Dual-Unit Parameter Model (`normalized` + `value` + `unit`)

To support 60fps SVG/Canvas rotary knobs in the **Premium World-Class Dark UI** without duplicating math in JavaScript:
- Every parameter descriptor and update carries **both**:
  - `normalized`: `0.0` to `1.0` (used directly by UI knob arc ring angle `-135°` to `+135°`).
  - `value`: Engineering value in native units (e.g. `-55.0`, `360.0`, `20000.0`).
  - `unit`: Display unit string (`"dB"`, `"Hz"`, `"ms"`, `"%"`, `"st"`, `""`).
  - `taper`: `"linear"` | `"log_hz"` | `"db"` | `"discrete"`.
- A client `set_param` request may provide **either** `normalized` (`0.0..1.0`) **or** `value` (engineering unit). The C++ engine computes the counterpart deterministically using the parameter's registered taper and returns both in the ack/broadcast.

### Parameter Registry Subset (Phase 1 Host + Chain Skeleton)

| Block (`block`) | Param (`param`) | Kind | Min (`min`) | Max (`max`) | Default (`default`) | Unit (`unit`) | Taper (`taper`) |
|---|---|---|---|---|---|---|---|
| `input` | `trim` | `float` | `-24.0` | `+24.0` | `0.0` | `dB` | `linear` |
| `gate` | `enabled` | `bool` | `0.0` | `1.0` | `1.0` | `bool` | `discrete` |
| `gate` | `threshold` | `float` | `-80.0` | `-20.0` | `-55.0` | `dB` | `linear` |
| `gate` | `release` | `float` | `10.0` | `500.0` | `50.0` | `ms` | `linear` |
| `gate` | `hold` | `float` | `0.0` | `200.0` | `50.0` | `ms` | `linear` |
| `gate` | `range` | `float` | `-90.0` | `-20.0` | `-60.0` | `dB` | `linear` |
| `pitch` | `enabled` | `bool` | `0.0` | `1.0` | `0.0` | `bool` | `discrete` |
| `pitch` | `semitones` | `float` | `-24.0` | `+24.0` | `0.0` | `st` | `linear` |
| `pitch` | `glide` | `float` | `0.0` | `100.0` | `0.0` | `%` | `linear` |
| `pitch` | `mix` | `float` | `0.0` | `1.0` | `1.0` | `%` | `linear` |
| `screamer` | `enabled` | `bool` | `0.0` | `1.0` | `0.0` | `bool` | `discrete` |
| `screamer` | `drive` | `float` | `0.0` | `1.0` | `0.4` | `%` | `linear` |
| `screamer` | `tone` | `float` | `0.0` | `1.0` | `0.6` | `%` | `linear` |
| `screamer` | `level` | `float` | `0.0` | `1.0` | `0.7` | `%` | `linear` |
| `amp` | `enabled` | `bool` | `0.0` | `1.0` | `1.0` | `bool` | `discrete` |
| `amp` | `gain` | `float` | `0.0` | `1.0` | `0.65` | `%` | `linear` |
| `amp` | `bass` | `float` | `0.0` | `1.0` | `0.55` | `%` | `linear` |
| `amp` | `mid` | `float` | `0.0` | `1.0` | `0.50` | `%` | `linear` |
| `amp` | `treble` | `float` | `0.0` | `1.0` | `0.60` | `%` | `linear` |
| `amp` | `presence` | `float` | `0.0` | `1.0` | `0.60` | `%` | `linear` |
| `amp` | `master` | `float` | `0.0` | `1.0` | `0.70` | `%` | `linear` |
| `eq` | `enabled` | `bool` | `0.0` | `1.0` | `0.0` | `bool` | `discrete` |
| `cab` | `enabled` | `bool` | `0.0` | `1.0` | `1.0` | `bool` | `discrete` |
| `cab` | `level` | `float` | `0.0` | `2.0` | `1.0` | `%` | `linear` |
| `cab` | `lowcut` | `float` | `20.0` | `500.0` | `20.0` | `Hz` | `log_hz` |
| `cab` | `highcut` | `float` | `1000.0` | `20000.0` | `20000.0` | `Hz` | `log_hz` |
| `cab` | `mix` | `float` | `0.0` | `1.0` | `1.0` | `%` | `linear` |
| `mod` | `enabled` | `bool` | `0.0` | `1.0` | `0.0` | `bool` | `discrete` |
| `mod` | `rate` | `float` | `0.0` | `1.0` | `0.5` | `%` | `linear` |
| `mod` | `depth` | `float` | `0.0` | `1.0` | `0.5` | `%` | `linear` |
| `mod` | `mix` | `float` | `0.0` | `1.0` | `0.5` | `%` | `linear` |
| `delay` | `enabled` | `bool` | `0.0` | `1.0` | `0.0` | `bool` | `discrete` |
| `delay` | `time` | `float` | `20.0` | `2000.0` | `360.0` | `ms` | `linear` |
| `delay` | `feedback` | `float` | `0.0` | `0.95` | `0.35` | `%` | `linear` |
| `delay` | `mix` | `float` | `0.0` | `1.0` | `0.25` | `%` | `linear` |
| `reverb` | `enabled` | `bool` | `0.0` | `1.0` | `0.0` | `bool` | `discrete` |
| `reverb` | `decay` | `float` | `0.0` | `1.0` | `0.5` | `%` | `linear` |
| `reverb` | `tone` | `float` | `0.0` | `1.0` | `0.5` | `%` | `linear` |
| `reverb` | `mix` | `float` | `0.0` | `1.0` | `0.2` | `%` | `linear` |
| `master` | `volume` | `float` | `0.0` | `2.0` | `1.0` | `%` | `linear` |

---

## 4. Command & Response Messages

### 4.1 `ping`
**Request:**
```json
{ "type": "ping", "req_id": "1" }
```
**Response:**
```json
{ "type": "pong", "req_id": "1", "ok": true, "engine_version": "0.1.0-phase1" }
```

### 4.2 `get_state`
Returns full state for initializing the UI (devices, stream configuration, global bypass, active scene `0..7`, ordered signal chain blocks, and all parameters with both `normalized` and `value` + `unit`).

**Request:**
```json
{ "type": "get_state", "req_id": "2" }
```

### 4.3 `start_stream` / `stop_stream`
Starts or stops the native audio stream (`WASAPI` hardware backend or `null_realtime` pacer for deterministic CI/headless testing when hardware is busy).

**Request:**
```json
{
  "type": "start_stream",
  "req_id": "3",
  "sample_rate": 48000,
  "buffer_size": 128,
  "backend": "auto",
  "input_device_id": -1,
  "output_device_id": -1
}
```

### 4.4 `set_bypass`
Toggles global engine hard-bypass (smooth crossfade) or individual block bypass.

**Request:**
```json
{
  "type": "set_bypass",
  "req_id": "4",
  "global_bypass": true,
  "block": "amp",
  "enabled": false
}
```

### 4.5 `set_param`
Updates a parameter via lock-free SPSC command queue using either `normalized` (`0.0..1.0`) or engineering `value`.

**Request:**
```json
{
  "type": "set_param",
  "req_id": "5",
  "block": "amp",
  "param": "gain",
  "normalized": 0.75
}
```
**Response:**
```json
{
  "type": "param_updated",
  "req_id": "5",
  "ok": true,
  "block": "amp",
  "param": "gain",
  "normalized": 0.75,
  "value": 0.75,
  "display_value": 75.0,
  "unit": "%"
}
```

### 4.6 `set_scene`
Switches between Scenes `0..7` (`A`–`H`) without reallocating DSP state or reloading models/IRs, applying scene bypasses and parameter overrides atomically.

**Request:**
```json
{
  "type": "set_scene",
  "req_id": "6",
  "scene_index": 2
}
```

### 4.7 `get_metrics` / `reset_metrics`
Returns real-time timing percentiles (`p50_ms`, `p95_ms`, `p99_ms`, `p99_9_ms`, `max_ms`, `avg_ms`), `deadline_ms`, `xruns`, `over_deadline_blocks`, `over_half_deadline_blocks`, `nonfinite_blocks`, `clipped_blocks`, and Phase 1 gate evaluation (`pass_phase1_gate`).

**Request:**
```json
{ "type": "get_metrics", "req_id": "7" }
```
**Response:**
```json
{
  "type": "metrics",
  "req_id": "7",
  "ok": true,
  "is_running": true,
  "backend": "wasapi",
  "sample_rate": 48000,
  "buffer_size": 128,
  "deadline_ms": 2.667,
  "callback_count": 28125,
  "percentile_blocks": 8192,
  "p50_ms": 0.008,
  "p95_ms": 0.015,
  "p99_ms": 0.024,
  "p99_9_ms": 0.042,
  "avg_ms": 0.009,
  "max_ms": 0.081,
  "warmup_max_ms": 0.112,
  "xruns": {
    "input_underflow": 0,
    "input_overflow": 0,
    "output_underflow": 0,
    "output_overflow": 0,
    "total": 0
  },
  "over_half_deadline_blocks": 0,
  "over_deadline_blocks": 0,
  "nonfinite_blocks": 0,
  "clipped_blocks": 0,
  "callback_errors": 0,
  "meters": {
    "input_dbfs": -42.1,
    "output_dbfs": -42.1,
    "input_Linear": 0.0078,
    "output_linear": 0.0078
  },
  "gate_check": {
    "xrun_zero": true,
    "p99_under_50pct": true,
    "p99_9_under_80pct": true,
    "finite_clean": true,
    "passed": true
  }
}
```

---

## 5. Phase 1 Live Gate Criteria (Bypass / Passthrough @ 48 kHz)

| Buffer Size | Deadline ($T_{\text{buf}}$) | Max Allowed `p99` ($< 50\%$) | Max Allowed `p99.9` ($< 80\%$) | Max Allowed `XRUN` | Max Allowed `NaN/Inf` |
|---|---|---|---|---|---|
| **64 samples** | `1.333 ms` | `< 0.667 ms` | `< 1.067 ms` | `0` | `0` |
| **128 samples** | `2.667 ms` | `< 1.333 ms` | `< 2.133 ms` | `0` | `0` |
| **256 samples** | `5.333 ms` | `< 2.667 ms` | `< 4.267 ms` | `0` | `0` |
