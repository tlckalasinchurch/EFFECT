# ⚡ กดจนหลอนTone - Guitar Rig & Amp Workstation

โปรแกรมจำลองตู้แอมป์กีตาร์ไฟฟ้าระดับโปรสำหรับ Windows 11 ที่รวมสถาปัตยกรรมระดับโลกของ **KEMPER Rig Manager** และ **TONE3000** (Neural Amp Modeler) โดยประมวลผลเสียงแบบ Native DSP บนคอมพิวเตอร์ผ่าน Audio Interface Line 6 UX1 ด้วย Low Latency

## 🎯 Features

- **Vectorized DSP Engine** - Low-latency audio processing (~10.6ms @ 512 samples)
- **4-Zone UI** - Kemper-style interface (Locations, Grid, Inspector, Signal Chain)
- **KEMPER Integration** - Load from 35 Kemper Rig Packs (.rigpack SQLite)
- **TONE3000 Integration** - Load 8 Factory Neural Presets (.t3kpreset)
- **Real-time Tuner** - NSDF pitch detection (throttled 15 Hz)
- **Custom Presets** - Save and load user presets via SQLite
- **VU Meters** - Real-time input/output level monitoring
- **Modular Signal Chain** - Gate, TS-9 Overdrive, Amp Head, Cabinet IR, Delay, Reverb

## 🚀 Quick Start

### Prerequisites

- Windows 11
- Python 3.14+
- Line 6 UX1 Audio Interface (or any ASIO/WASAPI device)
- Audio Interface: Input + Output

### Installation

1. **Clone or download the project**
```bash
cd C:\Users\Administrator\Desktop\Hack-effect
```

2. **Install dependencies**
```bash
uv pip install -r requirements.txt
```

3. **Run the application**
```bash
run.bat
```

Or manually:
```bash
python main.py
```

## 🎮 Usage

### Basic Controls

1. **Start Audio Engine**
   - Click **POWER** button in top-right
   - Select Line 6 UX1 (auto-detected: In=17, Out=15)
   - Latency: ~10.6ms (512 samples @ 48kHz)

2. **Load Presets**
   - Browse presets in **Zone 2 (Rig Grid)**
   - Click on preset to load
   - Categories: Factory, TONE3000 Neural, Kemper, User

3. **Adjust Parameters**
   - Click module in **Signal Chain** (bottom)
   - Drag knobs vertically to adjust
   - Toggle modules with ⏻ buttons

4. **Use Tuner**
   - Click **TUNER** button
   - Play guitar string
   - Follow needle indicator

### Signal Chain

```
INPUT → [NOISE GATE] → [TS-9 DRIVE] → [AMP HEAD] → [CABINET IR] → [DELAY] → [REVERB] → OUTPUT
```

### Preset Management

- **Save**: Click "💾 Save Tone" in grid toolbar
- **Load**: Click preset in table
- **Kemper**: Expand "Kemper Rig Packs" in sidebar
- **TONE3000**: Click "TONE3000 Neural Rigs" in sidebar

## 🛠️ Technical Details

### Audio Engine
- **Sample Rate**: 48,000 Hz
- **Buffer Size**: 512 samples (WASAPI Exclusive)
- **Latency**: ~10.6ms
- **Processing**: Vectorized NumPy operations (no Python loops in signal path)

### DSP Modules
- **Noise Gate**: Envelope tracking with attack/release
- **TS-9 Overdrive**: Asymmetric soft clipping (tube diode simulation)
- **Amp Head**: Multi-stage tube saturation + Tone Stack EQ
- **Cabinet**: FIR convolution with 4 synthetic IRs
- **Delay**: Circular ring buffer with feedback
- **Reverb**: Schroeder comb/allpass algorithm

### Tuner Algorithm
- **Method**: NSDF (Normalized Square Difference Function)
- **Range**: 60-1200 Hz (guitar range)
- **Throttling**: 15 Hz (to protect audio thread)

## 📁 Project Structure

```
Hack-effect/
├── run.bat                    # Launcher script
├── main.py                    # Entry point (FastAPI + pywebview)
├── server.py                  # FastAPI backend (14 endpoints)
├── audit_test.py              # Test suite (14/14 passing)
├── config.py                  # Configuration management
├── setup_logging.py           # Logging setup
├── requirements.txt            # Python dependencies
├── presets.db                 # SQLite database
├── engine/
│   ├── __init__.py            # Package init
│   ├── audio.py               # AudioEngine (WASAPI, Tuner)
│   ├── dsp.py                 # DSP Signal Chain
│   ├── presets.py             # Preset management
│   ├── kemper_importer.py     # Kemper .rigpack importer
│   └── tone3000_importer.py   # TONE3000 .t3kpreset importer
├── web/
│   ├── index.html             # 4-Zone UI
│   ├── style.css              # Kemper green theme
│   └── app.js                 # Frontend logic
├── docs/
│   └── ui-references/kemper/  # UI reference images
└── README.md                  # This file
```

## 🧪 Testing

Run the audit test suite:
```bash
python audit_test.py
```

Expected output:
```
==============================================================
  กดจนหลอนTone Workstation -- AUDIT REPORT
==============================================================
[OK] Import: engine modules -> All engine modules imported
[OK] Import: server (FastAPI) -> FastAPI app: กดจนหลอนTone
[OK] DSP: signal chain (256-sample block) -> shape=(256,) range=[-1.0,1.0]
...
  Result: 14/14 passed -- ALL CLEAR! App is READY TO LAUNCH.
```

## 🔧 Configuration

### Environment Variables (Optional)
Create `.env` file:
```env
AUDIO_INPUT_DEVICE=17
AUDIO_OUTPUT_DEVICE=15
SAMPLE_RATE=48000
BUFFER_SIZE=512
LOG_LEVEL=INFO
```

### Audio Device Auto-Detection
The system auto-detects Line 6 UX1 with WASAPI priority:
- WASAPI (hostapi=2) > DirectSound (hostapi=1) > MME (hostapi=0)

## 📊 Performance Metrics

- **DSP Processing Time**: 0.466ms (4.4% of buffer time)
- **Tuner Throttling**: 15 Hz (every 6th callback)
- **Memory Usage**: ~50MB (Python + NumPy)
- **CPU Usage**: <5% (idle), <15% (active processing)

## 🎨 UI Reference

The UI is based on KEMPER Rig Manager design:
- **Colors**: Kemper Green (#33715b), Mint (#4ef58d)
- **Layout**: 4-Zone workspace + Signal Chain + Parameter Strip
- **Knobs**: Rotary drag controls with visual feedback
- **Performance Bar**: 5-slot live switching

## 🔮 Future Roadmap

1. **NAM Inference** - Direct Neural Amp Modeler integration (ONNX/Rust)
2. **Custom IR Loader** - Drag & Drop .wav impulse responses
3. **Parallel Signal Chain** - Dual routing paths
4. **Standalone Binary** - PyInstaller/Nuitka packaging
5. **MIDI Footcontroller** - External pedal support

## 📄 License

MIT License - See LICENSE file

## 🙏 Credits

- **KEMPER** - UI design inspiration and Rig Pack format
- **TONE3000** - Neural Amp Modeler technology
- **Neural Amp Modeler (NAM)** - Deep learning audio modeling
- **Line 6** - UX1 Audio Interface hardware

## 📞 Support

For issues or questions, please refer to PROJECT_HANDOFF.md for detailed technical documentation.

---

**⚡ กดจนหลอนTone - Professional Guitar Rig Workstation**
