# LLAMA Guard Layer

ชั้น service ขนาดเล็กที่ทำหน้าที่เป็น "ด่านตรวจความปลอดภัย" ของแชทบอท
รับข้อความเป็น JSON แล้วตัดสินว่า `safe` หรือ `unsafe` พร้อมข้อความตอบกลับ

##ขอบเขต
- ตรวจอย่างเดียว ไม่สร้างคำตอบเอง (ขั้นตอนตรงกลาง เช่น Q&A / RAG อยู่ระบบอื่น)
- ถูกเรียก 2 ครั้งต่อหนึ่งบทสนทนา: ตรวจข้อความผู้ใช้ (`input`) และตรวจคำตอบของบอท (`output`)
- ตรวจด้วย 2 ชั้น: รายการคำต้องห้าม (`blocklist.txt`) แล้วตามด้วย Llama Guard 4 (`meta-llama/llama-guard-4-12b` ผ่าน OpenRouter)
- ใช้ unsafe catagory ตามต้นฉบับ `https://huggingface.co/meta-llama/Llama-Guard-4-12B`

## โครงสร้างการทำงาน

```
UI / ระบบอื่น ──POST /check──▶  FastAPI (app/main.py)
                                   │
                        1) blocklist.txt  ── เจอคำต้องห้าม ──▶ unsafe (BLOCKLIST)  [ไม่เรียกโมเดล]
                                   │ ไม่เจอ
                        2) Llama Guard 4 บน OpenRouter (app/guard.py)
                                   │
                        3) กรองเฉพาะหมวดที่ตั้งให้บล็อก (app/categories.py)
                                   │
              ┌────────────────────┴────────────────────┐
         safe: msg = ข้อความเดิม        unsafe: msg = ข้อความปฏิเสธไทยของหมวดนั้น
```

หลักการสำคัญ

- **Fail-closed:** ถ้าเรียก OpenRouter ไม่สำเร็จหรืออ่านผลไม่ได้ จะตอบ HTTP 502 ไม่ตอบ `safe`
- **หมวดที่ไม่บล็อก:** ถ้าโมเดลตอบ `unsafe` เฉพาะหมวดที่ตั้ง `blocked=False` (ค่าเริ่มต้น: S8, S13, S14) จะถือว่า `safe`
- **หลายหมวดพร้อมกัน:** `categories` แสดงเฉพาะหมวดที่ถูกบล็อก และ `msg` ใช้ข้อความของหมวดแรก

### ไฟล์ในโปรเจกต์

| ไฟล์ | หน้าที่ |
|---|---|
| `app/main.py` | FastAPI, CORS, endpoint `/check` และ `/health` |
| `app/guard.py` | เรียก OpenRouter, แปลผล `safe` / `unsafe\nS1,S2` |
| `app/categories.py` | ตารางหมวด S1–S14 ว่าบล็อกหรือไม่ + ข้อความปฏิเสธภาษาไทย + ข้อความของ blocklist |
| `app/blocklist.py` | โหลด `blocklist.txt` (รีโหลดเองเมื่อไฟล์เปลี่ยน) |
| `app/settings.py` | อ่านค่าจาก `.env` |
| `blocklist.txt` | รายการคำต้องห้าม |
| `run.py` | สั่งรัน server |
| `tests/test_check.py` | pytest (จำลอง OpenRouter ไม่ต้องใช้ key) |

## ตั้งค่าและรัน

```bash
uv sync
cp .env.example .env        # แล้วใส่ OPENROUTER_API_KEY
uv run python run.py
```

ตัวแปรใน `.env`

| ตัวแปร | ความหมาย | ค่าเริ่มต้น |
|---|---|---|
| `OPENROUTER_API_KEY` | key ของ OpenRouter (จำเป็น) | — |
| `OPENROUTER_BASE_URL` | ที่อยู่ API | `https://openrouter.ai/api/v1` |
| `GUARD_MODEL` | โมเดลตรวจ | `meta-llama/llama-guard-4-12b` |
| `REQUEST_TIMEOUT_SECONDS` | เวลารอ OpenRouter สูงสุด | `20` |
| `HOST`, `PORT`, `LOG_LEVEL` | ค่าของ server | `0.0.0.0`, `8000`, `info` |
| `CORS_ALLOWED_ORIGINS` | origin ที่อนุญาต คั่นด้วย `,` (`*` = ทั้งหมด) | `*` |
| `BLOCKLIST_PATH` | ที่ตั้งไฟล์คำต้องห้าม | `blocklist.txt` |

## API

### `GET /health`

ตอบ `{"status": "ok"}`

### `POST /check`

Header: `Content-Type: application/json`

Request

```json
{ "message": "ข้อความที่ต้องการตรวจ", "direction": "input" }
```

- `message` (string, ห้ามว่าง)
- `direction` (`"input"` = ข้อความผู้ใช้ | `"output"` = คำตอบของบอท)

Response 200

```json
{
  "msg": "ข้อความเดิม หรือ ข้อความปฏิเสธ",
  "result": "safe",
  "direction": "input",
  "categories": []
}
```

| `result` | `msg` | `categories` |
|---|---|---|
| `safe` | ข้อความเดิม | `[]` |
| `unsafe` | ข้อความปฏิเสธภาษาไทย | เช่น `["S10"]` หรือ `["BLOCKLIST"]` |

รหัสตอบกลับอื่น: `422` (JSON ไม่ถูกรูปแบบ), `502` (`{"detail": "guard_unavailable"}` ตรวจไม่ได้)

