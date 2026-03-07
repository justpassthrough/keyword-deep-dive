#!/usr/bin/env python3
"""
longtail_goldmine.py — ㄱㄴㄷ 자동완성 롱테일 발굴 + 금맥 카테고리 분류

기존 dive.py 파이프라인과 독립적으로 동작.
Deep Dive 대시보드 하단에 별도 섹션으로 표시.

실행: python scripts/longtail_goldmine.py
스케줄: 주 1회 (weekly_goldmine.yml)
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── 설정 ───────────────────────────────────────────────

KST = timezone(timedelta(hours=9))

# ㄱ~ㅎ 14자음
JAMO_LIST = list("ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ")

# 네이버 검색 API (환경변수 — 이 레포 전용 _DIVE 키 사용)
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

# 경로
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_KW_PATH = BASE_DIR / "data" / "root_keywords.json"
KNOWN_PRODUCTS_PATH = BASE_DIR / "data" / "known_products.json"
OUTPUT_PATH = BASE_DIR / "data" / "longtail_goldmine.json"

# API 호출 간격 (초)
AUTOCOMPLETE_DELAY = 0.3
BLOG_SEARCH_DELAY = 0.15

# ─── 금맥 카테고리 정의 ────────────────────────────────────

GOLDMINE_CATEGORIES = {
    "①처방약+영양제 병용": {
        "id": "drug_nutrient",
        "icon": "💊",
        "description": "약사 아니면 답 못 하는 병용 질문",
        "patterns": [
            # "혈압약 오메가3", "당뇨약 비타민" 등
            r"(혈압약|당뇨약|고지혈증약|항응고제|혈당약|고혈압약|스타틴|아스피린|와파린|메트포르민|"
            r"항생제|소염제|진통제|수면제|항우울제|갑상선약|위장약|이뇨제|스테로이드|면역억제제)"
            r".*(영양제|비타민|오메가|유산균|마그네슘|철분|칼슘|아연|셀레늄|코엔자임|밀크씨슬|홍삼|인삼)",

            r"(영양제|비타민|오메가|유산균|마그네슘|철분|칼슘|아연|셀레늄|코엔자임|밀크씨슬|홍삼|인삼)"
            r".*(혈압약|당뇨약|고지혈증약|항응고제|혈당약|고혈압약|스타틴|아스피린|와파린|메트포르민|"
            r"항생제|소염제|진통제|수면제|항우울제|갑상선약|위장약|이뇨제|스테로이드|면역억제제)",

            # "같이 먹어도", "병용", "상호작용"
            r".*(같이|병용|상호작용|함께|겸용|복용).*(약|처방|먹)",
            r".*(약|처방).*(같이|병용|상호작용|함께|겸용).*먹",
        ],
    },
    "②건기식 vs 의약품": {
        "id": "supplement_vs_drug",
        "icon": "⚖️",
        "description": "건기식과 의약품 차이를 아는 사람이 없음",
        "patterns": [
            r".*(건기식|건강기능식품|영양제).*(처방|의약품|약국|전문의약품|일반의약품).*차이",
            r".*(처방|의약품).*(건기식|건강기능식품|영양제).*차이",
            r".*(vs|차이|비교|다른점|구별).*(건기식|처방|의약품)",
            r"(밀크씨슬|오메가3|비타민|유산균|루테인|프로바이오틱스).*(처방|의약품|약).*(차이|비교|vs)",
        ],
    },
    "③성분표 분석": {
        "id": "ingredient_analysis",
        "icon": "🔬",
        "description": "약사/연구자만 할 수 있는 성분 해석",
        "patterns": [
            r".*(성분|함량|원료|첨가물|부형제|코팅|제형|원산지|GMP|표시|뒷면|라벨)",
            r".*(몇mg|몇정|얼마나|충분|부족|과다|적정).*(함량|용량|복용량)",
            r".*(추천.*안|안.*추천|비추|주의).*(이유|성분|함량)",
            r".*(진짜|가짜|품질|등급|원료).*(구별|차이|확인|고르는)",
        ],
    },
    "④신약/정책 뉴스 해설": {
        "id": "pharma_news",
        "icon": "📰",
        "description": "속도+전문성 필요한 시사 해설",
        "patterns": [
            r".*(허가|승인|출시|발매|건보|급여|리콜|회수|판매중지|품절|공급|부족)",
            r".*(FDA|식약처|식약청|EMA|임상|3상|승인|허가).*(결과|발표|소식|뉴스)",
            r".*(먹는|경구|주사|패치).*(위고비|마운자로|오젬픽|삭센다|컨투브|젭바운드)",
            r".*(신약|제네릭|바이오시밀러|특허|만료|출시)",
        ],
    },
    "⑤약사 FAQ": {
        "id": "pharmacist_faq",
        "icon": "🗣️",
        "description": "현장 경험 기반 FAQ",
        "patterns": [
            r".*(같이 먹어도|먹어도 되|괜찮|되나요|돼요|될까|되는지)",
            r".*(언제|아침|저녁|공복|식후|식전|자기전).*(먹|복용|섭취)",
            r".*(얼마나|며칠|몇달|기간|오래).*(먹|복용|섭취|효과)",
            r".*(끊어도|중단|멈춰도|안 먹으면|빼먹으면)",
            r".*(임산부|수유|어린이|노인|소아|청소년).*(먹|복용|괜찮|주의)",
            r".*(약국|처방전|없이|구매|살 수|파는|구입)",
        ],
    },
}

# ─── 네이버 자동완성 API ────────────────────────────────────

def fetch_autocomplete(query: str) -> list[str]:
    """네이버 검색창 자동완성 결과를 가져온다."""
    encoded = urllib.parse.quote(query)
    url = f"https://ac.search.naver.com/nx/ac?q={encoded}&con=1&frm=nv&ans=2&t=0"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://search.naver.com/",
    })

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # items[0] = 자동완성 목록 (각 항목의 [0]이 키워드)
            items = data.get("items", [[]])[0]
            return [item[0] for item in items if item and item[0]]
    except Exception as e:
        print(f"  [WARN] 자동완성 실패: {query} → {e}")
        return []


def mine_longtails_for_root(root: str) -> list[dict]:
    """
    뿌리 키워드에 ㄱ~ㅎ를 붙여 자동완성 롱테일을 수집한다.
    방법 2: ABC/ㄱㄴㄷ 기법
    """
    results = []
    seen = set()

    for jamo in JAMO_LIST:
        query = f"{root} {jamo}"
        suggestions = fetch_autocomplete(query)
        time.sleep(AUTOCOMPLETE_DELAY)

        for suggestion in suggestions:
            # 뿌리 자체와 같으면 스킵
            normalized = suggestion.strip()
            if normalized == root or normalized in seen:
                continue
            seen.add(normalized)

            # 뿌리를 포함하는지 확인 (관련성)
            if root not in normalized:
                continue

            # 뿌리를 빼고 나머지를 tail로 추출
            tail = normalized.replace(root, "").strip()
            if not tail:
                continue

            results.append({
                "keyword": normalized,
                "root": root,
                "tail": tail,
                "source_jamo": jamo,
            })

    return results


# ─── 금맥 카테고리 분류 ─────────────────────────────────────

def classify_goldmine(keyword: str) -> list[dict]:
    """키워드를 금맥 카테고리 5개에 대해 매칭한다. 복수 매칭 가능."""
    matched = []
    for cat_name, cat_info in GOLDMINE_CATEGORIES.items():
        for pattern in cat_info["patterns"]:
            if re.search(pattern, keyword):
                matched.append({
                    "category": cat_name,
                    "id": cat_info["id"],
                    "icon": cat_info["icon"],
                })
                break  # 같은 카테고리 내 중복 방지
    return matched


# ─── 네이버 블로그 검색 (전문가 갭 산출용) ──────────────────────

def search_blog_count(query: str) -> int:
    """네이버 블로그 검색 결과 총 건수를 반환한다."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return 0

    encoded = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/blog.json?query={encoded}&display=1&sort=sim"

    req = urllib.request.Request(url, headers={
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    })

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("total", 0)
    except Exception as e:
        print(f"  [WARN] 블로그 검색 실패: {query} → {e}")
        return 0


