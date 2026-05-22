import os
import sys
import subprocess

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_PATH = r"c:\Users\manasicha.son\Desktop\BOT\code\analyze_error.py"
ICON_SOURCE  = r"c:\Users\manasicha.son\Downloads\Laplus_ch._3F3F3F3F3F_-_holoX_-_2g.webp"
ICON_PATH    = r"c:\Users\manasicha.son\Desktop\BOT\code\bot_icon.ico"
SHORTCUT_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "NTB Error Bot.lnk")

def install(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True, capture_output=True)

def convert_to_ico(src, dst):
    try:
        from PIL import Image
    except ImportError:
        print("ติดตั้ง Pillow...")
        install("Pillow")
        from PIL import Image

    img = Image.open(src).convert("RGBA")
    img = img.resize((256, 256))
    img.save(dst, format="ICO", sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
    print(f"แปลงไอคอนสำเร็จ: {dst}")

def create_shortcut(target, icon, shortcut_path):
    py_exe = sys.executable
    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{shortcut_path}")
$s.TargetPath = "{py_exe}"
$s.Arguments = '"{target}"'
$s.IconLocation = "{icon}"
$s.WorkingDirectory = "{os.path.dirname(target)}"
$s.Description = "NTB API Error Analyzer"
$s.Save()
"""
    result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"สร้าง shortcut สำเร็จ: {shortcut_path}")
    else:
        print(f"เกิดข้อผิดพลาด: {result.stderr}")

if __name__ == "__main__":
    if not os.path.exists(ICON_SOURCE):
        print(f"ไม่พบไฟล์รูป: {ICON_SOURCE}")
        print("กรุณาบันทึกรูปจากแชทลง Downloads แล้วแก้ชื่อไฟล์ใน ICON_SOURCE ให้ตรงกัน")
        sys.exit(1)

    convert_to_ico(ICON_SOURCE, ICON_PATH)
    create_shortcut(SCRIPT_PATH, ICON_PATH, SHORTCUT_PATH)
