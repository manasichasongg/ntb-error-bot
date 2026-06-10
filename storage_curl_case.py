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
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

app = Flask(__name__)

DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
STORAGE_FILE  = os.path.join(DATA_DIR, "curl_cases.json")
ROLE_FILE     = os.path.join(DATA_DIR, "role_permissions.json")
MISSIONS_FILE = os.path.join(DATA_DIR, "missions.json")
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
ANALYZE_WEBHOOK = (
    os.environ.get("ANALYZE_WEBHOOK", "")
    or _config.get("webhook_url", "")
    or "https://chat.googleapis.com/v1/spaces/AAQAy9XnBM0/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=cGQbSiUNTUj0tH5PnglbpgPMJlKy33KDrYmLFK8z58Y"
)

SHEETS_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1w_09e8L52gLSz4U6tOeHkQmddS6D2CGWAoH028gU9oY"
    "/export?format=csv&gid=0"
)
SHEETS_TTL = 300  # refresh ทุก 5 นาที
_sheets_cache: dict = {"data": None, "ts": 0}
NGROK_DOMAIN = "epileptic-kennel-fling.ngrok-free.dev"
REPOS_DIR = r"C:\Users\manasicha.son\Downloads\theme"
ANALYZE_SPACE = "spaces/AAQAy9XnBM0"  # ห้อง Bot error analyze — ไม่ส่ง webhook ซ้ำจากห้องนี้
WEBHOOK_ENABLED = True  # ตั้งเป็น False เมื่อต้องการหยุดส่งข้อความเข้าห้อง Bot error analyze
GITLAB_URL = os.environ.get("GITLAB_URL", "https://git.ntbx.tech")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "aV1D4MnkC-_8pXW9DxJ6")

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
    "`ล้างแชท`\n\n"
    "*📌 Mission ประจำวัน*\n"
    "`mission add [รายละเอียด]` — เพิ่ม mission\n"
    "`mission` — ดู mission ทั้งหมดที่ยังค้างอยู่\n"
    "`mission done [id]` — ทำเสร็จแล้ว\n"
    "`mission clear` — ลบ mission ที่เสร็จแล้วทั้งหมด"
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


def _gitlab_request(path: str) -> list:
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{GITLAB_URL}/api/v4{path}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": GITLAB_TOKEN})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        return json.loads(resp.read())


def extract_service_name(text: str) -> str:
    """ดึงชื่อ service จาก error เช่น [HOGAN] หรือ [ERROR] PREDATOR"""
    m = re.search(r'\[([A-Z][A-Z0-9_-]{2,})\]', text)
    if m and m.group(1) not in ('API', 'ERROR', 'API_ERROR'):
        return m.group(1)
    return ""


def search_gitlab_code(identifiers: list, service_name: str = "", max_results: int = 4) -> str:
    """ค้นหา source code จาก GitLab API — หา project จากชื่อ service แล้วค้นหา blobs"""
    if not GITLAB_TOKEN:
        return ""
    snippets = []
    seen = set()

    # หา project id จากชื่อ service
    project_ids = []
    if service_name:
        try:
            projects = _gitlab_request(f"/projects?search={service_name.lower()}&per_page=5&membership=true")
            project_ids = [p["id"] for p in projects]
        except Exception as e:
            print(f"[gitlab] find project: {e}")

    for term in identifiers[:3]:
        for pid in project_ids[:3] or [None]:
            try:
                if pid:
                    path = f"/projects/{pid}/search?scope=blobs&search={term}&per_page=3"
                else:
                    break
                results = _gitlab_request(path)
                for r in results:
                    key = f"{r.get('project_id')}/{r.get('path')}"
                    if key not in seen:
                        seen.add(key)
                        snippets.append(f"// {r.get('path', '')}\n{r.get('data', '')}")
                        if len(snippets) >= max_results:
                            return "\n\n".join(snippets)
            except Exception as e:
                print(f"[gitlab] search {term} in {pid}: {e}")
    return "\n\n".join(snippets)


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

    # ถ้าดูเหมือน error — ค้นหา source code จาก GitLab API
    source_section = ""
    if is_error_message(text):
        identifiers = extract_identifiers(text)
        service_name = extract_service_name(text)
        if identifiers or service_name:
            combined = search_gitlab_code(identifiers, service_name)
            if combined:
                if len(combined) > 4000:
                    combined = combined[:4000] + "\n... (ตัดออกเพราะยาวเกิน)"
                source_section = f"\n\nSource code จาก GitLab (ใช้ประกอบการวิเคราะห์):\n```\n{combined}\n```"

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
        "🔴 [SERVICE] | [METHOD] [PATH] | [STATUS]\n"
        "📋 อาการ: {สรุปอาการสั้นๆ ว่าเกิดอะไรขึ้น}\n"
        "🔍 Root Cause: {อธิบายสาเหตุที่แท้จริง เป็นภาษาคนอ่านเข้าใจง่าย}\n"
        "📁 ไฟล์ที่เกี่ยวข้อง: {ชื่อไฟล์:บรรทัด} ← ใส่เฉพาะเมื่อทราบจาก stack trace หรือ source code\n"
        "🔗 Service ที่เกี่ยวข้อง: {บอกทุก service ในสาย error chain เช่น A → B → C}\n"
        "✅ แนวทางแก้ไข:\n"
        "  ระยะสั้น: {action ที่ทำได้ทันที}\n"
        "  ระยะยาว: {action ป้องกันไม่ให้เกิดซ้ำ}\n\n"
        "หมายเหตุ:\n"
        "- ถ้าข้อมูลบางส่วนไม่มีใน log ให้ใส่ - แทน อย่าเดาข้อมูล\n"
        "- ถ้าเคยเกิดมาแล้วให้เพิ่มบรรทัด: ⚠️ เคยเกิดมาแล้ว: {timestamp} — {สรุปสั้นๆ}\n"
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


