import tkinter as tk
import sys
import os
import json
import threading
import subprocess
from urllib.parse import quote

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BG        = "#1b1b2f"
INPUT_BG  = "#2a2a45"
BORDER    = "#404060"
ACCENT    = "#4dc8e0"
TEXT      = "#e8e8ff"
HINT      = "#606090"
START_BG  = "#6de4f0"
START_FG  = "#111122"
STATUS_OK = "#4dc8a0"
STATUS_WN = "#e0a84d"

FONT       = ("Segoe UI", 10)
FONT_BOLD  = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 8)
FONT_START = ("Segoe UI", 12, "bold")

ICON_PATH   = r"c:\Users\manasicha.son\Desktop\BOT\code\bot_icon.ico"
CONFIG_PATH = r"c:\Users\manasicha.son\Desktop\BOT\code\config.json"

SYSTEM_PROMPT = """คุณเป็น expert วิเคราะห์ API error สำหรับระบบ .NET microservices
ของบริษัท NTB (Ngernturbo) ที่มี services ได้แก่ GOLDEN, GRINGOTTS, TITAN, CERSEI, TYREK, GALANGAL เป็นต้น

เมื่อได้รับ error log ให้วิเคราะห์และตอบในรูปแบบนี้:
1. *สรุปปัญหา* - อธิบายสั้นๆ ว่าเกิดอะไรขึ้น
2. *Root Cause* - สาเหตุที่แท้จริง
3. *ไฟล์/บรรทัดที่น่าจะเกิดปัญหา* - ระบุให้ชัดเจนถ้าทำได้
4. *Short Term Solution* - แก้ไขเฉพาะหน้า
5. *Long Term Solution* - แก้ไขถาวร"""


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"git_user": "", "git_pass": "", "git_host": "git.ntbx.tech",
            "api_key": "", "webhook_url": ""}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


GIT_HOST = load_config().get("git_host", "git.ntbx.tech")


def styled_entry(parent, width=30, show=""):
    return tk.Entry(
        parent, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
        relief="flat", highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=ACCENT,
        font=FONT, width=width, show=show
    )


class BotLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AllTicket Bot Launcher")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._show_pass = False
        self._show_key  = False
        self._cfg = load_config()
        try:
            self.iconbitmap(ICON_PATH)
        except Exception:
            pass
        self._build()

    def _build(self):
        wrap = tk.Frame(self, bg=BG, padx=30, pady=24)
        wrap.pack(fill="both", expand=True)

        def row():
            f = tk.Frame(wrap, bg=BG)
            f.pack(fill="x", pady=6)
            return f

        def lbl(parent, text):
            tk.Label(parent, text=text, bg=BG, fg=TEXT,
                     font=FONT, width=14, anchor="w").pack(side="left")

        # ── อีเมล ─────────────────────────────────────────────────────────────
        r = row()
        lbl(r, "อีเมล")
        self.ent_email = styled_entry(r, width=28)
        self.ent_email.insert(0, self._cfg.get("git_user", ""))
        self.ent_email.pack(side="left", ipady=5)

        # ── รหัสผ่าน ──────────────────────────────────────────────────────────
        r = row()
        lbl(r, "รหัสผ่าน")
        self.ent_pass = styled_entry(r, width=25, show="●")
        self.ent_pass.insert(0, self._cfg.get("git_pass", ""))
        self.ent_pass.pack(side="left", ipady=5)
        tk.Button(r, text="👁", bg=ACCENT, fg=BG, font=FONT,
                  relief="flat", cursor="hand2", padx=6, pady=3, bd=0,
                  activebackground="#7de8f5",
                  command=self._toggle_pass).pack(side="left", padx=(6, 0))

        # separator
        tk.Frame(wrap, bg=BORDER, height=1).pack(fill="x", pady=10)

        # ── ชื่อโปรเจค ────────────────────────────────────────────────────────
        r = row()
        lbl(r, "Projects Name")
        self.ent_project = styled_entry(r, width=28)
        self.ent_project.pack(side="left", ipady=5)

        tk.Label(wrap, text=f"ค้นหาและโคลนจาก {GIT_HOST}",
                 bg=BG, fg=HINT, font=FONT_SMALL).pack(pady=(0, 6))

        # separator
        tk.Frame(wrap, bg=BORDER, height=1).pack(fill="x", pady=10)

        # ── Error Message ─────────────────────────────────────────────────────
        tk.Label(wrap, text="Error Message", bg=BG, fg=TEXT,
                 font=FONT, anchor="w").pack(fill="x")
        self.txt_error = tk.Text(
            wrap, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
            font=FONT, width=44, height=6, wrap="word"
        )
        self.txt_error.pack(fill="x", pady=(4, 2))

        clr_row = tk.Frame(wrap, bg=BG)
        clr_row.pack(fill="x")
        tk.Label(clr_row, text="วาง error log ที่ต้องการวิเคราะห์",
                 bg=BG, fg=HINT, font=FONT_SMALL).pack(side="left")
        tk.Button(clr_row, text="ล้าง", bg=BORDER, fg=TEXT, font=FONT_SMALL,
                  relief="flat", cursor="hand2", padx=8, pady=1,
                  command=lambda: self.txt_error.delete("1.0", "end")
                  ).pack(side="right")

        # separator
        tk.Frame(wrap, bg=BORDER, height=1).pack(fill="x", pady=10)

        # ── Anthropic API Key ─────────────────────────────────────────────────
        r = row()
        lbl(r, "Anthropic Key")
        self.ent_apikey = styled_entry(r, width=25, show="●")
        self.ent_apikey.insert(0, self._cfg.get("api_key", ""))
        self.ent_apikey.pack(side="left", ipady=5)
        tk.Button(r, text="👁", bg=ACCENT, fg=BG, font=FONT,
                  relief="flat", cursor="hand2", padx=6, pady=3, bd=0,
                  activebackground="#7de8f5",
                  command=self._toggle_key).pack(side="left", padx=(6, 0))

        # ── GChat Webhook URL ─────────────────────────────────────────────────
        r = row()
        lbl(r, "GChat Webhook")
        self.ent_webhook = styled_entry(r, width=28)
        self.ent_webhook.insert(0, self._cfg.get("webhook_url", ""))
        self.ent_webhook.pack(side="left", ipady=5)

        tk.Label(wrap, text="วิเคราะห์ error แล้วส่งผลไป Google Chat",
                 bg=BG, fg=HINT, font=FONT_SMALL).pack(pady=(0, 6))

        # ── START BOT ─────────────────────────────────────────────────────────
        self.start_btn = tk.Button(
            wrap, text="▶   START BOT",
            bg=START_BG, fg=START_FG, font=FONT_START,
            relief="flat", cursor="hand2",
            padx=50, pady=10, bd=0,
            activebackground="#9af0f8",
            command=self._on_start,
        )
        self.start_btn.pack(pady=14)

        # ── Status ────────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(wrap, textvariable=self.status_var,
                                   bg=BG, fg=STATUS_OK, font=FONT_SMALL)
        self.status_lbl.pack()

    def _set_status(self, msg, warn=False):
        self.status_var.set(msg)
        self.status_lbl.config(fg=STATUS_WN if warn else STATUS_OK)

    def _toggle_pass(self):
        self._show_pass = not self._show_pass
        self.ent_pass.config(show="" if self._show_pass else "●")

    def _toggle_key(self):
        self._show_key = not self._show_key
        self.ent_apikey.config(show="" if self._show_key else "●")

    def _on_start(self):
        email       = self.ent_email.get().strip()
        password    = self.ent_pass.get().strip()
        project     = self.ent_project.get().strip()
        error_log   = self.txt_error.get("1.0", "end").strip()
        api_key     = self.ent_apikey.get().strip()
        webhook_url = self.ent_webhook.get().strip()

        if not email:
            self._set_status("⚠ กรุณากรอกอีเมล", warn=True); return
        if not password:
            self._set_status("⚠ กรุณากรอกรหัสผ่าน", warn=True); return
        if not project and not error_log:
            self._set_status("⚠ กรุณากรอกชื่อโปรเจค หรือวาง error log", warn=True); return

        cfg = self._cfg.copy()
        cfg.update({"git_user": email, "git_pass": password,
                    "git_host": GIT_HOST, "api_key": api_key,
                    "webhook_url": webhook_url})
        save_config(cfg)

        self.start_btn.config(state="disabled", text="⏳  กำลังทำงาน...")
        self.update()

        # รัน 2 flow พร้อมกัน (ถ้ามีข้อมูลครบ)
        if project:
            self._set_status(f"กำลังเปิดเบราว์เซอร์ค้นหา '{project}' ...")
            threading.Thread(target=self._search_and_open,
                             args=(email, password, project, error_log),
                             daemon=True).start()

        if error_log and api_key and webhook_url:
            self._set_status("กำลังวิเคราะห์ error...")
            threading.Thread(target=self._analyze_and_send,
                             args=(error_log, api_key, webhook_url),
                             daemon=True).start()
        elif error_log and (not api_key or not webhook_url):
            self._set_status("⚠ กรุณากรอก Anthropic Key และ GChat Webhook เพื่อวิเคราะห์ error", warn=True)
            self.start_btn.config(state="normal", text="▶   START BOT")

    def _analyze_and_send(self, error_log, api_key, webhook_url):
        import anthropic, requests

        def status(msg, warn=False):
            self.after(0, lambda m=msg, w=warn: self._set_status(m, w))

        def reset_btn():
            self.after(0, lambda: self.start_btn.config(state="normal", text="▶   START BOT"))

        try:
            status("กำลังวิเคราะห์ error ด้วย Claude...")
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"วิเคราะห์ error นี้:\n\n{error_log}"}]
            )
            analysis = msg.content[0].text

            status("ส่งผลวิเคราะห์ไป Google Chat...")
            short_err = error_log[:600] + ("..." if len(error_log) > 600 else "")
            text = (
                "🔍 *NTB Error Analysis*\n\n"
                f"*Error Log:*\n```\n{short_err}\n```\n\n"
                f"{analysis}"
            )
            resp = requests.post(webhook_url, json={"text": text}, timeout=15)
            resp.raise_for_status()
            status("ส่งผลวิเคราะห์ไป Google Chat สำเร็จ ✓")
        except Exception as e:
            status(f"⚠ {str(e)[:120]}", warn=True)
        finally:
            reset_btn()

    def _search_and_open(self, email, password, project, error_log):
        def status(msg, warn=False):
            self.after(0, lambda m=msg, w=warn: self._set_status(m, w))

        def reset_btn():
            self.after(0, lambda: self.start_btn.config(state="normal", text="▶   START BOT"))

        try:
            search_url = f"http://{GIT_HOST}/search?search={project}&scope=projects"
            status(f"เปิด Chrome ค้นหา '{project}'...")
            chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            subprocess.Popen([chrome_exe, search_url])
            status(f"ค้นหา '{project}' แล้ว — เลือก repo แล้วกด Clone ในบอท")
            self.after(0, lambda: self._ask_repo_url(email, password, project))
            reset_btn()
        except Exception as e:
            status(f"⚠ {str(e)[:100]}", warn=True)
            reset_btn()

    def _ask_repo_url(self, email, password, project):
        popup = tk.Toplevel(self)
        popup.title("โคลนโปรเจค")
        popup.configure(bg=BG)
        popup.resizable(False, False)
        popup.grab_set()

        tk.Label(popup, text=f"วาง Clone URL ของ repo '{project}'",
                 bg=BG, fg=TEXT, font=FONT_BOLD, padx=20, pady=10).pack()

        ent = styled_entry(popup, width=48)
        ent.pack(padx=20, pady=4, ipady=5)

        def do_clone():
            repo_url = ent.get().strip()
            if not repo_url:
                return
            user_enc = quote(email,    safe="")
            pass_enc = quote(password, safe="")
            auth_url = repo_url.replace("http://", f"http://{user_enc}:{pass_enc}@", 1)
            theme_dir = r"C:\Users\manasicha.son\Downloads\theme"
            os.makedirs(theme_dir, exist_ok=True)
            dest = f"{theme_dir}\\{project}-master"

            if os.path.exists(dest):
                git_cmd = f'git -C "{dest}" pull'
            else:
                git_cmd = f'git clone {auth_url} "{dest}"'

            popup.destroy()
            self.clipboard_clear()
            self.clipboard_append(git_cmd)

            subprocess.Popen(
                ["powershell", "-NoExit"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=theme_dir
            )

            def paste_and_run():
                import time, pyautogui
                time.sleep(1.5)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.2)
                pyautogui.press("enter")

            threading.Thread(target=paste_and_run, daemon=True).start()
            self._set_status(f"เปิด PowerShell รัน git clone '{project}' แล้ว")
            self.start_btn.config(state="normal", text="▶   START BOT")

        def skip():
            popup.destroy()
            self.start_btn.config(state="normal", text="▶   START BOT")

        btn_row = tk.Frame(popup, bg=BG)
        btn_row.pack(pady=12)
        tk.Button(btn_row, text="📋 Clone", bg=ACCENT, fg=BG, font=FONT_BOLD,
                  relief="flat", cursor="hand2", padx=16, pady=6,
                  command=do_clone).pack(side="left", padx=6)
        tk.Button(btn_row, text="ข้าม", bg=BORDER, fg=TEXT, font=FONT,
                  relief="flat", cursor="hand2", padx=16, pady=6,
                  command=skip).pack(side="left", padx=6)


if __name__ == "__main__":
    app = BotLauncher()
    app.mainloop()
