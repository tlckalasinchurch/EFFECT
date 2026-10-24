# Phase 7 — Final Hardware Acceptance Test

**Project:** Hack-effect / กดจนหลอนTone  
**Branch:** `arena/c84662a0-effect` (continues `feat/pro-nam-desktop`)  
**Execution date:** 2026-10-24  
**Harness host:** Linux `e2b.local` 6.1.158+ x86_64, Python 3.11.2, g++ 12.2.0  
**Target production host (not available here):** Windows 11 + Line 6 POD Studio UX1 ASIO  

This report independently checks the Phase 6 claim that `hack_effect_host.exe` owns the production audio stream through the Line 6 UX1 ASIO driver. It does **not** treat a DSP microbenchmark, a realtime pacer loop, or a hardcoded GUI latency string as a live hardware pass.

**Production readiness: NOT CLAIMED.** Hardware-dependent criteria were not verified on Line 6 UX1.

---

## 1. Environment (what this run actually had)

| Item | Result |
|---|---|
| OS | Linux 6.1.158+ x86_64 (not Windows 11) |
| `run.bat` | Present, but it is a `cmd.exe` launcher. `bash run.bat` failed (`@echo: command not found`) |
| Line 6 UX1 | **Not present.** `/proc/asound/cards` does not exist. No ALSA devices. No `lsusb`. |
| ASIO | Windows COM / `HKLM\SOFTWARE\ASIO` only. Enumeration returned **zero drivers**. |
| `hack_effect_host.exe` | **Not in the tree.** `cpp_engine/build/` is gitignored; no prebuilt Windows binary shipped. |
| Native host built here | `cpp_engine/build/hack_effect_host` (ELF, Linux) compiled with g++ `-std=c++20` |
| Analog loopback cable | **Not present** |
| Python | 3.11.2 venv (repo pin is 3.14+ / Windows). Packages installed from PyPI. |
| PortAudio / libportaudio | **Not installed.** `sounddevice` cannot open a stream. |
| TONE3000 factory `.t3kpreset` | **Not present** (`C:\ProgramData\TONE3000\...` is a Windows path) |
| `nam_c99.dll` | Present as a Windows DLL; will not load on Linux |

Phase 6 numbers (17.50 ms UX1 round-trip, 23 ASIO blocks, 0 XRUNs on hardware) **could not be reproduced** in this environment. They remain unverified.

---

## 2. Independent check of the Phase 6 production-path claim

Phase 6 stated that launching `run.bat` / `main.py` makes `hack_effect_host.exe` own the Line 6 UX1 ASIO stream, that Python PortAudio is not opened, and that the GUI reports 17.50 ms driver latency.

Code inspection **before** the Phase 7 fixes found the following:

1. **The native host is optional.** `main.py` only spawned `cpp_engine/build/Release/hack_effect_host.exe`. If that file is missing (as in this checkout), Python remains the audio owner.
2. **Process-alive was treated as ASIO-alive.** If the host started, `engine.native_cpp_active = True` with **no query** of `active_backend()`. On this Linux build the host always falls back to `realtime_pacer` (synthetic 110 Hz sine, no DAC).
3. **Latency was invented.** `AudioEngine.audio_path_info()` returned hardcoded `reported_io_ms: 17.5`, `input_ms: 5.83`, `output_ms: 11.67`, driver name `ASIO UX1` whenever `native_cpp_active` was set — even if ASIO never started.
4. **The GUI toasted the same fiction:** `Native C++ ASIO Engine เชื่อมต่อสำเร็จ (17.5 ms UX1)` on WebSocket open, with no driver telemetry.
5. **DSP defaulted to bypass.** `AudioHost::global_bypass_` was `true`, and `cppBridge` never sent `set_bypass`. `process_block` therefore skipped screamer / amp / NAM / cab / delay unless something else unbypassed it.
6. **`try_start_wasapi` was declared and never defined.** Latent ODR/link hazard if anything called it.
7. **C++ `process_block` is a subset of the Python chain.** Gate, pitch, EQ, mod, reverb, stereo doubler, and GUI effects-order are **not** in the native callback. A passing DSP unit test is not live UX1 audio.
8. **Phase 5 ASIO test printed PASS when it only initialized COM, or SKIP with no drivers,** and `main()` still printed `ALL ... ASIO TESTS PASSED`. That is not hardware evidence.

These are the reasons Phase 6 cannot be accepted as a hardware pass.

---

## 3. Defects fixed in this Phase 7 pass

