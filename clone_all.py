"""
clone_all.py — โหลดทุก repo จาก GitLab ลง Downloads\theme\
รัน: py clone_all.py
"""

import json
import os
import ssl
import subprocess
import sys
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8")

GITLAB_URL = "https://git.ntbx.tech"
TOKEN      = "aV1D4MnkC-_8pXW9DxJ6"
DEST_DIR   = r"C:\Users\manasicha.son\Downloads\theme"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

os.makedirs(DEST_DIR, exist_ok=True)


def fetch_all_repos() -> list:
    repos = []
    page = 1
    while True:
        url = f"{GITLAB_URL}/api/v4/projects?membership=true&per_page=100&page={page}"
        req = Request(url, headers={"PRIVATE-TOKEN": TOKEN})
        with urlopen(req, timeout=15, context=ctx) as r:
            batch = json.loads(r.read())
        if not batch:
            break
        repos.extend(batch)
        print(f"  ดึงรายชื่อ... {len(repos)} repos", end="\r")
        page += 1
    return repos


def clone_or_pull(repo: dict, idx: int, total: int):
    name      = repo["path"]
    namespace = repo["namespace"]["path"]
    clone_url = repo["http_url_to_repo"]

    # force https and inject token
    https_url = clone_url.replace("http://", "https://", 1)
    auth_url  = https_url.replace("https://", f"https://oauth2:{TOKEN}@", 1)
    dest      = os.path.join(DEST_DIR, namespace, name)
    label     = f"{namespace}/{name}"

    os.makedirs(os.path.join(DEST_DIR, namespace), exist_ok=True)

    if os.path.exists(os.path.join(dest, ".git")):
        action = "pull"
        cmd = ["git", "-C", dest, "pull", "--quiet", "--ff-only"]
    else:
        action = "clone"
        cmd = ["git", "clone", "--quiet", "--depth=1", auth_url, dest]

    print(f"[{idx}/{total}] {action} {label} ...", end=" ", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("OK")
    else:
        err = (result.stderr or result.stdout).strip()[:100]
        print(f"FAIL — {err}")


if __name__ == "__main__":
    print(f"กำลังดึงรายชื่อ repos จาก {GITLAB_URL} ...")
    repos = fetch_all_repos()
    print(f"\nพบ {len(repos)} repos — เริ่ม clone/pull ลง {DEST_DIR}\n")

    for i, repo in enumerate(repos, 1):
        clone_or_pull(repo, i, len(repos))

    print(f"\nเสร็จแล้ว! ดู repos ได้ที่ {DEST_DIR}")
