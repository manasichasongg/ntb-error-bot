import tkinter as tk
import threading
import anthropic
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Theme ──────────────────────────────────────────────────────────────────────
BG          = "#1b1b2f"
CHAT_BG     = "#13132a"
INPUT_BG    = "#2a2a45"
BORDER      = "#3a3a5a"
ACCENT      = "#4dc8e0"
TEXT        = "#e8e8ff"
HINT        = "#606090"
USER_COLOR  = "#89d4ff"
BOT_COLOR   = "#88e8b0"
SYS_COLOR   = "#606090"
ERR_COLOR   = "#ff7080"
SEND_BG     = "#4dc8e0"
SEND_FG     = "#111122"

FONT        = ("Segoe UI", 10)
FONT_BOLD   = ("Segoe UI", 10, "bold")
FONT_SMALL  = ("Segoe UI", 9)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
ICON_PATH   = os.path.join(os.path.dirname(__file__), "bot_icon.ico")

SYSTEM_PROMPT = """คุณเป็น expert วิเคราะห์ API error สำหรับระบบ .NET microservices
ของบริษัท NTB (Ngernturbo) ที่มี services ได้แก่ GOLDEN, GRINGOTTS, TITAN, CERSEI, TYREK, GALANGAL เป็นต้น

เมื่อได้รับ error log ให้วิเคราะห์และตอบในรูปแบบนี้:
1. **สรุปปัญหา** - อธิบายสั้นๆ ว่าเกิดอะไรขึ้น
2. **Root Cause** - สาเหตุที่แท้จริง
3. **ไฟล์/บรรทัดที่น่าจะเกิดปัญหา** - ระบุให้ชัดเจนถ้าทำได้
4. **Short Term Solution** - แก้ไขเฉพาะหน้า
5. **Long Term Solution** - แก้ไขถาวร

หากผู้ใช้ถามคำถามติดตาม ให้ตอบในบริบทของ error เดิม และให้รายละเอียดเพิ่มเติมตามที่ถาม"""


# ── Config helpers ─────────────────────────────────────────────────────────────
def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── Settings popup ─────────────────────────────────────────────────────────────
class SettingsPopup(tk.Toplevel):
    def __init__(self, parent, cfg: dict, on_save):
        super().__init__(parent)
        self.title("ตั้งค่า")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()

        wrap = tk.Frame(self, bg=BG, padx=24, pady=16)
        wrap.pack()

        def row(label, default="", show=""):
            tk.Label(wrap, text=label, bg=BG, fg=TEXT, font=FONT).pack(anchor="w", pady=(8, 0))
            ent = tk.Entry(wrap, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                           relief="flat", highlightthickness=1,
                           highlightbackground=BORDER, highlightcolor=ACCENT,
                           font=FONT, width=48, show=show)
            ent.insert(0, default)
            ent.pack(ipady=5)
            return ent

        self._ent_key     = row("Anthropic API Key", cfg.get("api_key", ""), show="●")
        self._ent_webhook = row("Google Chat Webhook URL", cfg.get("webhook_url", ""))

        def _show_toggle():
            show = self._ent_key.cget("show")
            self._ent_key.config(show="" if show else "●")

        tk.Button(wrap, text="แสดง/ซ่อน API Key", bg=BORDER, fg=TEXT,
                  font=FONT_SMALL, relief="flat", cursor="hand2",
                  padx=8, pady=3, command=_show_toggle).pack(anchor="e", pady=(2, 10))

        tk.Button(wrap, text="บันทึก", bg=ACCENT, fg=BG, font=FONT_BOLD,
                  relief="flat", cursor="hand2", padx=24, pady=6,
                  command=lambda: self._save(cfg, on_save)).pack()

    def _save(self, cfg, on_save):
        cfg["api_key"]     = self._ent_key.get().strip()
        cfg["webhook_url"] = self._ent_webhook.get().strip()
        save_config(cfg)
        on_save()
        self.destroy()


