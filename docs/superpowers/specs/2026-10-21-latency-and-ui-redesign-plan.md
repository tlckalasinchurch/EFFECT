# แผนงาน: ลดความหน่วงเสียง + ปรับ GUI ใหม่ (สำหรับทำต่อ 2026-10-21)

> เขียนเมื่อ 2026-10-21 หลัง brainstorm กับผู้ใช้ · สถานะ: **P0 + P1 ทำเสร็จแล้ว** (ดู §8) · P2–P4 ยังรอการตัดสินใจ
> อ่านไฟล์นี้ก่อนเริ่มงานวันถัดไป · ป้ายหลักฐาน: **VERIFIED** (ตรวจในเซสชันนี้) / **ASSUMPTION** / **BLOCKER** / **NEXT**
>
> **อัปเดต 2026-10-21 (รอบที่ 2):** P0 ผ่าน, P1 แก้จริงและวัดผลได้ — สรุปอยู่ท้ายไฟล์ §8

---

## 1. เป้าหมายของผู้ใช้ (คำของผู้ใช้เอง)

- ใช้ **ซ้อมที่บ้านเป็นหลัก** รองลงมาคือเล่นสดแทน Kemper / Quad Cortex. ฟังผ่าน **หูฟังที่ต่อ UX1 โดยตรง**.
- พฤติกรรมหลัก: "เปิดมาโหลดเสียงแล้วเล่นเลย".
- ปัญหาที่บ่น: (1) เสียง **ออกช้ากว่าที่ดีด** และไม่เหมือน Kemper / Quad Cortex / ตัวอื่นที่เคยใช้ (2) GUI **ใช้ยาก หาปุ่มไม่เจอ ปุ่มเมนูงง เหมือน AI slop และไม่ทันสมัย**
- อยากให้หน้าตาเป็นแบบ **ล้ำ ๆ** เหมือน Quad Cortex กับปลั๊กอิน Neural DSP และมี "ของดีของแต่ละเจ้า" รวมกัน.
- ภาพ reference ที่ผู้ใช้ให้: `docs/ui-references/tone3000/tone3000_plugin_reference.jpg` (TONE3000 Plugin style: แผงแอมป์ใหญ่กลางจอ, Tone Library ขวา, chain การ์ดสีต่อกันด้วย `+`, การ์ดเอฟเฟกต์ล่าง, status bar). ผมคัดลอกมาจากโฟลเดอร์อัปโหลดของเครื่องมืออื่น เพราะใน `docs/ui-references/` เดิมมีแต่ภาพ Kemper.

## 2. Anti-goals (ถ้าเป็นแบบนี้ถือว่าล้มเหลว แม้ทำงานได้)

- หน้าตาสวยแต่ปุ่มไม่ต่อเข้า DSP จริง (Mock UI).
- ฟีเจอร์เพิ่มแต่หาปุ่มยากกว่าเดิม.
- แก้ latency แล้วเสียงขาดช่วง/แตก (xrun) หรือล็อกการ์ดเสียงจนใช้อย่างอื่นไม่ได้โดยผู้ใช้ไม่รู้ตัว.

---

## 3. สถานะปัจจุบัน

### ที่ตรวจแล้ว (VERIFIED)
- **ความหน่วง:** `audio_settings.json` = 48000 Hz, buffer 128, device 17 (เข้า) / 15 (ออก). ทั้งสองเป็น **Windows WASAPI แบบ shared** บน Line 6 UX1 (ตรวจด้วย `sd.query_devices`). `sd.Stream` ที่ `engine/audio.py:212` ตั้ง `latency='low'` แต่ไม่ตั้ง exclusive.
- PortAudio ใน `sounddevice` 0.5.6 มี host API แค่ MME, DirectSound, WASAPI, WDM-KS **ไม่มี ASIO**. โค้ดที่ `engine/audio.py:63-74` ตั้งใจเลือก ASIO ก่อนจึงไม่เคยได้ผล. ในโฟลเดอร์ `ASIO driver/` มีแค่ `ASIO4ALL_2_15_En.exe` ที่ยังไม่ได้ติดตั้ง.
- **Audit + แก้บั๊กรอบก่อน (2026-10-20):** `web/app.js` ขาด 4 ฟังก์ชัน ทำให้ `boot()` พัง. กู้คืนแล้ว, แก้ scene override สะสม, EQ Studio (Low/High Cut, shelf จริง), Reverb tone/type, tube saturation, filter-state ไม่รีเซ็ตตอนปรับ. รัน `.venv/Scripts/python.exe -m unittest discover -s tests -t .` ได้ **74 tests OK (skipped 2)**. เทสต์ใหม่อยู่ที่ `tests/test_audit_fixes.py`.
- ไฟล์ `engine/nam_c99.dll`, `nam_c99.py`, `a2lite_template.bin`, `a2full_template.bin` มีอยู่ใน repo.

