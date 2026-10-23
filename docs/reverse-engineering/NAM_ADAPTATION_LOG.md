# NAM Workstation Adaptation Log

This document records the exact adaptations, data models, backend audio engine extensions, and frontend interfaces integrated into the NAM Workstation based on verified reverse-engineering evidence.

---

## 1. Engine & Data Model Extensions

### 1.1 `engine/cortex_models.py`
* **Scene Color Palette**: Cloned from Quad Cortex hardware LED rings and Cortex Control `sceneColours` (8 colors: Red `#e74c3c`, Cyan `#00bcd4`, Yellow `#f1c40f`, Violet `#9b59b6`, Green `#2ecc71`, Blue `#3498db`, Amber `#e67e22`, Magenta `#e91e63`).
* **`SceneDefinition` Dataclass**: Models scene index (0-7 / A-H), name label, hex color, block bypass map (`bypasses: Dict[str, bool]`), and block parameter overrides (`param_overrides: Dict[str, Dict[str, float]]`).
* **Factory Multi-Scene Presets**:
  * `cortex_british_lead_100`: 8 distinct scenes (Clean Chime, Verse Crunch, Chorus Heavy, Solo Boost Lead, Ambient Swell, Octave Lead, Tight Rhythm, Dry Direct).
  * `cortex_american_clean_twin`: 8 distinct scenes (Studio Clean, Analog Chorus, Texas Blues Breakup, Warm Slapback, Cathedral Clouds, Rotary Organ, Lo-Fi Vinyl, Spring Reverb Only).
  * `cortex_high_gain_rectifier`: 8 distinct scenes (Djent Rhythm, Liquid Solo, Clean Intro, Octave Drop Solo, Brutal Scoop, Ambient Lead, Heavy Staccato, Bypass Mute).

### 1.2 `engine/cortex_scenes.py`
* **`CortexSceneManager`**:
  * Maintains the 8 scenes for the active preset.
  * Implements `set_active_scene(idx, chain)`: instantly toggles block bypasses (`noise_gate`, `screamer`, `amp`, `cab`, `eq`, `mod`, `delay`, `reverb`, `pitch_shifter`) and applies parameter overrides without dropping audio or reloading DSP models.
  * Implements `load_preset(preset_data, chain)`: applies base settings and switches to default scene.
  * Implements `update_scene(idx, label, color_hex, bypasses, param_overrides, chain)`.

---

## 2. API & Server Integration (`server.py`)

* Attached `cortex_mgr = CortexSceneManager()` to global engine state.
* Updated `GET /api/status` to include real-time Cortex state (`st["cortex"] = cortex_mgr.get_state()`).
* Added dedicated Cortex endpoints:
  * `GET /api/cortex/scenes`: Lists all 8 scenes, color palette, active scene index.
  * `POST /api/cortex/scene/select`: Instant zero-glitch scene switching (`{ "index": 0..7 }`) executed under `ENGINE_STATE_LOCK`.
  * `POST /api/cortex/scene/update`: Real-time updates to scene labels, colors, bypasses, and parameter overrides.
  * `GET /api/cortex/presets`: Lists all multi-scene factory and user presets.
  * `POST /api/cortex/preset/load`: Loads a multi-scene preset and activates its default scene.
  * `GET /api/cortex/export`: Exports the current rig and 8 scenes as a Cortex-compatible `.cortex.json` multi-scene preset.

---

## 3. Web Frontend Enhancements

### 3.1 Quad Cortex Scene Bar (`web/index.html` & `web/style.css`)
* Inserted a sleek dark scene selector bar directly above the signal chain.
* Displays 8 scene buttons (`[A]` through `[H]`), each with:
  * Glowing LED indicator matching the Quad Cortex scene color.
  * Scene letter badge and customizable title (e.g. `[A] Clean Chime`, `[B] Verse Crunch`).
  * Active scene highlighting with glowing borders and color-matched halo.
* Integrated Cortex Multi-Scene preset dropdown selector.

