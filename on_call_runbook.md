# On-Call Runbook — NTB Error Quick Reference
> อัปเดต: 2026-05-19 | ใช้สำหรับ on-call วิเคราะห์ error เบื้องต้น

---

## วิธีใช้
1. ดู **HTTP status** + **duration** + **error message** จาก log
2. จับคู่กับ pattern ด้านล่าง
3. ทำตาม "วิธีตรวจสอบ" → "วิธีแก้เบื้องต้น"

---

## Pattern 1 — Timeout (duration ≈ 100,000ms)

**อาการ**
- Response time ≈ 100,391ms (ใกล้เคียง 100 วินาทีพอดี)
- HTTP 500

**สาเหตุ**
HttpClient.Timeout ใน .NET ตั้งค่าที่ 100s — request ถูก cancel หลังรอครบเวลา แปลว่า downstream service ไม่ตอบ

**วิธีตรวจสอบ**
1. เช็ค service ที่เรียก (ดู Dependency Chain ใน `ntb_service_flow.md`)
2. เปิด log ของ downstream service ช่วงเวลาเดียวกัน
3. เช็ค CPU / Memory / Pod count ของ downstream

**วิธีแก้เบื้องต้น**
- Restart pod ของ downstream service ที่น่าสงสัย
- ถ้า downstream เป็น external (Viriyah, SAP, KKP) → แจ้งทีม vendor

**ตัวอย่างที่เคยเกิด**
- `2026-05-07` CERSEI POST /api/risk-rules/customer — 100,391ms → downstream ไม่ตอบ

---

## Pattern 2 — UndefindedTypeException

**อาการ**
- Exception message: `UndefindedTypeException`
- Duration ปกติ (ไม่ถึง 100s)
- HTTP 500

**สาเหตุ**
Downstream service ตอบกลับด้วย HTTP error ที่ไม่ใช่ 400 หรือ 404 → `BaseExternalService.HandleHttpError()` ไม่รู้จัก → throw `UndefindedTypeException`
> ⚠️ ชื่อ exception นี้ **ไม่ได้** แปลว่าปัญหาเรื่อง "ประเภท" — มันคือ unhandled HTTP error จาก downstream

**วิธีตรวจสอบ**
1. เช็ค log ของ **downstream service** ช่วงเวลาเดียวกัน (ดูว่า return HTTP อะไร)
2. สงสัย service ไหน → ดู `ntb_service_flow.md` ว่า service นั้นเรียกใครบ้าง

**วิธีแก้เบื้องต้น**
- Restart pod ของ downstream ที่ล้มเหลว
- ถ้า 5xx จาก downstream → escalate ทีมที่รับผิดชอบ service นั้น

**ตัวอย่างที่เคยเกิด**
- `2026-05-07` CERSEI POST /api/risk-rules/automobiles — applicationId 1933676

---

## Pattern 3 — "Connection is not open"

**อาการ**
- Error message: `Connection is not open`
- Duration สั้นมาก (~3ms)
- HTTP 500
- errorCode: `999999`

**สาเหตุ**
DB connection pool คืน connection ที่ตายแล้ว → EF Core ใช้ connection นั้น → error  
DbRetryHelper ไม่จับ "not open" (จับแค่ "broken"/"closed"/"lost") → ไม่ retry → throw ทันที

**วิธีตรวจสอบ**
1. เช็ค DB server health (CPU, connections, locks)
2. เช็คว่ามีหลาย request พร้อมกันไหม (connection pool exhausted)
3. ดู pod restart ก่อนหน้าไหม (connection state หลุด)

**วิธีแก้เบื้องต้น**
- Restart pod ของ service นั้น (reset connection pool)
- ถ้าเกิดบ่อย → เพิ่ม `"not open"` ใน DbRetryHelper.cs (แก้ code)

**ตัวอย่างที่เคยเกิด**
- `2026-05-19` ARTEMIS POST /api/distribute-event/manage — 3ms

---

## Pattern 4 — "Unexpected character encountered while parsing value: <"

**อาการ**
- Error message: `Unexpected character encountered while parsing value: <`
- แปลว่า service พยายาม parse JSON แต่ได้ HTML กลับมาแทน
- HTTP 500

**สาเหตุ**
Downstream service return HTML error page (502/503 → Nginx/load balancer) แทน JSON → JsonConvert.Deserialize ล้มเหลวที่ตัวอักษร `<`

**วิธีตรวจสอบ**
1. **เช็ค downstream service ก่อนเลย** — มักเป็น pod crash / restart
2. ดู pattern: `"Error X from service Y: Unexpected character..."` → Y คือ service ต้นเหตุ
3. เช็ค pod restart history ของ Y ช่วงเวลาเดียวกัน

**วิธีแก้เบื้องต้น**
- Restart pod ของ downstream service (Y)
- รอ pod healthy แล้ว retry request