### ที่ยังไม่ได้ตรวจ (NOT VERIFIED)
- **ยังไม่เคยเปิดหน้าเว็บจริงในเบราว์เซอร์หลังแก้ `app.js`** สกรีนช็อตแอปของเครื่องมืออื่น (`.gemini/.../.tempmediaStorage/media_1792427204683_b875f05a.png`) เป็นหน้าขาวล้วน. อาจเป็นอาการ boot พังเดิม หรืออย่างอื่น. ASSUMPTION ว่าแก้แล้ว.
- `audio.py` เรียก C99 engine (`nam_c99`) จริงหรือไม่ (log ของเครื่องมืออื่นบอกขัดกันเอง). ตัวเลข "14/14", "47 tests" ใน log ของเครื่องมืออื่น ไม่ใช่หลักฐานของผม.
- ไม่ได้ฟังเสียงจริง (tube saturation, คลิกตอนลากไมค์/ปรับ EQ).
- ใน `docs/HANDOFF.md` ระบุ "working tree สะอาด" ซึ่ง **ไม่ตรงความจริงแล้ว** (มีไฟล์แก้ไขและ untracked จำนวนมาก, ยังไม่ commit อะไรเลย).

### ช่องว่างจาก audit ที่ยังเปิดอยู่
- Parallel ยังไม่มีแผนผัง Split/Merge ใน UI (มีแค่ปุ่ม + สไลเดอร์).
- Ducking มีแค่ checkbox + Depth ไม่มี Threshold/Sensitivity (threshold 0.035 hardcode ใน `engine/dsp.py`, envelope ทำระดับ block).
- Morph ทำ interpolation แค่ 8 พารามิเตอร์ และสลับ enabled แบบขั้นบันไดที่ 0.5.
- EQ Studio: ความถี่ของ Mid 1 (700 Hz), Mid 2 (2400 Hz), shelf (150 Hz / 6 kHz) ตายตัว.
- `Reverb.process` พังถ้า block ยาวกว่า comb ที่สั้นสุด 1422 samples (`engine/dsp.py` ลูป comb). block จริง 128–512 จึงไม่เจอ.

---

## 4. แผนงาน (เรียงตามลำดับ)

### P0 — ยืนยันว่าแอปเปิดได้จริง (ทำก่อนทุกอย่าง) · NEXT
1. รัน `run.bat` (หรือ `.venv\Scripts\python.exe main.py`) เปิดหน้าเว็บจริง. เปิด DevTools ดู console ว่าไม่มี `ReferenceError`.
2. เช็ค: ปุ่มซีน A–H ขึ้นหรือไม่, กด Gig View ได้, Esc ปิดได้, ลากไมค์ในบล็อก IR CAB, EQ แสดงกราฟ, Morph/Parallel ตอบสนอง.
3. ถ้าพังให้แก้ก่อน P1/P2. **ห้ามเขียน UI ใหม่ทับของที่ยังไม่เคยเห็นว่าทำงาน.**

### P1 — ลดความหน่วงเสียง (ตรงกับปัญหาแรกของผู้ใช้)
- ทางเลือก (ผู้ใช้ตัดสินใจ ดูข้อ 6):
  - **A (แนะนำ):** WASAPI exclusive ผ่าน `sd.WasapiSettings(exclusive=True)` ใน `engine/audio.py` (จุดเปิด stream บรรทัด ~212 และ fallback ~230). แก้ง่าย แต่ล็อก UX1 ให้แอปนี้ตัวเดียว (เสียงจากโปรแกรมอื่นผ่าน UX1 จะไม่ออกระหว่างแอปเปิด).
  - **B:** ASIO จริง ต้องเปลี่ยนไปใช้ PortAudio ที่ build มาพร้อม ASIO + driver ของ UX1. เสี่ยงและงานมากกว่า.
