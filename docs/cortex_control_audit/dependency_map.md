# Dependency Map: Neural DSP Cortex Control (v4.1.0)

## 1. Executive Summary
This document provides a comprehensive, evidence-grounded dependency map for **Neural DSP Cortex Control v4.1.0** (`Cortex Control.exe`, SHA-256: `9be548fb6cbd2e8c80715015c2a2f0f248c9b01a7165004e2b017ffe2b14e65a`).

The application is compiled as a 64-bit AMD64 PE32+ binary using **Microsoft Visual C++ 2022 (Linker v14.44)**. It incorporates an audio application engine built upon the **JUCE C++ framework**, an embedded declarative XML UI subsystem, a **Google Protocol Buffers v2** messaging pipeline, a **USB HID** control-plane communicator, and **Microsoft Edge WebView2** for cloud integration.

---

## 2. Static PE Import Table (DLLs & Key APIs)

| Module Name | Bound Functions | Key APIs & Subsystems Identified | Architectural Role in Cortex Control |
| :--- | :---: | :--- | :--- |
| **`SETUPAPI.dll`** | 7 | `SetupDiGetClassDevsW`, `SetupDiEnumDeviceInfo`, `SetupDiGetDeviceRegistryPropertyW`, `SetupDiBuildDriverInfoList`, `SetupDiEnumDriverInfoW`, `SetupDiDestroyDriverInfoList`, `SetupDiDestroyDeviceInfoList` | **Hardware Device Detection**: Scans Windows PnP device tree to detect Quad Cortex and Quad Cortex mini USB audio & control interfaces. Checks driver vendor string (`NeuralDSP`) and verifies minimum version `5.58`. |
| **`WS2_32.dll`** | 28 | `getaddrinfo`, `freeaddrinfo`, `getnameinfo`, socket ordinals (`closesocket`, `connect`, `recv`, `send`, `socket`, `bind`, `listen`, `accept`, `select`, `setsockopt`) | **Network Communications**: Handles socket connectivity diagnostics (`RemoteHostSocketCheckStrategy`), internet ping (`8.8.8.8`), and potential Wi-Fi device synchronization. |
| **`WININET.dll`** | 17 | `InternetOpenW`, `InternetConnectW`, `HttpOpenRequestW`, `HttpSendRequestExW`, `InternetReadFile`, `InternetWriteFile`, `HttpQueryInfoW` | **Cloud API Client**: Direct HTTPS client for REST operations against Cortex Cloud (`api.neuraldsp.com`), downloading presets, neural captures, and cabinet IRs. |
| **`WINMM.dll`** | 24 | `midiInOpen`, `midiInStart`, `midiInClose`, `midiInAddBuffer`, `midiInPrepareHeader`, `midiOutOpen`, `midiOutShortMsg`, `midiOutLongMsg`, `timeSetEvent`, `timeBeginPeriod` | **Windows Multimedia MIDI & Timers**: Handles hardware MIDI In/Out ports and high-precision multimedia timers for audio thread scheduling. |
| **`d3d11.dll`** | 1 | `D3D11CreateDevice` | **Direct3D 11 Backend**: Hardware-accelerated GPU graphics context creation for low-latency rendering of complex grid topologies and animated meters. |
| **`d2d1.dll`** | 1 | `D2D1CreateFactory` (Ordinal 1) | **Direct2D Rendering**: Vector graphics rendering for curve interpolation, parametric EQ plots, and anti-aliased UI components. |
| **`dxgi.dll`** | 1 | `CreateDXGIFactory` | **DirectX Swap Chains**: Buffer presentation and vsync timing control. |
| **`dcomp.dll`** | 1 | `DCompositionCreateDevice` | **DirectComposition**: Smooth window animations and hardware-composed visual layers. |
| **`dwmapi.dll`** | 1 | `DwmSetWindowAttribute` | **Desktop Window Manager**: Modern window framing, dark mode title bar styling, and acrylic effects. |
| **`ole32.dll`** | 15 | `CoInitializeEx`, `CoCreateInstance`, `DoDragDrop`, `RegisterDragDrop`, `RevokeDragDrop`, `OleInitialize` | **COM & Drag-and-Drop**: OLE subsystem initialization, inter-thread marshalling, and drag-and-drop support for presets, captures, and IR blocks. |
| **`CRYPT32.dll`** | 7 | `CertOpenStore`, `CertCloseStore`, `CertFindCertificateInStore` | **Certificate Validation**: Validates TLS certificates for secure communication with Neural DSP cloud services. |
| **`bcrypt.dll`** | 1 | `BCryptGenRandom` | **Cryptographic Primitives**: Cryptographically secure random number generation for tokens and nonce values. |
| **`ADVAPI32.dll`** | 36 | `RegOpenKeyExW`, `RegQueryValueExW`, `CryptAcquireContextW`, `GetUserNameW` | **Windows Registry & Security**: Reads driver registration parameters and system cryptographic providers. |
| **`KERNEL32.dll`** | 225 | `CreateFileW`, `ReadFile`, `WriteFile`, `CreateNamedPipeW`, `ConnectNamedPipe`, `InitializeCriticalSection`, `CreateThread` | **Core Win32 OS Runtime**: Memory allocation, multi-threading, synchronization primitives, and file I/O. |
| **`USER32.dll`** | 110 | `CreateWindowExW`, `DefWindowProcW`, `DispatchMessageW`, `GetMessageW`, `SetWindowPos` | **Win32 Windowing**: Top-level application window creation and message dispatch loop. |
| **`GDI32.dll`** | 23 | `CreateFontIndirectW`, `GetStockObject`, `DeleteObject` | **GDI Font Fallback**: Legacy font enumeration and text rendering fallback. |
| **`IMM32.dll`** | 7 | `ImmGetContext`, `ImmReleaseContext`, `ImmSetCompositionWindow` | **Input Method Editor**: Multilingual text input support for preset and scene naming. |
| **`dbghelp.dll`** | 4 | `MiniDumpWriteDump`, `SymInitialize` | **Crash Reporting**: Generates minidump files upon unhandled exceptions for diagnostic analysis. |

