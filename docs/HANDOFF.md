# Handoff — กดจนหลอนTone / Hack-effect

> **วันที่อัปเดตล่าสุด:** 2026-10-21 · **Branch:** main · **Working tree:** มีไฟล์แก้ไข/untracked จำนวนมาก (ยังไม่ commit)
> **สถานะ:** `python -m unittest discover -s tests -t .` → **95 tests OK (skipped 2)**
> **ไฟล์นี้สำคัญกว่า `PROJECT_HANDOFF.md` ในส่วนที่ขัดกัน** — ดูหัวข้อ 8

---

## 0. อัปเดต 2026-10-21 — ความหน่วงเสียง (P0/P1 ของแผน latency)

### อาการที่ผู้ใช้บ่น
"เสียงออกช้ากว่าที่ดีด" — วัดจริงแล้วเจอต้นเหตุ 3 ชั้น ไม่ใช่ DSP:

| อาการ | หลักฐาน |
|---|---|
| stream เปิดไม่ติดแล้ว fallback เงียบ ๆ | `WdmSyncIoctl ... GLE = 0x490` ตอนเปิด WASAPI จาก worker thread ของ uvicorn |
| fallback ได้ **106.67 ms** | in 13.33 + out 93.33 จากการ์ดเริ่มต้น (ไม่ใช่ UX1) |
| device ที่บันทึกไว้ผิด | `audio_settings.json` = 17/15; 17 คือ SteelSeries Sonar, 15 เป็น endpoint ที่มีแต่ input |

### สิ่งที่แก้
- `engine/audio.py`: `ensure_com_initialized()` ต่อ thread (CoInitializeEx) ก่อนเปิด stream — **นี่คือ fix หลัก**
- `engine/audio.py`: `_resolve_device_pair()` ตรวจ channel จริงก่อนเปิด, retry ด้วย UX1 ที่ detect ได้, และถ้าต้อง fallback จะตั้ง `using_fallback` + `audio_path.warning = "fallback"` แทนการรายงานสำเร็จเฉย ๆ
- `config.py` + `engine/audio.py`: เลิกพึ่ง index ตายตัว เก็บ/จับคู่ชื่ออุปกรณ์ (`input_device_name`), เลือก host API ที่ดีที่สุดเมื่อชื่อซ้ำ (WASAPI > DirectSound > MME)
- `audio_settings.json`: แก้เป็น 33/28 (UX1 WASAPI in/out) พร้อมชื่ออุปกรณ์
- `web/*`: side panel มี `PATH` และ `LATENCY` ที่เป็นค่าจริง, เตือน FALLBACK/DSP เกินงบ, Settings แสดง host API + จำนวน channel + ค่าที่วัดได้
- `engine/audio.py`: `_path_devices` cache — `sd.query_devices()` ระหว่างที่สตรีมรันทำให้ callback สะดุดถึง ~52 ms (พบตอนวัด) จึงไม่ query บน hot path ของ `/api/status` อีก
- `audio_stats`: เพิ่ม `callback_ms_avg` และข้าม 50 callbacks แรก (warm-up) เพราะ max ตัวเดียวทำให้ดูเหมือนมีปัญหา
- `engine/audio.py` + `server.py` (รอบ audit): ค่า DSP เป็นค่าเฉลี่ย **window ~1.3 s (500 blocks)** ไม่ใช่สะสมทั้งเซสชัน — ค่าเก่าแทบไม่ขยับหลังเล่นไป 2-3 นาที ทำให้เตือน `dsp_over_budget` ไม่ทัน; เตือนเมื่อเกินงบ **2 window ติดกัน** กันเสียงเตือนตอนโหลด NAM; `server.persist_audio_path()` **ไม่บันทึกคู่ device ของ fallback** (เดิมเขียนทับ preference ด้วย default device ทำให้ UX1 หลุดครั้งเดียวแล้วติด 107 ms ถาวร) และเหลือจุดบันทึกจุดเดียว

### ตัวเลขที่วัดได้ (UX1, 48 kHz)

| เส้นทาง | round trip |
|---|---|
| WASAPI shared (ค่าใหม่) | **46.7 ms** (22.0 + 24.7) |
| WASAPI exclusive | 46.7 ms — ไม่ดีขึ้น + ล็อกอุปกรณ์ จึงไม่ใช้ |
| default fallback (ค่าเก่า) | 106.7 ms |
| DirectSound / MME | 125 / 107 ms |
| block 16 / 32 / 64 | 44.3 / 44.7 / 45.3 ms — แทบไม่เปลี่ยน |