**ตัวอย่างที่เคยเกิด**
- `2026-05-19` ATHENA GET /api/risk-rule/product-shelf-channel — TYRION ส่ง HTML กลับ

---

## Pattern 5 — errorCode: 999999 (ไม่มี errorCode จริง)

**อาการ**
- Response body มี `"errorCode": "999999"`
- ใน Hedwig middleware หมายถึง exception ที่ throw มาไม่ใช่ `BaseException`

**สาเหตุที่เป็นไปได้**
| สาเหตุ | วิธีสังเกต |
|--------|-----------|
| Downstream HTML response | message มี `Unexpected character <` |
| DB connection ตาย | message มี `Connection is not open` |
| Timeout | duration ≈ 100,000ms |
| Exception ห่อหลายชั้น | ดู innermost exception ใน log |

**วิธีตรวจสอบ**
- อ่าน `message` field ใน response ให้ละเอียด → จับคู่กับ Pattern 1–4 ด้านบน
- ถ้า message ไม่ชัด → เปิด Application Insight / log ของ service นั้น

---

## Pattern 6 — Silent Failure (ไม่มี error ใน response แต่ข้อมูลหาย)

**อาการ**
- API return 200 แต่ข้อมูลบางส่วนหาย / ไม่อัปเดต
- ไม่มี error log

**สาเหตุ**
หลาย service มี fire-and-forget (`Task.Run()` / `Task.Factory.StartNew()`) ที่ไม่มี error handling — ถ้า background task ล้มเหลวจะไม่มีร่องรอยใน response

**Services ที่เสี่ยง**
- HAIBARA (AutoCheck, Email)
- MALIBU (Elastic, Repair — empty catch {})
- PICASSO (async routes — unhandled Promise rejection)

**วิธีตรวจสอบ**
- เปิด CloudWatch / Application Insight → กรอง `TaskScheduler.UnobservedTaskException`
- เช็ค S3 bucket / email queue ว่าไฟล์/email ถูกสร้างไหม

---

## Pattern 7 — Deadlock / Async Deadlock

**อาการ**
- Request ค้างนาน แล้ว timeout
- อาจเจอ `System.Threading.Tasks.TaskCanceledException` หรือ request หายเงียบ

**สาเหตุ**
`.GetAwaiter().GetResult()` หรือ `.Result` บน async method ใน ASP.NET sync context → deadlock

**Services ที่เสี่ยง**
- WHITEBEARD (ทุก external call ใช้ `.Result`)
- CARAXES (AuthService.cs line ~35)
- CATHERINE (หลาย batch method)
- HAIBARA

**วิธีแก้เบื้องต้น**
- Restart pod เพื่อคลาย thread pool ที่ติด
- Long-term: แก้ code เปลี่ยนเป็น `await` แบบถูกต้อง

---

## Pattern 8 — Race Condition (ข้อมูลปนกัน)

**อาการ**
- Request ของ user A ได้ข้อมูลของ user B
- Token/session ผิดคน

**Services ที่เสี่ยง**
- WHITEBEARD: `static AccessToken` ใช้ร่วมกันทุก thread — ถ้า token refresh พร้อมกัน อาจใช้ token ผิดคน

**วิธีตรวจสอบ**
- เช็ค timestamp ของ request ที่ผิดพลาด ว่ามีหลาย request พร้อมกันไหม
- เช็ค log ว่า token ที่ใช้ตรงกับ user จริงไหม

---

## สรุป Quick Reference

| Duration | Error message | Pattern | เช็คก่อน |
|----------|---------------|---------|----------|
| ~100,000ms | — | Timeout | downstream service health |
| ปกติ | UndefindedTypeException | Downstream HTTP error | log ของ downstream |
| ~3ms | Connection is not open | DB connection pool | DB health, pod restart |
| ปกติ | Unexpected character `<` | Downstream HTML (502/503) | downstream pod restart |
| ปกติ | errorCode: 999999 | อ่าน message ให้ละเอียด | จับคู่กับ pattern ด้านบน |
| 200 OK แต่ข้อมูลหาย | — | Silent failure | CloudWatch UnobservedTask |
| request ค้าง | TaskCanceledException | Async deadlock | restart pod |

---

## Escalation Path

```
On-call เจอ error
  ├─→ ดู log → จับ pattern → restart pod ที่ต้องการ
  │
  ├─→ ยังไม่หาย → แจ้ง owner ของ service นั้น
  │
  └─→ เป็น external service (Viriyah, Chubb, SAP, KKP)
        └─→ แจ้งทีม vendor + ทำ workaround ชั่วคราว
```

---

## ไฟล์อ้างอิง

| ไฟล์ | ใช้ทำอะไร |
|------|----------|
| `ntb_service_flow.md` | ดู call chain ว่า service เรียกใคร |
| `incident_review.html` | บันทึก incident พร้อม root cause |
| `.claude/projects/.../memory/project_error_history.md` | ประวัติ error ที่วิเคราะห์แล้ว |