def calc_expert_gap(keyword: str) -> dict:
    """전문가 갭: 전체 블로그 / (약사 블로그 + 1)"""
    total = search_blog_count(keyword)
    time.sleep(BLOG_SEARCH_DELAY)

    expert = search_blog_count(f"{keyword} 약사")
    time.sleep(BLOG_SEARCH_DELAY)

    if total < 5:
        return {"total": total, "expert": expert, "ratio": 0, "label": "수요없음", "score": 0.5}

    ratio = total / (expert + 1)

    if ratio >= 50:
        return {"total": total, "expert": expert, "ratio": round(ratio, 1), "label": "전문가 전무", "score": 2.0}
    elif ratio >= 30:
        return {"total": total, "expert": expert, "ratio": round(ratio, 1), "label": "전문가 갭 큼", "score": 1.5}
    elif ratio >= 10:
        return {"total": total, "expert": expert, "ratio": round(ratio, 1), "label": "전문가 부족", "score": 1.2}
    elif ratio >= 3:
        return {"total": total, "expert": expert, "ratio": round(ratio, 1), "label": "보통", "score": 1.0}
    else:
        return {"total": total, "expert": expert, "ratio": round(ratio, 1), "label": "전문가 포화", "score": 0.7}


# ─── 약사 가치 점수 ─────────────────────────────────────────

# 의도 키워드 → 약사 전문성 등급
INTENT_KEYWORDS = {
    4: ["부작용", "상호작용", "복용법", "성분", "비교", "함량", "주의사항", "금기", "병용", "과다"],
    3: ["효과", "품절", "대체", "추천", "차이", "선택", "고르는", "좋은", "vs"],
    2: ["후기", "전후", "결과", "경험", "리뷰", "솔직", "실제"],
    1: ["가격", "최저가", "약국", "구매", "할인", "쿠팡", "직구", "편의점"],
}


