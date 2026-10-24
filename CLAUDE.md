# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"กดจนหลอนTone" (Hack-effect): a Windows desktop guitar amp/effects workstation. Python DSP engine + FastAPI server + HTML/JS UI shown in a pywebview window. Docs and many comments are in Thai. Python >=3.14, Windows only (WASAPI, COM, WebView2).

## Commands

Use the project venv (`.venv\Scripts\python.exe`); it was built with `uv`, so `pip` is not in it (`uv pip install -r requirements.txt`, or call the venv python directly).

```powershell
.\run.bat                                          # launch app (main.py: uvicorn thread + pywebview)
.\.venv\Scripts\python.exe -m pytest tests -q      # full suite
.\.venv\Scripts\python.exe -m pytest tests/test_param_registry.py::TestX::test_y   # single test
.\.venv\Scripts\python.exe audit_test.py           # import/route audit (does NOT test sound)
node --check web\app.js                            # JS syntax check (no JS build/lint step)
```

No linter is configured. `cpp_engine/` is a separate, isolated native host (CMake; see `cpp_engine/IPC_CONTRACT.md`); the Python app does not depend on it.

## Architecture

- `main.py` starts `server.app` (FastAPI, `server.py` ~2150 lines, all REST routes) in a thread, then opens a pywebview window on `web/` (`index.html`, `app.js`, `style.css`).
- `engine/audio.py` `AudioEngine`: owns the sounddevice stream, device-pair resolution/fallback, block timing stats, sample-rate hot-switch (`rebuild_chain_for_rate`). Shared state is guarded by `self._lock` (an RLock); the audio callback must not allocate or query PortAudio devices.
- `engine/dsp.py` `GuitarSignalChain`: Gate -> TS-9 -> AmpHead -> Cabinet IR -> Delay/Reverb/Pitch/EQ/Modulation. Cabinet long-IR convolution lives in `engine/convolver.py` (partitioned). `world_class_dsp.py` / `master_bank.py` / `ai_tone_matcher.py` are newer, partly untracked additions.
- **Parameter registry**: `engine/params.py` is the single source of truth for modules/params (data only). Writes go through `engine/param_access.py` (`set`, `apply_settings`; raises `NonFiniteValue`, `ServerOwnedParameter`, `ModuleNotInstalled`). Other copies of the parameter set (`get_state()` shape, `load_preset`, cortex/morph tables, `web/app.js` BLOCKS/KNOB_SETS) still exist and are pinned to the registry by `tests/test_param_registry.py` — change them together.
- Presets: `engine/presets.py` + `presets.db` (SQLite; contract in `docs/PRESET_DATA_CONTRACT.md`). `engine/rigdoc.py` defines RigDocument v2 and the lossless legacy adapter (`from_v1`). Importers: `kemper_importer.py` (.rigpack, read-only SQLite), `tone3000_importer.py` (.t3kpreset/NAM, cached in `tone3000_cache/`), `mooer_*`, `cortex_*` (scenes/morph).
- NAM neural amps: `engine/nam.py` + `nam_c99.py` (ctypes over `nam_c99.dll`). NAM CPU is the budget risk (block deadline = block/sample_rate).

## Testing rules that are easy to break

- Golden baselines in `tests/golden/` (`dsp_chain_baseline.json`, `dsp_chain_sweep.json`) are change detectors, recorded at 48 kHz / block 128 and fingerprinted to `dsp.py`. Re-record only deliberately: `python -m tests.test_chain_sweep --write` (refuses on fingerprint mismatch unless `--accept-changed-dsp`). Do not re-record to make a failing test pass; DSP sound changes need an owner listening sign-off first (see `docs/superpowers/plans/2026-10-23-cab-f1-f2-signoff-and-cpu-measurement.md`).
- Tests must never write the real `presets.db`; use a temp DB (`cortex_mgr`/`morph_mgr` share a global instance — isolate it).
- `.rigpack` and `presets.db` validation opens with `mode=ro`.

## Gotchas

- Device indices are not stable; settings store device names and pick the best host API (WASAPI > DirectSound > MME). Streams must be opened after `ensure_com_initialized()` on the opening thread. Don't persist a fallback device pair to `audio_settings.json`.
- `rigKey()` in the UI is not `r.id` (ids repeat across packs). Escape any external data put in `innerHTML` with `esc()`.
- Secrets live in `t3k_config.json` / `t3k_tokens.json` (local, uncommitted); never print them.
- `docs/HANDOFF.md` outranks `PROJECT_HANDOFF.md` where they conflict (the latter has unverified numbers). Large untracked vendor files in the repo root (ASIO driver, Cortex/Quad Cortex installers, GE150) are reference material, not source.
