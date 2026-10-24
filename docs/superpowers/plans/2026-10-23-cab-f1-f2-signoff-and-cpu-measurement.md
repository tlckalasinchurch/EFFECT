# F1/F2 Sound Sign-off and CPU Measurement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the cabinet (F1) and AmpHead EQ (F2) sound fix: the owner listens and approves, the golden baselines are re-recorded only after that approval, and CPU is measured afterwards.

**Architecture:** The code for F1/F2 is already written and sits uncommitted in the working tree (`engine/convolver.py`, `engine/dsp.py`, `config.py`, `server.py`, `tests/test_cab_convolution.py`). What is left is a human listening gate, a controlled golden re-record, one decision about a coverage test, and a live CPU measurement. No step in this plan may run before the gate before it is passed.

**Tech Stack:** Python 3.14 in `.venv`, NumPy, SciPy, pytest, sounddevice.

**Spec:** No spec file exists. The design was agreed in the brainstorming chat on 2026-10-23 and is restated under Global Constraints.

## Global Constraints

- Local-only: no `git push`, no PR, no tag, no remote call of any kind unless the owner orders it in that message.
- No automatic commit. The owner decides when to commit. Git use is read-only (`git status`, `git diff`, `git log`). No branch change, reset, clean, revert, stash or history edit.
- Do not delete or revert files the owner has not approved.
- Goal is to match the TONE3000 plugin as closely as possible. The owner judges by ear; there are no plugin renders.
- Sound first, CPU second: do not change the DSP for speed before the sound is approved.
- IR cap is 1 second at the current sample rate (`config.ir_max_samples(rate)`), with no resampling added.
- `engine/dsp.py` equations and processing order change only as already written for F1 and F2.
- Nothing may claim it passed a listening test until the owner says so.
- Golden files (`tests/golden/dsp_chain_baseline.json`, `tests/golden/dsp_chain_sweep.json`, plus the two dispatch goldens) are not re-recorded, and `--accept-changed-dsp` is not used, until Task 3. `tests/test_chain_sweep.py::DspChainSweepTests::test_cases_are_distinguishable_from_each_other` is not edited to make the suite pass.
- No test run may write to `presets.db`. Check with `md5sum presets.db` (expected `e6f2e71ce3ef4c493df88061c6f55482`) before and after.
- The audio device is not opened without the owner's explicit go-ahead in that message.

## Review Focus

1. **NaN or inf reaching the cab convolver.** `engine/convolver.py` keeps history, so one non-finite input sample poisons the output until the convolver is reset. The callback silences non-finite output but does not clear this state. Expected: the cab recovers (silence, then normal sound) after the bad input stops.
2. **Sample-rate change with a loaded IR.** `rebuild_chain_for_rate` copies the IR unchanged, so a 48 kHz IR is used at another rate. Expected: no crash, the IR cap still applies in samples for the new rate, and the owner knows it is not resampled.
3. **Very long or huge IR uploads.** A 16 MB upload is cut to `config.ir_max_samples(rate)`. Expected: the cut is reported (`truncated`), and the convolver build on the control thread does not block the API for long.
4. **Cab toggled during playback.** Bypass then enable must not replay old tail. Expected: first block after enabling has no tail (covered for the convolver; the cut filters and tube/mic voicing still keep their own state, which is existing behavior).
5. **Short or irregular callback sizes.** Expected: output identical to a single pass (covered for 1, 37, 64, 100, 128, 300, 333, 512).

---

### Task 1: Listening gate (owner)

**Files:** none changed.

**Interfaces:**
- Consumes: the uncommitted working tree.
- Produces: one of three verdicts that decides Task 2 or Task 3.

- [ ] **Step 1: Owner runs the app.** Start with `run.bat` (it uses `.venv`), pick the `Celestion V30 4x12` cab, same guitar and same input level as for the plugin.
- [ ] **Step 2: Owner compares against TONE3000.** Listen for the low end (about 100–400 Hz), the body and ring of the cab, and sweep the amp EQ knobs (bass, mid, treble, presence) with no NAM model loaded to hear any zipper or click.
- [ ] **Step 3: Owner reports one verdict.** A: sound approved. B: still thin or low end missing. C: a new artifact (click, ring, level jump).
- [ ] **Step 4: Record the verdict** in the chat. Nothing else happens until then.

