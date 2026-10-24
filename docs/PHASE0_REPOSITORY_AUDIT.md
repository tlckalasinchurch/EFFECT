# Phase 0 — Repository Audit & Architecture Baseline

**Project**: กดจนหลอนTone (NAM Guitar Workstation)  
**Target Platform**: Windows 10/11 Desktop (x64)  
**Hardware Grounding**: Line 6 POD Studio UX1 (ToneDirect / WASAPI & ASIO)  
**Date**: October 24, 2026  
**Branch**: `feat/pro-nam-desktop`

---

## 1. Executive Summary & Verification Baseline

This audit grounds the development roadmap on verified source code and measured runtime behavior rather than assumptions.

### Verified Test Baseline
- **Audit Suite (`audit_test.py`)**: `14/14 passed` (ALL CLEAR).
  - Modules: Engine, FastAPI server, DSP 256-sample block, silence/NaN guards, lowcut filter, UX1 auto-detection, callback stereo fill, Tuner pitch detection (A2=110 Hz), Factory presets, Kemper packs, TONE3000 discovery, 65 registered API routes, pywebview integration.
- **Pytest Suite (`pytest tests -q`)**: `291 passed, 3 skipped, 4 warnings, 665 subtests passed in 13.86s`.
- **C++ Native Engine Suite (`cpp_engine/build/Release/hack_effect_tests.exe`)**:
  - `[PASS] test_spsc_ring_buffer`
  - `[PASS] test_param_registry_dual_units`
  - `[PASS] test_audio_callback_nan_guard_and_bypass`
  - `[PASS] test_ipc_protocol_and_security`
  - `[PASS] test_phase2_amp_and_cab_python_parity (max_amp_err=1.19e-07, max_conv_err=0, max_cab_err=4.76e-07)`
  - `[PASS] test_phase3_cloned_flagship_dsp (Overdrive + Neural Stereo Doubler + QC Ducking Delay + Kemper Morph)`
- **HTTP / API Server Response Time**: `/api/status` round-trip is **~8.1 ms**; process memory is **~98 MB to 131 MB**.

---

## 2. Current Architecture & Working Features

### Working Features Verified in Code
1. **Signal Chain**:
   - Noise Gate (`NoiseGate`): RMS detection, threshold, hold, release, range dB.
   - Overdrive (`TubeScreamer`): Asymmetric diode soft-clipping, tone filter, drive, level.
   - Amplifier (`GuitarAmp`): Tube saturation, gain, 3-band tone stack (Bass, Mid, Treble, Presence).
   - Cabinet IR Convolver (`CabSimulator`): Partitioned/direct impulse response convolution, high/low cut filters.
   - Delay (`StereoDelay` / `DuckingDelay`): Tempo sync, feedback, ducking sensitivity, stereo ping-pong.
   - Reverb (`PlateReverb` / `RoomReverb`): Multi-comb filter Schroeder/Moorer matrix, damping, mix.
   - World Class DSP (`WorldClassAudioProcessor`): Crest-factor anti-squash, true stereo imaging, mastering limiter.
2. **NAM Engine**:
   - JSON `.nam` (WaveNet architecture).
   - Binary `.namb` / `BMAN` / `NAMB` A2 SlimmableContainer formats.
   - Pre-compiled C99 dynamic library (`engine/nam_c99.dll`) for accelerated A2 inference.
3. **TONE3000 Cloud Integration**:
   - Live real-time catalog search and 1-click loading directly into the signal chain.
   - OAuth 2.0 PKCE flow (`server.py` + `t3k_fastapi.py`).
4. **Hardware Rig Modeling**:
   - Kemper Profiler (`.kipr` & `.rigpack` importer, category browser, MIDI CC mapping).
   - Quad Cortex Scene Manager (Scenes A through H, morphing controller A↔B, parallel clean path blend).
   - Mooer GE150 preset importer/exporter.

---

## 3. Audio Callback and Threading Model

### Audio Thread Rules
| Rule | Status | Implementation Details |
| :--- | :---: | :--- |
| **No File I/O** | Compliant | IRs and NAM weights are loaded into RAM in worker threads; the callback only reads pre-allocated buffers. |
| **No Network Calls** | Compliant | TONE3000 API and REST requests run strictly in asynchronous FastAPI worker threads. |
| **No Blocking Locks** | Compliant | Audio thread in `cpp_engine` uses a lock-free SPSC queue (`spsc_queue.hpp`). In `engine/audio.py`, state locks (`ENGINE_STATE_LOCK`, `_lock`) are non-blocking or atomic value reads. |
| **No Heavy Math in Callback** | Compliant | Pitch detection for the tuner is decoupled to `AudioTunerWorker` (daemon thread). Audio callback only copies a short slice (<0.001 ms). |
| **Priority Elevation** | Compliant | `set_realtime_priority()` invokes Win32 `SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS)`. `cpp_engine` invokes `AvSetMmThreadCharacteristicsW(L"Pro Audio", &task_index)`. |

