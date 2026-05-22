"""
NTB Error Analysis — Google Chat Bot
รัน: python gchat_bot.py
ต้องตั้งค่า env: ANTHROPIC_API_KEY=sk-ant-...
"""

from flask import Flask, request, jsonify
import anthropic
import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Config ─────────────────────────────────────────────────────────────────────
PORT             = int(os.environ.get("PORT", 8080))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MAX_HISTORY      = 20   # จำนวน messages ต่อ thread (10 คู่ user/bot)

SYSTEM_PROMPT = """คุณเป็น expert วิเคราะห์ API error สำหรับระบบ .NET microservices
ของบริษัท NTB (Ngernturbo) ที่มี services ได้แก่ GOLDEN, GRINGOTTS, TITAN, CERSEI, TYREK, GALANGAL เป็นต้น

เมื่อได้รับ error log ให้วิเคราะห์และตอบในรูปแบบนี้:
1. *สรุปปัญหา* - อธิบายสั้นๆ ว่าเกิดอะไรขึ้น
2. *Root Cause* - สาเหตุที่แท้จริง
3. *ไฟล์/บรรทัดที่น่าจะเกิดปัญหา* - ระบุให้ชัดเจนถ้าทำได้
4. *Short Term Solution* - แก้ไขเฉพาะหน้า
5. *Long Term Solution* - แก้ไขถาวร

หากผู้ใช้ถามคำถามติดตาม ให้ตอบในบริบทของ error เดิม
ใช้ format ของ Google Chat: *bold* แทน **bold**, `code` สำหรับโค้ด"""

# ── App setup ──────────────────────────────────────────────────────────────────
app    = Flask(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# เก็บ conversation history แยกตาม thread (key = thread name)
_history: dict[str, list[dict]] = defaultdict(list)


# ── Helpers ────────────────────────────────────────────────────────────────────
def md_to_gchat(text: str) -> str:
    """แปลง Markdown → Google Chat format"""
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)          # **bold** → *bold*
    text = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)  # ## heading
    return text


def trim_history(thread_key: str):
    hist = _history[thread_key]
    if len(hist) > MAX_HISTORY:
        _history[thread_key] = hist[-MAX_HISTORY:]


def gchat_reply(text: str):
    return jsonify({"text": text})


# ── Main webhook ───────────────────────────────────────────────────────────────
@app.route("/", methods=["POST"])
def handle():
    event      = request.get_json(silent=True) or {}
    event_type = event.get("type", "")

    # บอทถูกเพิ่มเข้า Space
    if event_type == "ADDED_TO_SPACE":
        return gchat_reply(
            "สวัสดีครับ! 👋 ผมคือ *NTB Error Analyzer Bot*\n\n"
            "วาง error log มาได้เลย จะวิเคราะห์หาสาเหตุให้ทันที 🔍\n\n"
            "คำสั่ง:\n"
            "• `!clear` — ล้างประวัติการสนทนาใน thread นี้\n"
            "• `!help`  — แสดงคำแนะนำ"
        )

    if event_type == "REMOVED_FROM_SPACE":
        return gchat_reply("")

    if event_type != "MESSAGE":
        return gchat_reply("")

    # ── แยก text ออกมา ─────────────────────────────────────────────────────────
    message    = event.get("message", {})
    raw_text   = message.get("text", "").strip()
    thread_key = message.get("thread", {}).get("name", "default")

    # ลบ @mention ออก (เช่น <users/12345> หรือ <users/all>)
    user_text = re.sub(r'<users/[^>]+>', '', raw_text).strip()

    # log ทุก request เพื่อ debug
    print(f"[EVENT] type={event_type} raw={raw_text!r} clean={user_text!r}", flush=True)

    if not user_text:
        return gchat_reply("ส่ง error log มาได้เลยครับ 🔍")

    # ── คำสั่งพิเศษ ─────────────────────────────────────────────────────────────
    cmd = user_text.lower()

    if cmd in ("!clear", "/clear"):
        _history[thread_key].clear()
        return gchat_reply("ล้างประวัติการสนทนาแล้ว ✓  ส่ง error ใหม่ได้เลย")

    if cmd in ("!help", "/help"):
        return gchat_reply(
            "*วิธีใช้งาน NTB Error Bot*\n\n"
            "1. วาง error log หรือ stack trace มาใน chat\n"
            "2. บอทจะวิเคราะห์หา Root Cause และแนวทางแก้ไข\n"
            "3. ถามต่อเนื่องได้เลย เช่น _'แล้วจะแก้ยังไง?'_\n\n"
            "*คำสั่ง:*\n"
            "• `!clear` — ล้างประวัติ thread นี้\n"
            "• `!help`  — แสดงหน้านี้"
        )

    # ── ตรวจสอบ API Key ─────────────────────────────────────────────────────────
    if not client:
        return gchat_reply("⚠ ANTHROPIC_API_KEY ยังไม่ได้ตั้งค่าบน server")

    # ── เรียก Claude ─────────────────────────────────────────────────────────────
    _history[thread_key].append({"role": "user", "content": user_text})
    trim_history(thread_key)

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=_history[thread_key],
        )
        analysis = msg.content[0].text
        _history[thread_key].append({"role": "assistant", "content": analysis})
        return gchat_reply(md_to_gchat(analysis))

    except Exception as e:
        _history[thread_key].pop()   # ลบ message ที่ fail ออก
        return gchat_reply(f"⚠ เกิดข้อผิดพลาด: {str(e)[:200]}")


# ── Health check ───────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "api_key_set": bool(ANTHROPIC_API_KEY),
        "active_threads": len(_history),
    })


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not ANTHROPIC_API_KEY:
        print("⚠  WARNING: ANTHROPIC_API_KEY ยังไม่ได้ตั้งค่า")
        print("   ตั้งค่าด้วย: set ANTHROPIC_API_KEY=sk-ant-...")
    print(f"🚀 NTB Error Bot starting on port {PORT} ...")
    app.run(host="0.0.0.0", port=PORT, debug=False)
