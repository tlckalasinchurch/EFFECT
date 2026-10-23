# UI Modernization Proposal — กดจนหลอนTone

> **Source:** imported from `ทำความเข้าใจและปรับปรุงโปรเจกต์ให้ทันสมัย.zip` (file `Pasted_content_41.txt`)
> **Status:** proposal only — no code from this document has been implemented yet.
> **Scope:** usability + visual modernization of the 4-Zone workstation UI.

---

มีครับ จากโครงสร้าง UI ปัจจุบันของ `EFFECT` ยังมีหลายจุดที่ทำให้ใช้งานง่ายและดูทันสมัยขึ้นได้ โดยเฉพาะ workflow ของนักกีตาร์ที่ต้องปรับเสียงเร็ว ๆ ระหว่างซ้อมหรือแสดงสด

## สถานะเทียบกับโค้ดปัจจุบัน (audit 2026-10-21)

เอกสารนี้เป็น proposal เก่า ไม่ใช่รายการงานที่ยังไม่ทำทั้งหมด:

- **มีแล้ว:** Gig View, Scene A–H, preset search/filter, favorites, parameter panel, tuner, audio health, morph A/B, parallel clean blend และ drag ตำแหน่งไมค์
- **ยังขาดสำหรับระดับใช้งานจริง:** morph/snapshot persistence และ validation, scene switching ที่ทดสอบการเปลี่ยนเสียงโดยไม่ click/dropout, graph routing จริง, lazy rendering สำหรับคลังขนาดใหญ่, undo/redo และการทดสอบเสียงเทียบ reference
- **ไม่ยืนยันจาก reverse engineering เพียงอย่างเดียว:** ความเข้ากันได้กับฮาร์ดแวร์/ซอฟต์แวร์ต้นฉบับ และคุณภาพเสียงที่เทียบเท่า Kemper/Quad Cortex/MOOER

## จุดที่ควรปรับปรุงมากที่สุด

### 1. ปรับโครงสร้างหน้าให้เน้น “เสียงที่กำลังใช้” มากขึ้น

ปัจจุบันหน้าแบ่งเป็น Library, Preset Table, Details, Signal Chain และ Parameter Panel ซึ่งมีข้อมูลค่อนข้างมากในหน้าจอเดียว อาจทำให้ผู้ใช้ใหม่รู้สึกแน่นและไม่รู้ว่าควรเริ่มตรงไหน

ข้อเสนอ:

- เพิ่มโหมด **Play Mode** สำหรับใช้งานจริง
- ซ่อน Library และรายละเอียดที่ไม่จำเป็นระหว่างเล่น
- เหลือเฉพาะ:
  - ชื่อ preset ปัจจุบัน
  - ปุ่มเปลี่ยน preset
  - tuner
  - signal chain
  - macro controls
  - input/output meter
- เพิ่มปุ่มสลับ `Edit Mode / Performance Mode`

แนวคิดนี้มี Gig View อยู่แล้วในโค้ดปัจจุบัน งานต่อไปควรเน้นความน่าเชื่อถือของการสลับ scene, การคืนสถานะ และการตรวจ latency แทนการสร้าง performance mode ซ้ำ

---

### 2. ทำ Preset Browser ให้ค้นหาและจัดการง่ายขึ้น

ตอนนี้มี search และหมวด Library แล้ว แต่สามารถพัฒนาให้เป็นระบบมากขึ้นได้:

- เพิ่ม filter แบบ chip:
  - Clean
  - Crunch
  - High Gain
  - Ambient
  - Bass
  - Acoustic
  - Favorites
- เพิ่มการเรียงลำดับ:
  - ล่าสุด
  - ชื่อ
  - ใช้บ่อยที่สุด
  - gain level
- เพิ่ม preview metadata เช่น:
  - แอมป์
  - cab / IR
  - ผู้สร้าง
  - key / tuning
  - ประเภทดนตรี
