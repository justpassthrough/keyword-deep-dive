#!/usr/bin/env python3
"""검색광고 API 연결 테스트. 루트의 .env를 읽어 키워드 몇 개의 월간검색수를 출력."""
import os
import sys

# .env 수동 로드 (python-dotenv 의존성 없이)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(BASE, ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dive import fetch_search_volume, NAVER_AD_CUSTOMER_ID

if not NAVER_AD_CUSTOMER_ID:
    print("키가 없습니다. .env에 NAVER_AD_* 3개를 채워주세요.")
    sys.exit(1)

test_keywords = ["위고비 부작용", "마운자로", "글루타치온 효과", "오메가3 추천"]
print(f"테스트 키워드: {test_keywords}\n")
vol = fetch_search_volume(test_keywords)
if not vol:
    print("결과 없음 — 키/서명/권한을 확인하세요.")
    sys.exit(1)

for kw in test_keywords:
    key = kw.replace(" ", "").upper()
    info = vol.get(key)
    if info:
        print(f"  {kw}: 월간검색 {info['total']:,}회 "
              f"(PC {info['pc']:,} / 모바일 {info['mobile']:,}), 경쟁 {info['comp_idx']}")
    else:
        print(f"  {kw}: (응답에 없음)")