### Task 2: Diagnose a negative verdict (only for B or C)

**Files:** scratch scripts under the session scratchpad only.

**Interfaces:**
- Consumes: verdict B or C from Task 1.
- Produces: a written list of causes, each tagged CONFIRMED, INFERRED or UNKNOWN, with numbers.

- [ ] **Step 1: Confirm which IR is actually in use.** Read `chain.cab.ir_name` and `len(chain.cab.ir_data)` from the running state (`/api/status`), expected `Mesa_Boogie_ST_4x12A_V30.wav` at 24000 samples if the real file is used, 600 if the synthetic one.
- [ ] **Step 2: Compare level and spectrum offline.** Render an impulse through `CabinetSimulator` with that IR and compare its magnitude response to the raw WAV. Expected difference: only peak normalization in `_prepare_ir` and the cut filters.
- [ ] **Step 3: List what the plugin may do differently** (level matching, IR normalization, low cut default of 20 Hz, tube/mic voicing). Mark every item INFERRED until it is checked.
- [ ] **Step 4: Report and stop.** Do not change code without the owner's approval of a specific change.

### Task 3: Re-record the golden baselines (only after verdict A)

**Files:**
- Modify: `tests/golden/dsp_chain_baseline.json`, `tests/golden/dsp_chain_sweep.json`

**Interfaces:**
- Consumes: the owner's explicit approval of the sound, in the chat.
- Produces: goldens recorded from the F1/F2 code. The two dispatch goldens (`parameter_dispatch.json`, `mooer_apply.json`) must stay byte-identical.

- [ ] **Step 1: Confirm the approval is in the owner's latest message.** If not, stop.
- [ ] **Step 2: Record the baseline.** `.venv/Scripts/python.exe -m tests.test_characterization --write`. Expected output: `wrote ...dsp_chain_baseline.json`.
- [ ] **Step 3: Record the sweep.** `.venv/Scripts/python.exe -m tests.test_chain_sweep --write --accept-changed-dsp`. Expected output: `wrote ...dsp_chain_sweep.json`.
- [ ] **Step 4: Verify only those two files changed.** `git status --short tests/golden` shows exactly `dsp_chain_baseline.json` and `dsp_chain_sweep.json` as modified, and the two dispatch goldens are not listed.
- [ ] **Step 5: Run the suite.** `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -p no:cacheprovider -q`. Expected: only `test_cases_are_distinguishable_from_each_other` fails (the 15 golden cases pass). Report the exact counts. Do not commit.

### Task 4: Resolve the distinguishability test (owner decides)

**Files:** none until the owner chooses.

**Interfaces:**
- Consumes: the failing test from Task 3 (`gate_tight` and `amp_clean` RMS closer than 1e-3).
- Produces: a decision, then one targeted change.

- [ ] **Step 1: Measure the collision.** In a scratch script, print the RMS of every sweep case under the new code and the pairs closer than 1e-3. Report the numbers.
- [ ] **Step 2: Present the owner's options with consequences,** without choosing: (a) change one scenario's settings in `tests/test_chain_sweep.py` so the two sound different, then re-record the sweep; (b) lower the 1e-3 threshold; (c) drop one overlapping scenario. Each weakens or reshapes the sweep differently.
- [ ] **Step 3: Apply only the chosen option,** re-run the suite, and report counts. Do not commit.

### Task 5: Expose the callback stats, then measure CPU live (owner go-ahead for the audio device)

**Files:**
- Modify: `engine/audio.py` (the `audio_stats` dict in `get_state`, near line 766)
- Test: `tests/test_audio_latency.py` or a new `tests/test_rt_hardening.py` case

