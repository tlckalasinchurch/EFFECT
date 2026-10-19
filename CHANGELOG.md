# Changelog

All notable changes to กดจนหลอนTone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project documentation files (README.md, LICENSE, CHANGELOG.md)
- Configuration management (config.py)
- Logging system (setup_logging.py)
- Python package structure (engine/__init__.py)
- Dependencies management (requirements.txt)
- Git ignore rules (.gitignore)
- Environment variables template (.env.example)

### Changed
- Updated main.py to use centralized configuration
- Updated server.py to use logging system
- Integrated config module for audio settings

## [1.0.0] - 2026-10-19

### Added
- Initial release of กดจนหลอนTone
- Vectorized DSP audio engine (NumPy-based)
- WASAPI audio support with Line 6 UX1 auto-detection
- 4-Zone Kemper-style UI (Locations, Grid, Inspector, Signal Chain)
- KEMPER Rig Pack integration (35 packs, SQLite .rigpack)
- TONE3000 Factory Preset integration (8 neural presets)
- Real-time NSDF tuner (throttled 15 Hz)
- VU meters for input/output monitoring
- Preset management system (SQLite database)
- Modular signal chain (Gate, TS-9, Amp, Cab, Delay, Reverb)
- 5-slot Performance bar for live switching
- Rotary knob controls with drag interaction
- Custom preset saving and loading
- Webview desktop window (native Windows app)

### Technical
- Sample Rate: 48kHz
- Buffer Size: 512 samples (~10.6ms latency)
- DSP Processing Time: 0.466ms (4.4% of buffer time)
- All DSP operations vectorized (no Python loops in signal path)
- Audio callback optimized with tuner throttling

### Known Limitations
- DSP simulation only (no actual NAM inference)
- Synthetic cabinet IRs only (4 presets)
- Single signal chain (no parallel routing)
- No custom IR drag-and-drop support
- No MIDI footcontroller support
- Windows-only (WASAPI dependency)

### Future Roadmap
- NAM inference integration (ONNX/Rust)
- Custom IR loader with drag-and-drop
- Parallel signal chain support
- Standalone binary packaging (PyInstaller/Nuitka)
- MIDI footcontroller integration
