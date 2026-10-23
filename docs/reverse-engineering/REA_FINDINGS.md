# Technical Reverse Engineering Findings (REA)

## 1. Target A: Cortex Control v4.1.0 Binary Reverse Engineering

### 1.1 Architecture & Subsystems
* **Executable**: `C:\Program Files\Neural DSP\Cortex Control\Cortex Control.exe`
* **Size**: 67,060,088 bytes | AMD64 PE32+
* **Framework**: Built on JUCE C++ audio application framework (`juce::Component`, `juce::AudioProcessorValueTreeState`).
* **Rendering Pipeline**: Direct2D and Direct3D 11 (`d2d1.dll`, `d3d11.dll`) with Microsoft Edge WebView2 for cloud/community integration.
* **Extraction Results**:
  Using string scanning, binary dissection, and XML stream parsing, 514 XML layout and view controller definitions were unpacked into `scratch/cortex_re/`.

### 1.2 Extracted UI Layouts & View Controllers
Key extracted controllers include:
1. `gridViewController.xml`: Defines the 4-row grid routing matrix, block insertion points, splitter (`combined_splitter`), and mixer (`hard_pan_mixer`) blocks.
2. `gigViewController.xml` & `gigViewEditor.xml`: Defines the 8 footswitch performance view, supporting Stomp mode, Scene mode, and Preset mode.
3. `cabsimPanelView.xml`: Dual cabinet IR loader with 3D mic distance/position sliders, mic model selector, and tube power-amp voicing.
4. `globalEQViewController.xml`: 5-band studio parametric EQ (low cut, low shelf, 3 mid peaking bands, high shelf, high cut).
5. `ioSettingsViewController.xml`: Multi-channel USB audio routing, input gain trims, ground lift, and XLR output levels.

### 1.3 Scene Architecture & Color Palette
Extracted from `sceneColours` within the binary:
* **Scene A**: Red (`#e74c3c`)
* **Scene B**: Cyan (`#00bcd4`)
* **Scene C**: Yellow (`#f1c40f`)
* **Scene D**: Violet (`#9b59b6`)
* **Scene E**: Green (`#2ecc71`)
* **Scene F**: Blue (`#3498db`)
* **Scene G**: Amber (`#e67e22`)
* **Scene H**: Magenta (`#e91e63`)

In Quad Cortex, each preset contains 8 scenes. Switching scenes never re-initializes neural models or IR buffers; it alters the `SceneBlockBypass` boolean map and interpolates parameters defined in `SceneParamOverride`.

### 1.4 Wire Protocol & Serialization
* Found references to `cortex_protobuf_v2` with 153 Protocol Buffer message definitions.
* Key message descriptors:
  * `BinaryPreset`: Root preset container including metadata, tempo, grid blocks, and scene definitions.
  * `Scene`: Contains `scene_index`, `name`, `color_id`, `block_bypasses`, and `parameter_overrides`.
  * `DeviceSync`: Bidirectional synchronization message over USB bulk endpoint / WebSocket for real-time knob syncing.

---

## 2. Target B: Quad Cortex mini Installer Analysis

* **Filename**: `Neural DSP Quad Cortex mini v5.74.0.exe`
* **File Size**: 6,429,392 bytes | 32-bit x86 PE executable.
* **Header Inspection**:
  * PE subsystem: Windows GUI.
  * Compiler / Packager: Thesycon Setup Stub / Self-Extracting Archive.
  * Product Name: "Quad Cortex mini USB Audio 2.0 Driver".
  * Driver Version: `5.74.0.23632`.
* **Hardware Identifiers Extracted**:
  * `USB\VID_152A&PID_892F`: Hardware ID for the Quad Cortex / Quad Cortex mini USB audio interface.
  * Device Setup Class GUID: `{27ED5E6D-F002-4774-8B76-A65A0CF80FED}`.
  * ASIO CLSID: `{EEFF0306-8C65-4262-B564-A2AD904FA021}`.
* **Confirmation**: The installer contains kernel `.sys` drivers (`tusbaudio.sys`), `.inf` setup files, and an ASIO DLL wrapper. It is not an executable DSP model or software emulator.

---

## 3. MOOER GE150 Reverse Engineering Summary

* **Binary**: `C:\Program Files (x86)\Mooer Audio Corp\Mooer Studio for GE150\GE150.exe`.
* **Framework**: Qt 5.9.8 (32-bit MSVC).
* **Signal Chain**: Fixed 9-stage module routing (`FX/COMP -> DS/OD -> AMP -> CAB -> NS -> EQ -> MOD -> DELAY -> REVERB`).
* **Catalog Extracted**:
  * 65 Amp models (Fender, Marshall, Vox, Mesa Boogie, Soldano, Peavey, Diezel, ENGL, EVH).
  * 36 Cabinet IRs with tube power-amp emulation (6L6, EL34, EL84) and 4 microphone models (SM57, MD421, U87, C414).
* **Preset Format**: JSON document with module enable bits and 0-100 normalized byte values, mapped to our engine via `engine/mooer_preset.py`.
