#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""미니PC(관제탑) 로컬 실행기 (2026-09-20). 작업 스케줄러가 부른다.

왜 로컬인가: GitHub Actions 예약 실행이 늘 밀린다(09-09~19 실측 30회: 07:30 회차 +1.6~2.3시간, 19:00 회차 +3.3~6.1시간).
아침 06:30 글쓰기가 항상 전날 밤 자료를 쓰게 돼, 트렌드 스캐너처럼 정시에 도는 미니PC 로 옮긴다.
GitHub 는 그대로 결과 배포(raw 주소)·Pages 대시보드·코드 보관 역할을 한다. 워크플로의 cron 은 주석 처리(수동 실행·비상용으로 남김).

순서: git pull → (모드별 스크립트) → 대시보드 빌드·주입 → data/·docs/ 커밋 → push. 실패하면 텔레그램.
  python scripts/run_local.py            # 매일 스캔(dive.py)
  python scripts/run_local.py discover   # 주간 뿌리 발굴(discover_roots.py → dive.py)
  python scripts/run_local.py goldmine   # 주간 롱테일(longtail_goldmine.py)
  --no-push 를 붙이면 커밋·push 없이 끝낸다(시험용)
비밀값은 저장소에 두지 않는다: 네이버 키는 이 폴더의 .env(없으면 트렌드 스캐너 폴더의 .env), GitHub 토큰·텔레그램은 video-auto 의 .env.local.
"""
import base64
import os
import re
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_ENV = os.environ.get("SHARED_ENV", r"C:\auto\video-auto\.env.local")
FALLBACK_ENV = os.environ.get("NAVER_ENV_FALLBACK", r"C:\auto\health-trend-scanner\.env")
LOG = os.path.join(BASE, "run_local.log")


def read_env(path):
    out = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
                if m:
                    out[m.group(1)] = m.group(2).strip('"')
    except OSError:
        pass
    return out


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(args, env=None, timeout=5400):
    p = subprocess.run(args, cwd=BASE, env=env, capture_output=True, timeout=timeout)
    out = (p.stdout + p.stderr).decode("utf-8", errors="replace")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(out[-6000:] + "\n")
    return p.returncode, out


def notify(shared, text):
    token, chat = shared.get("TELEGRAM_BOT_TOKEN"), shared.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text[:3500]}, timeout=15)
    except Exception:
        pass


def main():
    mode = next((a for a in sys.argv[1:] if not a.startswith("--")), "dive")
    dry = "--no-push" in sys.argv
    shared = read_env(SHARED_ENV)
    keys = {**read_env(FALLBACK_ENV), **read_env(os.path.join(BASE, ".env"))}
    env = {**os.environ, **keys, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    gh = shared.get("INFLOW_GITHUB_TOKEN", "")
    auth = ["-c", "http.extraheader=AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{gh}".encode()).decode()] if gh else []

    log(f"=== 딥다이브 시작({mode}) ===")
    if not env.get("NAVER_CLIENT_ID"):
        log("NAVER_CLIENT_ID 없음 — 중단")
        notify(shared, "⚠️ 키워드 딥다이브(미니PC): 네이버 키를 못 읽음(.env)")
        return 1
    code, _ = run(["git", *auth, "pull", "--rebase", "--autostash"])
    if code != 0:
        log("git pull 실패 — 그대로 진행")

    steps = {"dive": ["dive.py"], "discover": ["discover_roots.py", "dive.py"], "goldmine": ["longtail_goldmine.py"]}.get(mode)
    if not steps:
        log(f"모르는 모드: {mode}")
        return 2
    for script in steps:
        code, out = run([sys.executable, f"scripts/{script}"], env=env)
        if code != 0:
            tail = "\n".join(out.strip().splitlines()[-6:])
            log(f"{script} 실패")
            notify(shared, f"⚠️ 키워드 딥다이브(미니PC) 실패 — {script}\n{tail}")
            return 1

    # 대시보드: goldmine 은 자기 섹션만, 나머지는 전체 빌드 뒤 섹션 주입(없으면 조용히 넘어감 — Actions 의 '|| true' 와 같다)
    builds = [["build_goldmine_section.py"]] if mode == "goldmine" else [["build_dashboard.py"], ["build_goldmine_section.py", "--inject"], ["build_hot_section.py", "--inject"]]
    for b in builds:
        code, _ = run([sys.executable, f"scripts/{b[0]}", *b[1:]], env=env)
        if code != 0 and b[0] == "build_dashboard.py":
            log("대시보드 빌드 실패")
            notify(shared, "⚠️ 키워드 딥다이브(미니PC): 대시보드 빌드 실패(데이터는 저장됨)")

    log("스캔 완료")
    if dry:
        log("--no-push: 커밋·push 생략")
        return 0
    run(["git", "add", "data", "docs"])
    run(["git", "-c", "user.name=deep-dive(minipc)", "-c", "user.email=deep-dive@users.noreply.github.com",
         "commit", "-m", f"{mode}(local): {datetime.now():%Y-%m-%d %H:%M}"])
    for _ in range(3):
        code, _ = run(["git", *auth, "push"])
        if code == 0:
            log("push 완료")
            return 0
        run(["git", *auth, "pull", "--rebase", "--autostash"])
    log("push 실패")
    notify(shared, "⚠️ 키워드 딥다이브(미니PC): 스캔은 됐는데 GitHub push 실패")
    return 1


if __name__ == "__main__":
    sys.exit(main())
