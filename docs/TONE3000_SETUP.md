# TONE3000 integration (NAM AMP)

กดจนหลอนTone เชื่อมต่อ TONE3000 ผ่าน OAuth 2.0 + PKCE ตาม
<https://www.tone3000.com/api> — ผู้ใช้ล็อกอินบนเว็บ TONE3000 เลือกเสียง
แล้วแอปดาวน์โหลด `.nam` เข้าบล็อก NAM AMP ให้อัตโนมัติ

## สิ่งที่ต้องเตรียม

| สิ่งที่ต้องใช้ | เอาได้จากไหน | หมายเหตุ |
|---|---|---|
| **Publishable key** (`t3k_pub_...`) | tone3000.com → Settings → API Keys | ใส่ในหน้า TONE3000 ของแอป (เก็บใน `t3k_config.json`) |
| **Redirect URI** | ตั้งใน Settings ของ TONE3000 | ค่าเริ่มต้น `http://127.0.0.1:8000/api/t3k/callback` |
| Secret key (`t3k_cs_...`) | — | **ไม่ต้องใช้และห้ามใส่ในแอป** (แอปใช้ PKCE) |

ถ้าใน Settings มีการลงทะเบียน redirect URI ไว้ ต้องเพิ่ม URI ข้างต้นให้ตรงทุกตัวอักษร
(พอร์ตต้องตรงกับ `WEB_PORT`; ค่าเริ่มต้นคือ 8000)

## วิธีใช้

1. เปิดแอป (`run.bat` หรือ `uvicorn server:app`)
2. ที่บล็อก **NAM AMP** กดปุ่ม **TONE3000 หาเสียง**
3. วาง Publishable key → **บันทึก Key** → **เข้าสู่ระบบ TONE3000**
4. แท็บใหม่จะเปิด tone3000.com: ล็อกอิน → เลือกเสียง
5. แท็บแสดง **“โหลดเสียงเรียบร้อย”** → ปิดแท็บ
6. กลับมาในแอป: บล็อก NAM AMP เปลี่ยนเป็นเสียงนั้น (มีป้าย `T3K`)

ในหน้าต่าง TONE3000 ของแอปยัง browsed คลังได้โดยตรง:
Trending / Latest / Favorites / Downloaded / Created, ค้นหา, กรองชนิดเกียร์,
เลือก model (standard/lite/feather/nano) แล้วกดโหลดเข้า NAM AMP ได้เลย

## สถาปัตยกรรมโมเดล (A1 / A2)

- ค่าเริ่มต้นคือ **A2** (`architecture=2`) เพราะ `engine/nam.py` อ่าน
  `SlimmableContainer` (A2) ได้
- ถ้า TONE3000 ส่งไฟล์ A2 มาเป็น `.namb` (binary) ซึ่ง engine นี้ยังไม่รองรับ
  แอปจะดาวน์โหลดโมเดล **A1 ของเสียงเดียวกัน** มาให้อัตโนมัติ
- ถ้าเสียงนั้นมีแต่ A2 และอ่านไม่ได้ ระบบจะแจ้งให้เปลี่ยนเป็น A1
  (ปุ่ม ⚙ ในหน้าต่าง TONE3000 → Model architecture → A1)

## ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | หน้าที่ |
|---|---|
| `t3k_fastapi.py` | OAuth PKCE, refresh token, search/list/detail, ดาวน์โหลด model (stdlib ล้วน) |
| `server.py` | endpoints `/api/t3k/*`, แปลง `.nam` เป็น `NamChain`, ติดตั้งเข้า NAM AMP |
| `web/index.html` | ปุ่ม TONE3000, modal SELECT TONE, ป้าย T3K บน signal block |
| `web/app.js` | flow ทั้งหมด + polling หลังล็อกอิน |
| `web/style.css` | สไตล์ modal (ส่วนที่ 9) |
| `t3k_config.json` | เก็บ key/redirect/architecture (git-ignored) |
| `t3k_tokens.json` | เก็บ token + โปรไฟล์ผู้ใช้ (git-ignored, สิทธิ์ 600) |

## Endpoints ภายในแอป

| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/api/t3k/status` | configured / logged_in / user / last_load / engine_nam |
| POST | `/api/t3k/config` | บันทึก key, redirect URI, architecture |
| POST | `/api/t3k/connect` | สร้าง authorize URL + เปิดเบราว์เซอร์ |
| GET | `/api/t3k/callback` | รับ code + tone_id, แลก token, ติดตั้งเสียง |
| GET | `/api/t3k/tones` | list/search สำหรับ browser ในแอป |
| GET | `/api/t3k/tones/{id}` | รายละเอียดเสียง + models |
| POST | `/api/t3k/load` | ติดตั้งเสียงที่เลือกเข้า NAM AMP |
| POST | `/api/t3k/logout` | ลบ token ที่เก็บไว้ |

## ข้อควรรู้

- TONE3000 จำกัด 100 requests/นาที และแนะนำให้ใช้ Select flow มากกว่า
  `/tones/search` (search ถูก rate-limit หนักกว่า) — ในแอปมี debounce 350 ms
- Free tier ของ TONE3000 ใช้ได้กับงาน non-commercial และอนุญาตเฉพาะ OAuth
  prompt flow (`select_tone`) + bounded lists (favorited/downloaded/created/
  trending/latest) — หากแอปเป็นเชิงพาณิชย์ต้องทำข้อตกลงกับ TONE3000
- Token หมดอายุ→ ระบบ refresh เอง; ถ้า refresh ไม่ได้ UI จะกลับไปหน้าเชื่อมต่อ
- ถ้า callback ขึ้น `state ไม่ตรงหรือหมดอายุ` ให้เริ่มกด “เข้าสู่ระบบ” ใหม่
  (state เก็บใน memory อายุ 15 นาที และใช้ได้ครั้งเดียว)
