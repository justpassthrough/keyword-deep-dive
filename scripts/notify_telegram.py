"""
텔레그램 알림 공용 헬퍼 (블로그 알림봇 @andy_claude_manager_bot).

토큰·챗ID는 코드에 넣지 않고 환경변수로 받는다 (공개 repo 보호):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

사용법:
  python scripts/notify_telegram.py "보낼 메시지"
  echo "메시지" | python scripts/notify_telegram.py   # stdin도 가능

로컬 러너(run_hot_combo_local.ps1)와 감시견 워크플로우가 공통으로 호출한다.
토큰이 없으면 조용히 건너뛴다(로컬 개발 시 에러 안 나게).
"""
import os
import sys

import requests


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("[notify_telegram] 토큰/챗ID 없음 — 전송 건너뜀", file=sys.stderr)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
        ok = r.json().get("ok", False)
        if not ok:
            print(f"[notify_telegram] 전송 실패: {r.text}", file=sys.stderr)
        return ok
    except Exception as e:
        print(f"[notify_telegram] 예외: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]).strip()
    if not msg:
        msg = sys.stdin.read().strip()
    if not msg:
        print("[notify_telegram] 보낼 메시지가 비어 있음", file=sys.stderr)
        sys.exit(1)
    sys.exit(0 if send(msg) else 1)
