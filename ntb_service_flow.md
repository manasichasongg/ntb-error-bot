# NTB Service Call Flow Map
> อัปเดต: 2026-05-19

---

## สายหลัก (Core Flows)

### 1. ใบสมัครสินเชื่อ (LOS)
```
Consumer / Staff
  └─→ GOLDEN (รับใบสมัคร)
        ├─→ CERSEI (risk rules รถ/ที่ดิน)
        │     ├─→ Drogon (ข้อมูล loan)
        │     ├─→ TYREK (collection history)
        │     ├─→ Galangal / B-Score (เครดิต)
        │     ├─→ ANYA (litigation risk)
        │     │     ├─→ JUMMENG (คดีความ)
        │     │     └─→ GOLDEN (สัญญา)
        │     └─→ Walle, Sompong
        └─→ ATHENA (risk rules นาโน/online)
              ├─→ TYRION (ค้นหา)
              ├─→ Galangal
              └─→ Sompong
```

### 2. Auth / Token
```
ทุก Service
  └─→ EOWYN (validate token)

Service ที่ต้องการ token
  └─→ R2D2 (ออก OAuth token)
        └─→ GOLDEN /api/login/oauth (verify credentials)
```

### 3. Consumer App (Mobile)
```
Mobile App
  └─→ SIDIOUS (GraphQL BFF)
        ├─→ GOLDEN (สัญญา, ใบสมัคร)
        ├─→ EOWYN (auth)
        ├─→ NIFFLER (BNPL / DPD history)
        ├─→ ATHENA (nano / online booking)
        └─→ JAJABING
```

---

## สายประกัน (Insurance Flows)

### 4. ประกันรถยนต์ (Viriyah)
```
หน้าบ้าน / Staff
  └─→ VHAGAR (ขายประกัน)
        ├─→ KAIDO (precheck + issue)
        │     └─→ Viriyah API [external]
        ├─→ ROSIE (insurance application)
        └─→ SHINZO (accounting / payment)
```

### 5. ประกัน Chubb
```
Staff
  └─→ WHITEBEARD
        ├─→ VHAGAR → KAIDO → Viriyah API [external]
        ├─→ Chubb API [external]
        └─→ Karoo, Diamante

VISERION (คำนวณ rate ประกัน)
  └─→ Galangal / B-Score
```

### 6. QR / ใบรับเงินชั่วคราว (ประกัน)
```
Staff / System
  └─→ ELROND (สร้าง QR, Barcode, PDF)
        └─→ Sauron (ข้อมูลบริษัท / logo)
```

---

## สายติดตามหนี้ (Collection Flows)

### 7. Collection ทั่วไป
```
Staff (ฝ่ายติดตามหนี้)
  └─→ TYREK (collection)
        ├─→ GOLDEN (ข้อมูลสัญญา)
        ├─→ JUMMENG (litigation)
        └─→ SHINZO (accounting)
```

### 8. Dunning Letter (จดหมายทวงหนี้)
```
CATHERINE (Batch Job)
  ├─→ GOLDEN (สัญญา)
  ├─→ TYREK (collection)
  ├─→ TYRION (ค้นหา)
  ├─→ Drogon (loan summary)
  ├─→ MALIBU (property sale)
  ├─→ Hulk
  ├─→ AWS Email / SMTP
  └─→ EMMANUELLE (สร้าง PDF จดหมาย)
        ├─→ GOLDEN (สัญญา)
        ├─→ Drogon (loan)
        ├─→ Batman (payup)
        └─→ ECTOPLASM (facility loans)
```

### 9. Litigation (คดีความ)
```
Staff / System
  └─→ JUMMENG (litigation API)
        └─→ K2 / Jira [external workflow]

MATER (workflow)
  ├─→ JUMMENG
  └─→ Jira / K2 [external]
```

---

## สายบัญชี (Accounting Flows)

### 10. Accounting Gateway
```
System
  └─→ NESSIE (gateway กลาง)
        ├─→ SHINZO (core accounting)
        │     └─→ SAP [external ERP]
        ├─→ GRINGOTTS (config)
        ├─→ JUMMENG (litigation)
        └─→ Morning, Babigon, Redeye (ระบบบัญชีอื่น)
```

### 11. KKP Bank
```
System
  ├─→ ARGENTINUS (transaction KKP)
  │     └─→ KKP Bank API [external]
  └─→ MARS (reconcile ไฟล์ KKP)
        └─→ KKP Bank files
```