- เพิ่ม shortcut:
  - `↑ / ↓` เปลี่ยน preset
  - `Enter` โหลด preset
  - `F` เพิ่ม Favorites
- เพิ่ม loading skeleton ระหว่างโหลด Kemper pack และ TONE3000

โดยเฉพาะ Kemper ที่มีหลายร้อยหรือหลายพัน rig ควรเพิ่ม virtualized list หรือ lazy rendering เพื่อไม่ต้อง render ตารางทั้งหมดพร้อมกัน

---

### 3. ทำ Signal Chain ให้เข้าใจได้เร็วขึ้น

Signal Chain เป็นหัวใจของแอป แต่ tile ปัจจุบันยังเน้นข้อมูลเชิงเทคนิคมากกว่าการอ่านเร็ว

ข้อเสนอ:

- เพิ่มเส้นทางสัญญาณที่ชัดขึ้นระหว่างแต่ละ block
- ใช้สีแยกประเภท:
  - Input / Utility
  - Dynamics
  - Drive
  - Amp
  - Cab
  - Time-based FX
  - Output
- แสดงสถานะ bypass ให้ชัดกว่า opacity อย่างเดียว
- เพิ่ม drag handle สำหรับ reorder โดยเฉพาะบนมือถือ
- เพิ่มปุ่ม `Solo` หรือ `Focus` สำหรับฟังเฉพาะ block
- เพิ่ม context menu ที่อ่านง่ายขึ้นแทนการพึ่งคลิกขวา/แตะค้าง
- เพิ่มปุ่ม duplicate block
- เพิ่ม preset ของแต่ละ block เช่น delay preset, reverb preset, cab preset

สำหรับผู้ใช้ใหม่ อาจเพิ่ม tooltip แบบสั้น เช่น:

> Delay — สร้างเสียงสะท้อนแบบ rhythmic  
> Gate — ลดเสียงจี่ระหว่างหยุดเล่น

---

### 4. ปรับ Knob ให้แม่นและใช้งานง่ายขึ้น

Knob แบบลากแนวตั้งเหมาะกับ desktop แต่ยังมีข้อจำกัดเรื่องความแม่นและการใช้งานบน touch screen

ควรเพิ่ม:

- คลิกค่าตัวเลขเพื่อพิมพ์ค่าโดยตรง
- ดับเบิลคลิกเพื่อ reset เป็นค่า default
- กด `Shift` เพื่อปรับละเอียด
- กด `Alt` หรือ `Ctrl` เพื่อปรับเร็ว
- แสดงค่า min/max ตอนกำลังลาก
- รองรับ mouse wheel
- รองรับ keyboard:
  - Arrow Up/Down
  - Home/End
- มี tooltip แสดงหน่วยที่ชัดเจน
- เพิ่ม automation หรือ value history ในอนาคต

สำหรับ touch ควรมี slider สำรอง เพราะ knob drag อาจควบคุมยากบนมือถือหรือจอสัมผัส

---

### 5. เพิ่ม Macro Controls

ปัจจุบันการปรับเสียงต้องเข้าไปแก้แต่ละ block ซึ่งดีสำหรับ sound design แต่ไม่เหมาะกับการใช้งานจริง

แนะนำเพิ่ม macro 4–8 ตัว เช่น:

- Gain
- Brightness
- Tightness
- Space
- Delay
- Reverb
- Output
- Noise

แต่ละ macro สามารถควบคุมหลาย parameter พร้อมกันได้ ตัวอย่างเช่น:

- `Tightness` ลด bass ใน amp และลด delay/reverb
- `Space` เพิ่ม delay mix กับ reverb mix
- `Lead` เพิ่ม gain และ volume พร้อมลด bass เล็กน้อย

นี่จะช่วยให้ผู้ใช้ปรับโทนระหว่างเล่นได้เร็วมาก

---