# ── Mission helpers ────────────────────────────────────────────────────────────

def load_missions() -> list:
    try:
        with open(MISSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_missions(missions: list):
    with open(MISSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(missions, f, ensure_ascii=False, indent=2)


def mission_next_id(missions: list) -> int:
    return max((m["id"] for m in missions), default=0) + 1


def handle_mission_add(text: str, added_by: str = "") -> str:
    if not text.strip():
        return "ใส่รายละเอียด mission ด้วยนะ เช่น: `mission add ตรวจสอบ error log`"
    missions = load_missions()
    mission = {
        "id": mission_next_id(missions),
        "text": text.strip(),
        "added_by": added_by,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "done": False,
    }
    missions.append(mission)
    save_missions(missions)
    return f"📌 เพิ่ม mission #{mission['id']} แล้ว: {mission['text']}"


def handle_mission_list() -> str:
    missions = load_missions()
    pending = [m for m in missions if not m["done"]]
    if not pending:
        return "✅ ไม่มี mission ค้างอยู่"
    lines = [f"📋 *Mission ที่ยังค้างอยู่ ({len(pending)} รายการ)*\n"]
    for m in pending:
        lines.append(f"  #{m['id']} — {m['text']}")
        lines.append(f"  _เพิ่มโดย {m['added_by'] or 'ไม่ระบุ'} เมื่อ {m['added_at']}_\n")
    return "\n".join(lines)


def handle_mission_done(id_str: str) -> str:
    if not id_str.strip().isdigit():
        return "ระบุ ID เป็นตัวเลข เช่น: `mission done 3`"
    mid = int(id_str.strip())
    missions = load_missions()
    m = next((x for x in missions if x["id"] == mid), None)
    if not m:
        return f"ไม่พบ mission #{mid}"
    if m["done"]:
        return f"mission #{mid} ทำเสร็จไปแล้ว"
    m["done"] = True
    save_missions(missions)
    return f"✅ mission #{mid} เสร็จแล้ว: {m['text']}"


def handle_mission_clear() -> str:
    missions = load_missions()
    remaining = [m for m in missions if not m["done"]]
    removed = len(missions) - len(remaining)
    save_missions(remaining)
    return f"🧹 ลบ mission ที่เสร็จแล้ว {removed} รายการ"


def format_remind_message() -> str:
    missions = load_missions()
    pending = [m for m in missions if not m["done"]]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not pending:
        return f"📌 *Daily Mission* | {now_str}\n\n✅ ไม่มี mission ค้างอยู่ในวันนี้"
    lines = [f"📌 *Daily Mission* | {now_str}\n"]
    for m in pending:
        lines.append(f"  ☐ #{m['id']} — {m['text']}")
    lines.append(f"\nพิมพ์ `mission done [id]` เมื่อทำเสร็จ")
    return "\n".join(lines)


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

    # ── Mission commands ──────────────────────────────────────────────────────
    if lower.startswith("mission add ") or lower.startswith("mission add:"):
        body = re.split(r"mission add[: ]+", text, maxsplit=1, flags=re.IGNORECASE)[-1].strip()
        sender = session_key.split("_")[1] if "_" in session_key else session_key
        return handle_mission_add(body, added_by=sender)

    if lower.startswith("mission done ") or lower.startswith("mission done:"):
        id_str = re.split(r"mission done[: ]+", text, maxsplit=1, flags=re.IGNORECASE)[-1].strip()
        return handle_mission_done(id_str)

    if lower == "mission clear":
        return handle_mission_clear()

    if lower in ("mission", "mission list", "missions"):
        return handle_mission_list()

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
    if not WEBHOOK_ENABLED:
        return False
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
                if is_error_message(arg_text) and space != ANALYZE_SPACE:
                    header = f"🔔 *Auto-analyzed* | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    threading.Thread(target=send_to_gchat_webhook, args=(header + reply,), daemon=True).start()
                return addons_response(reply)
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
            return jsonify({"text": reply})

    return jsonify({})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/remind", methods=["GET", "POST"])
def remind():
    """ถูกเรียกโดย cron-job.org ตาม schedule → ส่ง mission ไปห้อง Bot error analyze"""
    msg = format_remind_message()
    sent = send_to_gchat_webhook(msg)
    print(f"[remind] ส่ง mission reminder {'สำเร็จ' if sent else 'ล้มเหลว'}")
    return jsonify({"status": "ok", "sent": sent, "missions": msg})


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


def _scheduled_remind():
    msg = format_remind_message()
    sent = send_to_gchat_webhook(msg)
    print(f"[scheduler] remind {'ok' if sent else 'failed'}", flush=True)

_bkk = pytz.timezone("Asia/Bangkok")
_scheduler = BackgroundScheduler(timezone=_bkk)
for _hr in (9, 13, 16):
    _scheduler.add_job(_scheduled_remind, "cron", hour=_hr, minute=0)
_scheduler.start()
print("[scheduler] started — remind at 09:00, 13:00, 16:00 BKK", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    print(f"Curl Case Bot starting on http://localhost:{port}")
    print("Storage:", STORAGE_FILE)
    app.run(host="0.0.0.0", port=port, debug=False)
