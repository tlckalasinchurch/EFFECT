# Phase 1 — Open Source Component Evaluation & Architecture Integration

**Project**: กดจนหลอนTone (NAM Guitar Workstation)  
**Date**: October 24, 2026  
**License Strategy**: Permissive / Clean-room separation

---

## 1. Candidate Repositories Evaluation

| Repository | Upstream URL | License | Architecture | Evaluated Components | Integration Decision |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **NeuralAmpModelerCore** | `sdatkinson/NeuralAmpModelerCore` | **MIT** | C++17/20, Eigen SIMD | WaveNet, LSTM, Linear inference, model parsing | **Adopted as Primary C++ NAM Foundation**. Permissive MIT license allows embedding into native C++ engine / DLL. |
| **Plectrify** | `patrickiel/plectrify` | **None (ARR)** | JUCE, Svelte, WebSockets | Desktop host, embedded web UI, TONE3000 OAuth, scenes | **Architectural Reference Only**. No code copying. We use our existing custom Web UI, FastAPI backend, and WebSocket IPC. |
| **NeuralRack** | `brummer10/NeuralRack` | **BSD-3-Clause** | C++, DPM, LV2/Standalone | Zero-latency partitioned convolution, latency compensation | **Permissive Reference**. Mathematical algorithms for partitioned convolution and resampling are used. |
| **AmpForge** | `Loursy/AmpForge` | **GPL-3.0** | C++, JUCE | Modular, drag-and-drop reorderable signal chain | **Conceptual Reference Only**. GPL-3.0 prevents direct code copying. Modular reordering is designed natively from scratch. |

---

## 2. Licensing Obligations & Architecture Boundaries

1. **Permissive Core (MIT / BSD-3)**:
   - DSP algorithms derived from `NeuralAmpModelerCore` and partitioned convolution from `NeuralRack` maintain their respective MIT and BSD-3 notices.
2. **Proprietary / All Rights Reserved (`plectrify`)**:
   - Zero source lines copied. Clean-room implementation of TONE3000 OAuth 2.0 PKCE and scene management.
3. **Copyleft Guard (`AmpForge` - GPL-3.0)**:
   - To preserve maximum flexibility and avoid licensing encumbrance on the host project, no GPL source code is copied or linked. The reorderable chain concept is implemented independently in Python (`engine/dsp.py`) and C++ (`cpp_engine/src/audio_host.cpp`).