### 6. ปรับ Tuner ให้เด่นและใช้งานเร็วขึ้น

Tuner มีอยู่แล้ว แต่สามารถทำให้เป็นเครื่องมือหลักมากขึ้น:

- เปิด tuner ด้วย `T`
- fullscreen tuner mode
- แสดงชื่อสาย เช่น E, A, D, G, B, E
- แสดง cent deviation เป็นตัวเลข
- แสดงสถานะด้วยสีที่อ่านง่าย:
  - แดง = ต่ำ/สูงมาก
  - เหลือง = ใกล้
  - เขียว = ตรง
- มีโหมด mute output ขณะจูน
- เพิ่ม calibration เช่น 440 Hz / 442 Hz

---

### 7. ปรับ Status และ Audio Health ให้เข้าใจง่าย

ปัจจุบันมี CPU, RAM, sample rate, buffer, latency และ xrun แต่เป็นข้อมูลเทคนิคที่ผู้ใช้ทั่วไปอาจตีความยาก

แนะนำเปลี่ยนเป็น status card:

- `Audio Ready`
- `Input: Line 6 UX1`
- `Latency: 5.3 ms`
- `CPU: 8%`
- `XRUN: 0`
- `Signal: Good`

เมื่อเกิดปัญหาให้แสดงคำแนะนำโดยตรง เช่น:

> Buffer ต่ำเกินไป อาจเกิดเสียงแตก ลองเพิ่มเป็น 256 samples

หรือ:

> ไม่พบ input device กรุณาตรวจสอบ audio interface

---

### 8. เพิ่ม Undo / Redo และ Snapshot

**สถานะปัจจุบัน:** Morph A/B บันทึก snapshot ของพารามิเตอร์ที่รองรับลง SQLite พร้อมสถานะว่าง/บันทึกแล้วและเวลาที่ capture; capture/clear ไม่เปลี่ยนเสียงสด และ API ปฏิเสธ slot ที่ไม่ถูกต้องกับค่าที่ไม่ finite. ขอบเขต snapshot ปัจจุบันมี amp gain/master, screamer drive/level/enabled, delay mix/enabled และ reverb mix เท่านั้น — ยังไม่ใช่ preset เต็ม, undo/redo หรือการเปลี่ยนเสียงแบบไร้รอยต่อ.

การปรับเสียงมักมีการลองผิดลองถูก จึงควรเพิ่ม:

- Undo / Redo
- Compare กับค่าก่อนแก้
- A/B snapshot
- Copy/paste settings ของ block
- Lock block ไม่ให้ถูกเปลี่ยนเมื่อโหลด preset
- “Revert to saved”

ฟีเจอร์ A/B จะมีประโยชน์มาก เช่น กด `A/B` เพื่อฟังว่าเสียงก่อนและหลังปรับแตกต่างกันอย่างไร

---

### 9. ปรับ Settings ให้เข้าใจง่ายขึ้น

หน้าต่าง Settings ปัจจุบันรวม Audio, Pitch Shift และ NAM Quality ไว้ด้วยกัน แนะนำแบ่งเป็นหมวด:

- Audio
  - Input device
  - Output device
  - Sample rate
  - Buffer size
- NAM
  - Architecture
  - Quality
  - Input gain
- Interface
  - Theme
  - Show pitch block
  - Compact mode
- MIDI / Controller
  - เตรียมไว้สำหรับอนาคต

ควรแสดงผลกระทบก่อน Apply เช่น:

> Buffer 128 samples — latency ต่ำ แต่ใช้ CPU สูงขึ้น

---

### 10. ปรับ visual design ให้มี hierarchy มากขึ้น

ธีมสีเข้มและสีทองใช้งานได้ดี แต่บางพื้นที่ยังมี contrast ใกล้กันมาก ทำให้แยก panel ยาก

ข้อเสนอ:

- ใช้สี accent แยกสถานะ:
  - Gold = primary action
  - Green = active/healthy
  - Red = clipping/error
  - Blue/Purple = modulation/space effects
- ลดเส้น border ที่ไม่จำเป็น
- ใช้ surface elevation แทนเส้นกรอบทุกส่วน
- เพิ่ม spacing ระหว่างกลุ่มข้อมูล
- ทำปุ่ม primary ให้เด่นเพียง 1–2 ปุ่มต่อบริบท
- เพิ่ม light glow เฉพาะสถานะ active ไม่ใช่ทุก panel
- ใช้ icon system ที่เป็นชุดเดียวกันทั้งหมด

ควรระวังไม่ให้ UI กลายเป็น “dashboard ที่มีข้อมูลเต็มไปหมด” จนเสียความรู้สึกเป็นเครื่องดนตรี

---

## อัปเดตการทำงาน — A/B Morph persistence และความน่าเชื่อถือ (2026-10-21)

- Slot A/B เก็บใน SQLite (`presets.db`) แยกตารางจาก preset; ค่า default แสดงเป็น Empty จนกว่าจะ capture จริง
- Capture ตรวจ slot, chain modules และ finite numeric values ก่อนเขียนแบบ atomic และไม่เปลี่ยนค่าใน live chain
- UI ซิงก์สถานะ Empty/Saved หลังโหลดเสร็จก่อนส่ง slider, ถามยืนยันเมื่อเขียนทับ, และรองรับ clear slot ที่ไม่กระทบเสียงสด
- Slot มี capture timestamp และ clear/delete คงสถานะหลัง restart; slider ใช้ request queue แบบ single-flight
- เพิ่ม tests สำหรับ reload จาก SQLite, live-chain invariance, clear persistence, validation, atomic failure และ interpolation

ขอบเขตที่ยังไม่อ้างว่าเสร็จ: snapshot เป็น global ต่อการติดตั้ง ไม่ได้ผูกกับ preset; ยังไม่มีชื่อ/ลบ/คืนค่า factory, smoothing ใน audio callback หรือการวัด transient/click บนอุปกรณ์จริง การ bypass แบบ threshold 50% ยังเปลี่ยนทันที จึงไม่รับประกัน seamless/zero-glitch

## ลำดับที่ผมแนะนำให้ทำ

### รอบที่ 1: ใช้งานง่ายขึ้นทันที

1. เพิ่ม Performance Mode
2. เพิ่ม keyboard shortcuts
3. เพิ่ม input field สำหรับค่าของ knob
4. เพิ่ม preset filter และ sort
5. เพิ่ม loading state
6. เพิ่ม audio health messages
7. ปรับ tuner ให้เปิดได้เร็ว

### รอบที่ 2: Sound design workflow

1. Undo / Redo
2. A/B Compare
3. Copy/paste block settings
4. Duplicate block
5. Macro controls
6. ปรับ drag-and-drop signal chain

### รอบที่ 3: Visual modernization

1. ปรับ hierarchy ของ panel
2. แยกสีตามประเภท effect
3. ปรับ responsive layout ให้เหมาะกับ touch
4. เพิ่ม theme presets
5. เพิ่ม compact / spacious density mode

## สิ่งที่ควรทำก่อนเป็นพิเศษ

ถ้าต้องเลือกเพียงสามอย่าง ผมแนะนำ:

1. **Performance Mode** — ทำให้แอปเหมาะกับการใช้งานจริงมากขึ้น  
2. **Knob interaction ที่แม่นขึ้น** — พิมพ์ค่า, reset, keyboard และ mouse wheel  
3. **Preset Browser ที่ค้นหาเร็วขึ้น** — filter, sort, favorites และ lazy rendering  

สามส่วนนี้จะช่วยทั้งผู้ใช้ใหม่และผู้ใช้ที่เล่นจริง โดยไม่ต้องเปลี่ยนสถาปัตยกรรม DSP เดิมมากนัก.
