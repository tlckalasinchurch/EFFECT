# SIGNAL_CHAIN_READINESS — Phase 1B Audit (read-only)

> **สถานะ:** audit เสร็จ · **ยังไม่มีการแก้โค้ดใน Phase นี้** · รออนุมัติก่อนเริ่ม refactor
> **วันที่:** 2026-10-23 · **Branch:** `main` · **HEAD:** `bd623ed`
> **Baseline อ้างอิง:** `tests/golden/dsp_chain_baseline.json` (Phase 1A, `engine/dsp.py` sha256 `21dcda2b7c0996d7`, ตรงกับไฟล์ปัจจุบัน)
>
> ป้ายหลักฐาน: **VERIFIED** (อ่านโค้ด/วัดในเซสชันนี้) · **PARTIALLY VERIFIED** · **NOT VERIFIED** · **BLOCKED**

---

## 1. ขอบเขตและข้อสรุปหลัก

เป้าหมาย Phase ถัดไปคือเปลี่ยน `GuitarSignalChain` จาก **class ที่มี attribute ตายตัวและลำดับ hardcode** ให้เป็น **ordered module list** โดยไม่เปลี่ยนเสียง

**ข้อสรุปหลัก 3 ข้อ:**

1. **ลำดับการประมวลผลถูก hardcode ที่เดียว** — `GuitarSignalChain.process` ([engine/dsp.py:1074](../engine/dsp.py#L1074)) ไม่มีข้อมูลลำดับที่ใดอื่นเลย ∴ ต่อให้ UI ลากสลับได้ Engine ก็ทำตามไม่ได้ (VERIFIED)
2. **UI กับ Engine ขัดกันอยู่แล้ววันนี้** — UI แสดง `cab` ก่อน `eq` แต่ Engine ทำ `eq` ก่อน `cab`; และ **`mod` ไม่มีอยู่ใน UI เลย** ทั้งที่ Engine ประมวลผล (VERIFIED)
3. **"พารามิเตอร์" ถูกประกาศซ้ำ 6 ที่** — ไม่มี single source of truth ∴ refactor ต้องรวมมัน ไม่ใช่แค่เปลี่ยน `process()` (VERIFIED)

---

## 2. Current Architecture — เส้นทางสัญญาณจริง

### 2.1 ลำดับใน Engine (VERIFIED — `engine/dsp.py:1074-1120`)

| # | Stage | Runtime object | เงื่อนไข bypass | State ที่ถือข้าม block |
|---|---|---|---|---|
| 0 | input meter + trim | inline | `input_trim_db == 0` → ข้ามการคูณ | `input_level_meter` |
| 1 | Noise Gate | `chain.noise_gate` | `enabled=False` → `return audio` | `envelope`, `last_gain`, `hold_counter` |
| 2 | Pitch Shift | `chain.pitch_shifter` | `enabled=False` หรือ `semitones==0 and cents==0 and mix>=0.999` | `buffer` 2048, `write_pos`, `phase`, portamento `semitones` |
| 3 | Drive / Screamer | `chain.screamer` | `enabled=False` (default **False**) | `zi` biquad |
| 4 | Amp **หรือ** NAM | `chain.amp` / `chain.nam` | NAM ถ้าถูกติดตั้งและ `nam.enabled` ไม่งั้นใช้ `amp` | `amp.lowcut_zi`; NAM ถือ history ทั้งโมเดล |
| 5 | Studio EQ | `chain.eq` | `enabled=False` (default **False**) | `_sections[i][3]` zi ต่อ band |
| 6 | Cabinet IR | `chain.cab` | `enabled=False` | `hp_zi`, `lp_zi`, comb ของ `_tube_mic_sections` |
| 7 | Parallel blend | inline | `parallel_enabled=False` หรือ `blend<=0.001` | ไม่มี (stateless) |
| 8 | Modulation | `chain.mod` | `enabled=False` (default **False**) | `delay_buf`, `write_pos`, `lfo_phase` |
| 9 | Delay | `chain.delay` | `enabled=False` หรือ `mix<=0.001` | `buffer` 2 s, `write_pos`, `_duck_gain` |
| 10 | Reverb | `chain.reverb` | `enabled=False` หรือ `mix<=0.001` | 4 comb buffers, `comb_pos[]`, `_tone_zi`, `_duck_gain` |
| 11 | Master + clip | inline | ไม่มี | `output_level_meter` |

**Parallel tap:** `clean_dry` ถูกจับที่ [dsp.py:1089](../engine/dsp.py#L1089) → หลัง gate+pitch ก่อน drive
**สูตร:** `x = (1-blend)*x + blend*clean_dry` ([dsp.py:1105](../engine/dsp.py#L1105)) — เป็น "dry/wet blend ของทั้ง chain" ไม่ใช่ split/merge จริง

### 2.2 ลำดับที่ UI แสดง (`web/app.js:125-136`) — **ไม่ตรงกับ Engine**

```
UI:     INPUT → GATE → PITCH → DRIVE → AMP → CAB → EQ → DELAY → REVERB → OUTPUT
Engine:          GATE → PITCH → DRIVE → AMP → EQ  → CAB → MOD → DELAY → REVERB
                                                ↑ สลับกัน      ↑ หายจาก UI
```

- `cab` ↔ `eq` สลับกัน (VERIFIED)
- **`mod` ไม่มีใน `BLOCKS` และไม่มีใน `KNOB_SETS`; `grep "\.mod\b" web/app.js` = 0 ผลลัพธ์** → `ModulationProcessor` ถูกประมวลผลแต่ผู้ใช้เปิด/ปรับไม่ได้จาก UI (VERIFIED; เข้าถึงได้ทางเดียวคือ preset ที่ import มาแล้วตั้งค่าไว้)
- `parallel` ก็ไม่มีใน `BLOCKS` เช่นกัน

### 2.3 Noise Gate และ block size (VERIFIED — ต้นเหตุของ baseline ที่ผูกกับ 128)

[dsp.py:49-62](../engine/dsp.py#L49): ค่า `rms` คำนวณจาก **ทั้ง block** แล้ว `target_gain` ถูกนำไปใช้กับ `np.linspace(last_gain, target_gain, len(mono))`

∴ (ก) gain ที่ใช้ขึ้นกับความยาว block (ข) `hold_counter -= len(mono)` ทำให้ hold time ถูก quantize เป็นจำนวน block
**วัดจริง (Phase 1A):** อินพุตเดียวกัน 128 vs 512 samples ต่างกันถึง peak **0.21**; 128 vs 1280 ต่าง **0.30**
**ผลต่อ Phase ถัดไป:** ห้ามเทียบผลข้าม block size และห้าม "แก้" ให้ invariant ในงาน refactor (จะกลายเป็นเปลี่ยนเสียง)

### 2.4 Stateful DSP — จุดที่การเปลี่ยนลำดับ/พารามิเตอร์มีผลข้างเคียง

| Object | เมื่อค่าเปลี่ยน | state ถูกล้าง? | หลักฐาน |
|---|---|---|---|
| `GraphicEqualizer` | `_design_filters()` | **ไม่** — กู้ zi เดิมต่อ section key | dsp.py:900-905 "Reuse filter history per section key so a slider move does not click" |
| `Overdrive` | `_update_filter()` | **ใช่** — `self.zi = np.zeros(...)` | dsp.py:74-81 |
| `CabinetSimulator` | `set_cutoffs()` → `_design_cutoffs()` | **ใช่** — `hp_zi/lp_zi` ถูกล้าง | dsp.py:381-389 |
| `CabinetSimulator` | `set_ir_data()` | **ใช่** — zi ใหม่ + IR ใหม่ | dsp.py:597-600 |
| `Delay` | `time_sec` | ไบต์ไม่ล้าง แต่ read pointer กระโดด → click | dsp.py:739-753 |
| `Reverb` | `decay`/`type` | ไม่ล้าง buffer | dsp.py:772-830 |
| `PitchShifter` | `set_semitones` | ไม่ล้าง buffer, มี portamento | dsp.py:674-690 |

**ข้อบกพร่องที่พบ:** ถ้า `len(audio) > 1422` (comb ที่สั้นสุด) `Reverb.process` จะพังด้วย shape mismatch และ `np.concatenate` ([dsp.py:805-810](../engine/dsp.py#L805)) — ไม่เกิดกับ block 128–512 ที่ใช้จริง ∴ เป็น latent bug (VERIFIED โดยอ่านโค้ด, ยังไม่ได้ reproduce ด้วยการรัน)

### 2.5 Threading — **lock ที่ประกาศไว้ไม่ถูกล็อกจริง**

`server.py:61-66` ประกาศ `ENGINE_STATE_LOCK` และ `_CAB_IR_LOCK` พร้อมคอมเมนต์ว่า "must not race the audio callback"

- `engine/dsp.py` **ไม่มี `import threading`** เลย
- `engine/audio.py` ใช้ `self._lock` เฉพาะใน `start()` (L414) และ `stop()` (L614) — **callback ที่ L305 เรียก `self.chain.process(mono_in)` ไม่ได้ถือ lock ใดๆ**
- ∴ lock ทั้งสองตัวกันได้แค่ HTTP handler ชนกันเอง (VERIFIED)
- `chain.cab.select_cab(...)` ใน `/api/preset/load` ([server.py:342](../server.py#L342)) **ไม่ได้อยู่ใน `_CAB_IR_LOCK`** ขณะที่ `/api/parameter` ([server.py:243](../server.py#L243)) ใส่มา — ไม่สม่ำเสมอ
- `chain.nam = ...` ถูกเขียน 7 จุดโดยไม่มี lock; ปลอดภัยในระดับ reference เพราะ `process()` อ่าน `nam = self.nam` ครั้งเดียวต่อ block ([dsp.py:1093](../engine/dsp.py#L1093)) แต่ `nam.enabled`/`set_input_gain_db` ยังแข่งได้

---

## 3. Proposed Architecture (ยังไม่เขียนโค้ด)

### 3.1 แยก Persistent Configuration ออกจาก Runtime State

```
RigDocument  (persistent, versioned, JSON-serialisable)
├─ schema_version: 2
├─ id / name / author / category
├─ master: { volume, input_trim_db }
├─ parallel: { enabled, blend }            ← ยังเป็น blend เดี่ยว (Engine ไม่รองรับ split จริง)
└─ modules: [ ModuleConfig, ... ]          ← ลำดับคือลำดับประมวลผล
      ├─ slot_id   : "m3"                  ← stable, ไม่ซ้ำ, ใช้ระบุ instance
      ├─ type      : "gate"|"pitch"|"drive"|"amp"|"nam"|"eq"|"cab"|"mod"|"delay"|"reverb"
      ├─ enabled   : bool
      └─ params    : { ... }               ← เฉพาะค่าที่ type นั้นประกาศ

SignalChain (runtime only)
├─ modules: [ {slot_id, type, instance, enabled} ]   ← ลำดับเดียวกับ document
├─ parallel_enabled / parallel_blend / master_volume
├─ _taint(): เก็บ dry tap ตามตำแหน่งที่ document กำหนด
└─ process(x): วนตาม list → gate → ... (ผลลัพธ์ต้องเท่าเดิมเมื่อลำดับเป็น default)
```

**หลักการบังคับ:**

1. **Instance ผูกกับ `slot_id` ไม่ใช่ตำแหน่ง** — ย้าย/สลับลำดับต้องไม่สร้าง object ใหม่ ∴ delay/reverb ไม่เสีย buffer
2. **ลบ module = ทิ้ง instance** — การเพิ่มกลับได้ instance สะอาด (ตั้งใจ)
3. **`apply_params(diff)`** — เทียบ dict เก่า/ใหม่ แล้วเรียก setter เฉพาะค่าที่เปลี่ยน; หลีกเลี่ยงการเรียก `_design_*` ที่ล้าง state โดยไม่จำเป็น (Overdrive zi, cab cutoff zi)
4. **`amp` และ `nam` เป็น module คนละ type** ที่แย่งกัน occupy ตำแหน่งเดียว — document เก็บ `type: "amp"` + `model: {"kind": "dsp"|"nam", ...}` เพื่อไม่ให้เกิด amp+nam พร้อมกัน
5. **ผลลัพธ์ที่ยอมรับได้ของ Phase แรก: default order ต้องให้ผลตรง baseline เป๊ะ และ UI ต้องแสดงลำดับจาก Engine ไม่ใช่ hardcode ใน `BLOCKS`**

### 3.2 ตาราง Parameter ที่ต้องรวมเป็นหนึ่งเดียว (6 ที่ — VERIFIED)

| # | ที่มา | รูปแบบ | จำนวน |
|---|---|---|---|
| 1 | `server.py:194-298` `/api/parameter` | if/elif ต่อ section+param | ~90 บรรทัด |
| 2 | `engine/audio.py:687-760` `get_state()["chain"]` | nested dict (เป็น schema ที่ preset ใช้) | 12 section |
| 3 | `engine/cortex_scenes.py:20-28` `BLOCK_ATTRS`/`PARAM_ALIASES`/`SPECIAL_PARAMS` | name→attr map | 9 block |
| 4 | `engine/morph.py` `DEFAULTS` + `_validate_snapshot` | flat `amp_gain`, `delay_mix`, … | 8 ค่า |
| 5 | `engine/dsp.py:1130-1181` `apply_mooer_preset` | nested dict → attribute | 9 section |
| 6 | `web/app.js:125-215` `BLOCKS` + `KNOB_SETS` | UI descriptor | 10 block / ~40 knob |

**นี่คือเหตุผลที่ refactor ต้องเริ่มจาก *ตาราง* ไม่ใช่จาก `process()`** — ถ้าเปลี่ยนเป็น module list แต่ยังมี 6 ตาราง này diverged ต่อไป จะได้ UI ที่ลากได้แต่ค่าไม่ตรง

---

## 4. Dependency / Call-site Inventory

### 4.1 ผู้สร้างและผู้เรียก `GuitarSignalChain`

| ไฟล์ | ตำแหน่ง | บทบาท |
|---|---|---|
| `engine/audio.py` | L69 | สร้าง instance เดียวของแอป (`AudioEngine.chain`) |
| `engine/audio.py` | L305 | **เรียก `process()` บน audio callback** |
| `engine/audio.py` | L438 | `chain.sample_rate = target_sr` (ไม่สร้าง chain ใหม่, ไม่รีเซ็ต state) |
| `engine/audio.py` | L675-760 | `get_state()` อ่าน attribute ตรงๆ ~90 จุด |
| `server.py` | L194-298 | เขียน attribute ตรงๆ จาก HTTP |
| `server.py` | L304-386 | `load_preset()` เขียน attribute ~40 จุด |
| `server.py` | L805-900 | `/api/kemper/load` เขียน attribute |
| `server.py` | L1048-1170 | `/api/tone3000/load` ติดตั้ง `chain.nam` |
| `engine/morph.py` | `capture_slot`/`set_morph` | เขียน `amp.*`, `screamer.*`, `delay.*`, `reverb.*` |
| `engine/cortex_scenes.py` | L100-180 | เขียน/อ่านผ่าน `BLOCK_ATTRS` |
| `engine/mooer_preset.py` | L212+ | สร้าง dict (ไม่แตะ chain) — apply อยู่ที่ `dsp.apply_mooer_preset` |
| `tests/` | 54 การอ้างถึง attribute | ผูกกับ attribute โดยตรง |

### 4.2 Preset / Format ที่กระทบ

| Format | ที่เก็บ | รูปร่าง | version field |
|---|---|---|---|
| Preset ภายใน | `presets.db.settings_json` | `get_state()["chain"]` ทั้งก้อน | **ไม่มี** |
| Factory presets | `engine/presets.py:DEFAULT_PRESETS` | dict เดียวกัน (subset) | ไม่มี |
| `.rigpack` | SQLite ของ Kemper | blob SysEx → แปลงเป็น attribute | N/A |
| `.t3kpreset` | ไฟล์ภายนอก | NAM weights + chain | ของ TONE3000 |
| MOOER `.mo` | JSON | `mo_to_workstation_preset()` → nested dict | ไม่มี |
| Cortex scenes | dict ใน memory + `SCENE_COLORS` | `param_overrides` ต่อ block | ไม่มี |
| Morph slots | `presets.db.morph_slots` | flat 8 ค่า | ไม่มี |

---

## 5. Refactor Risk Register

| ID | ความเสี่ยง | หลักฐาน | ผลกระทบ | likelihood | mitigation |
|---|---|---|---|---|---|
| R1 | ลำดับ default เปลี่ยนโดยไม่ตั้งใจ → เสียงเปลี่ยน | baseline 3 เคส | สูง | กลาง | characterization test ต้องผ่านก่อน merge |
| R2 | ย้าย/สลับ module แล้ว state (delay/reverb buffer) หาย | dsp.py:733, 777 | กลาง (click) | **สูง** ถ้าสร้าง instance ใหม่ตาม index | ผูก instance กับ `slot_id` |
| R3 | UI ยังใช้ `BLOCKS` hardcode → ลากแล้วไม่ตรง Engine | app.js:125 | สูง | สูง | Phase แรกให้ API ส่ง `modules[]` แล้ว UI render จากมัน |
| R4 | 6 ตารางพารามิเตอร์ diverged ต่อ | §3.2 | สูง | สูง | สร้าง registry เดียวแล้วให้ทุกจุดอ่านจากมัน |
| R5 | lock ที่ไม่ล็อก audio thread ทำให้ IR/cutoff swap ชน | §2.5 | กลาง (เสียงแตก/exception) | กลาง | หลัง refactor ให้ parameter queue ต่อ block |
| R6 | Reverb พังเมื่อ block > 1422 | dsp.py:805 | ต่ำ (ไม่เกิดที่ 128–512) | ต่ำ | ไม่แก้ในงาน refactor; บันทึกไว้ |
| R7 | Noise gate ยัง block-size dependent → เทสต์ข้าม block size ไม่ได้ | §2.3, วัด 0.21 | กลาง (วางกับดัก test) | สูง | ตรึง 128 ในทุก test |
| R8 | preset เก่าโหลดไม่ได้ถ้า schema ใหม่ไม่รับ `settings_json` เดิม | presets.db ไม่มี version | **สูง** (ข้อมูลผู้ใช้หาย) | กลาง | adapter: `settings_json` v1 → `RigDocument` v2 |
| R9 | `apply_mooer_preset` special-case pitch/mod (เลือกทีละตัว) ขัดกับ module list | dsp.py:1156-1170 | กลาง | กลาง | แปลงเป็น "ตั้ง enabled ต่อ module" ตาม preset |
| R10 | `morph.py` เขียน attribute แบบ flat 8 ค่า | engine/morph.py:20-42 | กลาง | กลาง | map ผ่าน registry |

---

## 6. Test Matrix และ Acceptance Criteria

ทุก test รันที่ **48 kHz / block 128 / tolerance 1e-6** ตาม baseline (ยกเว้นที่ระบุ)

| # | Test | ชนิด | เกณฑ์ผ่าน |
|---|---|---|---|
| T1 | default order = baseline 3 เคส | characterization | `test_recorded_cases_still_render_the_same_audio` ผ่าน |
| T2 | bypass ทุก module = passthrough | invariant | bit-exact กับอินพุต |
| T3 | bypass ทีละ module | characterization | RMS/peak ตรงค่าที่บันทึกไว้ ±1e-6 |
| T4 | สลับลำดับ (eq↔cab) | behavior | ผล **ต่าง** จาก baseline อย่างมีนัย (พิสูจน์ว่าลำดับมีผลจริง) และ determinism คงอยู่ |
| T5 | ย้าย delay ไปก่อน cab | state | buffer ไม่ถูกล้าง: ตรวจ `write_pos` ต่อเนื่อง + ไม่มี click ที่ block แรก |
| T6 | เพิ่ม module ที่ไม่มีใน chain | smoke | instance ใหม่ state ว่าง, ไม่มี exception |
| T7 | ลบแล้วเพิ่มกลับ | state | ซ้ำได้ determinism |
| T8 | preset v1 ทุกตัวใน `presets.db` | regression | โหลดได้, ไม่มี KeyError, ค่าตรงกับ `settings_json` |
| T9 | preset v1 → v2 → โหลด | round-trip | ค่า invariant ทุก field |
| T10 | stateful ต่อเนื่อง 10 blocks | state | delay/reverb tail ต่อเนื่อง ไม่ถูกตัด |
| T11 | NaN/Inf parameter | robustness | ถูก reject ที่ boundary (เหมือน `test_morph_quality`) |
| T12 | render ซ้ำ 2 instance | determinism | bit-exact |
| T13 | morph capture/apply | integration | 8 ค่าเดิมแมปถูกหลัง registry เปลี่ยน |
| T14 | `/api/status` chain shape | API | UI ที่มีอยู่ไม่พัง (หรือ UI แก้พร้อมกัน) |

**Acceptance criteria ของ Phase refactor:**
- T1, T2, T3, T8, T10, T12 ผ่านครบ → ถือว่า "พฤติกรรมเดิมไม่เปลี่ยน"
- T4/T5/T7 ผ่าน → ถือว่า "ordered module list ทำงานจริง"
- `115 tests OK (skipped=2)` ต้องคงอยู่ (ห้ามลดจำนวน)
- ไม่แตะค่า DSP algorithm ใดๆ

> ⚠️ **ห้ามอ้างว่า baseline พิสูจน์คุณภาพเสียง** — มันพิสูจน์แค่ว่า "ไม่เปลี่ยนจากเดิม" ยังไม่มี reference จากเครื่องจริงหรือ loopback

---

## 7. ไฟล์ที่ Phase ถัดไปอาจต้องแก้

| ไฟล์ | เหตุผล | ความเสี่ยง |
|---|---|---|
| `engine/dsp.py` | `GuitarSignalChain` → module list; `apply_mooer_preset` | สูงสุด — baseline ผูกกับไฟล์นี้ |
| `engine/audio.py` | `get_state()["chain"]`, sample_rate change, lock | สูง (schema ที่ UI ใช้) |
| `server.py` | `/api/parameter`, `load_preset`, kemper/t3k load | สูง |
| `engine/cortex_scenes.py` | `BLOCK_ATTRS` → registry | กลาง |
| `engine/morph.py` | flat 8 ค่า → registry keys | กลาง |
| `engine/presets.py` | adapter v1 → v2 | กลาง |
| `web/app.js` | `BLOCKS`/`KNOB_SETS` ← รับจาก API | กลาง (ไม่มี test ครอบ UI) |
| `engine/mooer_preset.py` | output ของ `mo_to_workstation_preset` | ต่ำ |
| `tests/test_audit_fixes.py`, `test_cortex.py`, `test_mooer_dsp.py`, `test_pitch_shift.py` | 54 จุดอ้าง attribute | ต่ำ (แก้กลไก ไม่แก้ความหมาย) |

---

## 8. Checkpoint Plan (ต้องได้รับอนุมัติก่อนทำ)

**สถานะจริงของ working tree (VERIFIED, 2026-10-23):** 15 ไฟล์ tracked ที่ถูกแก้ + 34 รายการ untracked (49 ทั้งหมด) — 15 ไฟล์ tracked แก้มาก่อน Phase 1A และ **ไม่ใช่งานที่ผมสร้าง**; ส่วนที่เพิ่มเข้ามาใน Phase 1A/1B คือไฟล์ใหม่ 4 รายการ (`engine/morph.py` แก้ของเดิมแต่ยัง untracked, `tests/test_characterization.py`, `tests/test_morph_storage.py`, `tests/golden/`, `docs/SIGNAL_CHAIN_READINESS.md`) ∴ **ไม่มีไฟล์ tracked ใดถูกแก้เลย**

**ปัญหาที่ต้องตัดสินใจ:** `engine/morph.py` เป็นไฟล์ **untracked** มาตั้งแต่ก่อน Phase 1A ∴ ในประวัติ git ไม่มี "เวอร์ชันก่อนแก้" ให้แยก — เนื้อหาทั้งไฟล์ (ของผู้พัฒนาก่อนหน้า + fix ของ Phase 1A) จะเข้ามาเป็นไฟล์ใหม่ทีเดียว แยกไม่ได้ด้วย git

ทางเลือก (ยังไม่ทำอันใด):

| ทางเลือก | ทำอะไร | ข้อดี | ข้อเสีย |
|---|---|---|---|
| **A (แนะนำ)** | commit เฉพาะ 4 ไฟล์ของ Phase 1A (`engine/morph.py`, `tests/test_characterization.py`, `tests/test_morph_storage.py`, `tests/golden/dsp_chain_baseline.json`) พร้อมข้อความระบุว่า `morph.py` มีงานเดิมอยู่ก่อน | checkpoint ที่ผูกกับ Phase 1A ตรง, ไม่แตะไฟล์อื่น | ต้องยอมรับว่า morph.py ยกมาทั้งไฟล์ |
| B | commit ทั้งหมดเป็น "WIP checkpoint" เดียว | ปลอดภัยต่อการ rollback ที่สุด | ปนงานหลายเจตนา, ต้องอนุมัติชัดเจน |
| C | ไม่ commit — สำรองเป็น zip ที่ `exports/` หรือ `scratch/` | ไม่แตะ git เลย | ไม่ใช่จุดอ้างอิงที่ตรวจสอบได้ |

**ห้าม:** `git add -A`, `git reset`, `git checkout`, `git clean`, commit ไฟล์ installer/`.superpowers/`/`t3k_tokens.json`

---

## 9. สิ่งที่ยังยืนยันไม่ได้

| หัวข้อ | สถานะ | เหตุผล |
|---|---|---|
| เสียงจริงเทียบ Kemper/Quad Cortex | **NOT VERIFIED** | ไม่มี reference และไม่มี loopback |
| Latency หลังแก้ | **NOT VERIFIED** | ยังไม่วัดจาก stream จริง |
| Reverb block > 1422 พังจริง | **PARTIALLY VERIFIED** | อ่านโค้ดชี้ว่า shape mismatch แต่ยังไม่ได้รัน reproduce |
| UI ไม่มี `mod` | **VERIFIED** | `grep "\.mod\b" web/app.js` = 0, ไม่มีใน `BLOCKS`/`KNOB_SETS` |
| NAM golden vector | **BLOCKED** | ไม่มี checkout `tone-3000/embedded` |
| `nam_c99.dll` ทำงานได้จริงไหม | **NOT VERIFIED** | ไม่มี `.namb` และไม่มีโค้ดเรียกใช้ |

---

## 10. Phase 2B — ต่อ registry เข้ากับ write path (ทำแล้ว)

**สถานะ:** implemented · **วันที่:** 2026-10-23 · ต่อจาก Phase 2A (`engine/params.py` เป็น data ล้วน)

### 10.1 สิ่งที่เปลี่ยน

| ไฟล์ | เดิม | ใหม่ |
|---|---|---|
| `engine/param_access.py` | — | ทางเขียนพารามิเตอร์ทางเดียว: coerce ตาม `kind`, clamp เฉพาะที่ `Param.clamp`, เรียก setter ตาม signature จริงของ method, รับ index (`band3`) |
| `server.py` `update_parameter` | if/elif ~85 บรรทัด ฝังชื่อ attribute ทุกตัว | 1 call เข้า `param_access.set` + 2 ข้อยกเว้นที่อธิบายไว้ (nam, cab IR lock) |
| `engine/dsp.py` `apply_mooer_preset` | ~60 บรรทัดไล่ assign ทีละ key | `param_access.apply_settings` ต่อ block, เก็บเฉพาะตรรกะ pitch/mod และการไม่ทับ `amp.model` |
| `engine/params.py` | — | เพิ่ม `assign` (setter เป็นเจ้าของการเขียน) และ `clamp` (ที่ที่ API เคย clamp จริง) |

`assign=False` มี 3 ตัว และเป็นเหตุผลเชิงพฤติกรรม ไม่ใช่สไตล์: `pitch.semitones` (ต้องให้ค่า audible glide ตาม), `eq.model_id` (`set_model` reset bands เฉพาะเมื่อ model เปลี่ยน), `eq.bands` (`set_bands` เป็นเจ้าของ list + การ design filter)

### 10.2 หลักฐานว่าเสียง/พฤติกรรมไม่เปลี่ยน

| หลักฐาน | ผล |
|---|---|
| `tests/golden/parameter_dispatch.json` — state ที่ `/api/parameter` คืนให้ 1 probe ต่อพารามิเตอร์ + probe นอกช่วง | บันทึกจากโค้ดเดิม **ก่อน** refactor, replay ตรงทุก byte |
| `tests/golden/mooer_apply.json` — state หลัง `apply_mooer_preset` ของ factory preset ทั้งหมด | ตรงทุก byte |
| Audio ของ `apply_mooer_preset`: old apply vs new apply, 4096 samples @48k/block 128 | **bit-identical ทั้ง 5 preset** (วัดในเซสชันนี้ ไม่ได้เก็บเป็น test เพราะโค้ดเก่าจะหายไปหลัง commit) |
| `tests/test_chain_sweep.py` (12 scenarios) + `test_characterization.py` | ผ่าน — `process()` ไม่ถูกแตะ |
| Negative control | บังคับ clamp ทุกพารามิเตอร์ → golden fail ที่ `gate.threshold`/`mod.model_id`; เลิก withhold `amp.model` → mooer golden fail ทั้ง 5 preset |

### 10.3 Bug ที่เจอและ **จงใจไม่แก้** ในรอบนี้

`apply_mooer_preset` เดิมเขียน `screamer.tone = ...` โดยไม่เรียก `_update_filter()` ∴ biquad ของ tone ค้างค่าจาก preset ก่อนหน้า (หรือค่า default 0.6) ทั้งที่ state บอกค่าใหม่ — preset 3 ใน 5 ตัวมี tone ต่างจาก default จึงได้เสียงไม่ตรงกับปุ่มที่แสดง

ถ้าปล่อยให้ registry เรียก setter ตามปกติ เสียงจะเปลี่ยน (ถูกต้องขึ้น) แต่ **golden ที่บันทึกไว้มองไม่เห็น** เพราะ state ที่ API เปิดเผยไม่มีค่า coefficient ∴ รอบนี้จึงเก็บพฤติกรรมเดิมไว้ด้วย `param_access.set(..., hook=False)` และคอมเมนต์กำกับ **การแก้คือลบ `hook=False` ออกบรรทัดเดียว** แล้ว re-record golden ด้วย `--accept-changed-code`

### 10.4 ที่ยังไม่ต่อ registry (ตั้งใจ)

`engine/audio.py get_state()` (schema ที่ UI/preset ใช้), `server.py load_preset` (มี default ต่อ block + NAM/T3K), `cortex_scenes.py`, `morph.py`, `web/app.js` — ทั้งหมดยังประกาศซ้ำ แต่ `tests/test_param_registry.py` ผูกไว้กับ registry แล้ว (state shape, BLOCK_ATTRS, PARAM_ALIASES, morph flat keys, mooer producer keys, UI knobs)

---

## 11. Device-mode plan — เหลือเฉพาะ generic และ TONE3000/NAM

**สถานะ:** generic และ NAM/TONE3000 ใช้งานได้; GE150, Quad Cortex และ Kemper modes ถูกถอดออกเพราะเสียงไม่ผ่านการใช้งาน · **วันที่:** 2026-10-24

### 11.1 สิ่งที่เปลี่ยน

| ไฟล์ | เดิม | ใหม่ |
|---|---|---|
| `engine/device_mode.py` | — | ตาราง mode เหลือ `generic` และ `nam`; `mode_for_source()` เลือก NAM เฉพาะ TONE3000/NAM |
| `engine/dsp.py` `GuitarSignalChain` | `process()` เรียกบล็อกตามลำดับตายตัว | เรียกตาม `self._stage_order` ของ `device_mode`; `generic` คือลำดับเดิมทั้งหมด |
| `tests/test_device_mode.py` | — | 12 tests: ความครบของตาราง, mapping source, setter, และ generic ต้องตรง golden |

`device_mode` เป็น property: generic เป็นค่าเริ่มต้นและพรีเซ็ต MOOER ไม่ auto-switch; โหลด TONE3000/NAM แล้วเลือก `nam` ส่วนชื่อโหมดอื่น raise `ValueError` (พรีเซ็ตเก่าที่มีโหมดที่ถอดออกจะ fallback เป็น generic)

### 11.2 หลักฐานว่า generic ไม่เปลี่ยนเสียง

| หลักฐาน | ผล |
|---|---|
| `dsp_chain_baseline.json` (3 เคส), `dsp_chain_sweep.json` (12 เคส), `hd_chain_sweep.json` (13 เคส) | ผ่านโดยไม่ re-record หลังแก้ `process()` |
| `test_generic_mode_reproduces_the_recorded_sweep` | เทียบ golden ที่ `atol=1e-9` (golden ปัด 9 ตำแหน่งแล้ว) |
| `test_explicit_generic_matches_the_default_constructor_bit_for_bit` | `assert_array_equal` ระหว่าง chain ที่ตั้ง `generic` กับ constructor ปกติ |
| `test_stage_calls_follow_the_declared_engine_order` (มีอยู่แล้วใน `test_rigdoc.py`) | ยังผ่าน: ชื่อบล็อกและลำดับใน `process()` ตรง `params.PROCESS_ORDER` |

### 11.3 ลำดับที่ยังรองรับ

| โหมด | ลำดับ | ที่มา |
|---|---|---|
| `generic` | gate → pitch → tap → screamer → amp → eq → cab → parallel → mod → delay → reverb | ลำดับเดิมของ engine; พรีเซ็ต MOOER และเสียงในตัวใช้เส้นทางนี้ |
| `nam` | เท่า `generic` | TONE3000/NAM แทน amp block |

การเลือก `nam` ไม่อ้างว่า emulation ของ GE150/Cortex/Kemper ใช้ได้; โหมดและ auto-switch ของสามแหล่งนั้นปิดไว้จนกว่าจะมี implementation และ listening verification จริง
- per-mode defaults และ voicing ภายในแต่ละบล็อก (GE150 amp 55 แบบ, Kemper profile, Cortex scenes, NAM หลาย stage) ยังไม่ทำในระยะนี้