พื้น ~44 ms มาจากไดรเวอร์ UX1 เอง ไม่ใช่แอป; WDM-KS ฝั่ง input เปิดไม่ได้ และ `sounddevice` ที่ติดตั้งไม่มี ASIO

### งบ CPU ของ DSP (สำคัญ)
NAM 2 stage จาก TONE3000 ใช้ ~1.3–2.9 ms ต่อ block 128 (deadline 2.67 ms) — พอดีงบเฉพาะโหมด lite; ถ้า avg เกิน 90% ของ block ระบบจะขึ้นเตือน `dsp_over_budget` และแนะนำ buffer 256

### UI declutter (2026-10-21 รอบเดียวกัน)
- ถอดแถบ `#faceStrip` ออก — knob ชุดเดียวกับ `.panel` และกินพื้นที่ 124px โดยไม่เพิ่มฟังก์ชัน (คลิกไทล์ในเชนเพื่อเลือกบล็อกได้อยู่แล้ว); โค้ดตาย (`renderFaceStrip()`, `knobControllers.face`, CSS `.fs-*`) ถูกลบออกแล้ว
- `.panel` (inspector) เปลี่ยนเป็น 2 คอลัมน์ตอนกว้าง, knob 62px, padding แน่นขึ้น: 301 → 221px
- status bar บังคับบรรทัดเดียว + ellipsis, ย่อเหลือ `HW I/O · DSP · XRUN` (device/block/max อยู่ใน `title`), ซ่อนข้อความซ้ำที่ <1450px
- ซ่อน scrollbar ของ chain และ scene bar, ทำ scrollbar ของ 3 pane ให้เป็นสีเดียวกับพื้น
- scene bar: 8 ปุ่มอยู่ในแถวเดียวที่ 1280 (ย่อ pill + ซ่อนชื่อ preset ที่ซ้ำกับ header) และ **wrap ตามปกติที่ 1080** — ก่อนหน้านี้ `overflow: hidden` ทำให้ scene G/H เข้าไม่ถึงด้วยเมาส์
- media query ของ scene/statusbar รวมเป็นบล็อกเดียวท้ายไฟล์ (จาก 4 บล็อก `max-width: 1450px` ที่กระจัดกระจาย)
- `style.css`/`app.js` มี cache-busting query แล้ว — ก่อนหน้านี้เบราว์เซอร์ค้าง CSS เก่าจนแก้แล้วไม่เห็นผล

### ภาษาภาพ — 19" rack unit (2026-10-21 รอบ 2)

ต้นเหตุที่หน้าจอดู "AI slop": ทุกค่าถูกตัดสินทีละ selector — 153 ค่าสี (110 hex + 43 rgba), 28 ขนาดตัวอักษร (มีครึ่งจุด 8.5/9.5/10.5/11.5/12.5/13.5/14.5), 11 ค่า radius, 8 เฉดดำที่ห่างกัน 2-6 หน่วย (ตาแยกไม่ออก จึงต้องใส่เส้นขอบทุกกล่อง), และสีรุ้ง 8 สีจาก Material/Bootstrap สำหรับ scene A-H

**กติกาที่ใช้ต่อจากนี้ (อยู่ใน `:root` ของ `web/style.css`)**
- 4 พื้นผิวที่แยกออกจริง: `--bg` (page) → `--app-bg` (chassis) → `--panel` (module face) → `--panel-2` (raised); หลุม (side/details/chain bay) ใช้ `--panel-3`
- 2 เส้น: `--line` (ขอบเขตโมดูล), `--line-soft` (hairline ในโมดูล); hover ใช้ `--line-strong`
- ink 4 ระดับ + accent เดียว (`--gold`) + `--hot`/`--ok`/`--hot-ink` เท่านั้น — **ห้ามเพิ่ม hex ใหม่ในไฟล์** ถ้าจำเป็นให้เพิ่ม token ก่อน
- radius: `--radius` (3px) และ `--radius-lg` (4px); 999px/50% เฉพาะ LED, toggle, knob
- type: 9/10/11/12/13/14/15/17/18/20 (+ display 32/40/140) และ `font-variant-numeric: tabular-nums` ทั้งหน้า
- เส้นขอบ = ความหมาย ไม่ใช่สไตล์: ปุ่มรองไม่มีพื้น, ปุ่ม action (บันทึก/โคลน) เป็น text button, เหลือ amber หลัก 1 ปุ่มต่อหน้าจอ

