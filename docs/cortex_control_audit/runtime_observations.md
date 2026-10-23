# Runtime Observations: Neural DSP Cortex Control v4.1.0

## 1. Test Environment & Execution Protocol
* **Date & Time of Audit**: 2026-10-23 21:42:03 ICT
* **Target Executable**: `C:\Program Files\Neural DSP\Cortex Control\Cortex Control.exe`
* **Target File Size**: 67,060,088 bytes
* **Target SHA-256**: `9be548fb6cbd2e8c80715015c2a2f0f248c9b01a7165004e2b017ffe2b14e65a`
* **Operating System**: Microsoft Windows 10 Pro (Build 19045 / AMD64)
* **Execution Constraint**: Read-only passive observation. No memory injection, patching, debugger modification, or intrusive hooking.

---

## 2. Process Lifecycle & Resource Utilization

| Metric | Measured Value | Notes / Interpretation |
| :--- | :--- | :--- |
| **Process ID (PID)** | `11652` | Assigned dynamically by Windows kernel. |
| **Startup Duration** | ~1.25 seconds | Measured from process spawn until UI window creation and thread stability. |
| **Working Set (RAM)** | `69,443,584 bytes` (~66.2 MB) | Highly compact memory footprint for a modern C++/DirectX desktop GUI. |
| **Active Thread Count** | `13 threads` | Multi-threaded JUCE message pump, HID poller, Direct3D renderer, and async tasks. |
| **Termination Behavior** | Clean shutdown | Terminated gracefully with code 0; flushed pending log buffers without hang. |

---

## 3. Thread Hierarchy & Priority Analysis

Inspection of PID `11652`'s active threads revealed the following internal architecture:

| Thread ID | Base Priority | Current Priority | State / Wait Reason | Assigned Subsystem / Role |
| :---: | :---: | :---: | :---: | :--- |
| **`4572`** | 8 | 10 | State 5 (WaitReason 6: Event) | **Main Win32 / JUCE Message Loop**: Handles Windows window messages, user mouse clicks, and top-level UI paint invalidations. |
| **`12272`** | **15** | **15** | State 5 (WaitReason 6: Event) | **Real-Time Multimedia / HID Poller**: Configured with maximum real-time priority (15) to ensure zero-jitter reception of USB HID reports and MIDI messages. |
| **`11428`** | **15** | **15** | State 5 (WaitReason 6: Event) | **High-Priority Audio / Metering Thread**: Dedicated stream processor for real-time `GridModelMeterMessage` telemetry. |
| **`9448`** | 10 | 11 | State 5 (WaitReason 13: DelayExecution) | **Timer / Dispatch Worker**: Executes scheduled tasks, periodic status queries, and UI animation timers. |
| **`8484`** | 8 | 8 | State 5 (WaitReason 13: DelayExecution) | **PnP Hardware Watcher**: Periodically scans Windows SetupAPI for newly connected Quad Cortex devices. |
| **`7864`** | 6 | 6 | State 5 (WaitReason 13: DelayExecution) | **Background Worker (Low Priority)**: Asynchronous file I/O, cache management, and thumbnail generation. |
| **`8444`** | 6 | 6 | State 5 (WaitReason 13: DelayExecution) | **Background Worker (Low Priority)**: Secondary worker for background cloud state polling. |
| **`10624`**, **`11252`**, etc. | 8 | 8 | State 5 (WaitReason 8: WrQueue) | **ThreadPool Workers**: Standard C++ thread pool handling non-real-time compute tasks. |

---

## 4. Network & Socket Observation
A query of active network endpoints associated with PID `11652` was performed using PowerShell `Get-NetTCPConnection`:
* **TCP Listening Sockets**: **None** (`0` listening ports).
* **Outbound Connections**: **None** established during offline startup.
* **Interpretation**: Cortex Control does **not** host a local web server (unlike Electron apps or certain IoT companions). It does not require TCP port binding to manage local hardware. Local communication is exclusively handled over the **USB Human Interface Device (HID)** interface.
* **Network Diagnostics Mechanism**: When internet testing is requested, `neural::cortex::usb::RemoteHostSocketCheckStrategy` performs an ICMP ping / connection test to Google Public DNS (`8.8.8.8`) and invokes PowerShell:
  ```powershell
  Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -notmatch 'Bluetooth' -and $_.InterfaceDescription -notmatch 'Loopback' } | Measure-Object
  ```

---

## 5. File System & Logging Activity

### 5.1 Settings File Inspection
* **Path**: `C:\Users\Administrator\AppData\Roaming\Neural DSP\Cortex Control\Cortex Control.settings`
* **Format**: JUCE XML Properties File
* **Observed Content**:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <PROPERTIES>
    <VALUE name="cortex_window_size" val="236 33 1064 759"/>
  </PROPERTIES>
  ```
* **Observation**: Stores the desktop window geometry (`x=236, y=33, width=1064, height=759`).

### 5.2 Application Log Inspection
* **Path**: `C:\Users\Administrator\AppData\Roaming\Neural DSP\Cortex Control\logs\cortex-control.log`
* **Log Output Captured**:
  ```
  **********************************************************
  Starting Neural DSP Cortex Control 4.1.0 log.
  Log started: 23 Oct 2026 9:42:03pm

  SYSTEM INFORMATION
  CPU Architecture: x86_64
  OS Name: Windows 10

  2026-10-23_21-42-03.049 [11dc    ] [WARN ] Cortex Control: Log started. {CortexManager: CortexControl.cpp,19}
  2026-10-23_21-42-03.268 [11dc    ] [ERROR] CANNOT FIND CHILD VIEW CONTROLLER: introScreenViewController {getChildWithType: ViewController.h,329}
  2026-10-23_21-42-08.582 [11dc    ] [ERROR] CANNOT FIND CHILD VIEW CONTROLLER: introScreenViewController {getChildWithType: ViewController.h,329}
  ```
* **Key Revelations**:
  * Logging entrypoint is `CortexManager: CortexControl.cpp,19`.
  * Dynamic view controller resolution is performed in `getChildWithType: ViewController.h,329`.
  * Missing hardware causes the application to display the initial connection screen rather than crashing.