---

## 4. NAM Model Compatibility Analysis

| Format | Extension | Architecture | Engine Support | Performance |
| :--- | :--- | :--- | :--- | :--- |
| **Standard NAM** | `.nam` (JSON) | WaveNet | `engine/nam.py` (`WaveNet`) | Python/NumPy (~1.2 ms per 256 samples) |
| **TONE3000 A2** | `.namb` (Binary) | SlimmableContainer (A2) | `engine/nam.py` (`SlimmableWaveNet`) + `engine/nam_c99.dll` | C99 Native (~0.18 ms per 256 samples) |
| **TONE3000 Bundle** | `.t3kpreset` | Amp + Cab + Metadata | `engine/tone3000_importer.py` | Direct extraction & injection into Chain |
| **Legacy LSTM** | `.nam` (LSTM) | LSTM | Requires NeuralAmpModelerCore C++ | Under Phase 1/2 integration |

---

## 5. Latency Capabilities & Target Audio Hardware Analysis

### Target Hardware: Line 6 POD Studio UX1
- **Driver**: Line 6 UX1 v4.2.7.7 (USB 1.1/2.0 Audio Device)
- **Native Operating Mode**: `48000 Hz, 24-Bit`
- **Host APIs Available**:
  - `Windows WASAPI` (Devices 15 & 17): Direct driver access, native 48 kHz.
  - `ASIO`: Available when using ASIO4ALL or Line 6 ASIO driver.
  - `MME / DirectSound`: Emulated layers (unsuitable for pro audio due to >40 ms buffer latency).
- **Latency Measurements at 48000 Hz**:
  - **128 samples**: Hardware deadline `2.67 ms`. Average DSP `0.74 ms`. Suitable with ASIO/WASAPI Exclusive.
  - **256 samples**: Hardware deadline `5.33 ms`. Average DSP `1.01 ms`. Total round-trip latency `~10.5 ms` (imperceptible to human ear; 100% glitch-free on standard Windows scheduling).

---

## 6. Open Source Component Evaluation & License Constraints

### Detailed Evaluation Table

| Repository | License | Key Strengths | Integration Decision |
| :--- | :---: | :--- | :--- |
| **NeuralAmpModelerCore** | **MIT** | Reference C++ DSP foundation; clean separation from UI/JUCE; Eigen SIMD acceleration; supports WaveNet, LSTM, Linear. | **Primary C++ NAM Foundation**. Safe to compile and link directly into native DLL / host. |
| **Plectrify** | **None (ARR)** | Embedded web UI in desktop host; TONE3000 workflow; scene switching. | **Architectural Reference Only**. Do NOT copy source code. We use our existing custom Web UI, FastAPI, and WebSocket IPC. |
| **NeuralRack** | **BSD-3** | Zero-latency partitioned IR convolution; latency compensation; safe buffer management. | **Permissive Reference**. Algorithms for partitioned convolution and resampling can be adopted cleanly. |
| **AmpForge** | **GPL-3.0** | Modular, drag-and-drop reorderable DSP signal chain. | **Conceptual Reference**. GPL prevents direct source copying into permissive projects. We implement modular chain reordering natively in `engine/dsp.py` and `cpp_engine`. |

---

## 7. Gap Analysis & Roadmap for Phases 1–4

1. **Phase 1 (Open Source Integration)**:
   - Integrate standard WaveNet and LSTM support from NeuralAmpModelerCore concepts into native inference.
   - Clean-room architectural design honoring license boundaries.
2. **Phase 2 (Native Audio Engine)**:
   - Implement **dynamic reorderable effects chain** in `GuitarSignalChain` (`engine/dsp.py` and `cpp_engine`).
   - Add zero-latency partitioned IR convolution with automatic resampling.
   - Add safe crossfading during preset/scene switching to eliminate switching clicks.
3. **Phase 3 (Professional Desktop GUI)**:
   - Add visual **Signal Chain Drag-and-Drop / Reordering** in `web/index.html` and `web/app.js`.
   - Add **Clean / Rhythm / Lead 3-Scene Quick Switcher** in addition to the 8 Cortex scenes.
   - Add **MIDI Learn Modal** for physical footswitch / expression pedal assignment.
   - Add **A/B Comparison Switcher** for instant tone matching.
4. **Phase 4 (Regression & Verification)**:
   - Maintain 100% test compatibility for Kemper, Mooer, and TONE3000.
   - Benchmark latency and CPU under sustained playback.