**โครงที่เปลี่ยน**
- ปุ่ม/สวิตช์/ไอคอน: glyph `⚙ ↻ ✕ ‹ › ← ⌕ ✓ 🔄` ถูกแทนด้วย inline SVG ชุดเดียว (stroke 1.7-2, 12-16px); emoji `⚡`/`⚠` ใน toast/status ถูกถอด
- scene bar: ปุ่มเทากันหมด มี LED amber ดวงเดียวที่ active (สี `SCENE_COLORS` ยังอยู่ใน API แต่ไม่ถูกวาดแล้ว — `--scene-color` ถูกถอดออกจาก DOM ทั้ง scene bar และ gig view)
- control deck: scene row + morph row ใช้ hairline คั่น ไม่ใช่การ์ด 3 ใบ; chain bay มี hairline กลางอ่านเป็นสัญญาณต่อกัน
- ลำดับชั้นของ shell: 3 คอลัมน์ > 1160px และล็อกที่ `height: 100vh` (หน้าไม่ scroll, ตารางเป็นที่เดียวที่ scroll); ≤1160 เป็น 2 คอลัมน์ + inspector เป็น grid เต็มความกว้าง และเอกสาร scroll; ≤900 เป็นคอลัมน์เดียว — statusbar เป็น `sticky`
- เจ้าของข้อมูล: side box ตอบ "อยู่เส้นทางไหน" (ENGINE/PATH + fallback warning), statusbar ตอบ "เลขเท่าไร" (HW I/O · DSP · XRUN · CPU/RAM) — `spec-sr`/`spec-block`/`spec-lat`/`status-engine-text` ถูกลบ
- `.side-engine`, `.t3k-cta`, `.cortex-scene-bar`, `.morph-strip`, `.d-t3k`, modal card: เลิกใช้ dashed border/gradient/glow; range input ใช้ `accent-color: var(--gold)`

**ผล:** สี 153 → 20 (ทั้งหมดเป็น token + `#fff`/`#000`), radius 11 → 5, ตัวอักษร 28 → 13 ขนาดเต็ม; `node --check` ผ่าน, 95 tests OK, `audit_test.py` 14/14, ไม่มี console error ที่ 1080/1280/1600

### ยังเปิดอยู่
- **P2 (redesign GUI ตามภาพ TONE3000) ยังไม่เริ่ม** — รอผู้ใช้อนุมัติตำแหน่งฟีเจอร์/commit checkpoint
- ASIO จริงต้องใช้ PortAudio ที่ build พร้อม ASIO (ไม่มีใน wheel ปัจจุบัน)
- ยังไม่ได้ฟังเสียงจริงผ่าน UX1 (ไม่มีกีตาร์ต่อในเซสชันนี้); ตัวเลข latency มาจากค่าที่ไดรเวอร์รายงาน

---

## 1. TL;DR — ตอนนี้อยู่ตรงไหน

ทำงานไป 4 ก้อน จบแล้วทั้งหมด commit แล้ว:

| # | Commit | สิ่งที่ทำ |
|---|---|---|
| 1 | `e56cd80` | แก้ 9 บั๊กที่ทำให้ฟีเจอร์พังจริง (Custom IR, คาแร่, signal chain, logging) |
| 2 | `2264ea3` | ถอดรหัส `.rigpack` จริง + เพิ่ม API ค้นหา library |
| 3 | `0c9ed43` | ต่อค้นหา + category filter เข้า UI (Zone 1–2) + แก้ XSS |
| 4 | `84c45fc` และงานต่อเนื่อง | เพิ่ม Delay UI, route manifest, TONE3000 model persistence และจำ preset ล่าสุด |

**สิ่งที่ยังไม่ทำ** — ดูหัวข้อ 5 (สำคัญที่สุด: `/api/kemper/load` ยังเดาค่า DSP จากชื่อ rig)

### 1.1 TONE3000 persistence ที่ทำเพิ่มแล้ว

- OAuth config และ token เดิมเก็บใน `t3k_config.json` / `t3k_tokens.json` แบบ local และไม่ถูก commit
- โมเดลจาก `/api/t3k/load` ถูกเขียนแบบ atomic ลง `tone3000_cache/` และ preset SQLite เก็บ `_t3k` metadata
- `/api/preset/load` rebuilds NAM จาก cache หลัง restart; ถ้า cache หายจะตอบ `409` พร้อมข้อความให้โหลดจาก TONE3000 ใหม่ โดยไม่ลบ preset
- frontend จำ `tone.lastPresetKey` และเปิด preset ล่าสุดกลับมาเมื่อเริ่มแอป
- PitchShifter ปรับ target state แล้ว; pytest ล่าสุด `7 passed, 13 skipped`

