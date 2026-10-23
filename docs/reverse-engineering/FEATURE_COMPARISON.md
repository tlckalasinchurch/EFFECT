# Feature Comparison & Architectural Matrix

This document benchmarks the architectures, signal-chain routing, scene management, live performance modes, and preset serialization across the analyzed guitar platforms against our open-source NAM Workstation (`กดจนหลอนTone`).

| Capability | Neural DSP Quad Cortex / Cortex Control | MOOER GE150 Studio | Kemper Profiler (Rig Manager) | TONE3000 | NAM Workstation (`กดจนหลอนTone`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Signal Chain Topology** | 4-Row Grid with splitters (`combined_splitter`) & mixers | Fixed Linear 9-Stage Chain (`FX -> DS -> AMP -> CAB -> NS -> EQ -> MOD -> DLY -> REV`) | Pre-Amp Stomps (A-D) -> Stack (Amp + Cab) -> Post-Amp (X, MOD, DLY, REV) | Linear Effect Chain with NAM Amp Engine | Dynamic Linear / Stomp / Mod Chain with NAM Stage & Dual Cab IRs |
| **Scene / Snapshot Switching** | **8 Scenes (A-H)** per preset with zero-gap block bypass & parameter morphing | No Scenes (full patch preset change with audio mute gap) | Morphing between 2 states per Rig | Single patch mode | **8 Scenes (A-H)** with Quad Cortex color palette, instant zero-glitch bypass & param overrides |
| **Live Performance UI** | **Gig View**: Full-screen oversized footswitches (Stomp/Scene modes) | Basic Desktop Editor UI | Performance Mode with 5-slot banks | Web player | **Gig View Mode**: 2x4 footswitch grid, giant LED rings, stage tuner, live level meters |
| **Preset File Format** | Google Protocol Buffers v2 (`cortex_protobuf_v2`, `BinaryPreset`) | JSON format (`.mo`) with decimal/hex arrays | Proprietary Binary (`.kipr`) & SQLite RigPack | Binary `.t3kpreset` | Open JSON presets + Native `.cortex.json` + Native `.mo` import/export |
| **Amp Modeling Technology** | Neural Capture (black-box ML) + Component Models | Algorithmic DSP Non-Linear Emulation | Profiling (Dynamic Volterra / IR Transfer) | Neural Amp Modeler (NAM A1 / A2 WaveNet / LSTM) | **Dual Engine**: Neural Amp Modeler (NAM A1 / A2) + Algorithmic DSP Tube Heads |
| **Speaker Cabinet / IR** | Dual IR with 3D mic position (`distance`, `center`, mic type) | Fixed single IR + 3 tube power-amp types + 4 mic models | Studio Cab Profile or Impulse Response | Single Wave IR file | **Stereo / Dual IR Engine** + 3D Mic positioning + Tube Power-Amp coloration |
| **Hardware Driver Integration** | Thesycon USB Audio 2.0 ASIO Driver (`VID_152A PID_892F`) | MOOER USB Audio ASIO Driver | Kemper Profiler USB Audio Driver | Generic ASIO / CoreAudio | **Auto-Detect ASIO / WASAPI / UX1** with latency reporting & buffer configuration |
| **Parameter Smoothing** | Hardware DSP interpolation | Stepped digital potentiometer | Parameter ramping | Audio block level | Linear gain ramp + RLock concurrency safety |

---

## Key Takeaways for the NAM Workstation

1. **Scene Mode is Essential for Live Playing**:
   Traditional modelers drop audio buffers or click when switching presets due to neural model re-initialization and IR reloading. Quad Cortex solves this by preloading the complete grid and using **Scene switching** to merely flip bypass states and ramp parameter dials in real time. We have directly adopted this into `engine/cortex_scenes.py`.

2. **Gig View Eradicates Stage Distractions**:
   While intricate knobs and signal chain editors are ideal for studio tweaking, live stages demand large, touch/foot-friendly targets with unmistakable visual feedback (color-coded footswitches, high-contrast tuner, and large active scene badges). The newly implemented **Gig View** in `web/index.html` and `web/app.js` fulfills this need.

3. **Multi-Format Interoperability**:
   The NAM Workstation now serves as a universal bridge, supporting Neural DSP Cortex multi-scene JSON presets, MOOER GE150 `.mo` presets, Kemper `.kipr` rigs, and TONE3000 captures in a single unified interface.
