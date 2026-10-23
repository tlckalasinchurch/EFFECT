# Unresolved Questions & Evidence Boundaries

This document delineates the exact empirical boundaries of our reverse engineering audit, explicitly distinguishing directly verified facts from areas requiring live hardware instrumentation.

---

## 1. Physical Hardware & Wire Protocol Boundaries

### UNRES-01: USB HID Report ID & Framing Layout
* **Known Facts**:
  * Communication uses Windows `hid.dll` (`HidD_SetFeature`, `HidD_GetFeature`, `DeviceReportStream`).
  * Payloads encapsulate Google Protocol Buffers v2 messages (`cortex_protobuf_v2`).
  * Requests and responses are tracked with a 32-bit `DeviceRequestId`.
* **Unresolved Question**:
  * What is the exact byte framing of the HID packet? Specifically:
    * What are the Report IDs (e.g., Report ID `0x01` for Control, `0x02` for Telemetry)?
    * Does the protocol use 64-byte USB Interrupt transfers or multi-kilobyte HID Feature Reports?
    * How are large multi-chunk messages (such as transferring a 50 KB preset or 2 MB neural capture) fragmented and reassembled?
* **Reason Unresolved**:
  * Passive static analysis reveals the API calls and class names, but the low-level byte-packing logic cannot be conclusively mapped without capturing USB traffic from a physically connected Quad Cortex unit using a USB hardware analyzer (e.g., Beagle USB 480 or Wireshark with USBPcap).
* **Confidence**: **U (Unknown byte framing) / B (Supported HID architecture)**

---

### UNRES-02: Cryptographic Layer (`ZencryptionHelper` / `ZencryptionManager`)
* **Known Facts**:
  * Symbols `ZencryptionHelper` and `ZencryptionManager` appear adjacent to `HidLogger` and `Compiler` around offset `0x3413580`.
  * The binary links to `bcrypt.dll` and `CRYPT32.dll`.
* **Unresolved Question**:
  * Is the Protobuf byte stream encrypted across the USB HID wire, or is `ZencryptionManager` used exclusively for protecting proprietary Neural Capture weights and cloud user credentials?
* **Evidence Analysis**:
  * Standard USB HID peripheral protocols rarely encrypt local parameter knobs due to latency constraints, but licensing and proprietary neural models downloaded from Cortex Cloud require cryptographic protection.
* **Reason Unresolved**:
  * Without analyzing live decrypted buffers or executing disassembly of `ZencryptionHelper::encrypt`, wire encryption cannot be affirmed or refuted.
* **Confidence**: **C (Inferred: Cloud / Asset encryption only)**

---

### UNRES-03: Wi-Fi Synchronization Protocol
* **Known Facts**:
  * Quad Cortex hardware includes built-in Wi-Fi hardware.
  * Cortex Control contains string references to Wi-Fi settings (`deviceSettingsWifiViewController.xml`) and network diagnostics (`RemoteHostSocketCheckStrategy`).
  * `WS2_32.dll` is imported with standard socket functions.
* **Unresolved Question**:
  * When operating over Wi-Fi, does Cortex Control establish a direct TCP socket connection or WebSocket connection to the Quad Cortex unit on the local LAN, or does all communication route indirectly through Cortex Cloud?
* **Reason Unresolved**:
  * At offline startup without connected hardware, no listening or outbound TCP sockets were observed.
* **Confidence**: **U (Unknown local network wire behavior)**

---

### UNRES-04: Proprietary Neural Model File Format (`.cortex` / `.preset`)
* **Known Facts**:
  * Presets in memory are represented by `cortex_protobuf_v2::BinaryPreset`.
  * Presets contain references to neural models (`ModelPreset`, `DefaultParametersModel`).
* **Unresolved Question**:
  * How are Neural DSP proprietary plugin amp algorithms (e.g., Archetype Plini, Cory Wong, Nolly) structured when exported for Quad Cortex? Are they quantized PyTorch/TensorFlow models, custom C++ bytecode, or compiled fixed-architecture neural network weight matrices?
* **Reason Unresolved**:
  * The desktop editor contains only UI controllers and preset containers; the neural DSP execution engine resides entirely within the SHARC+ DSP firmware on the physical hardware.
* **Confidence**: **U (Hardware-resident firmware boundary)**

---

## 2. Recommended Next Verification Steps
1. **USB Protocol Capture**: When a physical Quad Cortex device is connected in an authorized testing lab, record USB descriptor negotiation and HID feature reports using Wireshark + USBPcap.
2. **Preset Export Dissection**: Save a local `.preset` file from Cortex Control and verify its alignment against our reconstructed `BinaryPreset` Protobuf v2 schema.
3. **HID Mocking**: Develop a virtual USB HID loopback device emulating VID `0x152A` & PID `0x892F` to observe Cortex Control's handshake sequence and initial device sync request.