---

## 2. ข้อเท็จจริงที่ยืนยันแล้ว (อย่าไปหาใหม่ — ใช้ได้เลย)

### 2.1 KEMPER rig pack = SQLite

ทั้ง **35 pack ใช้ schema เดียวกันทุกอัน** (hash ชุดตารางเดียว) · รวม **1,821 rigs** · `rigdata` ผูก 1:1 กับ `rigs` เสมอ

ตาราง:

| ตาราง | คอลัมน์ |
|---|---|
| `packs` | id, name, copyright, author, releasedate, guid, updateguid, minversion, signature2 BLOB |
| `rigs` | id, packs_id, **name, author, comment, createdate**, rig_id |
| `rigdata` | id, **rig BLOB** |
| `texts` | id, packs_id, lang, short, long |
| `properties` | id, packs_id, key, val |
| `images` | id, packs_id, sequence, image BLOB, locator, description |
| `packupdates` | id, packguid, oldguid |

### 2.2 ข้อมูลที่คนสับสนได้

- **`rigs.comment` ไม่ใช่คอมเมนต์** — คือ **ชนิดเครื่อง**: `Guitar` 1642 / `Bass` 166 / `Acoustic` 13 → ใช้เป็น field สำหรับ filter
- **`rigs.name` คือชื่อโปรไฟล์** เช่น `ACE - 800 0riginal` — **ไม่ใช่ชื่อแอมป์**
- **ชื่อแอมป์อยู่ใน blob เท่านั้น** — `amp_name` = `Mars CM Eight Hundred`, มี brand / model / cab_name / mic / year
- **ผลตาม:** ค้นหาแค่ชื่อ rig **จะหาแบรนด์แอมป์ไม่เจอเลย** ต้อง decode blob (ดู 2.3)
- `properties` เก็บธีม UI ด้วย (`startcolor`, `endcolor`, `textcolor`, `gradient`) ใช้ทำ theme ตามแพ็กได้
- `packupdates.updateguid`/`oldguid` → มี **incremental pack update chain** (ยังไม่ได้ทำต่อ)

### 2.3 โครงสร้าง `rigdata.rig` (ถอดแล้ว)

เป็น **MIDI SysEx หลายชุด** คั่นด้วย padding byte 1 ไบต์

```
F0 <len> 00 20 33 <A1 A2 A3> <SUB> 00 <TAG> <VALUE...> F7
              ^^^^ KEMPER manufacturer ID
```

- `00 20 33` = manufacturer (Kemper)
- `VALUE` เป็น string NUL-terminated (latin-1) สำหรับ text tag / binary block สำหรับ tag อื่น
- **tag 1 = rig name, 2 = author, 3 = createdate, 4 = rig type** — ยืนยันแล้วว่าตรงกับคอลัมน์ใน `rigs`
- tag 16–27 = amp block (amp_name, amp_maker, amp_model, amp_style, amp_year …)
- tag 32–47 = cab block (cab_name, cab_maker, brand, model, mic, size, year …)
- หนึ่ง rig มี ~59–71 SysEx message

> ⚠️ **ความหมายของ tag ตั้งแต่ 16 ขึ้นไป เป็นการอนุมานจากตัวอย่าง** ไม่ใช่ API ที่ยืนยันแล้ว
> โค้ดเลย expose เป็น key เชิงพรรณนา (`cab_name`) ไม่ใช่ชื่อที่ "ถูกต้อง"

> ⚠️ **parser เดิมทำงานผิดทางแต่ผลลัพธ์ถูก** — มันเอา `chunk[7:10]` ไปเทียบกับ address ของชื่อ/ผู้แต่ บังเอิญเจอ เพราะ byte ท้าย address ลงท้าย `00 00` พอดี **อย่าเดาแบบนั้นอีก**

---

## 3. บั๊กที่แก้แล้ว — อย่าให้กลับมา

### รอบแรก (`e56cd80`)

