#!/usr/bin/env python3
"""
키워드 딥다이브 스캐너 — 뿌리 자동 발굴
4가지 소스에서 새로운 뿌리 키워드 후보를 발견하고 검증.
"""

import json
import os
import re
import time
from collections import Counter
from datetime import datetime

import requests

# ── 환경변수 ──────────────────────────────────────────────
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
NAVER_HEADERS = {
    "X-Naver-Client-Id": NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 카테고리별 시드 쿼리 (소스 B)
CATEGORY_SEEDS = [
    "비만치료제 신약",
    "영양제 인기 순위",
    "약국 인기 의약품",
    "건강기능식품 트렌드",
    "탈모치료제 추천",
    "항노화 영양제",
    "다이어트 보조제",
    "간건강 영양제",
    "눈건강 영양제",
    "관절 영양제",
]


# ══════════════════════════════════════════════════════════
#  데이터 로드/저장
# ══════════════════════════════════════════════════════════

def load_roots():
    path = os.path.join(DATA_DIR, "root_keywords.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_roots(data):
    path = os.path.join(DATA_DIR, "root_keywords.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_known_products():
    path = os.path.join(DATA_DIR, "known_products.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data["products"])


# ══════════════════════════════════════════════════════════
#  네이버 API
# ══════════════════════════════════════════════════════════

def _naver_search(endpoint, params, timeout=10):
    if not NAVER_CLIENT_ID:
        return {"items": [], "total": 0}
    url = f"https://openapi.naver.com/v1/search/{endpoint}.json"
    try:
        r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            time.sleep(5)
            r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        return {"items": [], "total": 0}
    except Exception:
        return {"items": [], "total": 0}


def datalab_has_volume(keyword):
    """DataLab에서 검색량이 있는지 확인."""
    if not NAVER_CLIENT_ID:
        return False
    end_date = datetime.now().strftime("%Y-%m-%d")
    from datetime import timedelta
    start_date = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
    url = "https://openapi.naver.com/v1/datalab/search"
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}],
    }
    headers = {**NAVER_HEADERS, "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            if results and results[0].get("data"):
                ratios = [d["ratio"] for d in results[0]["data"]]
                return sum(ratios) > 0
        if r.status_code == 429:
            time.sleep(5)
            r = requests.post(url, headers=headers, json=body, timeout=10)
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if results and results[0].get("data"):
                    ratios = [d["ratio"] for d in results[0]["data"]]
                    return sum(ratios) > 0
        return False
    except Exception:
        return False


def get_blog_titles(query, count=50):
    """블로그 검색 제목 수집."""
    data = _naver_search("blog", {"query": query, "display": count, "sort": "date"})
    titles = []
    for item in data.get("items", []):
        title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        titles.append(title)
    return titles


def get_news_titles(query, count=50):
    """뉴스 검색 제목 수집."""
    data = _naver_search("news", {"query": query, "display": count, "sort": "date"})
    titles = []
    for item in data.get("items", []):
        title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        titles.append(title)
    return titles


def count_compound_keywords(keyword):
    """블로그에서 복합키워드 종류 수 카운트."""
    titles = get_blog_titles(keyword, 50)
    time.sleep(0.15)
    compounds = set()
    for title in titles:
        words = title.split()
        cleaned = [re.sub(r"[^가-힣a-zA-Z0-9]", "", w) for w in words]
        cleaned = [w for w in cleaned if w and w != keyword and len(w) >= 2]
        for w in cleaned:
            compounds.add(f"{keyword} {w}")
    return len(compounds)


# ══════════════════════════════════════════════════════════
#  소스 A: 이웃 발견 (active 뿌리 블로그에서 known_products 매칭)
# ══════════════════════════════════════════════════════════

def discover_neighbors(active_roots, known_products, existing_keywords):
    """active 뿌리 블로그 제목에서 다른 제품명 발견."""
    print("\n[소스 A] 이웃 발견 (블로그에서 제품명 추출)")
    candidates = Counter()
    unidentified = Counter()

    for root_info in active_roots:
        root = root_info["keyword"]
        titles = get_blog_titles(root, 50)
        time.sleep(0.15)

        for title in titles:
            words = title.split()
            for w in words:
                cleaned = re.sub(r"[^가-힣a-zA-Z0-9]", "", w)
                if not cleaned or cleaned == root or len(cleaned) < 2:
                    continue
                if cleaned in known_products and cleaned not in existing_keywords:
                    candidates[cleaned] += 1
                elif re.match(r"^[가-힣]{2,}$", cleaned) or re.match(r"^[A-Za-z0-9]{2,}$", cleaned):
                    if cleaned not in existing_keywords and cleaned not in known_products:
                        unidentified[cleaned] += 1

    found = [(kw, cnt) for kw, cnt in candidates.most_common(10) if cnt >= 3]
    unid = [(kw, cnt) for kw, cnt in unidentified.most_common(20) if cnt >= 5]
    print(f"  후보 {len(found)}개, 미확인 {len(unid)}개")
    return found, unid


# ══════════════════════════════════════════════════════════
#  소스 B: 카테고리 시드 쿼리
# ══════════════════════════════════════════════════════════

def discover_category_seeds(known_products, existing_keywords):
    """카테고리별 시드 쿼리에서 제품명 추출."""
    print("\n[소스 B] 카테고리 시드 쿼리")
    candidates = Counter()

    for seed in CATEGORY_SEEDS:
        titles = get_blog_titles(seed, 30)
        time.sleep(0.15)

        for title in titles:
            words = title.split()
            for w in words:
                cleaned = re.sub(r"[^가-힣a-zA-Z0-9]", "", w)
                if cleaned in known_products and cleaned not in existing_keywords:
                    candidates[cleaned] += 1

    found = [(kw, cnt) for kw, cnt in candidates.most_common(10) if cnt >= 2]
    print(f"  후보 {len(found)}개")
    return found


# ══════════════════════════════════════════════════════════
#  소스 C: 약업계 뉴스
# ══════════════════════════════════════════════════════════

NEWS_QUERIES = ["약국 신제품", "의약품 허가", "건강기능식품 출시", "비만치료제"]

def discover_pharma_news(known_products, existing_keywords):
    """약업계 뉴스에서 제품명 추출."""
    print("\n[소스 C] 약업계 뉴스")
    candidates = Counter()

    for query in NEWS_QUERIES:
        titles = get_news_titles(query, 30)
        time.sleep(0.15)

        for title in titles:
            words = title.split()
            for w in words:
                cleaned = re.sub(r"[^가-힣a-zA-Z0-9]", "", w)
                if cleaned in known_products and cleaned not in existing_keywords:
                    candidates[cleaned] += 1

    found = [(kw, cnt) for kw, cnt in candidates.most_common(10) if cnt >= 2]
    print(f"  후보 {len(found)}개")
    return found


# ══════════════════════════════════════════════════════════
#  소스 D: health-trend-scanner 연동
# ══════════════════════════════════════════════════════════

TREND_SCANNER_URL = "https://raw.githubusercontent.com/justpassthrough/health-trend-scanner/main/data/latest.json"

def discover_from_trend_scanner(known_products, existing_keywords):
    """health-trend-scanner latest.json에서 제품명 추출."""
    print("\n[소스 D] 트렌드 스캐너 연동")
    candidates = []

    try:
        r = requests.get(TREND_SCANNER_URL, timeout=15)
        if r.status_code != 200:
            print("  트렌드 스캐너 데이터 접근 실패")
            return candidates
        data = r.json()
    except Exception as e:
        print(f"  트렌드 스캐너 접근 오류: {e}")
        return candidates

    topics = data.get("topics", [])
    for topic in topics:
        kw = topic.get("keyword", "")
        if kw in known_products and kw not in existing_keywords:
            score = topic.get("score", 0)
            candidates.append((kw, score))

    # score 높은 순 정렬
    candidates.sort(key=lambda x: x[1], reverse=True)
    print(f"  후보 {len(candidates)}개")
    return candidates[:5]


# ══════════════════════════════════════════════════════════
#  후보 검증
# ══════════════════════════════════════════════════════════

def validate_candidate(keyword):
    """DataLab 검색량 있음 + 복합키워드 5종 이상 → watch 등록 가능."""
    has_vol = datalab_has_volume(keyword)
    time.sleep(1.0)
    if not has_vol:
        return False, "DataLab 검색량 없음"

    compound_count = count_compound_keywords(keyword)
    time.sleep(0.15)
    if compound_count < 5:
        return False, f"복합키워드 {compound_count}종 (5종 미만)"

    return True, f"검증 통과 (복합키워드 {compound_count}종)"


# ══════════════════════════════════════════════════════════
#  Dormant 관리
# ══════════════════════════════════════════════════════════

def check_dormant_roots(root_data):
    """dormant 뿌리 중 8주 이상 → archived 전환."""
    changed = False
    for root_info in root_data["roots"]:
        if root_info["status"] == "dormant":
            if root_info.get("consecutive_dormant_weeks", 0) >= 8:
                root_info["status"] = "archived"
                changed = True
                print(f"  [archived] {root_info['keyword']} (8주 이상 dormant)")
            else:
                # DataLab 검색량 확인 → 급등 시 active 복귀
                has_vol = datalab_has_volume(root_info["keyword"])
                time.sleep(1.0)
                if has_vol:
                    print(f"  [체크] {root_info['keyword']} — DataLab 검색량 존재 (다음 dive에서 평가)")
    return root_data, changed


# ══════════════════════════════════════════════════════════
#  카테고리 추정
# ══════════════════════════════════════════════════════════

CATEGORY_KEYWORDS = {
    "비만치료제": ["비만", "다이어트", "체중", "감량", "GLP", "식욕"],
    "영양제": ["영양제", "건강기능식품", "비타민", "미네랄", "보충제", "항산화"],
    "일반의약품": ["약국", "처방", "의약품", "OTC", "일반약"],
    "탈모치료": ["탈모", "모발", "두피"],
    "피부관리": ["피부", "미백", "주름", "콜라겐"],
}

def guess_category(keyword, titles=None):
    """제목 맥락에서 카테고리 추정."""
    if titles:
        text = " ".join(titles[:20])
    else:
        text = ""
        blog_titles = get_blog_titles(keyword, 10)
        text = " ".join(blog_titles)
        time.sleep(0.15)

    for cat, words in CATEGORY_KEYWORDS.items():
        if any(w in text for w in words):
            return cat
    return "기타"


# ══════════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("뿌리 자동 발굴 시작")
    print("=" * 60)

    if not NAVER_CLIENT_ID:
        print("[경고] NAVER_CLIENT_ID 환경변수가 없습니다. 빈 결과로 진행합니다.")

    root_data = load_roots()
    known_products = load_known_products()
    existing_keywords = {r["keyword"] for r in root_data["roots"]}
    active_roots = [r for r in root_data["roots"] if r["status"] in ("active", "watch")]

    all_candidates = {}  # keyword → count (중복 소스에서 발견 시 합산)

    # 소스 A: 이웃 발견
    neighbors, unidentified = discover_neighbors(active_roots, known_products, existing_keywords)
    for kw, cnt in neighbors:
        all_candidates[kw] = all_candidates.get(kw, 0) + cnt

    # 소스 B: 카테고리 시드
    seeds = discover_category_seeds(known_products, existing_keywords)
    for kw, cnt in seeds:
        all_candidates[kw] = all_candidates.get(kw, 0) + cnt

    # 소스 C: 약업계 뉴스
    news = discover_pharma_news(known_products, existing_keywords)
    for kw, cnt in news:
        all_candidates[kw] = all_candidates.get(kw, 0) + cnt

    # 소스 D: 트렌드 스캐너
    trend = discover_from_trend_scanner(known_products, existing_keywords)
    for kw, score in trend:
        all_candidates[kw] = all_candidates.get(kw, 0) + 3  # 트렌드 스캐너 가중치

    # 후보 검증 및 등록
    sorted_candidates = sorted(all_candidates.items(), key=lambda x: x[1], reverse=True)
    today = datetime.now().strftime("%Y-%m-%d")
    new_count = 0

    print(f"\n── 후보 검증 ({len(sorted_candidates)}개) ──")
    for kw, cnt in sorted_candidates[:15]:  # 상위 15개만 검증 (API 절약)
        print(f"  {kw} (빈도 {cnt}): ", end="")
        valid, reason = validate_candidate(kw)
        print(reason)

        if valid:
            category = guess_category(kw)
            root_data["roots"].append({
                "keyword": kw,
                "category": category,
                "status": "watch",
                "source": "auto",
                "parent": None,
                "added": today,
                "last_active": today,
                "consecutive_dormant_weeks": 0,
            })
            existing_keywords.add(kw)
            new_count += 1
            print(f"    → watch 등록 ({category})")

    # Dormant 관리
    print("\n── Dormant 관리 ──")
    root_data, dormant_changed = check_dormant_roots(root_data)

    # 저장
    if new_count > 0 or dormant_changed:
        save_roots(root_data)
        print(f"\n새 watch 뿌리 {new_count}개 등록, root_keywords.json 저장 완료")
    else:
        print("\n변경 사항 없음")

    print("\n" + "=" * 60)
    print("뿌리 자동 발굴 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