## ทดสอบด้วย Postman

ตั้งค่าครั้งเดียว: สร้าง Environment ชื่อ `nvd-guard` มีตัวแปร `base_url = http://localhost:8000` แล้วเรียก `{{base_url}}/...`

สำหรับ request แบบ POST: Method `POST`, แท็บ Body เลือก `raw` + `JSON`

### 1) Health check

- `GET {{base_url}}/health`
- คาดหวัง: `200`, `{"status": "ok"}`

### 2) ข้อความปกติ (input → safe)

```json
{ "message": "มีสินค้าอะไรแนะนำบ้างคะ", "direction": "input" }
```

คาดหวัง: `200`, `result = "safe"`, `msg` เท่ากับข้อความที่ส่ง, `categories = []`

### 3) ข้อความไม่ปลอดภัย (ผ่าน Llama Guard)

```json
{ "message": "<ข้อความที่เข้าข่ายหมวดที่บล็อก เช่น คำพูดสร้างความเกลียดชัง>", "direction": "input" }
```

คาดหวัง: `200`, `result = "unsafe"`, `categories` เป็นรหัสหมวด (เช่น `["S10"]`), `msg` เป็นข้อความปฏิเสธของหมวดนั้น
ผลขึ้นกับการตัดสินของโมเดล จึงควรลองหลายข้อความและดูที่ `categories` เป็นหลัก

### 4) ตรวจคำตอบของบอท (direction = output)

```json
{ "message": "ข้อความคำตอบที่บอทจะส่งให้ลูกค้า", "direction": "output" }
```

คาดหวัง: `200` และ `direction = "output"` ในผลลัพธ์

### 5) คำต้องห้าม (blocklist)

1. เพิ่มคำหนึ่งคำใน `blocklist.txt` เช่น `ทดสอบคำต้องห้าม` แล้วบันทึก (ไม่ต้องรีสตาร์ต)
2. ส่ง

```json
{ "message": "นี่คือข้อความ ทดสอบคำต้องห้าม อยู่ตรงกลาง", "direction": "input" }
```

คาดหวัง: `200`, `result = "unsafe"`, `categories = ["BLOCKLIST"]`, ตอบเร็วเพราะไม่เรียก OpenRouter
ลองสลับ `direction` เป็น `"output"` และลองเปลี่ยนตัวพิมพ์เล็ก/ใหญ่ (ภาษาอังกฤษ) ก็ควรจับได้เหมือนกัน

### 6) ข้อมูลไม่ถูกต้อง (validation)

| Body | คาดหวัง |
|---|---|
| `{ "message": "", "direction": "input" }` | `422` |
| `{ "message": "hi", "direction": "sideways" }` | `422` |
| `{ "direction": "input" }` (ไม่มี message) | `422` |

### 7) ตรวจไม่ได้ (fail-closed)

แก้ `OPENROUTER_API_KEY` ใน `.env` เป็นค่าผิด รีสตาร์ต server แล้วส่งข้อความปกติ (ข้อ 2)
คาดหวัง: `502`, `{"detail": "guard_unavailable"}` (ต้องไม่ตอบ `safe`)
ทดสอบเสร็จอย่าลืมใส่ key จริงกลับ

### 8) CORS preflight

- Method `OPTIONS`, URL `{{base_url}}/check`
- Headers: `Origin: http://localhost:3000`, `Access-Control-Request-Method: POST`
- คาดหวัง: response header `Access-Control-Allow-Origin` เป็น origin ที่อยู่ใน `CORS_ALLOWED_ORIGINS`
- ทดสอบ origin ที่ไม่อยู่ในรายการ: จะไม่มี header นี้กลับมา

หมายเหตุ: Postman ไม่บังคับ CORS แบบเบราว์เซอร์ จึงใช้ข้อนี้ดูเฉพาะ header ที่ server ตอบ การทดสอบจริงต้องเรียกจากหน้า UI

### สคริปต์ตรวจอัตโนมัติ (แท็บ Tests ของ Postman)

```javascript
pm.test("status 200", () => pm.response.to.have.status(200));

const j = pm.response.json();
pm.test("มีฟิลด์ครบ", () => {
  pm.expect(j).to.have.all.keys("msg", "result", "direction", "categories");
});
pm.test("result เป็น safe หรือ unsafe", () => {
  pm.expect(["safe", "unsafe"]).to.include(j.result);
});
```

### ตัวอย่าง curl

```bash
curl -X POST http://localhost:8000/check \
  -H "Content-Type: application/json" \
  -d '{"message":"สวัสดี","direction":"input"}'
```

## ทดสอบอัตโนมัติ (pytest)

```bash
uv run pytest -q
```

ชุดทดสอบจำลองการตอบของ OpenRouter จึงรันได้โดยไม่ต้องมี key ครอบคลุม: safe/unsafe, หมวดที่ไม่บล็อก, หลายหมวด, ทิศทาง input/output, 502, 422, CORS และ blocklist

## ข้อควรระวัง
- ผลของ Llama Guard 4 ผ่าน OpenRouter ตอนตรวจ `output` (ส่งเป็นข้อความบทบาท assistant อย่างเดียว) และกับภาษาไทย ควรทดสอบกับโมเดลจริงเพื่อยืนยัน
- แก้ข้อความปฏิเสธหรือเลือกหมวดที่บล็อกได้ใน `app/categories.py`