**Interfaces:**
- Consumes: `AudioEngine.callback_stats()` which already returns `p50_ms`, `p95_ms`, `p99_ms`, `p99_9_ms`, `percentile_blocks`, `over_deadline_blocks`, `over_half_deadline_blocks`, `warmup_max_ms`, `callback_errors`, `last_callback_error`, `nonfinite_blocks`, and the older `avg_ms`, `max_ms`, `window_blocks`, `over_budget_windows`.
- Produces: the same figures under `get_state()["audio_stats"]` (`/api/status`), so a live run can log them.

- [ ] **Step 1: Write the failing test** `test_audio_stats_exposes_percentiles`: build an engine, call `_record_block_time` with known values, and assert `engine.get_state()["audio_stats"]["p99_ms"]` and `["callback_errors"]` exist. Run it: expected FAIL with `KeyError`.
- [ ] **Step 2: Add the new `callback_stats()` fields to `audio_stats`** in `get_state`, keeping every existing key and its meaning unchanged. The UI reads only `xruns`, so extra keys are harmless.
- [ ] **Step 3: Run the new test and the full suite.** Expected: the new test passes; the only other failures are whatever Task 3 and 4 left open.
- [ ] **Step 4: Owner gives the go-ahead** to open the audio device and says which device and driver to use.
- [ ] **Step 5: Run the measurement protocol.** Record Python, NumPy, SciPy, sounddevice versions, host API, device, driver, sample rate, block size, `stream_latency`, power plan, CPU model. At least 10 minutes after a 60 s warm-up per scenario. Scenarios: amp only, NAM, V30 24000-sample IR, all effects on; block sizes 64, 128, 256. Log from `/api/status` at a fixed interval: `p50_ms`, `p99_ms`, `p99_9_ms`, `over_deadline_blocks`, `xruns`, `callback_errors`, `nonfinite_blocks`.
- [ ] **Step 6: Report** with the raw log file path, the setup record, and the pass thresholds the owner approved (proposal: zero xruns, p99.9 under 50% of the deadline, no callback error). Offline timing is never reported as live latency.

---

## Execution log

### 2026-10-24 — Task 3 run on an explicit owner decision, without a listening sign-off

- Diagnosis shown to the owner in chat: the working-tree goldens were recorded from `engine/dsp.py` `838e207c…`, but the tree is `d8086c38…`. Bypassing the AmpHead output soft-clip at runtime brings all twelve sweep cases back to within ~2% of the old golden (the stage lowers every case's peak and RMS to about 0.70×), so the stale goldens differ mainly by that deliberate anti-clipping stage, not by an accidental regression.
- The owner chose **"record new goldens from the current code"** over reverting the DSP. Recorded:
  - `tests/golden/dsp_chain_baseline.json` — 3 cases, fingerprint `d8086c38…`
  - `tests/golden/dsp_chain_sweep.json` — 12 cases, same fingerprint
  - `tests/golden/hd_chain_sweep.json` — 13 cases, `dsp.py` + `world_class_dsp.py` fingerprint `e7361d51…`
- **Task 1 is still open.** These goldens pin the sound that is in the tree now; they are not evidence that it sounds good or matches TONE3000. A negative verdict when the owner listens re-opens the DSP, and the goldens then have to be recorded again.
- Task 4 is moot: `test_cases_are_distinguishable_from_each_other` passes on the new sweep (no pair within 1e-3 RMS and 1e-3 waveform).
- Verification after recording: full suite `272 passed, 3 skipped, 636 subtests passed`; `presets.db` md5 `390b0f34b8e06d9e82a40de5c442ee89` unchanged before and after the run.
- Task 5 (live CPU measurement) untouched; the audio device was not opened.

## Self-review notes
- Spec coverage: listening gate, golden re-record, distinguishability, CPU measurement, local-only rule — each has a task or a Global Constraint.
- Known gap found while planning: `get_state()["audio_stats"]` does not expose the new D4 fields (checked at `engine/audio.py:766-773`), so Task 5 starts with that change; without it a live run cannot read the percentiles.
- No task contains a commit or push step, by the owner's rule.
