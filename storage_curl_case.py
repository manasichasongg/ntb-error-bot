import csv
import io
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from flask import Flask, request, jsonify
from groq import Groq

app = Flask(__name__)

DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
STORAGE_FILE = os.path.join(DATA_DIR, "curl_cases.json")
ROLE_FILE    = os.path.join(DATA_DIR, "role_permissions.json")
CONFIG_FILE  = os.path.join(DATA_DIR, "config.json")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

def _load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

_config = _load_config()
# รับจาก env var ก่อน ถ้าไม่มีค่อยอ่านจาก config.json
ANALYZE_WEBHOOK = os.environ.get("ANALYZE_WEBHOOK", "") or _config.get("webhook_url", "")

SHEETS_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1w_09e8L52gLSz4U6tOeHkQmddS6D2CGWAoH028gU9oY"
    "/export?format=csv&gid=0"
)
SHEETS_TTL = 300  # refresh ทุก 5 นาที
_sheets_cache: dict = {"data": None, "ts": 0}
NGROK_DOMAIN = "epileptic-kennel-fling.ngrok-free.dev"
REPOS_DIR = r"C:\Users\manasicha.son\Downloads\theme"

# conversation state per thread/space
_sessions: dict = {}


def _is_ngrok_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _restart_ngrok():
    print(f"[health] ngrok ไม่ตอบสนอง — กำลัง restart...")
    subprocess.Popen(
        ["ngrok", "http", f"--domain={NGROK_DOMAIN}", "8081"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print(f"[health] ngrok restart แล้ว ({NGROK_DOMAIN})")


def _health_check_loop():
    CHECK_INTERVAL = 300  # 5 นาที
    time.sleep(30)
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if _is_ngrok_running():
            print(f"[health] {now} — ngrok ปกติ ✓")
        else:
            print(f"[health] {now} — ngrok หลุด! กำลัง reconnect...")
            _restart_ngrok()
        time.sleep(CHECK_INTERVAL)


threading.Thread(target=_health_check_loop, daemon=True).start()

HELP_TEXT = (
    "*📌 วิธีใช้งาน Curl Case Bot*\n\n"
    "*➕ เพิ่ม curl case*\n"
    "`บันทึก: [คำอธิบาย] | [curl command]`\n\n"
    "*🔍 ค้นหา curl case*\n"
    "พิมพ์คำอธิบายได้เลย เช่น:\n"
    "`เปลี่ยนอีเมลพนักงาน`\n\n"
    "*📋 ดู curl ทั้งหมด*\n"
    "`รายการ`\n\n"
    "*🔎 ดู curl ตาม ID*\n"
    "`ดู: 3`  หรือพิมแค่ `3`\n"
    "ถ้า curl มีตัวแปร บอทจะถามให้กรอกทีละตัวเลย\n\n"
    "*✏️ แก้ไข curl case*\n"
    "`แก้ไข: [ID] | [คำอธิบายใหม่] | [curl ใหม่]`\n"
    "เว้นว่างส่วนที่ไม่แก้ได้ เช่น:\n"
    "`แก้ไข: 2 | ชื่อใหม่ |` — แก้แค่ชื่อ\n"
    "`แก้ไข: 2 | | curl ใหม่` — แก้แค่ curl\n\n"
    "*🗑️ ลบ curl case*\n"
    "`ลบ: 3`\n\n"
    "*🧹 ล้างค่าตัวแปรที่บันทึกไว้*\n"
    "`ล้างค่า: 3`\n\n"
    "*🔐 เช็ค Role / Permission*\n"
    "`หน้า [ชื่อหน้า]` — บอกว่า role ไหนเข้าหน้านั้นได้บ้าง\n"
    "เช่น: `หน้า BOS`, `หน้า OMS`\n"
    "`โรล [ชื่อ role]` — บอกว่า role นั้นเข้าหน้าไหนได้บ้าง\n"
    "เช่น: `โรล CO`, `โรล maker`, `โรล admin`\n"
    "หน้าที่มี: LOS, OMS, AMS, BES, BOS, CMS, RCS, RMS, PMS, WMS\n\n"
    "*🤖 ถามตอบ / วิเคราะห์ error*\n"
    "พิมข้อความอะไรก็ได้ บอทจะตอบด้วย AI\n"
    "เช่น: `error นี้แปลว่าอะไร`, `case 6 ใช้ทำอะไร`\n\n"
    "*🗑️ ล้างประวัติการสนทนา AI*\n"
    "`ล้างแชท`"
)


def fetch_sheets_data() -> str:
    """ดึง Google Sheets แล้ว cache ไว้ 5 นาที"""
    now = time.time()
    if _sheets_cache["data"] is not None and (now - _sheets_cache["ts"]) < SHEETS_TTL:
        return _sheets_cache["data"]
    try:
        req = urllib.request.Request(SHEETS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(raw)))
        rows = [r for r in rows if any(c.strip() for c in r)]
        if len(rows) < 2:
            _sheets_cache.update({"data": "", "ts": now})
            return ""
        headers = [h.strip() for h in rows[0]]
        lines = []
        for row in rows[1:300]:
            pairs = []
            for i, h in enumerate(headers):
                v = row[i].strip() if i < len(row) else ""
                if v:
                    pairs.append(f"{h}: {v}")
            if pairs:
                lines.append(" | ".join(pairs))
        result = (
            f"[Incident Sheet — {len(rows)-1} rows, โหลดเมื่อ {datetime.now().strftime('%H:%M')}]\n"
            f"คอลัมน์: {', '.join(headers)}\n\n"
            + "\n".join(lines)
        )
        _sheets_cache.update({"data": result, "ts": now})
        return result
    except Exception:
        _sheets_cache.update({"data": "", "ts": now})
        return ""


def load_role_perms() -> dict:
    if os.path.exists(ROLE_FILE):
        with open(ROLE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_cases() -> list:
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_cases(cases: list) -> None:
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)


def save_case_vars(case_id: int, vars_dict: dict) -> None:
    if not vars_dict:
        return
    cases = load_cases()
    match = next((c for c in cases if c["id"] == case_id), None)
    if match:
        match.setdefault("vars", {}).update(vars_dict)
        save_cases(cases)


def next_id(cases: list) -> int:
    return max((c["id"] for c in cases), default=0) + 1


def extract_identifiers(text: str) -> list:
    """ดึงชื่อ class/file จาก error stack trace เพื่อค้นหา source code"""
    identifiers = []
    identifiers += re.findall(r'at\s+[\w.]+\.(\w+)\.\w+\(', text)
    identifiers += re.findall(r'(\w+)\.java', text)
    identifiers += re.findall(r'File ["\'].*?/(\w+)\.py["\']', text)
    noise = {'Exception', 'Error', 'Throwable', 'RuntimeException', 'NullPointerException',
             'IllegalArgumentException', 'IllegalStateException', 'String', 'Object', 'List', 'Map'}
    return list(dict.fromkeys(x for x in identifiers if x not in noise and len(x) > 3))


def find_source_files(identifiers: list, max_files: int = 4) -> list:
    """ค้นหาไฟล์ source code จาก repos ที่โคลนมา"""
    if not identifiers or not os.path.exists(REPOS_DIR):
        return []
    skip_dirs = {'.git', 'node_modules', 'target', 'build', '.gradle', '__pycache__', '.idea', 'dist'}
    extensions = ('.java', '.py', '.js', '.ts', '.go', '.kt', '.xml', '.yaml', '.yml', '.properties')
    found = []
    seen = set()
    for term in identifiers:
        for root, dirs, files in os.walk(REPOS_DIR):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                if fname.endswith(extensions) and term.lower() in fname.lower():
                    fpath = os.path.join(root, fname)
                    if fpath not in seen:
                        seen.add(fpath)
                        found.append(fpath)
                        if len(found) >= max_files:
                            return found
    return found


def read_file_snippet(file_path: str, max_lines: int = 80) -> str:
    """อ่าน source code ไม่เกิน max_lines บรรทัด"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line)
        rel = os.path.relpath(file_path, REPOS_DIR)
        return f"// {rel}\n{''.join(lines)}"
    except Exception:
        return ""


def is_error_message(text: str) -> bool:
    """ตรวจว่าข้อความน่าจะเป็น error หรือถามให้วิเคราะห์"""
    keywords = ['exception', 'error', 'stack', 'at com.', 'at org.', 'caused by',
                'traceback', 'stacktrace', 'เกิด error', 'วิเคราะห์', 'แก้ยังไง',
                'แก้ไขยังไง', 'หมายความว่า', 'ดู error', 'null pointer', 'timeout']
    lower = text.lower()
    return any(k in lower for k in keywords)


def keyword_search(query: str, cases: list) -> list:
    words = query.lower().split()
    results = []
    for c in cases:
        desc = c["description"].lower()
        if any(w in desc for w in words):
            results.append(c)
    return results


def semantic_search(query: str, cases: list) -> list:
    if not cases:
        return []
    if not GROQ_API_KEY:
        return keyword_search(query, cases)

    cases_text = "\n".join(f"ID:{c['id']} | {c['description']}" for c in cases)
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"นี่คือรายการ curl cases:\n{cases_text}\n\n"
                    f"ค้นหา cases ที่เกี่ยวข้องกับ: \"{query}\"\n"
                    "ตอบแค่ IDs ที่เกี่ยวข้อง คั่นด้วย comma เช่น: 1,3,5\n"
                    "ถ้าไม่มีที่เกี่ยวข้องตอบว่า: none"
                ),
            }],
        )
        result = response.choices[0].message.content.strip()
        if result.lower() == "none":
            return []
        ids = {int(x.strip()) for x in result.split(",") if x.strip().isdigit()}
        return [c for c in cases if c["id"] in ids]
    except Exception:
        return keyword_search(query, cases)


def strip_mention(text: str) -> str:
    return re.sub(r"@\S+\s*", "", text).strip()


def fill_variables(curl: str, vars_dict: dict) -> str:
    for key, value in vars_dict.items():
        curl = curl.replace(f"{{{{{key}}}}}", value)
    return curl


def unique_vars(curl: str) -> list:
    seen = set()
    result = []
    for v in re.findall(r'\{\{(\w+)\}\}', curl):
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


# ── Session helpers ────────────────────────────────────────────────────────────

def get_session(key: str) -> dict:
    return _sessions.get(key, {})


def set_session(key: str, data: dict):
    _sessions[key] = data


def clear_session(key: str):
    _sessions.pop(key, None)


# ── Handlers ───────────────────────────────────────────────────────────────────

def handle_save(body: str) -> str:
    if "|" not in body:
        return "รูปแบบไม่ถูกต้อง ใช้: *บันทึก:* [คำอธิบาย] | [curl command]"

    desc, curl = body.split("|", 1)
    desc, curl = desc.strip(), curl.strip()
    curl = re.sub(r'\|\s*\[curl command\]\s*$', '', curl).strip()

    if not desc or not curl:
        return "คำอธิบายหรือ curl command ว่างเปล่า"

    cases = load_cases()
    new_case = {
        "id": next_id(cases),
        "description": desc,
        "curl": curl,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    cases.append(new_case)
    save_cases(cases)
    return f"✅ บันทึกแล้ว! ID: {new_case['id']}\n📝 {desc}"


def handle_find(query: str) -> str:
    cases = load_cases()
    matches = semantic_search(query, cases)
    if not matches:
        return "ไปถามคนอื่นนะ เรื่องนี้บอทไม่รู้ไม่เห็น 🤷"

    lines = [f"🔍 พบ {len(matches)} case(s) สำหรับ: {query}\n"]
    for c in matches:
        lines.append(f"*ID {c['id']}: {c['description']}*")
        lines.append(f"```\n{c['curl']}\n```")
    return "\n".join(lines)


def handle_view_filled(case_id: int, vars_dict: dict = None) -> str:
    cases = load_cases()
    match = next((c for c in cases if c["id"] == case_id), None)
    if not match:
        return f"ไม่พบ ID: {case_id}"

    curl = match.get("curl", "")
    merged = {**match.get("vars", {}), **(vars_dict or {})}
    if merged:
        curl = fill_variables(curl, merged)

    remaining = unique_vars(curl)
    warning = f"\n⚠️ ยังไม่ได้ใส่ค่า: {' | '.join(remaining)}" if remaining else ""

    return f"*ID {match['id']}: {match['description']}*\n```\n{curl}\n```{warning}"


def start_fill_conversation(case_id: int, session_key: str) -> str:
    cases = load_cases()
    match = next((c for c in cases if c["id"] == case_id), None)
    if not match:
        return f"ไม่พบ ID: {case_id}"

    curl = match.get("curl", "")
    if not unique_vars(curl):
        return handle_view_filled(case_id)

    saved = match.get("vars", {})
    prefilled = fill_variables(curl, saved)
    missing = unique_vars(prefilled)

    if not missing:
        return handle_view_filled(case_id)

    set_session(session_key, {
        "state": "CONFIRM_FILL",
        "case_id": case_id,
        "variables": missing,
        "collected": dict(saved),
    })

    var_list = "  |  ".join(f"`{{{{{v}}}}}`" for v in missing)
    return (
        f"*ID {match['id']}: {match['description']}*\n"
        f"```\n{prefilled}\n```\n"
        f"ตัวแปรที่ยังขาด: {var_list}\n"
        f"ใส่ค่า `{missing[0]}` : (หรือตอบ *ไม่*)"
    )


def handle_confirm_fill(text: str, session: dict, session_key: str) -> str:
    """state: CONFIRM_FILL — รอค่าแรก หรือ ไม่"""
    no = {"ไม่", "no", "n", "ไม่ใช่", "ไม่ต้อง"}
    lower = text.lower().strip()

    if lower in no:
        case_id = session["case_id"]
        clear_session(session_key)
        return handle_view_filled(case_id)

    variables = session["variables"]
    collected = {**session.get("collected", {}), variables[0]: text.strip()}
    remaining = variables[1:]

    if remaining:
        set_session(session_key, {
            "state": "COLLECTING",
            "case_id": session["case_id"],
            "remaining": remaining[1:],
            "collected": collected,
            "current_var": remaining[0],
        })
        return f"ใส่ค่า `{{{{{remaining[0]}}}}}` :"

    case_id = session["case_id"]
    clear_session(session_key)
    save_case_vars(case_id, collected)
    return handle_view_filled(case_id, collected)


def handle_collecting(text: str, session: dict, session_key: str) -> str:
    """state: COLLECTING — รับค่าตัวแปรทีละตัว"""
    collected = session["collected"]
    collected[session["current_var"]] = text.strip()

    remaining = session["remaining"]
    if remaining:
        next_var = remaining[0]
        set_session(session_key, {
            "state": "COLLECTING",
            "case_id": session["case_id"],
            "remaining": remaining[1:],
            "collected": collected,
            "current_var": next_var,
        })
        return f"ใส่ค่า `{{{{{next_var}}}}}` :"

    case_id = session["case_id"]
    clear_session(session_key)
    save_case_vars(case_id, collected)
    return handle_view_filled(case_id, collected)


def handle_clear_vars(id_str: str) -> str:
    try:
        target_id = int(id_str.strip())
    except ValueError:
        return "รูปแบบไม่ถูกต้อง ใช้: *ล้างค่า:* [ID]"

    cases = load_cases()
    match = next((c for c in cases if c["id"] == target_id), None)
    if not match:
        return f"ไม่พบ ID: {target_id}"

    if "vars" not in match:
        return f"ID {target_id} ไม่มีค่าที่บันทึกไว้"

    del match["vars"]
    save_cases(cases)
    return f"🗑️ ล้างค่าตัวแปรของ ID {target_id} แล้ว"


def handle_edit(body: str) -> str:
    parts = body.split("|")
    if len(parts) < 2:
        return "รูปแบบไม่ถูกต้อง ใช้:\n`แก้ไข: [ID] | [คำอธิบายใหม่] | [curl ใหม่]`"

    try:
        target_id = int(parts[0].strip())
    except ValueError:
        return "ID ต้องเป็นตัวเลข"

    cases = load_cases()
    match = next((c for c in cases if c["id"] == target_id), None)
    if not match:
        return f"ไม่พบ ID: {target_id}"

    new_desc = parts[1].strip() if len(parts) > 1 else ""
    new_curl = parts[2].strip() if len(parts) > 2 else ""

    if not new_desc and not new_curl:
        return "ไม่มีอะไรถูกแก้ไข กรุณาใส่คำอธิบายหรือ curl ใหม่"

    if new_desc:
        match["description"] = new_desc
    if new_curl:
        match["curl"] = new_curl

    match["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_cases(cases)
    return f"✏️ แก้ไข ID {target_id} แล้ว\n📝 {match['description']}"


def handle_list() -> str:
    cases = load_cases()
    if not cases:
        return "ยังไม่มี curl cases ที่บันทึกไว้"

    lines = [f"📋 มีทั้งหมด {len(cases)} case(s):\n"]
    for c in cases:
        lines.append(f"• *ID {c['id']}:* {c['description']}  _(บันทึก {c['created_at']})_")
    return "\n".join(lines)


def handle_delete(id_str: str) -> str:
    try:
        target_id = int(id_str)
    except ValueError:
        return "รูปแบบไม่ถูกต้อง ใช้: *ลบ:* [ID]"

    cases = load_cases()
    filtered = [c for c in cases if c["id"] != target_id]

    if len(filtered) == len(cases):
        return f"ไม่พบ ID: {target_id}"

    for i, c in enumerate(filtered, start=1):
        c["id"] = i
    save_cases(filtered)
    return f"🗑️ ลบ ID {target_id} แล้ว และเรียง ID ใหม่เรียบร้อย"


def handle_ai_chat(text: str, session_key: str) -> str:
    if not GROQ_API_KEY:
        return handle_find(text)

    session = get_session(session_key)
    history = session.get("history", [])

    cases = load_cases()
    cases_summary = "\n".join(f"ID {c['id']}: {c['description']}" for c in cases)

    perms = load_role_perms()
    role_summary = "\n".join(
        f"{r}: {', '.join(sc)}" for r, sc in perms.get("roles", {}).items()
    )
    sheets_data = fetch_sheets_data()
    sheets_section = f"\n\nข้อมูล incident/issue จาก Google Sheets:\n{sheets_data}" if sheets_data else ""

    # ถ้าดูเหมือน error — ค้นหา source code จาก repos ที่โคลนมา
    source_section = ""
    if is_error_message(text):
        identifiers = extract_identifiers(text)
        if identifiers:
            files = find_source_files(identifiers)
            if files:
                snippets = [read_file_snippet(f) for f in files]
                snippets = [s for s in snippets if s]
                if snippets:
                    combined = "\n\n".join(f"```\n{s}\n```" for s in snippets)
                    # จำกัดความยาวไม่ให้ prompt ใหญ่เกินไป
                    if len(combined) > 4000:
                        combined = combined[:4000] + "\n... (ตัดออกเพราะยาวเกิน)"
                    source_section = f"\n\nSource code จาก repo ที่เกี่ยวข้อง (ใช้ประกอบการวิเคราะห์):\n{combined}"

    system_prompt = (
        "คุณคือผู้ช่วย on-call สำหรับทีม NTB (บริษัทสินเชื่อมอเตอร์ไซค์และที่ดิน)\n"
        "ช่วยได้เรื่อง: วิเคราะห์ error log, อธิบายวิธีแก้ปัญหาระบบ, ตอบคำถามเกี่ยวกับ API และ database, "
        "อธิบาย curl cases ที่เก็บไว้, ตอบเรื่อง role permission, วิเคราะห์ข้อมูล incident\n\n"
        f"Curl cases ที่มีอยู่ตอนนี้:\n{cases_summary}\n\n"
        f"Role permissions (role → หน้าจอที่เข้าได้):\n{role_summary}"
        f"{sheets_section}"
        f"{source_section}\n\n"
        "=== รูปแบบการตอบเมื่อวิเคราะห์ ERROR (บังคับใช้ทุกครั้ง) ===\n"
        "เมื่อได้รับ error log หรือถูกขอให้วิเคราะห์ error ให้ตอบตามโครงสร้างนี้เสมอ:\n\n"
        "[ERROR] {ชื่อ service}   ← ถ้าเคยเกิดมาแล้วให้เป็น [ERROR - ซ้ำ!]\n"
        "{HTTP method} {endpoint} | {timestamp} | {duration} | {errorCode}   ← ถ้ามีข้อมูล\n\n"
        "Service: {ชื่อ service} -- {อธิบายหน้าที่ service สั้นๆ}\n\n"
        "สาเหตุที่เกิด\n"
        "{อธิบายว่า error เกิดจากอะไร เป็นภาษาคนอ่านเข้าใจง่าย ไม่ใช้ศัพท์เทคนิคเกินจำเป็น}\n\n"
        "เส้นทาง error\n"
        "{Class.Method()} -> {Class.Method()} -> {External API} -> {response} -> {Exception thrown} -> {ผลลัพธ์}\n"
        "← ถ้ามี source code ให้ trace ตาม class/method จริงๆ ที่เห็นในโค้ด\n\n"
        "เคยเกิดมาแล้ว   ← ใส่ section นี้เฉพาะเมื่อมีประวัติ error ซ้ำจาก Google Sheets หรือ history\n"
        "{timestamp} -- {สรุปสั้นๆ}\n"
        "{timestamp} -- {สรุปสั้นๆ}\n"
        "สัญญาณ: {วิเคราะห์ pattern ที่เห็น}\n\n"
        "service ที่อาจโดนต่อ\n"
        "{service}: {เหตุผลที่อาจได้รับผลกระทบ}\n\n"
        "service ที่เกี่ยวข้อง\n"
        "{service} ({internal/external}): {บทบาทใน error นี้}\n\n"
        "แนวทางแก้ไข\n"
        "[ทันที] {action ที่ต้องทำตอนนี้}\n"
        "[ฝั่ง NTB] {action ที่ทีม NTB ทำได้}\n"
        "← ใส่เฉพาะ action ที่เกี่ยวข้อง ไม่ต้องมีครบทุก tag\n\n"
        "=== จบรูปแบบ ===\n\n"
        "สำหรับคำถามทั่วไป (ไม่ใช่ error): ตอบภาษาไทยกระชับตรงประเด็น\n"
        "ถ้าไม่รู้คำตอบหรือข้อมูลไม่พอ: ตอบว่า ไปถามคนอื่นนะ เรื่องนี้บอทไม่รู้ไม่เห็น"
    )

    messages = [{"role": "system", "content": system_prompt}] + history[-20:] + [{"role": "user", "content": text}]

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1000,
            messages=messages,
        )
        reply = response.choices[0].message.content.strip()
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        session["history"] = history
        set_session(session_key, session)
        return reply
    except Exception as e:
        err = str(e)
        if "rate_limit" in err.lower() or "quota" in err.lower():
            return "⚠️ AI ตอบไม่ได้ตอนนี้ — เกิน rate limit ลองใหม่อีกครั้งนะครับ"
        if "auth" in err.lower() or "invalid" in err.lower() or "api_key" in err.lower():
            return "⚠️ AI ตอบไม่ได้ตอนนี้ — API key ไม่ถูกต้อง"
        return f"⚠️ AI ตอบไม่ได้ตอนนี้ — {err[:100]}"


def handle_role_query(text: str):
    lower = text.lower().strip()
    screen_prefixes = ("หน้าจอ ", "หน้า ", "screen:")
    role_prefixes = ("โรล:", "โรล ", "role:", "role ")

    query_type = None
    query_val = None

    for p in screen_prefixes:
        if lower.startswith(p):
            query_type = "screen"
            query_val = text[len(p):].strip().upper()
            break

    if not query_type:
        for p in role_prefixes:
            if lower.startswith(p):
                query_type = "role"
                query_val = text[len(p):].strip()
                break

    if not query_type:
        return None

    perms = load_role_perms()
    if not perms:
        return "ยังไม่มีข้อมูล role permissions"

    roles = perms.get("roles", {})
    screens = perms.get("screens", [])

    if query_type == "screen":
        if query_val not in screens:
            return f"ไม่พบหน้า: {query_val}\nหน้าที่มีทั้งหมด: {', '.join(screens)}"
        can_access = [r for r, sc in roles.items() if query_val in sc]
        if not can_access:
            return f"ไม่มี role ที่เข้า {query_val} ได้"
        role_list = "\n".join(f"• {r}" for r in can_access)
        return f"🖥️ *หน้า {query_val}* — role ที่เข้าได้:\n{role_list}"

    if query_type == "role":
        matched = next((r for r in roles if r.lower() == query_val.lower()), None)
        if not matched:
            partials = [r for r in roles if query_val.lower() in r.lower()]
            if len(partials) == 1:
                matched = partials[0]
            elif len(partials) > 1:
                return "พบหลาย role:\n" + "\n".join(f"• {r}" for r in partials) + "\nระบุชื่อให้ชัดขึ้น"
        if matched:
            sc_list = "  |  ".join(roles[matched])
            return f"👤 *Role: {matched}*\nเข้าได้: *{sc_list}*"
        return f"ไม่พบ role: {query_val}\nRole ที่มี: {', '.join(roles.keys())}"

    return None


def handle_clear_chat(session_key: str) -> str:
    session = get_session(session_key)
    session.pop("history", None)
    set_session(session_key, session)
    return "🗑️ ล้างประวัติการสนทนาแล้ว"


# ── Message router ─────────────────────────────────────────────────────────────

def process_message(raw_text: str, session_key: str = "default") -> str:
    text = strip_mention(raw_text)
    lower = text.lower().strip()

    # ── จัดการ conversation state ก่อนเสมอ ────────────────────────────────────
    session = get_session(session_key)
    state = session.get("state")

    # ยกเลิกได้ตลอดเวลาที่อยู่ใน conversation
    if state and lower in ("ยกเลิก", "cancel", "ออก", "exit"):
        clear_session(session_key)
        return "↩️ ยกเลิกแล้ว"

    if state == "CONFIRM_FILL":
        return handle_confirm_fill(text, session, session_key)

    if state == "COLLECTING":
        return handle_collecting(text, session, session_key)

    # ── คำสั่งปกติ ──────────────────────────────────────────────────────────────
    if lower.startswith("บันทึก:") or lower.startswith("save:"):
        return handle_save(text.split(":", 1)[1].strip())

    if lower.startswith("หา:") or lower.startswith("ค้นหา:") or lower.startswith("find:"):
        return handle_find(text.split(":", 1)[1].strip())

    if lower.startswith("ดู:") or lower.startswith("view:"):
        body = text.split(":", 1)[1].strip()
        # ถ้าใส่ค่าตัวแปรมาตรงๆ → fill + บันทึกค่าทันที
        if "|" in body:
            parts = [p.strip() for p in body.split("|")]
            vars_dict = {}
            for p in parts[1:]:
                if "=" in p:
                    k, v = p.split("=", 1)
                    vars_dict[k.strip()] = v.strip()
            try:
                cid = int(parts[0])
                save_case_vars(cid, vars_dict)
                return handle_view_filled(cid, vars_dict)
            except ValueError:
                return "ID ต้องเป็นตัวเลข"
        # ไม่มีค่า → ถามตัวแปรที่ขาด (ถ้ามี)
        try:
            return start_fill_conversation(int(body), session_key)
        except ValueError:
            return "ID ต้องเป็นตัวเลข"

    if lower in ("รายการ", "list", "ทั้งหมด", "all"):
        return handle_list()

    if lower.startswith("แก้ไข:") or lower.startswith("edit:"):
        return handle_edit(text.split(":", 1)[1].strip())

    if lower.startswith("ลบ:") or lower.startswith("delete:"):
        return handle_delete(text.split(":", 1)[1].strip())

    if lower.startswith("ล้างค่า:"):
        return handle_clear_vars(text.split(":", 1)[1].strip())

    if lower in ("ล้างแชท", "ล้างประวัติ", "clear chat", "reset chat"):
        return handle_clear_chat(session_key)

    role_result = handle_role_query(text)
    if role_result is not None:
        return role_result

    if lower in ("help", "ช่วยเหลือ", "?"):
        return HELP_TEXT

    # พิมแค่เลข ID → ถามตัวแปรที่ขาด (ถ้ามี)
    if lower.isdigit():
        return start_fill_conversation(int(lower), session_key)

    return handle_ai_chat(text, session_key)


# ── Response helpers ───────────────────────────────────────────────────────────

def addons_response(text: str):
    return jsonify({
        "hostAppDataAction": {
            "chatDataAction": {
                "createMessageAction": {
                    "message": {"text": text}
                }
            }
        }
    })


def _silent_analyze(text: str):
    """วิเคราะห์ error เงียบๆ แล้วส่งไปห้อง Bot error analyze"""
    try:
        analysis = handle_ai_chat(text, session_key="silent_monitor")
        header = f"🔔 *Auto-analyzed* | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        sent = send_to_gchat_webhook(header + analysis)
        print(f"[silent] ส่ง webhook {'สำเร็จ' if sent else 'ล้มเหลว'}")
    except Exception as e:
        print(f"[silent] error: {e}")


def send_to_gchat_webhook(text: str) -> bool:
    """ส่งข้อความไปห้อง Bot error analyze ผ่าน webhook"""
    if not ANALYZE_WEBHOOK:
        return False
    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            ANALYZE_WEBHOOK,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[webhook] ส่งไม่ได้: {e}")
        return False


# ── Webhook ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["POST"])
def webhook():
    event = request.get_json(silent=True, force=True) or {}

    if "commonEventObject" in event:
        chat = event.get("chat", {})
        if "messagePayload" in chat:
            msg = chat["messagePayload"].get("message", {})
            arg_text = (msg.get("argumentText") or "").strip()
            full_text = (msg.get("text") or "").strip()
            space = msg.get("space", {}).get("name", "")
            sender = msg.get("sender", {}).get("name", "")
            session_key = f"{space}_{sender}" or "default"

            if arg_text:
                # ถูก @mention → ตอบปกติ
                reply = process_message(arg_text, session_key)
                if is_error_message(arg_text):
                    header = f"🔔 *Auto-analyzed* | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    threading.Thread(target=send_to_gchat_webhook, args=(header + reply,), daemon=True).start()
                return addons_response(reply)
            elif full_text and is_error_message(full_text):
                # ไม่ถูก @mention แต่มี error → วิเคราะห์เงียบๆ background
                threading.Thread(target=_silent_analyze, args=(full_text,), daemon=True).start()
                return jsonify({})
            return jsonify({})
        if "addedToSpacePayload" in chat:
            return addons_response(f"สวัสดี! ฉันช่วยเก็บและค้นหา curl cases ให้\n\n{HELP_TEXT}")
        return jsonify({})

    event_type = event.get("type")
    if event_type == "ADDED_TO_SPACE":
        return jsonify({"text": f"สวัสดี! ฉันช่วยเก็บและค้นหา curl cases ให้\n\n{HELP_TEXT}"})
    if event_type == "MESSAGE":
        message = event.get("message", {})
        arg_text = (message.get("argumentText") or "").strip()
        raw_text = (message.get("text") or "").strip()
        space = message.get("space", {}).get("name", "")
        sender = message.get("sender", {}).get("name", "")
        session_key = f"{space}_{sender}" or "default"

        if arg_text:
            reply = process_message(arg_text, session_key)
            if is_error_message(arg_text):
                header = f"🔔 *Auto-analyzed* | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                threading.Thread(target=send_to_gchat_webhook, args=(header + reply,), daemon=True).start()
            return jsonify({"text": reply})
        elif raw_text and is_error_message(raw_text):
            threading.Thread(target=_silent_analyze, args=(raw_text,), daemon=True).start()
            return jsonify({})

    return jsonify({})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/ingest", methods=["POST"])
def ingest():
    """รับ error text จากระบบภายนอก → วิเคราะห์ → ส่งไปห้อง Bot error analyze"""
    data = request.get_json(silent=True, force=True) or {}
    # รับได้ทั้ง {"text": "..."} หรือ plain text body
    raw_text = data.get("text") or data.get("message") or request.get_data(as_text=True)
    raw_text = raw_text.strip() if raw_text else ""

    if not raw_text:
        return jsonify({"error": "no text provided"}), 400

    print(f"[ingest] รับ error: {raw_text[:120]}...")

    # วิเคราะห์ด้วย AI (ใช้ session แยกสำหรับ ingest)
    analysis = handle_ai_chat(raw_text, session_key="ingest_auto")

    # ส่งไปห้อง Bot error analyze
    header = f"🔔 *Auto-analyzed error* | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    sent = send_to_gchat_webhook(header + analysis)

    print(f"[ingest] ส่ง webhook {'สำเร็จ' if sent else 'ล้มเหลว'}")
    return jsonify({"status": "ok", "sent": sent})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    print(f"Curl Case Bot starting on http://localhost:{port}")
    print("Storage:", STORAGE_FILE)
    app.run(host="0.0.0.0", port=port, debug=False)
