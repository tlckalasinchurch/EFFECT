# Target Inventory & Ecosystem Catalog

## 1. Primary Neural DSP Targets

### Target A: Cortex Control (Desktop Editor)
* **Application Name**: Cortex Control
* **Installed Location**: `C:\Program Files\Neural DSP\Cortex Control\Cortex Control.exe`
* **File Version**: `4.1.0.0`
* **File Size**: 67,060,088 bytes (63.95 MB)
* **SHA-256**: `9be548fb6cbd2e8c80715015c2a2f0f248c9b01a7165004e2b017ffe2b14e65a`
* **PE Architecture**: PE32+ (x86-64 / AMD64 executable)
* **Digital Signature**: Neural DSP Technologies Oy (Verified Authenticode)
* **Framework & Tooling**:
  * **Audio/GUI Core**: C++ JUCE Framework (`juce_` namespace, 8,081 symbols matched).
  * **Graphics Backend**: Direct2D, DirectWrite, Direct3D 11 (`d3d11.dll`, `d2d1.dll`).
  * **Embedded Web Engine**: Microsoft Edge WebView2 (`WebView2Loader.dll`).
  * **Serialization / Wire Protocol**: Google Protocol Buffers v2 (`cortex_protobuf_v2` descriptor with 153 distinct message classes).
  * **Embedded UI Layouts**: 514 XML layout and view controller definitions extracted to `scratch/cortex_re/`.
* **Primary Role**: Official desktop companion editor for Neural DSP Quad Cortex. Controls the 4-row grid, 8 scenes (A-H), stomps, Gig View, cab simulator, and global EQ over USB/WiFi.

---

### Target B: Quad Cortex mini Installer / Driver
* **Executable Name**: `Neural DSP Quad Cortex mini v5.74.0.exe`
* **Workspace Location**: `c:\Users\Administrator\Desktop\Hack-effect\Neural DSP Quad Cortex mini v5.74.0.exe`
* **File Version**: `5.74.0.23632`
* **File Size**: 6,429,392 bytes (6.13 MB)
* **SHA-256**: `2340ec672bb6d4d55c9124a1fe2d28b1996f9e839c53bc55113b9543d4b1bb56`
* **PE Architecture**: PE32 (32-bit x86 GUI executable)
* **Identity Verified**: **Thesycon USB Audio 2.0 Class Driver Self-Extracting Installer** for Windows (build date: 2025-10-07).
* **Hardware USB Identity**:
  * **USB VID / PID**: `USB\VID_152A&PID_892F` ("Quad Cortex mini")
  * **Device Setup Class GUID**: `{27ED5E6D-F002-4774-8B76-A65A0CF80FED}`
  * **ASIO Driver GUID**: `{EEFF0306-8C65-4262-B564-A2AD904FA021}`
* **Analysis Verdict**: This binary is exclusively a kernel-mode USB audio driver installer for Windows host machines. It does not contain DSP algorithms, neural models, firmware images, or editor GUI code. Execution is safely bypassed.

---

## 2. Additional Evaluated Applications

### Target C: MOOER Studio for GE150
* **Location**: `C:\Program Files (x86)\Mooer Audio Corp\Mooer Studio for GE150\`
* **Installer Reference**: `Mooer_GE150_WIN_Setup_V1.3.8.exe`
* **Architecture**: 32-bit x86 C++ / Qt 5.9.8 GUI.
* **Findings**:
  * Fixed 9-stage signal chain (`FX/COMP -> DS/OD -> AMP -> CAB -> NS -> EQ -> MOD -> DELAY -> REVERB`).
  * 65 Amp models, 36 Cab IRs, 16 Overdrives, 19 Modulations, 5 Delays, 4 Reverbs.
  * Preset format: JSON-based `.mo` document containing hex/decimal parameter blocks.
* **Status in NAM**: Fully reverse engineered and integrated via `engine/mooer_models.py` and `engine/mooer_preset.py`.

### Target D: Kemper Profiler / Rig Manager
* **Location**: `C:\Program Files\Kemper Amps\Rig Manager\`
* **Findings**:
  * Proprietary binary `.kipr` presets and SQLite `.rigpack` bundles.
  * Rig structure with input definition, pre-stack stomps, profiled amp/stack, post-stack stomps, and delay/reverb.
* **Status in NAM**: Integrated via `engine/kemper_importer.py` (381 rigs loaded in library).

### Target E: TONE3000
* **Location**: `C:\ProgramData\TONE3000\Presets\`
* **Findings**:
  * `.t3kpreset` format with embedded NAM model references, IR files, and OAuth cloud API.
* **Status in NAM**: Integrated via `engine/tone3000_importer.py` and `t3k_fastapi.py`.

### Target F: Line 6 TonePort UX1
* **Hardware Type**: High-Z USB 1.1/2.0 guitar audio interface.
* **PortAudio Detection**: Integrated in `engine/audio.py` (`auto_detect_ux1()`) prioritizing ASIO, WASAPI, and DirectSound.