- งานในแอป: ปุ่มเลือกโหมดเสียงในหน้า Settings, แสดง latency จริง (ใช้ `audio_stats.stream_latency` ที่มีอยู่ใน `get_state()`) บนแถบบน, แจ้งเตือนถ้า exclusive เปิดไม่ได้ (fallback ไป shared แล้วบอกผู้ใช้ชัด ๆ).
- วัดผล: เทียบ latency ก่อน/หลัง ด้วยค่าที่ stream รายงาน และ `tools/mock_ux1_hardware.py`. **ผู้ใช้ต้องฟังเองว่าหายหน่วง** ผมวัด loopback จริงไม่ได้.
- ตรวจ xrun ที่ buffer 128 หลังเปลี่ยน (มี `audio_stats.xruns` อยู่แล้ว). ถ้าแตกให้ลอง 256.

### P2 — GUI ใหม่ตามภาพ TONE3000 (ต้องให้ผู้ใช้อนุมัติ mockup ก่อน)
เลย์เอาต์ตามภาพ reference + ตำแหน่งฟีเจอร์ของเรา (mockup: `docs/ui-references/tone3000/placement-ideas-mockup.html` เปิดในเบราว์เซอร์ได้):

| # | ฟีเจอร์ | ตำแหน่งที่เสนอ |
|---|---|---|
| 1 | Gig View | ปุ่ม `GIG VIEW` บนแถบบนสุด |
| 2 | ซีน A–H + Morph | แถบบางใต้หัวพรีเซ็ต (กดเลข 1–8 ได้), Morph A↔B ปลายแถบ |
| 3 | Parallel | ปุ่มเปิดแล้วมีเลนสะอาดโผล่ใต้ chain + Blend ให้เห็นจุดแยก/รวม |
| 4 | Delay (และ Mod) | เพิ่มเป็นบล็อกใน chain (reference ไม่มี แต่ DSP เรามีจริง) |
| 5 | EQ 5 ย่านพร้อมกราฟ, IR Cab + ไมค์ลากได้, Delay + Ducking | แท็บใน panel กลาง (ข้างแท็บ Amp Control/Gate/Pitch/Reverb) |
| 6 | การ์ดล่าง | 6 ใบ: Gate, Pitch, IR Cab, Delay, Reverb, Mod. Ducking เป็นสวิตช์ในการ์ด Delay/Reverb |

- Tone Library ขวาเป็นการ์ดมีรูป + ช่องค้นหา + ปุ่มกรอง; **เสียง Kemper แยกเป็นหมวดของตัวเอง**. รูปหัวแอมป์/ตู้ต้อง **วาดเองด้วย SVG/CSS** (ไม่มีรูปจริง) ← ASSUMPTION/การตัดสินใจของผม.
- แถบบน: สเปกเสียง + dropdown เลือก In/Out + Master + มิเตอร์ IN/OUT. Status bar ล่าง: CPU/RAM/latency (`audio.py` มี telemetry ผ่าน Win32 API ตาม log เครื่องมืออื่น — ต้องตรวจว่ามีใน repo นี้จริง).
- **กฎ:** ทุก control ต้องต่อ DSP จริง ถ้า backend ยังไม่มีให้ระบุ BLOCKER ห้ามทำปุ่มหลอก.
- **ความเสี่ยง:** เคยมีรอบที่ UI ถูกเขียนใหม่แล้วหายไป (log เครื่องมืออื่นบอกว่าสร้าง TONE3000 UI แต่ `web/index.html` ปัจจุบันไม่มีคำว่า `faceplate` หรือ `Tone Library` เลย). ก่อนเริ่ม P2 **ขอให้ผู้ใช้อนุญาต commit/สร้าง branch เป็น checkpoint** (ปัจจุบันยังไม่ commit อะไรเลยตามกฎของผู้ใช้).
- ทำทีละส่วน แล้วรัน `tests/test_audit_fixes.py` (เทสต์ผูก frontend: ฟังก์ชันที่เรียกต้องมีนิยาม) หลังทุกก้อน. ควรเพิ่มเทสต์ผูก id ของ DOM ที่ JS อ้างถึงต้องมีใน `index.html`.

