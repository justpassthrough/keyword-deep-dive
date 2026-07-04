"""
인물조합(hot_combo) 신선도 감시견.

data/hot_combos.json의 updated_at(로컬 PC가 KST로 기록)이 너무 오래됐으면
= 로컬 작업 스케줄러가 며칠째 안 돌았다는 뜻 → 경고 메시지를 stdout에 출력.
신선하면 아무것도 출력하지 않는다(항상 exit 0).

GitHub Actions(항상 켜짐)에서 하루 1회 실행 → 출력이 있으면 텔레그램 전송.
'로컬 실행이 조용히 멈추는' 구멍을 클라우드에서 메우는 장치.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

STALE_HOURS = 36  # 로컬은 하루 2회(10/16 KST) → 36h면 하루 통째로 놓친 뒤 경고
KST = timezone(timedelta(hours=9))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(HERE, "data", "hot_combos.json")


def main():
    if not os.path.exists(PATH):
        print("⚠️ 인물조합 데이터 파일(hot_combos.json)이 없습니다. 로컬 스캔이 한 번도 안 돌았을 수 있어요.")
        return
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ hot_combos.json 읽기 실패: {e}")
        return

    updated_at = data.get("updated_at", "")
    try:
        # updated_at은 로컬(KST) 기준 "%Y-%m-%d %H:%M"
        ts = datetime.strptime(updated_at, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    except ValueError:
        print(f"⚠️ 인물조합 updated_at 형식을 못 읽었습니다: {updated_at!r}")
        return

    now_kst = datetime.now(KST)
    age_h = (now_kst - ts).total_seconds() / 3600

    if age_h > STALE_HOURS:
        days = age_h / 24
        print(
            f"⚠️ 인물조합 스캔이 {age_h:.0f}시간({days:.1f}일)째 안 돌고 있습니다.\n"
            f"마지막 갱신: {updated_at} (KST)\n"
            f"→ 집 PC가 꺼져 있거나 작업 스케줄러/스크립트에 문제가 생겼을 수 있어요. "
            f"PC를 켜두거나 hot_combo_local.log를 확인하세요."
        )
    # 신선하면 출력 없음


if __name__ == "__main__":
    # 콘솔 인코딩 안전장치
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
