# Architecture Map: Neural DSP Cortex Control

## 1. System Overview & Component Diagram

Neural DSP Cortex Control is architected as a layered, multi-threaded C++ desktop application utilizing the **JUCE Framework**, a proprietary **Declarative Model-View-Controller (MVC)** UI engine, **Google Protocol Buffers v2** wire messaging, and a **USB HID control channel** paired with a **Thesycon USB Audio 2.0 Class driver**.

```
+---------------------------------------------------------------------------------------------------+
|                                  USER INTERFACE LAYER (C++ / JUCE)                                |
|  - XML Layout Engine (514 Declarative View Controller Definitions)                                |
|  - Custom LookAndFeel (Dark Theme, Sleek Knobs, SVG Asset Pipeline)                              |
|  - Direct2D / Direct3D 11 Hardware Rendering Backend                                              |
|                                                                                                   |
|  [Main Window]                                                                                    |
|   +-- TopbarViewController (Preset Info, Scene Bar, Tuner, CPU Load Meter)                        |
|   +-- GridViewController (4 Rows x 8 Columns Routing Matrix, Splitter / Mixer Nodes)              |
|   +-- GigViewController (8 Footswitch Performance View: Stomp, Scene A-H, Preset Modes)           |
|   +-- CabsimPanelViewController (Dual IR Cabinet Loader, 3D Mic Positioning, Tube Voicing)        |
|   +-- GlobalEQViewController (5-Band Studio Parametric Equalizer)                                 |
|   +-- DeviceSettingsViewController (Hardware, I/O Routing, Wi-Fi, MIDI, Updates)                 |
|   +-- CloudViewController (Microsoft Edge WebView2 Embedded Container)                            |
+---------------------------------------------------------------------------------------------------+
                                              |
                                              v
+---------------------------------------------------------------------------------------------------+
|                               STATE MANAGEMENT & DOMAIN LOGIC                                     |
|  - ApplicationStateController    - CortexStateController          - ConnectionStateController    |
|  - AuditionStateController       - CloudStateController           - DeviceBrowserListsState      |
|                                                                                                   |
|  Asynchronous Tasks:                                                                              |
|  - CreateNewPresetTask           - AuditionCaptureOnGridTask      - AuditionIrOnGridTask          |
|  - AddSetlistTask                - DeleteCaptureTask              - CopyModelsTask                |
+---------------------------------------------------------------------------------------------------+
                                              |
                                              v
+---------------------------------------------------------------------------------------------------+
|                               SERIALIZATION & WIRE PROTOCOL                                       |
|  - cortex_protobuf_v2 (Google Protocol Buffers v2 Specification)                                 |
|  - Descriptors: BinaryPreset, SceneMessage, GridMessage, CPULoadMessage, ModelPreset             |
|  - Binary Encoding: Length-delimited protobuf byte frames                                        |
+---------------------------------------------------------------------------------------------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
+------------------------------------------+     +------------------------------------------+
|      USB HID CONTROL CHANNEL (hid.dll)   |     |      AUDIO ENGINE LAYER (Thesycon ASIO)  |
|  - SetupAPI PnP Enumeration              |     |  - Kernel tusbaudio.sys                  |
|  - HidD_GetFeature / HidD_SetFeature     |     |  - VID: 0x152A | PID: 0x892F            |
|  - DeviceReportStream (HID IO Packets)   |     |  - ASIO x64 Wrapper                      |
|  - Request-Response via DeviceRequestId  |     |  - 48 kHz / 2048 Sample Buffer           |
|  - Bi-directional Real-time Knob Sync    |     |  - Multi-Channel USB Audio Streaming     |
+------------------------------------------+     +------------------------------------------+
                     |                                                 |
                     +------------------------+------------------------+
                                              |
                                              v
+---------------------------------------------------------------------------------------------------+
|                                 QUAD CORTEX HARDWARE UNIT                                         |
|  - SHARC+ DSP Core (Real-time Audio Processing, Neural Network Inference, IR Convolution)         |
|  - Embedded Linux OS (Communications Daemon, Preset Storage, Wi-Fi Engine)                        |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Declarative UI & Model-View-Controller (MVC) Pattern

### 2.1 View Controller Architecture
The application does not hardcode its UI widgets in monolithic C++ source files. Instead, it employs an extensible XML-driven declarative component hierarchy located in the namespace `neural::cortex::common::`:

* **`BasePanelViewController`**: Root class for all docked and floating parameter editor panels.
* **`GridViewController`**: Manages the 4-row DSP processing grid, drag-and-drop block placement, cable routing between rows, and splitter/mixer block placement.
* **`GigViewController`**: Renders the 8 footswitches (A through H) matching the physical hardware layout. Toggles between:
  * **Stomp Mode**: Individual block bypass toggles assigned to footswitches.
  * **Scene Mode**: Instant recall of Scenes A through H.
  * **Preset Mode**: Bank navigation (Up/Down) and preset slots A-D.
* **`CabsimPanelViewController` & `CabsimChannelPanelViewController`**: Dual cabinet impulse response editor featuring graphical 3D microphone placement (Distance and Position sliders), microphone model selection (SM57, MD421, U87, C414), and power amp tube saturation voicing (6L6, EL34, KT88).
* **`GlobalEQViewController`**: 5-band parametric equalizer layout with dynamic real-time frequency curve visualization and I/O assignment buttons (`assignOut12`, `assignOut34`).

### 2.2 XML Binding Contract
Each XML file (e.g., `023_globalEQViewController.xml`) defines layout associations, child controllers, widget types, bound properties, and message dispatch actions:

```xml
<globalEQViewController layout="globalEQPanel.xml" view="globalEQContainer" visible="true">
    <children>
        <child name="gainViewController" definition="globalEQSettingViewController.xml" 
               view="gainContainer" updateActionName="setGain" property="gain" 
               widgetType="knob" settingName="GAIN" valuePostfix=" dB"/>
        <child name="frequencyViewController" definition="globalEQSettingViewController.xml" 
               view="frequencyContainer" updateActionName="setFrequency" numDecimals="0" 
               property="frequency" widgetType="knob" settingName="FREQUENCY" valuePostfix=" Hz"/>
        <child name="qViewController" definition="globalEQSettingViewController.xml" 
               view="qContainer" updateActionName="setQ" property="q" 
               widgetType="knob" settingName="Q"/>
    </children>