### P3 — ฟีเจอร์ซ้อมที่บ้าน (เลือกตามที่ผู้ใช้อยากได้)
เสนอ (ยังไม่ได้ถามว่าอยากได้ข้อไหน): **Audition** (คลิกเสียงในลิสต์แล้วได้ยินเลย แบบ Kemper), **A/B เทียบเสียง**, **backing track + เมโทรโนม**, ตั้ง latency ในแอป (ซ้ำกับ P1). ผมแนะนำ Audition + A/B ก่อน เพราะแก้ปัญหา "หาเสียงยาก".

### P4 — เก็บช่องว่างจาก audit (ลำดับต่ำ)
แผนผัง Parallel, Ducking threshold/sensitivity + envelope ระดับ sample, Morph ครอบคลุมพารามิเตอร์มากขึ้นพร้อม smoothing, ความถี่ EQ ปรับได้, แก้ Reverb ให้รองรับ block ยาว, อัปเดต `docs/HANDOFF.md` ให้ตรงความจริง.

---

## 5. สิ่งที่ผมตัดสินใจเอง (ผู้ใช้ยังไม่ได้ยืนยัน)

- ใช้เลย์เอาต์ภาพ TONE3000 เป็นหลัก ฟีเจอร์ Quad Cortex/Kemper เป็นส่วนเสริมตามตาราง P2. (ผู้ใช้เลือกแนวภาพนี้ แต่ยังไม่ได้ตอบเรื่องตำแหน่งฟีเจอร์เสริม)
- วาดรูปแอมป์ด้วย SVG/CSS เอง.
- แนะนำ WASAPI exclusive ก่อน ASIO.

## 6. คำถามที่ต้องให้ผู้ใช้ตอบ (BLOCKER ของ P1/P2)

1. **WASAPI exclusive** ยอมให้ล็อก UX1 ตอนเปิดแอปไหม (เสียงโปรแกรมอื่นผ่าน UX1 จะไม่ออก)?
2. ตำแหน่งฟีเจอร์ตาม mockup ข้อ P2 โอเคไหม หรืออยากตัดอะไรออก?
3. อนุญาตให้ commit / สร้าง branch เป็น checkpoint ก่อนแก้ GUI ไหม?
4. ฟีเจอร์ซ้อมข้อไหนอยากได้จริง (Audition / A-B / backing track / เมโทรโนม)?

## 7. ไฟล์และคำสั่งที่เกี่ยวข้อง

- รันเทสต์: `.venv\Scripts\python.exe -m unittest discover -s tests -t .` (ไม่มี pytest ใน venv)
- รันแอป: `run.bat` → `main.py` → FastAPI ที่ `http://127.0.0.1:8000`
- ภาพ/mockup: `docs/ui-references/tone3000/` (reference .jpg + 2 mockup .html) · mockup ทั้งหมดของเซสชันนี้อยู่ใน `.superpowers/brainstorm/` (ยังไม่อยู่ใน `.gitignore` ← ควรเพิ่ม `.superpowers/`)
- ไฟล์โค้ดหลัก: `engine/audio.py` (stream, state), `engine/dsp.py` (DSP), `server.py` (API), `web/app.js` `web/index.html` `web/style.css`
- ผลงานรอบ audit: `tests/test_audit_fixes.py`; รายงานเดิม `docs/reverse-engineering/`
- **ข้อควรระวัง:** `scratch/patch_panel_and_features.py` มี guard string ที่ผิด (เป็นต้นเหตุให้ 4 ฟังก์ชันหาย) อย่ารันซ้ำ.

---

## 8. ผลการทำ P0 + P1 (2026-10-21 รอบที่ 2)