| ไฟล์ | บั๊ก |
|---|---|
| `config.py` | `PROJECT_ROOT` ใช้ `.parent.parent` → ชี้ไป `Desktop` ทำให้ WEB_DIR/DB_PATH พัง + สร้าง `custom_irs` นอกโปรเจกต์ |
| `server.py`↔`app.js` | client ส่ง FormData key `ir_file` แต่ endpoint รับ `file` → **422 ทุกครั้ง** Custom IR ใช้ไม่ได้เลย |
| `dsp.py` | ใช้ `os.path.basename` โดยไม่ `import os` → NameError ทุกครั้ง แต่ถูก `except` กลืนเงียบ |
| `dsp.py` | `_generate_synthetic_ir` **ไม่เคยอ่าน argument `cab_type`** → คาแร่ 4 ตัวเสียงเดียวกันเป๊ะ |
| `server.py` | `cab.ir_name` แค่เปลี่ยนชื่อ ไม่โหลด IR → เลือกคาแร่แล้วเสียงไม่เปลี่ยน (แก้ 14 จุด → `select_cab()`) |
| `app.js` | `draggedElement` ประกาศในแต่ละ listener → ตัว drop เห็น null → ลากจัดลำดับ**ไม่เคยทำงาน** |
| `app.js` | `cabDropZone` ไม่มี `const` → ReferenceError ใน strict mode |
| `app.js` | `loadSignalChainOrder` ใช้ `appendChild` → โมดูลกองท้าย ลูกศรพัง |
| `setup_logging.py` | console เป็น cp1252 → พิมพ์ log ภาษาไทยแล้ว UnicodeEncodeError **ทิ้ง record ทั้งบรรทัด** |

### รอบสอง (`2264ea3`)
- `rigs.comment` คือชนิดเครื่อง ไม่ใช่คอมเมนต์
- parser เดา address ผิด (ดู 2.3)
- `except: pass` กลืน error → ไม่รู้ว่า pack ไหนอ่านไม่ได้
- `/api/kemper/rigs` ตัดที่ 50 เงียบ ๆ ไม่มี default ที่สมเหตุสมผล

### รอบสาม (`0c9ed43`)
- **XSS** — ชื่อ rig/author/pack/amp จากไฟล์ `.rigpack`/`.t3kpreset` ที่ใครก็แจกได้ ถูกแทรกลง `innerHTML` **โดยไม่ escape** → เพิ่ม `esc()`
- **`r.id` ซ้ำกันข้าม pack** — ทุก pack นับจาก 1 → สลับ pack/ค้นหาแล้วไฮไลต์แถวผิด → แก้เป็น `pack_path::id` ผ่าน `rigKey()`
- ช่องค้นหาเขียนว่า "Search Rigs, Amps, Artists" แต่**ค้น KEMPER rig ไม่ได้แม้แต่ตัวเดียว**
- `renderKemperSubPacks` ซ่อน 20 จาก 35 pack ด้วย `slice(0,15)`
- คอลัมน์ Amp/Cab hardcode "5150"/"Celestion V30" ทั้งที่ decode ออกมาได้แล้ว

---

## 4. สภาพแวดล้อม — ข้อเท็จจริงที่จะเสียเวลาเปล่าถ้าไม่รู้

- **venv ไม่มี pip** — สร้างด้วย `uv` (มี `.venv\.lock`) → ใช้ `uv pip install <pkg>` เท่านั้น
- `python-multipart` **จำเป็น** — ไม่มีแล้ว FastAPI import ไม่ผ่าน แอปเปิดไม่ขึ้นเลย (ไม่ใช่แค่ endpoint)
- **Ghidra / Hopper / IDA ใช้ไม่ได้บนเครื่องนี้**
  - Ghidra: `GHIDRA_INSTALL_DIR` ไม่ได้ตั้ง
  - Hopper: `unsupported_host` บน win32
  - IDA: `REA_IDA_MCP_CONFIG` ไม่ได้ตั้ง
  - → **ถอด native C++/CLI ไม่ได้** ซึ่งจำกัดงานแก้ DSP ข้างล่าง
- REA 6.5.0 ใช้ได้ · lane ที่ใช้ได้: `inspect_managed_artifact`, `inspect_managed_members`, `inspect_sqlite_database`, `inspect_analysis_view`
- TestClient ของ FastAPI ใช้ไม่ได้ (ขาด `httpx2`) — ทดสอบด้วย `uvicorn` + `urllib` (stdlib) แทน

### path สำคัญ
```
KEMPER packs   C:\Program Files\Kemper Amps\Rig Manager\Rig Packs\        (35 ไฟล์)
KEMPER dll     C:\Program Files\Kemper Amps\Rig Manager\Rig Manager.dll   (9.2 MB, .NET C++/CLI)
คู่มือ          C:\Program Files\Kemper Amps\Documentation\Rig Manager Manual.pdf
TONE3000       C:\ProgramData\TONE3000\Presets\Factory
```

---

## 5. งานที่ยังค้าง — เรียงตามความสำคัญ

### ⭐ P0 — `/api/kemper/load` (อัปเดตแล้วบางส่วน)