| Defect | Fix |
|---|---|
| Fake 17.5 ms / ASIO UX1 in `audio_path_info()` | Report live `cpp_host_info` from the host WebSocket. If ASIO is not running, `native_cpp_asio` is false, `reported_io_ms` is `None`, warning `native_cpp_not_asio`. |
| Fake 17.5 ms GUI toast | Toast only reports WS connect; latency must come from the host. |
| Host process treated as ASIO | `main.py` probes `snapshot_host()` and sets `native_cpp_asio` from `asio_running`. |
| Host binary path Windows-only | `engine/cpp_host.py::find_cpp_host_binary()` also looks for the Linux CMake binary. |
| DSP globally bypassed by default | `global_bypass_` default is `false`; GUI sends `set_bypass` on connect; scenes go to C++ via `set_scene`. |
| Missing `try_start_wasapi` body | Stub returns `false` (ASIO is the production path; pacer is the fallback). |
| WS server compiled but dead on Linux | POSIX sockets, SHA-1 Accept key, `/dev/urandom` tokens, `shutdown()` on stop. 401/403 tests now run on all platforms. |
| C++ tests claiming ASIO ALL PASSED | Skips stay skips. New `test_dsp_unbypass_changes_signal`. |
| `ctypes.WINFUNCTYPE` crash on Linux import | MIDI listener builds the winmm thunk only on Windows. |
| `sounddevice` import crash without libportaudio | Module stays importable; stream open still fails honestly. |

---

## 4. Required tests — commands, measurements, verdicts

### 4.1 Launch via `run.bat`