</globalEQViewController>
```

When a user adjusts a UI knob, the controller invokes `updateActionName` (`setGain`), updates the in-memory parameter tree, and serializes a Protobuf message for transmission across the USB control channel.

---

## 3. Protocol Buffers Specification (`cortex_protobuf_v2`)

The application defines 285 distinct Protobuf message types in the `cortex_protobuf_v2` namespace. Key messages governing signal processing and device control include:

### 3.1 `BinaryPreset`
Root data structure representing a complete Quad Cortex preset:
* **`name`** (string): Preset title.
* **`uuid`** (string): Unique identifier.
* **`tempo`** (float): Preset BPM.
* **`grid`** (`GridMessage`): 4-row block arrangement, input blocks, output blocks, splitters, and mixers.
* **`scenes`** (repeated `SceneMessage`): Definitions for Scenes A through H.
* **`stomp_assignments`** (repeated `StompModeAssignment`): Footswitch-to-block mapping in Stomp mode.
* **`expression_settings`** (repeated `ExpPortSettings`): Expression pedal 1 & 2 curve assignments.

### 3.2 `SceneMessage` & Scene Architecture
Each preset contains 8 distinct scenes (`A` through `H`). Switching scenes does not interrupt audio or reload neural network weights into DSP memory; it executes a zero-latency state transition using:
* **`scene_index`** (uint32: 0 to 7).
* **`name`** (string): Scene label (e.g., "Clean", "Crunch", "Lead").
* **`color_id`** (uint32: 0 to 7): Associated color from the standard palette:
  * Scene A: `#e74c3c` (Red)
  * Scene B: `#00bcd4` (Cyan)
  * Scene C: `#f1c40f` (Yellow)
  * Scene D: `#9b59b6` (Violet)
  * Scene E: `#2ecc71` (Green)
  * Scene F: `#3498db` (Blue)
  * Scene G: `#e67e22` (Amber)
  * Scene H: `#e91e63` (Magenta)