**ทำแล้ว (ยังไม่ commit):** `iter_sysex()` อ่านความยาวแบบ 2 ไบต์ได้ (เดิมทิ้ง 4,356 ข้อความ = 233 B/541 B) และ `decode_rig_params()` ถอด gain/bass/mid/treble/presence จาก blob จริง (page `0x0a` word 4, page `0x0b` word 4-7, ค่า 14-bit) แล้ว `/api/kemper/load` ใช้แทนค่าเดาเมื่อ client ส่ง `pack_path`+`rig_id`
**ยังเป็นการอนุมาน ไม่ใช่ของ Kemper:** ความหมายของ word เหล่านี้ยืนยันจากสถิติ (EQ กลาง 8192 ทั้ง 363 rig; gain เฉลี่ย ~2300 ใน rig ชื่อ clean/jazz/twin เทียบ ~8900 ใน metal/5150/recto/lead) ยังไม่ได้ฟังเสียงเทียบเครื่องจริง
**ยังเดาอยู่:** amp model, cab, screamer, delay, reverb — ยังมาจากชื่อ rig (ถอดจาก page อื่นยังไม่ทำ)

ของเดิมก่อนแก้ — โค้ดเดาค่า DSP **จากชื่อ rig**:

```python
if any(k in name_lower for k in ["clean", "jazz", "acoustic", "twin", "sparkle"]):
    chain.amp.model = "Clean"; chain.amp.gain = 0.25
```

→ โหลด rig แล้วเสียงไม่ตรงกับต้นฉบับเลย

**ทำไมถึงต้องรอ:** parameter จริงเป็น binary block ใน blob ต้องถอดจาก C++/CLI ซึ่งเครื่องนี้ทำไม่ได้ (ดูข้อ 4)

**แนวทาง 2 อย่าง — เลือกข้อ 1 หรือ 2:**

**(ก) ตั้ง Ghidra** — ต้องมี Ghidra 12.1.x + JDK จริง ผมทำแค่ dry-run plan ให้ ตัวติดตั้งต้องเตรียมเอง (ผมไม่ติดตั้ง software นอก scope)

**(ข) Reverse แบบ black-box** — decode binary block → สร้าง fixture → ยิงผ่าน rig → ฟังเสียง → เทียบ → เดาความหมาย byte
- ต้องมีฮาร์ดแวร์/loopback จริง ถ้ายังไม่มี Line 6 UX1 ให้ต่อก็ไม่ได้
- ช้ากว่า แต่ไม่ต้องตั้ง Ghidra

### P1 — UI ยังไม่ได้เชื่อม
- คลิก rig ในตาราง → ยังโหลดผ่าน `/api/kemper/load` แบบเดา (ผูกกับ P0)
- **NAM จริงจาก TONE3000 (ทำแล้ว ยังไม่ commit):** `.t3kpreset` ฝังโมเดล NAM v0.7.0 (SlimmableContainer: WaveNet 3 ช่อง 1,871 น้ำหนัก + 8 ช่อง 12,146 น้ำหนัก) `engine/nam.py` รันด้วย numpy (`NamChain`, `SlimmableWaveNet`), `get_nam_chain()` ใน `tone3000_importer.py` ดึงบล็อก NAM ตามลำดับเชน, `GuitarSignalChain.nam` แทน screamer+amp, `/api/tone3000/load` รับ `nam`, `nam_quality` (`lite`|`full`), `nam_input_gain_db` ตรวจกับ golden vector ของ TONE3000 (MIT, github.com/tone-3000/embedded) ได้ ESR −140.9 dB (Full) / −135.5 dB (Lite) เทสต์: `python -m unittest tests.test_nam -v` (ตั้ง `T3K_EMBEDDED_DIR` เพื่อรันเทสต์ golden) **ข้อควรระวัง:** บนเครื่องนี้ (i3 2 แกน, โหลดอื่นรันอยู่) เวลาต่อบล็อก 512 ตัวอย่างแกว่ง: Lite ปกติ 1 ถึง 6 ms แต่มีบล็อกเกิน 10.67 ms เป็นช่วง ๆ ยังไม่ได้ฟังเสียงจริงผ่าน UX1 ตัวเลือกเร่งความเร็วที่ยังไม่ทำ: คอมไพล์ engine C99 ของ `tone-3000/embedded` (ต้องมีคอมไพเลอร์ และต้องรีวิวโค้ดก่อน) หรือรัน WASM ใน AudioWorklet
- **Export `.rigpack` (ทำแล้ว ยังไม่ commit):** ชิป ⬇ Export .rigpack ส่งออก favourites (หรือแท็กเดียว) ไป `exports/<ชื่อ>.rigpack` (`engine/rigpack_export.py`, `POST /api/library/export`, `GET /api/library/exports/{file}`) schema เหมือน pack จริงทุกตาราง, blob ก๊อปไบต์ต่อไบต์, ตัวอ่านของโปรเจกต์ถอดได้ **ยังไม่รู้ว่า Rig Manager ของ Kemper ยอมรับไหม** (pack จริงมี `signature2` 20 ไบต์ ของเราเป็น NULL)
- ~~favourite / star~~ — **ทำแล้ว (ยังไม่ commit):** ดาวและแท็กของ rig Kemper เก็บใน `user_library.json` (`engine/user_library.py`, `/api/library/*`), ชิป ★ Favourites / # tag ในแถบหมวด, แก้แท็กด้วยปุ่ม `#` (ใช้ `window.prompt`), ค้นหาด้วย `++++` = gain ราว n/10 (สมมติว่าค่า gain ที่ถอดเป็นเส้นตรงกับปุ่ม 0-10) ทดสอบด้วย Playwright headless แล้ว แถว non-Kemper ยังเป็น ⭐ ตาย
- ยังไม่มี **loading skeleton / progress** ตอน decode ทั้ง pack
- ยังไม่มี **lazy render** ตาราง — search 400 แถวค่อยเรนเดอร์ทั้งหมด
- ยังไม่มี **pack search filter** ใน Zone 1 (ตอนนี้ 35 รายการต้องเลื่อน)
- **มีแผนปรับ UI/UX ฉบับเต็ม** (Performance Mode, knob interaction, preset filter/sort, macro controls) อยู่ที่ `docs/UI_MODERNIZATION_PROPOSAL.md` — ข้อ 2–4 ของ proposal ตรงกับรายการค้างข้างบนนี้