### P0 — VERIFIED
เปิด `uvicorn server:app` ที่ `http://127.0.0.1:8000` แล้วเปิดด้วยเบราว์เซอร์จริง:
- console ไม่มี `ReferenceError` (network: `/api/presets`, `/api/tone3000/presets`, `/api/status` = 200 ทั้งหมด)
- ซีน A–H ครบ, Morph + Parallel ตอบสนอง, Gig View เปิด/ปิดได้, ตั้งค่าเปิดได้
- side panel + status bar อัปเดตค่าจริงจาก engine

### P1 — เวอร์ชันที่ทำจริง (ต่างจากแผนเดิม เพราะหลักฐานการวัด)
แผนเดิมเสนอ WASAPI exclusive; วัดแล้ว **exclusive ไม่ลด latency เลย** (46.7 ms เท่ากับ shared) แต่ล็อกอุปกรณ์ให้แอปเดียว → **ไม่เพิ่มตัวเลือก exclusive** และแก้ที่ต้นเหตุจริงแทน:

1. **`ensure_com_initialized()`** — WASAPI ต้องมี COM apartment ของ thread ที่เปิด stream; uvicorn รัน handler บน worker thread ที่ไม่มี COM ทำให้เปิด UX1 ไม่ได้ (`WdmSyncIoctl ... GLE = 0x490`) แล้วตกลงไปใช้การ์ดเริ่มต้นที่ 106.67 ms. fix นี้ทำให้ได้ 46.7 ms
2. **ตรวจ device ก่อนเปิด** — `_resolve_device_pair()` กัน index ที่ชี้ผิด/ไม่มี channel; retry ด้วย UX1 ที่ detect ได้
3. **fallback ที่มองเห็นได้** — `audio_path.warning = "fallback"` + UI แดง + toast
4. **ชื่ออุปกรณ์แทน index** — `audio_settings.json` เก็บ `input_device_name`/`output_device_name`; ชื่อซ้ำข้าม host API จะเลือก WASAPI ก่อน
5. **latency จริงใน UI** — `LATENCY` = ค่าที่ไดรเวอร์รายงาน, `PATH` = WASAPI/FALLBACK; status bar มี in/out device
6. **ไม่ query อุปกรณ์บน hot path** — `sd.query_devices()` ระหว่างสตรีมรันทำให้ callback สะดุดถึง ~52 ms; cache ไว้และ refresh ตอนเปิด stream เท่านั้น
7. **`callback_ms_avg` + warm-up 50 blocks** — เลิกใช้ max ตัวเดียวตัดสินสุขภาพเสียง
8. **เตือน DSP เกินงบ** — NAM 2 stage ใช้ 1.3–2.9 ms/block (deadline 2.67) → `dsp_over_budget` แนะนำ buffer 256

### ตัวเลขวัดจริง (VERIFIED, UX1 @ 48 kHz)
| เส้นทาง | round trip |
|---|---|
| WASAPI shared (ใหม่) | **46.67 ms** (22.0 + 24.67) |
| WASAPI exclusive | 46.67 ms |
| default fallback (เก่า) | 106.67 ms |
| DirectSound / MME | 125.3 / 106.7 ms |
| block 16 / 32 / 64 | 44.3 / 44.7 / 45.3 ms |
| DSP (ไม่มี NAM) | 0.54–0.72 ms/block |
| DSP (NAM 2 stage, lite) | 1.31–2.86 ms/block |
| DSP (NAM full) | 4.13 ms mean, max 70 ms → ใช้ full ที่ 128 ไม่ได้ |

สรุป: พื้น ~44 ms เป็นข้อจำกัดไดรเวอร์ UX1 + PortAudio ที่ไม่มี ASIO ไม่ใช่โค้ดแอป — จะต่ำกว่านี้ต้องเปลี่ยน PortAudio build ที่รองรับ ASIO หรือเปลี่ยนอินเทอร์เฟซ

### ยังไม่ทำ / รอผู้ใช้
- **P2**: ยังไม่แตะ layout ใหญ่ (รออนุมัติตำแหน่งฟีเจอร์ + checkpoint commit)
- **P3/P4**: ยังไม่เริ่ม
- คำถาม BLOCKER §6 ยังไม่ได้คำตอบ (ยกเว้นข้อ 1 ที่ตัดสินด้วยการวัดแล้วว่าไม่ต้องใช้ exclusive)