---

## 3. Dynamic & Runtime-Loaded Dependencies

These libraries are not linked directly into the static PE Import Directory; instead, they are loaded on-demand via `LoadLibraryW` / `GetProcAddress`:

### 3.1 `hid.dll` (Human Interface Device Subsystem)
* **Resolved Symbols**:
  * `HidD_GetHidGuid`
  * `HidD_GetAttributes`
  * `HidD_GetSerialNumberString`
  * `HidD_GetManufacturerString`
  * `HidD_GetProductString`
  * `HidD_SetFeature`
  * `HidD_GetFeature`
  * `HidD_SetNumInputBuffers`
  * `HidP_GetCaps`
  * `HidD_FreePreparsedData`
* **Evidence Location**: Offset `0x02257588` – `0x022576b0` in `.rdata`.
* **Purpose**: Primary control-plane communication channel between the PC desktop editor and the Quad Cortex hardware unit. Sends structured Protobuf command packets via USB HID Feature/Output reports and receives live parameter updates and metering streams via HID Input reports.

### 3.2 `cfgmgr32.dll` (Configuration Manager 32)
* **Resolved Symbols**: `CM_Locate_DevNodeW`, `CM_Get_Device_IDW`.
* **Evidence Location**: Offset `0x022576a8` in `.rdata`.
* **Purpose**: Correlates USB HID child devices with the parent USB composite device node and the Thesycon USB Audio driver.

### 3.3 Microsoft Edge WebView2 (`WebView2Loader.dll`)
* **Classes Discovered**:
  * `UICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler`
  * `UICoreWebView2CreateCoreWebView2ControllerCompletedHandler`
  * `UICoreWebView2WebMessageReceivedEventHandler`
  * `UICoreWebView2NavigationCompletedEventHandler`
  * `UICoreWebView2ExecuteScriptCompletedHandler`
* **Evidence Location**: MSVC RTTI descriptors in `.rdata` (Offset `0x02241b00` – `0x02242000`).
* **Purpose**: Renders OAuth login flows, web user account profile pages, and the Cortex Cloud marketplace within the native application window without leaving the editor.

---

## 4. Third-Party Framework & Component Catalog

```
+---------------------------------------------------------------------------------------+
|                              Neural DSP Cortex Control v4.1.0                          |
+---------------------------------------------------------------------------------------+
|  Application Domain (neural::cortex::common)                                           |
|  - 493 Controller & Task classes (ApplicationStateController, GridViewController, etc)|
+---------------------------------------------------------------------------------------+
|  UI & Rendering Backend                                                               |
|  - JUCE Framework (juce::Component, juce::AudioProcessorValueTreeState, juce::Path)   |
|  - Microsoft Direct2D (d2d1.dll), Direct3D 11 (d3d11.dll), DirectWrite               |
|  - Microsoft Edge WebView2 (Cloud / OAuth embedded web container)                     |
+---------------------------------------------------------------------------------------+
|  Data & Serialization Layer                                                           |
|  - Google Protocol Buffers v2 / v3 (cortex_protobuf_v2 namespace, 285 message types)  |
|  - Declarative XML Views (514 embedded XML view controller definitions)              |
+---------------------------------------------------------------------------------------+
|  Hardware & Device Communication                                                      |
|  - Windows SetupAPI (PnP Device enumeration & driver validation)                      |
|  - Windows HID Subsystem (hid.dll - DeviceReportStream, DeviceRequestId)             |
|  - Thesycon USB Audio 2.0 Class Driver (Kernel tusbaudio.sys, ASIO x64 wrapper)      |
|  - Windows Multimedia MIDI (WINMM.dll - MIDI In/Out ports)                           |
+---------------------------------------------------------------------------------------+
```

### 4.1 JUCE Framework
* **Namespace**: `juce::`
* **Count**: 1,228 distinct RTTI classes identified.
* **Modules Detected**:
  * `juce_core`: String, File, MemoryBlock, PropertiesFile, Thread, CriticalSection.
  * `juce_graphics`: Graphics, Colour, Path, Font, GlyphArrangement.
  * `juce_gui_basics`: Component, Button, Slider, Label, Viewport, LookAndFeel.
  * `juce_gui_extra`: OpenGLContext, WebBrowserComponent.
  * `juce_audio_basics`: AudioBuffer, MidiMessage, MidiBuffer.
  * `juce_audio_processors`: AudioProcessor, AudioProcessorValueTreeState.

### 4.2 Google Protocol Buffers (cortex_protobuf_v2)
* **Descriptor Namespace**: `cortex_protobuf_v2::`
* **Count**: 285 distinct message and enum types identified.
* **Role**: Defines every domain entity in the Quad Cortex ecosystem: presets, scenes, grid blocks, splitters/mixers, CPU load, tuner, global EQ, device settings, cloud transfers, and diagnostic dumps.

---

## 5. Security & Verification Status
* **Authenticode Publisher**: `Neural DSP Technologies Oy`
* **Verification Status**: `Valid` (Self-verified on Windows host via `Get-AuthenticodeSignature`).
* **Timestamp Authority**: DigiCert Trusted G4 RSA4096 SHA256 TimeStamping CA.
* **Integrity Guarantee**: Executable binary has not been modified, patched, or tampered with.