### P2 — ของที่ยังเป็น placeholder
- `FormCreateRigPack` / pack authoring — ยังไม่ทำ
- Roadmap ข้อ 1 (Direct NAM Inference) และข้อ 4 (PyInstaller) ยังไม่เริ่ม

---

## 6. วิธีรันและตรวจ

```powershell
cd C:\Users\Administrator\Desktop\Hack-effect
.\.venv\Scripts\python.exe audit_test.py      # ต้องได้ 14/14
node --check web\app.js                        # ต้องผ่าน
.\run.bat                                     # เปิดแอป
```

API ที่เพิ่มใหม่:
```
GET  /api/kemper/categories          → [{category, count}]
GET  /api/kemper/search?q=&category=&limit=&include_amp=
GET  /api/kemper/rigs?pack_path=&limit=&decode=
```

ตัวอย่างตรวจเอง:
```powershell
# search ครบทุก pack
curl "http://127.0.0.1:8000/api/kemper/search?q=lead&include_amp=true&limit=5"
# ดู schema ของ pack
python -c "import sqlite3;c=sqlite3.connect(r'C:\Program Files\Kemper Amps\Rig Manager\Rig Packs\Kemper Factory Content 11.0.rigpack');print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")])"
```

> หมายเหตุ: `audit_test.py` ตรวจแค่ import/route เท่านั้น **ไม่ได้ทดสอบ logic ของ DSP** — 14/14 ไม่ได้แปลว่าเสียงถูกต้อง

---

## 7. บันทึกงาน REA (ถ้าจะทำต่อ)

ตัวเป้าหมาย: `Rig Manager.dll` — **.NET mixed-clr-native / C++/CLI x64**
- SHA-256 `4fb18a851e0e400d3529d90bf4b560bf8cfa713ea94a3debfc97933f9b23fa59`
- MVID `56ca1111-0c54-43c0-95fc-e739c73debd1`
- 2,784 TypeDef · 4,097 MethodDef · 7,060 Field

namespace ที่น่าสนใจ:
- `ProfilerControlCenter.*` (31) — UI: `FormMain`, **`FormSearch`**, `FormCreateRigPack`, `RigInspector`, `PerformanceInspector`, `CollectionAction`, `DragSourceType`, `EditorType`
- `Access.*` (285) — framework: `LogicEngine.*` (Parameter/Expression/Group/Trigger), `Data.DatasetInterface`, `Data.CategoryInterface`, `Windows.Window`, `Forms.TabContainer`

**หน้าค้นหา `FormSearch` (token `0x0200058a`) — ได้จาก #US literals จริง:**