---

## สายขายทรัพย์ (Property Sale)

### 12. Property Sale
```
Staff
  └─→ MALIBU (ประมูล / ขายทรัพย์)
        ├─→ GOLDEN
        ├─→ TYREK
        ├─→ Drogon
        ├─→ VISERION (rate ประกัน)
        ├─→ TYRION (ค้นหา)
        ├─→ GRINGOTTS (config)
        ├─→ EMMANUELLE (PDF)
        ├─→ SHINZO (accounting)
        └─→ Thelord, Godzilla, Warmachine, Sauron, Hulk, Lambda
```

---

## สาย Event / Queue

### 13. Event Distribution
```
ทุก Service
  └─→ ARTEMIS /api/distribute-event/manage
        └─→ AWS SQS
              └─→ GOLDEN, HEPHAESTUS, ... (downstream)
```

---

## สาย NCB / Consent

### 14. NCB เครดิตบูโร
```
Staff / System
  └─→ VONTALON (e-consent + NCB inquiry)
        └─→ ROLLO (NCB connector)
              └─→ NCB เครดิตบูโร [external]

VALIANT (รายงาน NCB)
  └─→ PostgreSQL + MongoDB
```

### 15. Consent Management
```
Consumer / Staff
  └─→ BOGO (consent)
        ├─→ Warmachine
        └─→ VALIANT
```

---

## สาย Campaign / Lead

### 16. Lead & Campaign
```
Facebook / Tiktok [external ads]
  └─→ TITAN (Lead management)

GEMINI (แบบสอบถาม)
  ├─→ TITAN (webhook → lead)
  └─→ VHAGAR (webhook → insurance)
```

---

## สาย Upsell / Top-up

### 17. Upsell Check
```
System
  └─→ MARTYN (เช็ค upsell condition)
        ├─→ GOLDEN
        ├─→ GRINGOTTS (config)
        ├─→ Morghul
        └─→ NIFFLER (BNPL DPD history)

NAGA (credit scoring model — standalone)
```

---

## สายอื่นๆ

### 18. เช็คต้น (Cheque)
```
Staff
  └─→ HAIBARA (จัดการเช็คต้น)
        ├─→ GOLDEN
        ├─→ CUPID (GraphQL - credit workflow)
        ├─→ Warmachine
        ├─→ AWS S3 (เก็บไฟล์)
        └─→ Vendor (ผลเช็คต้น) [external]
```

### 19. Registration / ลงทะเบียน
```
User
  └─→ JUDY (ข้อมูลส่วนตัว / สมัครสมาชิก)
        ├─→ Buttercup
        ├─→ Aragorn
        ├─→ Gollum
        └─→ Warmachine
```

### 20. Connectivity (Horaland ecosystem)
```
System
  └─→ UHU (connectivity hub)
        ├─→ Bezos
        ├─→ Gemini
        └─→ Horaland

PICASSO (wallpaper - Horaland)
  ├─→ UHU → Bezos, Horaland
  └─→ Warmachine, Hulk, Friday, Museum, Meraxes
```

### 21. Notification
```
System
  └─→ OSSE (ส่ง email ไปสาขา)
        └─→ Email / SMTP
```

### 22. DevOps
```
Dev Team
  ├─→ GROOT (CI/CD, release management)
  ├─→ WANDA (Git merge management)
  └─→ HOGAN (pipeline manager)
        ├─→ Jenkins [external]
        ├─→ SonarQube [external]
        ├─→ RabbitMQ
        └─→ AWS Step Functions
```

---

## Hub Services (ถูกเรียกบ่อยที่สุด)

| Service | ถูกเรียกจาก |
|---------|------------|
| **GOLDEN** | แทบทุก service — CERSEI, TYREK, ATHENA, ANYA, MALIBU, CATHERINE, EMMANUELLE, MARTYN, HAIBARA, R2D2, ... |
| **TYRION** | CERSEI, ATHENA, CATHERINE, MALIBU |
| **GRINGOTTS** | NESSIE, MALIBU, MARTYN |
| **EOWYN** | ทุก service (token validation) |
| **JUMMENG** | TYREK, ANYA, NESSIE, MATER |
| **SHINZO** | TYREK, VHAGAR, NESSIE, MALIBU |
| **Warmachine** | BOGO, HAIBARA, JUDY, PICASSO, MALIBU |