```text
$ bash run.bat
run.bat: line 1: @echo: command not found
run.bat: line 2: chcp: command not found
...
run.bat: line 12: syntax error near unexpected token `('
```

**Verdict: NOT VERIFIED** (Windows `cmd.exe` workflow cannot run here). This is an environment gap, not a product crash on Windows.

### 4.2 Native host, authenticated WebSocket, ASIO init

Built and started:

```text
g++ -std=c++20 -O2 -I cpp_engine/include ... -pthread -o cpp_engine/build/hack_effect_host
./hack_effect_host --port 18765 --token phase7_acceptance_token --backend auto --sr 48000 --buffer 128
```

Log:

```text
[HACK-EFFECT C++ HOST] Listening on ws://127.0.0.1:18765/ws?token=phase7_acceptance_token
```

Authenticated loopback WebSocket (token + Origin allowlist):

| Command | Result |
|---|---|
| `ping` | `{"type":"pong","ok":true}` |
| `set_param amp.gain normalized=0.8` | `ok: true, display_value: 80.0` |
| `set_scene 3` | `Scene D - High-Gain Lead` |
| Wrong token | HTTP `401 Unauthorized` |
| Bad Origin | HTTP `403 Forbidden` |
| Bind `0.0.0.0` | Rejected by unit test |

Live `get_metrics` / `get_state` after ~3 minutes:

```text
backend:               realtime_pacer
asio_running:           false
asio_driver:            ""
sample_rate:            48000
buffer_size:            128
roundtrip_latency_ms:   None   (0.0 from driver because ASIO never started; Python probe maps that to None)
callback_count:         75151
avg_ms:                 0.029
p99_ms:                 0.0505
xruns.total:            0
callback_errors:        0
nonfinite_blocks:       0
using_nam:              false
```

Callback count vs wall clock: `75151 * 128 / 48000 ≈ 200.4 s`, matching ~3:20 of process time. That proves the **pacer** is running at 48 kHz / 128. It does **not** prove ASIO.

**Verdict:** WebSocket + token auth **PASS** (software). ASIO UX1 init **NOT VERIFIED**.

### 4.3 Python PortAudio not running concurrently

Unit test `tests/test_phase7_acceptance.py::test_native_cpp_active_skips_portaudio_stream` asserts `AudioEngine.start()` returns `"Native C++ ASIO Engine Active"` and never calls `_open_stream` when `native_cpp_active` is set.

This machine has no libportaudio, so a live dual-open on UX1 was not observed.

**Verdict: NOT VERIFIED** on hardware. Software exclusion **implemented and unit-tested**.

### 4.4 Channels, sample rate, buffer, driver latency

| Field | Host reported | Hardware confirmed? |
|---|---|---|
| Sample rate | 48000 | Requested; not confirmed against UX1 clock |
| Buffer size | 128 | Pacer period; not ASIO `createBuffers` |
| Input channel | n/a | ASIO in 0 never created |
| Output channels | n/a | ASIO out 0/1 never created |
| Input latency samples | 0 | Not a driver figure |
| Output latency samples | 0 | Not a driver figure |
| Round-trip | **None** | Not measured |

**Verdict: NOT VERIFIED** for UX1. Requested 48 kHz / 128 is what the pacer used.

### 4.5 Load a real NAM model and play live input

- `nam_c99.dll` does not load on Linux → C++ test `[SKIP] test_phase4_nam_c99_native_inference`.
- No TONE3000 factory presets, no guitar DI, no UX1 ADC.
- New IPC `load_nam` exists but was not fed a real model through a live converter.

**Verdict: NOT VERIFIED.** A WaveNet microbenchmark is not a live NAM test.

### 4.6 GUI changes vs real audio

Control plane over loopback WS (gain, scene, bypass) **PASS** in software.

Not wired to analog output here. Remaining native DSP gaps that would still bite on Windows even if ASIO starts:

- Native callback order is fixed: screamer → amp **or** NAM → cab → delay.
- Gate, pitch, EQ, mod, reverb, doubler are **not** in `AudioHost::process_block`.
- GUI effects-order (`/api/chain/reorder`) updates Python `GuitarSignalChain` only.
- Preset load still goes to FastAPI; per-knob `sendParamNow` also hits C++ when WS is up.

**Verdict: NOT VERIFIED** for real audio. Control-plane JSON **PASS**. Full GUI-to-DAC parity **FAIL as a remaining blocker** (subset DSP + no reorder).

### 4.7 Sustained playback, callback errors, XRUNs, CPU, memory

Linux pacer, ~3.5 minutes, PID 1763:

| Metric | Value | Meaning |
|---|---|---|
| Callbacks | 75151 | Timed software blocks, not ASIO bufferSwitch |
| avg / p99 DSP | 0.029 / 0.0505 ms | ~1.9% of the 2.667 ms deadline |
| XRUNs | 0 | Pacer never talks to a driver; this is **not** a hardware XRUN count |
| callback_errors | 0 | |
| nonfinite_blocks | 0 | |
| RSS | 3876 kB | |
| VmPeak | 219148 kB | Virtual map; not working set |
| CPU | ~2.6% | Pacer thread |
| Threads | 3 | |

**Verdict: NOT VERIFIED** for live ASIO. Pacer DSP budget **PASS** as a software observation only.

### 4.8 Analog round-trip latency

No loopback cable, no interface, no measurement rig.

Driver-reported latency from this run: **none** (`asio_running=false`).

Phase 6's 17.50 ms figure is **not** reused.

**Verdict: NOT VERIFIED.** Analog round-trip remains unverified. Driver-reported latency is also unverified.

### 4.9 Shutdown, restart, device-disconnect recovery

| Action | Result |
|---|---|
| Host `terminate` / WS stop | `LoopbackWsServer::stop()` now `shutdown()` + `close` + join (unit-tested) |
| `main.py` `atexit` `cleanup_cpp_process` | Still present |
| UX1 unplug / WASAPI endpoint loss | **Not tested** (no device) |
| App restart after unplug | **Not tested** |

**Verdict: NOT VERIFIED** for audio-device disconnection. Process teardown of the C++ host **PASS** in software.

### 4.10 Existing C++, Python, and audit regression tests

**C++** (`stdbuf -oL ./cpp_engine/build/hack_effect_tests`):

```text
[PASS] test_spsc_ring_buffer
[PASS] test_param_registry_dual_units
[PASS] test_audio_callback_nan_guard_and_bypass
[PASS] test_dsp_unbypass_changes_signal (max_delta=0.447267)
[PASS] test_ipc_protocol_and_security
[PASS] test_phase2_amp_and_cab_python_parity (max_amp_err=1.19209e-07, max_conv_err=0, max_cab_err=4.76837e-07)
[PASS] test_phase3_cloned_flagship_dsp
[SKIP] test_phase4_nam_c99_native_inference (nam_c99.dll not found in current path)
[SKIP] test_phase5_asio_driver_enumeration_and_com (no ASIO drivers found in registry)
```

**Python** (`.venv/bin/python -m pytest tests -q`):

```text
289 passed, 15 skipped, 5 warnings, 641 subtests passed in 8.50s
```

Includes new `tests/test_phase7_acceptance.py` (no invented 17.5 ms; PortAudio short-circuit; GUI no longer toasts 17.5 ms UX1).

**JS:** `node --check web/app.js` → exit 0.

**Audit** (`.venv/bin/python audit_test.py`): **12/14**. Failures are environment, not DSP:

- `Audio: UX1 auto-detection` → `PortAudio library not found`
- `TONE3000: neural presets discovery` → `Expected 8 presets, got 0`

**Verdict: PASS** for the runnable software suites on this host. Hardware/NAM/T3K cases skipped or failed as missing data, not as silent green.

---

## 5. Criterion scoreboard

| # | Criterion | Status | Why |
|---|---|---|---|
| 1 | Launch via normal `run.bat` workflow | **NOT VERIFIED** | `run.bat` is Windows-only; bash parse failed. No WebView2 desktop session. |
| 2 | Native host + authenticated WS + actual ASIO stream init | **NOT VERIFIED** | WS+auth PASS. ASIO UX1 never initialized (`asio_running=false`, backend `realtime_pacer`). |
| 3 | Python PortAudio not running concurrently | **NOT VERIFIED** | Short-circuit unit-tested. No live UX1 session to dual-open. |
| 4 | Input/output channels, sample rate, buffer, driver latency | **NOT VERIFIED** | Host used 48 kHz / 128 pacer. No driver channel map or `getLatencies`. |
| 5 | Load a real NAM model and play live input through native DSP | **NOT VERIFIED** | No UX1 input, no loadable `nam_c99.dll`, no T3K factory models. |
| 6 | GUI gain / bypass / order / presets / scenes affect real audio | **NOT VERIFIED** | WS gain/scene/bypass PASS. No DAC. Native chain still omits reorder + several blocks. |
| 7 | Sustained playback: callback errors, XRUNs, CPU, memory | **NOT VERIFIED** | Pacer: 0 errors, 0 software XRUNs, ~2.6% CPU, 3.8 MB RSS. Not ASIO XRUNs. |
| 8 | Analog round-trip latency | **NOT VERIFIED** | No loopback cable. No driver-reported ASIO latency either. |
| 9 | Shutdown, restart, recovery after audio-device disconnect | **NOT VERIFIED** | Host process stop PASS. Device unplug not tested. |
| 10 | Existing C++, Python, audit regression tests | **PASS** | C++ unit/IPC/DSP PASS (NAM/ASIO SKIP). pytest 289 passed / 15 skipped. Audit 12/14 with two env fails. |

No criterion that requires Line 6 UX1 hardware is PASS.

---

## 6. Remaining blockers before a real hardware sign-off

Must be re-run on a Windows 11 machine with the UX1 connected, using `run.bat`:

1. Ship or build `cpp_engine/build/Release/hack_effect_host.exe` on that machine.
2. Confirm `get_state.asio_running == true` and `asio_driver` contains UX1 — **do not** trust a toast or `audio_path_info` default.
3. Confirm Python `engine.stream is None` while ASIO is running (Task Manager / PortAudio).
4. Record ASIO `getLatencies` input/output samples and ms at the actual buffer size.
5. Load a real NAM (TONE3000 or `.nam`) into the native host (`load_nam`) and play guitar DI.
6. Listen: gain, bypass, scenes, presets. Native DSP still needs gate/pitch/EQ/mod/reverb/reorder if those GUI controls must be audible.
7. Capture ≥ several minutes of ASIO callback XRUNs / `callback_errors` / CPU / RSS.
8. If a hardware loopback cable exists, measure analog RTT separately from driver `getLatencies`.
9. Unplug UX1, confirm the app reports the failure (not a fake 17.5 ms success), then replug and recover.
10. Re-run `hack_effect_tests.exe`, `pytest tests`, and `audit_test.py` on that Windows box.

Until those complete, **do not ship this as a production ASIO guitar workstation.**

---

## 7. How to re-run this software harness

```bash
# C++ (no CMake required)
mkdir -p cpp_engine/build && cd cpp_engine/build
g++ -std=c++20 -O2 -Wall -I../include -c ../src/*.cpp ../tests/test_phase1.cpp
g++ -pthread -o hack_effect_tests param_registry.o metrics.o dsp_blocks.o asio_driver.o audio_host.o ws_server.o test_phase1.o
g++ -pthread -o hack_effect_host  param_registry.o metrics.o dsp_blocks.o asio_driver.o audio_host.o ws_server.o main.o
stdbuf -oL ./hack_effect_tests

# Python
python3 -m venv .venv
.venv/bin/pip install fastapi 'uvicorn[standard]' pydantic python-multipart numpy scipy sounddevice pytest pytest-asyncio starlette httpx pywebview
.venv/bin/python -m pytest tests -q
.venv/bin/python audit_test.py
node --check web/app.js
```

On Windows with UX1, the same host binary (MSVC) plus `run.bat` is the only path that can flip criteria 1–9 off **NOT VERIFIED**.