* **`block_bypasses`** (`SceneBlockBypass`): Bitmask/map of boolean bypass states for all active grid nodes.
* **`parameter_overrides`** (repeated `ParamValue`): Specific block parameters altered for this scene (e.g., Amp Gain increased from 3.5 to 7.0, Delay Mix enabled).

### 3.3 `GridMessage` & Matrix Topology
Defines the 4-row signal matrix:
* **Rows 1 & 2**: Typically assigned to DSP Core 1.
* **Rows 3 & 4**: Typically assigned to DSP Core 2.
* **Routing Nodes**:
  * `combined_splitter`: Splits a row into two parallel signal paths with adjustable balance and frequency crossover.
  * `hard_pan_mixer`: Recombines parallel paths with pan and gain controls before hitting output stages.

### 3.4 Live Telemetry & Metering
* **`CPULoadMessage`**: Real-time DSP load reporting partitioned into `CPUChainLoad` (Chains 1-4) and `CPUColumnLoad`.
* **`GridModelMeterMessage`**: Real-time peak and RMS audio levels streamed back to the desktop app to animate block meters and I/O level bars.

---

## 4. Hardware Integration & Communications Protocol

### 4.1 Device Discovery & Verification Pipeline
When Cortex Control launches, `neural::cortex::usb::ConnectionStateController` executes the following sequence:

1. **PnP Device Search**: Calls Win32 SetupAPI (`SetupDiGetClassDevsW`, `SetupDiEnumDeviceInfo`, `SetupDiGetDeviceRegistryPropertyW`) querying for USB devices matching VID `0x152A`.
2. **Driver Verification**: Queries installed driver metadata. The application enforces a strict check:
   * Required Vendor: `NeuralDSP`
   * Minimum Driver Version: `5.58` (Workspace driver installer provides `5.74.0`).
   * If absent, logs: `"Could not find any Quad Cortex device audio/USB driver, please install latest driver from Neural DSP downloads website."`
3. **USB HID Handle Acquisition**: Resolves `hid.dll` and locates device interfaces using `HidD_GetAttributes`, matching Product Name `"Quad Cortex"` or `"Quad Cortex mini"`.
4. **Endpoint Binding**: Opens read/write handles via Win32 `CreateFileW` with `FILE_FLAG_OVERLAPPED` for non-blocking I/O.

### 4.2 HID Framing & `DeviceReportStream`
Communication does not use raw TCP sockets or bulk endpoints; it operates entirely over **USB HID Feature and Input/Output Reports**:
* **`DeviceReportStream`**: Streams chunks of serialized Protobuf messages encapsulated in HID reports.
* **`DeviceRequestId`**: 32-bit correlation counter matching outgoing requests to incoming responses.
* **Knob Synchronization**: When a physical rotary encoder is turned on the Quad Cortex, an asynchronous HID Input Report carrying a `ParamValue` message is received, triggering `ParamValueChanged` in the desktop controller and updating the UI slider without latency.

---

## 5. Cloud Integration & Web Container

* **Embedded Browser**: Microsoft Edge WebView2 (`ICoreWebView2Controller`).
* **OAuth Authentication**: Handles user sign-in to Neural DSP Cloud via WebView2, storing the resulting `AuthorizationToken` securely.
* **Cortex Cloud REST Services**: Uses `WININET.dll` for API endpoints (`https://api.neuraldsp.com/v2/`):
  * Preset download and cloud backup synchronizer (`CloudBackupMessageSender`).
  * Neural Capture browsing, auditioning, and downloading directly into user directories.
  * Custom Impulse Response (.wav) upload and cloud sync.