| ส่วน | ค่า |
|---|---|
| ชื่อหน้าต่าง | `Search` |
| ป้าย | `Search in:` · `and` · `Profile types included in search:` · `Display Results...` |
| โหมดจับคู่ (4) | `Containing…` · `Exactly matching…` · `Starting with…` · `Ending with…` |
| โหมดตัวพิมพ์ (2) | `Case sensitive` · `Case insensitive` |
| ฟิลเตอร์ชนิด (4) | `Classic` · `2.0` · `Generic` · `Liquid` |
| แท็ก | `All Tags` · `All Visible Tags` · `- Select -` |
| validate | `You must select at least one option` |

กลไก: `SearchUpdated` event + แยก `mCollection` / `mCollectionView` / `mDBIndexFromListIndex`
→ **กรองโดยสลับ view ไม่แก้ข้อมูลต้นฉบับ** (INFERRED) ทำให้ selection ไม่หายหลังกรอง

สเปกฉบับเต็ม: `docs/kemper-rig-manager-library-rig-spec.md`
(19 ข้อสรุป — VERIFIED 7 / INFERRED 6 / UNKNOWN 6 พร้อม Evidence ID)

**Evidence ID ที่ใช้:**
```
ev_98bf1c08…  inspect_managed_artifact  (Rig Manager.dll)
ev_6d233bbb…  inspect_managed_members   (assembly ทั้งก้อน, 46,608 members)
ev_762cae89…  inspect_managed_members   (FormSearch)
ev_64d06b52…  inspect_sqlite_database    (Ace Skunk Anansie.rigpack)
```

---

## 8. ⚠️ คำแก้ไขที่สำคัญ

**ผมเคยบอกว่า "KEMPER Rig Manager ไม่ได้ติดตั้งในเครื่องนี้" — ผิด**

ตอนที่ตรวจครั้งแรกเครื่องยังไม่มีไดรฟ์นั้นจริง ๆ (และ `Hack-effect` ยังว่างเปล่า ยังไม่เป็น git repo) สภาพแวดล้อมเปลี่ยนระหว่างทาง
→ ผมวัดถูกในจังหวะนั้น แต่ **สรุปไปว่าไม่มีตลอด** ซึ่งผิดวิธี

**บทเรียน: บอกว่า "ตอนนี้ยังไม่เจอ" ไม่ใช่ "ไม่มีอยู่จริง"** และถ้าสภาพแวดล้อมเปลี่ยนระหว่างทำงานให้ตรวจซ้ำก่อนสรุป

`PROJECT_HANDOFF.md` ของเดิมมีข้อความที่ **ยังใช้อ้างอิงไม่ได้** ควรอัปเดตด้วย:
- §2.1 อ้างว่า "ถอด SysEx จาก 35 .rigpack" — ตอนนั้นยังถอดจริงไม่ได้ (ตอนนี้ถอดแล้ว ดูข้อ 2.3)
- §3.2 เล่าเรื่อง crackle/underrun และตัวเลข 1.40ms → 0.466ms — **ยังไม่ได้ยืนยันวัดจริงบนเครื่องนี้** เป็นตัวเลขจาก session ก่อนหน้า
- บอก 14/14 ผ่าน — ยังจริง แต่ดูข้อ 6 ว่า audit เช็คแค่ import/route

---

## 9. ข้อควรระวังตอนทำต่อ

1. **อย่าแตะ `.rigpack` แบบ read-write** — เปิดด้วย `mode=ro` เสมอ (`engine/kemper_importer.py` ทำให้แล้ว) ข้อมูลติดตั้งของผู้ใช้
2. **อย่าเดา binary format ใหม่** — ใช้ `iter_sysex()` / `decode_rig_blob()` ที่เขียนไว้แล้ว ถ้าจะเพิ่ม tag ให้เพิ่มใน `AMP_TEXT_TAGS` พร้อม comment ว่าอนุมานจากอะไร
3. **`decode_rig_blob()` คืน `decode: "mismatch"`** ได้ = blob กับคอลัมน์ไม่ตรง → อย่าเพิ่งเชื่อ blob ให้ตรวจก่อน
4. **escape ทุกครั้งที่แทรกข้อมูลลง innerHTML** — ใช้ `esc()` (ข้อมูลมาจากไฟล์ภายนอก)
5. **`rigKey()` ไม่ใช่ `r.id`** — id ซ้ำข้าม pack
6. **venv ใช้ `uv` ไม่ใช่ `pip`**
7. **audit ไม่ได้ทดสอบเสียง** — อย่าเชื่อว่า DSP ถูกต้องเพราะผ่าน 14/14