def calc_intent_score(keyword: str) -> int:
    """키워드에 포함된 의도 키워드로 약사 전문성 점수를 매긴다."""
    best = 1
    for score, words in INTENT_KEYWORDS.items():
        for w in words:
            if w in keyword:
                best = max(best, score)
    return best


def calc_pharma_value(keyword: str, gap: dict) -> float:
    """약사가치 = 의도점수 × 전문가갭배수 × 금맥보너스"""
    intent = calc_intent_score(keyword)
    gap_mult = gap["score"]

    # 금맥 카테고리 매칭 시 보너스
    goldmine_matches = classify_goldmine(keyword)
    goldmine_bonus = 1.0
    if goldmine_matches:
        goldmine_bonus = 1.3  # 금맥 카테고리 매칭 시 30% 보너스

    return round(intent * gap_mult * goldmine_bonus, 2)


# ─── 메인 파이프라인 ────────────────────────────────────────

def load_root_keywords() -> list[dict]:
    """root_keywords.json에서 active/watch 뿌리를 로드한다."""
    if not ROOT_KW_PATH.exists():
        print(f"[ERROR] {ROOT_KW_PATH} 없음. 기본 뿌리 사용.")
        return [{"keyword": kw, "status": "active"} for kw in
                ["마운자로", "위고비", "오메가3", "비타민D", "유산균", "콜라겐",
                 "마그네슘", "밀크씨슬", "알부민", "NMN", "루테인", "글루타치온"]]

    with open(ROOT_KW_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [r for r in data.get("roots", []) if r.get("status") in ("active", "watch")]


def run_pipeline():
    """전체 파이프라인 실행"""
    print("=" * 60)
    print(f"롱테일 금맥 스캐너 시작 — {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}")
    print("=" * 60)

    roots = load_root_keywords()
    print(f"\n뿌리 키워드 {len(roots)}개 로드")

    all_longtails = []
    api_calls = {"autocomplete": 0, "blog_search": 0}

    for i, root_info in enumerate(roots):
        root = root_info["keyword"]
        print(f"\n── [{i+1}/{len(roots)}] {root} ──")

        # Step 1: ㄱ~ㅎ 자동완성 수집
        longtails = mine_longtails_for_root(root)
        api_calls["autocomplete"] += len(JAMO_LIST)
        print(f"  자동완성: {len(longtails)}개 롱테일 발견")

        # Step 2: 각 롱테일에 금맥 카테고리 분류 + 전문가 갭 + 약사가치
        for lt in longtails:
            # 금맥 카테고리
            lt["goldmine"] = classify_goldmine(lt["keyword"])

            # 전문가 갭 (API 절약: 금맥 매칭 or 의도점수 3+ 만 조회)
            intent = calc_intent_score(lt["keyword"])
            lt["intent_score"] = intent

            if lt["goldmine"] or intent >= 3:
                lt["expert_gap"] = calc_expert_gap(lt["keyword"])
                api_calls["blog_search"] += 2
            else:
                lt["expert_gap"] = {"total": 0, "expert": 0, "ratio": 0, "label": "미조회", "score": 1.0}

            # 약사가치
            lt["pharma_value"] = calc_pharma_value(lt["keyword"], lt["expert_gap"])

        all_longtails.extend(longtails)

    # Step 3: 정렬 (약사가치 → 금맥 매칭 → 의도점수 순)
    all_longtails.sort(key=lambda x: (
        -x["pharma_value"],
        -len(x["goldmine"]),
        -x["intent_score"],
    ))

    # Step 4: 요약 통계
    goldmine_count = sum(1 for lt in all_longtails if lt["goldmine"])
    top_categories = {}
    for lt in all_longtails:
        for gm in lt["goldmine"]:
            cat = gm["category"]
            top_categories[cat] = top_categories.get(cat, 0) + 1

    summary = {
        "total_longtails": len(all_longtails),
        "goldmine_matches": goldmine_count,
        "categories": top_categories,
        "top_pharma_value": all_longtails[:10] if all_longtails else [],
        "api_calls": api_calls,
    }

    print(f"\n{'=' * 60}")
    print(f"결과 요약")
    print(f"  전체 롱테일: {len(all_longtails)}개")
    print(f"  금맥 매칭: {goldmine_count}개")
    for cat, cnt in sorted(top_categories.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {cnt}개")
    print(f"  API 호출: 자동완성 {api_calls['autocomplete']}회, 블로그 {api_calls['blog_search']}회")

    # Step 5: 결과 저장
    output = {
        "scan_time": datetime.now(KST).isoformat(),
        "scanner": "longtail_goldmine",
        "version": "1.0",
        "summary": summary,
        "roots_scanned": [r["keyword"] for r in roots],
        "longtails": all_longtails,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n저장 완료: {OUTPUT_PATH}")
    return output


if __name__ == "__main__":
    run_pipeline()