### 3.2 Gig View Mode (`web/index.html`, `web/style.css`, `web/app.js`)
* Added a `GIG VIEW` button in the top action bar.
* Features a full-screen, high-contrast live performance overlay:
  * 2x4 oversized footswitch grid (cloned from Quad Cortex hardware footswitches A-D and E-H).
  * Tactile press animations and giant glowing LED rings.
  * Integrated chromatic stage tuner badge.
  * High-visibility input/output level meters.
  * Global keyboard hotkeys: Press `1`-`8` or `A`-`H` to trigger scenes in real time; `Escape` exits Gig View.

---

## 4. Verification & Testing

* **`tests/test_cortex.py`**:
  * 10 automated unit tests covering:
    * Default 8 scenes initialization, colors, and letter badges.
    * Real-time DSP block bypass switching without dropouts.
    * Multi-scene preset loading and parameter overrides.
    * Boundary validation (rejects invalid scene indices).
    * API endpoint responses (`GET /api/cortex/scenes`, `POST /api/cortex/scene/select`, `GET /api/cortex/presets`, `POST /api/cortex/preset/load`, `GET /api/cortex/export`).
* **Test Suite Status**: 42 unit tests executed via `unittest discover tests` — **42 passed (100% success rate)**.


---

## 5. Phase 2 — Implementation of 5 Killer Sound Engine Features

### 5.1 3D Virtual Microphone Positioning & Power Tube Voicing
* **Location**: `engine/dsp.py` (`CabinetSimulator`), `web/app.js` (`attachCabMicDrag`), `web/style.css` (`.cab-3d-wrap`).
* **Microphone Modeling**: Shure SM57 (upper-mid bite), Sennheiser MD421 (tight bottom & crisp attack), Neumann U87 (smooth studio condenser), and Royer R-121 (warm ribbon with smooth natural high roll-off).
* **Power Tube Voicing**: OFF (pure IR), 6L6 (American scooped punch), EL34 (British crunch & presence), EL84 (Vox chime), 6V6 (vintage compression), and KT88 (high headroom & deep sub-bass).
* **Interactive 2D/3D Speaker Cone Canvas**: Draggable microphone interface updating `center` (axis) and `distance` (proximity effect) in real time.

### 5.2 5-Band Studio Parametric EQ & Real-Time Frequency Response Curve
* **Location**: `engine/dsp.py` (`GraphicEqualizer.model_id = 5`, `get_curve_points()`), `web/app.js` (`drawEqCurve()`), `web/style.css` (`.eq-curve-wrap`).
* **Curve Generation**: Computes exact 64-point log-spaced transfer function $H(e^{j\omega})$ in dB from 20 Hz to 20,000 Hz.
* **Graphical Vector Display**: Live SVG with 0 dB reference line and glowing gradient fill showing the composite EQ curve.

### 5.3 Kemper-Style Rig Morphing Engine
* **Location**: `engine/morph.py` (`MorphController`), `server.py` (`/api/morph/set`, `/api/morph/capture`), `web/index.html` & `web/app.js` (`#morphSlider`).
* **Mechanism**: Continuous interpolation between Slot A (Heel) and Slot B (Toe) for Amp Gain, Amp Master, Drive, Level, Delay Mix, Reverb Mix, and Stomp Bypasses without clicks or audio dropouts.

### 5.4 Dynamic Ducking in Delay and Reverb
* **Location**: `engine/dsp.py` (`Delay.ducking`, `Reverb.ducking`), `web/app.js`.
* **Mechanism**: Fast envelope follower detecting active picking. When RMS exceeds threshold, the wet return is dynamically attenuated (ducked) by up to 80% to keep fast licks distinct, blooming back to full depth during pauses or held notes.

### 5.5 Parallel Signal Grid (Splitter & Mixer)
* **Location**: `engine/dsp.py` (`GuitarSignalChain.parallel_enabled`, `parallel_blend`), `web/index.html` & `web/app.js` (`#btn-parallel-toggle`, `#parallelBlendSlider`).
* **Mechanism**: Pre-distortion clean tap split combined with the processed amp/cab path via a variable blend mixer.