# ── Main chat window ───────────────────────────────────────────────────────────
class ChatBot(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NTB Error Analysis Chat")
        self.configure(bg=BG)
        self.minsize(640, 520)
        self.geometry("760x640")

        self._cfg       = load_config()
        self._history:  list[dict] = []
        self._streaming = False
        self._client:   anthropic.Anthropic | None = None
        self._last_bot_response = ""

        try:
            self.iconbitmap(ICON_PATH)
        except Exception:
            pass

        self._build()
        self._init_client()
        self._sys_msg("สวัสดี! 👋  วาง error log ที่ต้องการวิเคราะห์ หรือถามคำถามได้เลย\n"
                      "Shift+Enter เพื่อขึ้นบรรทัดใหม่  •  Enter เพื่อส่ง")

    # ── Build ──────────────────────────────────────────────────────────────────
    def _build(self):
        # ── Top bar ────────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=BG, padx=16, pady=8)
        top.pack(fill="x")

        tk.Label(top, text="⚡  NTB Error Analysis Chat",
                 bg=BG, fg=ACCENT, font=FONT_BOLD).pack(side="left")

        self._key_var = tk.StringVar()
        key_lbl = tk.Label(top, textvariable=self._key_var,
                           bg=BG, fg=HINT, font=FONT_SMALL, cursor="hand2")
        key_lbl.pack(side="right")
        key_lbl.bind("<Button-1>", lambda _: self._open_settings())

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Input area (pack ก่อน แล้วค่อย chat เพื่อไม่ให้ถูกดันออก) ───────────
        tk.Label(self, text="Enter ส่ง  •  Shift+Enter ขึ้นบรรทัดใหม่",
                 bg=BG, fg=HINT, font=FONT_SMALL).pack(side="bottom", pady=(0, 6))

        bottom = tk.Frame(self, bg=BG, padx=16, pady=8)
        bottom.pack(side="bottom", fill="x")

        self._input = tk.Text(
            bottom, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
            font=FONT, height=4, wrap="word",
        )
        self._input.pack(side="left", fill="x", expand=True, ipady=6)
        self._input.bind("<Return>",       self._on_enter)
        self._input.bind("<Shift-Return>", lambda e: None)

        btn_col = tk.Frame(bottom, bg=BG)
        btn_col.pack(side="right", padx=(10, 0))

        self._send_btn = tk.Button(
            btn_col, text="ส่ง  ▶",
            bg=SEND_BG, fg=SEND_FG, font=FONT_BOLD,
            relief="flat", cursor="hand2",
            padx=16, pady=8, bd=0,
            activebackground="#7de8f5",
            command=self._on_send,
        )
        self._send_btn.pack(fill="x")

        tk.Button(
            btn_col, text="📤  GChat",
            bg=INPUT_BG, fg=TEXT, font=FONT_SMALL,
            relief="flat", cursor="hand2",
            padx=8, pady=5, bd=0,
            command=self._send_gchat_manual,
        ).pack(fill="x", pady=(5, 0))

        tk.Button(
            btn_col, text="🗑  ล้างแชท",
            bg=INPUT_BG, fg=HINT, font=FONT_SMALL,
            relief="flat", cursor="hand2",
            padx=8, pady=5, bd=0,
            command=self._clear_chat,
        ).pack(fill="x", pady=(5, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")

        # ── Chat area ──────────────────────────────────────────────────────────
        chat_frame = tk.Frame(self, bg=CHAT_BG)
        chat_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(chat_frame, bg=BG, troughcolor=INPUT_BG, bd=0, width=10)
        scrollbar.pack(side="right", fill="y")

        self._chat = tk.Text(
            chat_frame, bg=CHAT_BG, fg=TEXT,
            font=FONT, relief="flat", wrap="word",
            state="disabled", padx=16, pady=12,
            highlightthickness=0, spacing1=2, spacing3=6,
            yscrollcommand=scrollbar.set,
        )
        self._chat.pack(fill="both", expand=True)
        scrollbar.config(command=self._chat.yview)

        self._chat.tag_config("user_lbl",  foreground=USER_COLOR,  font=FONT_BOLD)
        self._chat.tag_config("user_txt",  foreground=TEXT,         lmargin1=28, lmargin2=28)
        self._chat.tag_config("bot_lbl",   foreground=BOT_COLOR,    font=FONT_BOLD)
        self._chat.tag_config("bot_txt",   foreground=TEXT,          lmargin1=28, lmargin2=28)
        self._chat.tag_config("sys_txt",   foreground=SYS_COLOR,    font=FONT_SMALL, justify="center")
        self._chat.tag_config("err_txt",   foreground=ERR_COLOR,    font=FONT_SMALL, lmargin1=28)


    # ── Client ─────────────────────────────────────────────────────────────────
    def _init_client(self):
        key = self._cfg.get("api_key", "")
        if key:
            self._client = anthropic.Anthropic(api_key=key)
            self._key_var.set("🔑 API Key ตั้งค่าแล้ว  (คลิกเพื่อแก้ไข)")
        else:
            self._client = None
            self._key_var.set("⚠  ยังไม่ได้ตั้งค่า API Key  (คลิกที่นี่)")

    def _open_settings(self):
        SettingsPopup(self, self._cfg, on_save=lambda: (
            self._init_client(),
            self._sys_msg("บันทึกการตั้งค่าแล้ว ✓"),
        ))

    # ── Chat write helpers ──────────────────────────────────────────────────────
    def _sys_msg(self, text: str):
        self._chat.config(state="normal")
        self._chat.insert("end", f"\n  {text}\n", "sys_txt")
        self._chat.config(state="disabled")
        self._chat.see("end")

    def _user_msg(self, text: str):
        self._chat.config(state="normal")
        self._chat.insert("end", "\nคุณ ►\n", "user_lbl")
        self._chat.insert("end", text + "\n", "user_txt")
        self._chat.config(state="disabled")
        self._chat.see("end")

    def _bot_start(self):
        self._chat.config(state="normal")
        self._chat.insert("end", "\nClaude ►\n", "bot_lbl")
        self._chat.config(state="disabled")
        self._chat.see("end")

    def _bot_chunk(self, chunk: str):
        self._chat.config(state="normal")
        self._chat.insert("end", chunk, "bot_txt")
        self._chat.config(state="disabled")
        self._chat.see("end")

    def _bot_done(self):
        self._chat.config(state="normal")
        self._chat.insert("end", "\n", "bot_txt")
        self._chat.config(state="disabled")
        self._chat.see("end")
        self._streaming = False
        self._send_btn.config(state="normal", text="ส่ง  ▶")

    def _err_msg(self, text: str):
        self._chat.config(state="normal")
        self._chat.insert("end", f"⚠  {text}\n", "err_txt")
        self._chat.config(state="disabled")
        self._chat.see("end")
        self._streaming = False
        self._send_btn.config(state="normal", text="ส่ง  ▶")

    def _clear_chat(self):
        self._chat.config(state="normal")
        self._chat.delete("1.0", "end")
        self._chat.config(state="disabled")
        self._history.clear()
        self._last_bot_response = ""
        self._sys_msg("เริ่มการสนทนาใหม่")

    # ── Send ───────────────────────────────────────────────────────────────────
    def _on_enter(self, event):
        if event.state & 0x0001:   # Shift held → ขึ้นบรรทัดใหม่
            return
        self._on_send()
        return "break"

    def _on_send(self):
        if self._streaming:
            return

        text = self._input.get("1.0", "end").strip()
        if not text:
            return

        if not self._client:
            self._sys_msg("⚠  กรุณาตั้งค่า API Key ก่อน (คลิกที่มุมขวาบน)")
            return

        self._input.delete("1.0", "end")
        self._user_msg(text)
        self._history.append({"role": "user", "content": text})

        self._streaming = True
        self._send_btn.config(state="disabled", text="⏳")
        threading.Thread(target=self._stream, daemon=True).start()

    def _stream(self):
        parts: list[str] = []
        try:
            self.after(0, self._bot_start)
            with self._client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=self._history,
            ) as stream:
                for chunk in stream.text_stream:
                    parts.append(chunk)
                    self.after(0, lambda c=chunk: self._bot_chunk(c))

            response = "".join(parts)
            self._history.append({"role": "assistant", "content": response})
            self._last_bot_response = response
            self.after(0, self._bot_done)
            threading.Thread(target=self._do_send_gchat, args=(response,), daemon=True).start()

        except Exception as e:
            self.after(0, lambda err=str(e): self._err_msg(err[:220]))

    # ── Google Chat ────────────────────────────────────────────────────────────
    def _send_gchat_manual(self):
        if not self._last_bot_response:
            self._sys_msg("ยังไม่มีผลวิเคราะห์ที่จะส่ง")
            return
        webhook = self._cfg.get("webhook_url", "")
        if not webhook:
            self._sys_msg("⚠  ยังไม่ได้ตั้งค่า Google Chat Webhook (คลิกตั้งค่า)")
            return
        threading.Thread(
            target=self._do_send_gchat,
            args=(self._last_bot_response,),
            daemon=True,
        ).start()

    def _do_send_gchat(self, analysis: str):
        import urllib.request as _req
        webhook = self._cfg.get("webhook_url", "")
        last_user = next(
            (m["content"] for m in reversed(self._history) if m["role"] == "user"), ""
        )
        short_err = last_user[:600] + ("..." if len(last_user) > 600 else "")
        text = (
            "🔍 *NTB Error Analysis*\n\n"
            f"*Error Log:*\n```\n{short_err}\n```\n\n"
            f"{analysis}"
        )
        data    = json.dumps({"text": text}).encode("utf-8")
        request = _req.Request(webhook, data=data,
                               headers={"Content-Type": "application/json"},
                               method="POST")
        try:
            with _req.urlopen(request, timeout=15) as resp:
                if resp.status == 200:
                    self.after(0, lambda: self._sys_msg("ส่งผลวิเคราะห์ไป Google Chat สำเร็จ ✓"))
                else:
                    self.after(0, lambda: self._sys_msg(f"Google Chat ตอบกลับ status {resp.status}"))
        except Exception as e:
            self.after(0, lambda err=str(e): self._sys_msg(f"⚠  ส่ง GChat ไม่สำเร็จ: {err[:120]}"))


if __name__ == "__main__":
    app = ChatBot()
    app.mainloop()
