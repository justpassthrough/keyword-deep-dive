#!/usr/bin/env python3
"""
compete.py — 상위노출 경쟁 분석기

키워드 하나를 넣으면 네이버 블로그 검색 1페이지(상위 10개)를 실제로 긁어서
"내가 실제로 이길 수 있나"를 판단한다.

  - 상위 10개 중 인플루언서가 몇 명인가?
  - 며칠 전 글인가? (최신성 — 다들 최근 글이면 경쟁 활발, 오래된 글뿐이면 기회)
  - 평균 글자수·이미지수는?
  - 제목 패턴은? (숫자/괄호/질문형, 자주 쓰인 단어)

  → 진입난이도: 쉬움/보통/어려움 + "이기려면 최소 X자·이미지 Y장"

dive.py의 약사가치·검색량이 "쓸 가치가 있나"라면, 이 도구는 "이길 수 있나"를 본다.
💎황금 키워드를 여기 통과시켜서 헛심을 거른다.

실행 (로컬 권장 — GitHub Actions 등 데이터센터 IP는 네이버가 차단할 수 있음):
  python scripts/compete.py "위고비 부작용"
  python scripts/compete.py "위고비 부작용" "마운자로 용량"   # 여러 개
  python scripts/compete.py --gold                            # latest.json의 💎황금 키워드 전부
  python scripts/compete.py --gold --limit 5                  # 기회점수 상위 5개만
  python scripts/compete.py "위고비 부작용" --save            # data/compete_latest.json 저장

의존성: requests, beautifulsoup4 (requirements.txt에 이미 포함)
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "compete_latest.json")

SERP_URL = "https://search.naver.com/search.naver"
PC_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://www.naver.com/",
}
MOBILE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

POST_FETCH_DELAY = 0.8    # 글 본문 수집 간격(초)
KEYWORD_DELAY = 1.5       # 키워드 간 간격(초)
TOP_N = 10                # 분석할 상위 글 개수

# 제목 단어 빈도에서 제외할 흔한 단어
TITLE_STOPWORDS = {
    "그리고", "하지만", "있는", "하는", "되는", "위한", "대한",
    "네이버", "블로그", "총정리", "정리", "알아보기", "알아보자",
}


# ══════════════════════════════════════════════════════════
#  1. SERP 수집 — 네이버 블로그 검색 1페이지
# ══════════════════════════════════════════════════════════

def fetch_serp_html(keyword):
    """네이버 블로그 탭 검색 결과 HTML. 차단되면 None."""
    params = {"ssc": "tab.blog.all", "sm": "tab_jum", "query": keyword}
    try:
        r = requests.get(SERP_URL, params=params, headers=PC_HEADERS, timeout=10)
    except Exception as e:
        print(f"  [오류] SERP 요청 실패: {e}")
        return None
    if r.status_code != 200 or "captcha" in r.text.lower():
        print(f"  [차단] SERP status {r.status_code} — 네이버가 이 IP의 검색을 막았을 수 있어요. "
              f"로컬 PC에서 실행하거나 잠시 후 다시 시도하세요.")
        return None
    return r.text


_DATE_ABS = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?")
_DATE_REL = re.compile(r"(\d+)\s*(분|시간|일|주)\s*전")


def parse_date_text(text):
    """'3일 전', '어제', '2026. 5. 1.' → 며칠 전인지(float). 모르면 None."""
    text = (text or "").strip()
    if not text:
        return None
    if "어제" in text:
        return 1.0
    m = _DATE_REL.search(text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return {"분": n / 1440, "시간": n / 24, "일": float(n), "주": n * 7.0}[unit]
    m = _DATE_ABS.search(text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST)
            return max((datetime.now(KST) - dt).days, 0)
        except ValueError:
            return None
    return None


_BLOG_LINK = re.compile(r"https?://(?:m\.)?blog\.naver\.com/([A-Za-z0-9_-]+)/(\d+)")


def parse_serp(html):
    """SERP HTML → 상위 글 목록 [{blog_id, log_no, title, date_text, days_ago, is_influencer}].
    네이버 마크업은 자주 바뀌므로 구조 파싱 실패 시 링크 기반으로 폴백."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    # ── 1차: 구조 기반 (블로그 탭의 결과 단위 블록) ──
    for item in soup.select("div.view_wrap, li.bx div.detail_box, div.total_wrap"):
        # 광고(파워컨텐츠) 제외
        if item.select_one(".link_ad, .ico_ad, .spblog_ad") or "광고" in (
                item.select_one(".user_box") or item).get_text()[:40]:
            continue
        title_el = item.select_one("a.title_link") or item.select_one(".title_area a")
        if not title_el or not title_el.get("href"):
            continue
        m = _BLOG_LINK.search(title_el["href"])
        if not m:
            continue
        key = (m.group(1), m.group(2))
        if key in seen:
            continue
        seen.add(key)
        date_el = item.select_one(".sub_time, .user_info span.sub")
        date_text = date_el.get_text(strip=True) if date_el else ""
        results.append({
            "blog_id": key[0],
            "log_no": key[1],
            "url": f"https://blog.naver.com/{key[0]}/{key[1]}",
            "title": title_el.get_text(" ", strip=True),
            "date_text": date_text,
            "days_ago": parse_date_text(date_text),
            # 작성자 영역에 인플루언서 홈(in.naver.com) 링크가 있으면 인플루언서
            "is_influencer": item.select_one('a[href*="in.naver.com"]') is not None,
        })
        if len(results) >= TOP_N:
            break

    # ── 2차 폴백: 본문 순서대로 blog.naver.com 링크 추출 ──
    if not results:
        for m in _BLOG_LINK.finditer(html):
            key = (m.group(1), m.group(2))
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "blog_id": key[0], "log_no": key[1],
                "url": f"https://blog.naver.com/{key[0]}/{key[1]}",
                "title": "", "date_text": "", "days_ago": None,
                "is_influencer": False,
            })
            if len(results) >= TOP_N:
                break
        if results:
            print("  [참고] SERP 마크업 구조 파싱 실패 → 링크 순서 폴백 사용 "
                  "(인플루언서/날짜 정보 없음)")
    return results


# ══════════════════════════════════════════════════════════
#  2. 글 본문 분석 — 글자수 / 이미지 / 동영상
# ══════════════════════════════════════════════════════════

def analyze_post(blog_id, log_no):
    """모바일 블로그 페이지에서 글자수·이미지수·동영상수 추출. 실패 시 None."""
    url = f"https://m.blog.naver.com/{blog_id}/{log_no}"
    try:
        r = requests.get(url, headers=MOBILE_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # SmartEditor ONE → 구버전 에디터 순으로 본문 컨테이너 탐색
        container = (soup.select_one("div.se-main-container")
                     or soup.select_one("div#viewTypeSelector")
                     or soup.select_one("div.post_ct"))
        if container is None:
            return None
        text = container.get_text(" ", strip=True)
        chars = len(re.sub(r"\s", "", text))
        images = len(container.select("img.se-image-resource"))
        if images == 0:
            # 구버전 에디터: 본문 첨부 이미지(postfiles/blogfiles)만 카운트
            images = sum(1 for img in container.select("img")
                         if any(h in (img.get("src") or "") for h in ("postfiles", "blogfiles")))
        videos = len(container.select(".se-video"))
        return {"chars": chars, "images": images, "videos": videos}
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
#  3. 제목 패턴 분석
# ══════════════════════════════════════════════════════════

def analyze_titles(titles, keyword):
    """상위 글 제목들의 공통 패턴: 숫자/괄호/질문형 비율 + 자주 쓰인 단어."""
    titles = [t for t in titles if t]
    if not titles:
        return None
    kw_tokens = set(keyword.split()) | {keyword.replace(" ", "")}
    counter = Counter()
    for t in titles:
        for tok in re.findall(r"[가-힣A-Za-z0-9]{2,}", t):
            if tok not in kw_tokens and tok not in TITLE_STOPWORDS:
                counter[tok] += 1
    common = [(w, c) for w, c in counter.most_common(8) if c >= 2][:5]
    return {
        "count": len(titles),
        "with_number": sum(1 for t in titles if re.search(r"\d", t)),
        "with_bracket": sum(1 for t in titles if re.search(r"[\[\(【]", t)),
        "question": sum(1 for t in titles if re.search(r"\?|까요|할까|나요", t)),
        "avg_len": round(sum(len(t) for t in titles) / len(titles), 1),
        "common_words": common,
    }


# ══════════════════════════════════════════════════════════
#  4. 진입난이도 산출
# ══════════════════════════════════════════════════════════

def calc_difficulty(serp, posts):
    """0~100 난이도 점수 + 라벨 + '이기려면' 목표치.
    serp: parse_serp 결과, posts: 글별 분석(None 포함 가능) 같은 순서."""
    n = len(serp)
    influencers = sum(1 for s in serp if s["is_influencer"])
    ages = [s["days_ago"] for s in serp if s["days_ago"] is not None]
    fresh7 = sum(1 for a in ages if a <= 7)
    median_age = statistics.median(ages) if ages else None

    char_list = [p["chars"] for p in posts if p]
    img_list = [p["images"] for p in posts if p]
    median_chars = int(statistics.median(char_list)) if char_list else None
    median_images = int(statistics.median(img_list)) if img_list else None

    score = 0.0
    # 인플루언서 비중 (최대 40)
    score += (influencers / max(n, 1)) * 40
    # 글 분량 (최대 20)
    if median_chars is not None:
        if median_chars >= 4000:
            score += 20
        elif median_chars >= 2500:
            score += 15
        elif median_chars >= 1500:
            score += 10
        elif median_chars >= 800:
            score += 6
        else:
            score += 3
    else:
        score += 10  # 정보 없음 → 중립
    # 이미지 물량 (최대 15)
    if median_images is not None:
        if median_images >= 15:
            score += 15
        elif median_images >= 8:
            score += 11
        elif median_images >= 4:
            score += 7
        elif median_images >= 1:
            score += 3
    else:
        score += 7
    # 최신성 — 최근 글이 많을수록 경쟁 활발 (최대 15)
    if fresh7 >= 5:
        score += 15
    elif fresh7 >= 3:
        score += 10
    elif fresh7 >= 1:
        score += 5
    # 상위권이 낡았으면 기회 (감점)
    if median_age is not None:
        if median_age > 365:
            score -= 12
        elif median_age > 180:
            score -= 8
        elif median_age > 90:
            score -= 4

    score = round(min(max(score, 0), 100), 1)
    label = "쉬움" if score < 35 else ("보통" if score < 60 else "어려움")

    # '이기려면' 목표: 상위 글 분량의 1.2배(중앙값 기준)를 100자 단위로 올림
    target_chars = None
    if median_chars:
        target_chars = int(-(-median_chars * 1.2 // 100) * 100)
    target_images = (median_images + 2) if median_images is not None else None

    tips = []
    if influencers >= 5:
        tips.append("상위권 절반 이상이 인플루언서 — 정면승부보다 더 구체적인 롱테일"
                    "(예: '+복용법', '+상호작용')로 비껴가는 게 낫습니다.")
    if median_age is not None and median_age > 180:
        tips.append(f"상위 글 중간 나이가 {int(median_age)}일 — 최신 정보로 쓰면 "
                    "최신성 점수로 밀어낼 여지가 큽니다.")
    if fresh7 >= 5:
        tips.append("일주일 내 글이 절반 이상 — 지금 활발히 경쟁 중인 키워드라 "
                    "발행 즉시 묻힐 수 있습니다.")
    if median_chars is not None and median_chars < 1500:
        tips.append("상위 글들이 짧습니다 — 약사 전문성으로 깊이 있게 쓰면 "
                    "분량만으로도 차별화됩니다.")

    return {
        "score": score,
        "label": label,
        "influencers": influencers,
        "result_count": n,
        "analyzed_posts": len(char_list),
        "fresh7": fresh7,
        "median_age_days": round(median_age, 1) if median_age is not None else None,
        "median_chars": median_chars,
        "min_chars": min(char_list) if char_list else None,
        "max_chars": max(char_list) if char_list else None,
        "median_images": median_images,
        "target_chars": target_chars,
        "target_images": target_images,
        "tips": tips,
    }


# ══════════════════════════════════════════════════════════
#  5. 키워드 1개 전체 분석 + 리포트 출력
# ══════════════════════════════════════════════════════════

def analyze_keyword(keyword):
    """SERP 수집 → 글별 본문 분석 → 난이도 산출. 결과 dict 반환(실패 시 None)."""
    print(f"\n{'═' * 58}")
    print(f"🔍 \"{keyword}\" 상위노출 경쟁 분석")
    print("═" * 58)

    html = fetch_serp_html(keyword)
    if html is None:
        return None
    serp = parse_serp(html)
    if not serp:
        print("  [오류] 검색 결과를 못 읽었어요. 네이버 마크업이 바뀌었을 수 있습니다.")
        return None

    posts = []
    for s in serp:
        posts.append(analyze_post(s["blog_id"], s["log_no"]))
        time.sleep(POST_FETCH_DELAY)

    diff = calc_difficulty(serp, posts)
    title_pat = analyze_titles([s["title"] for s in serp], keyword)

    # ── 리포트 ──
    print(f"\n  진입난이도: {diff['label']}  (점수 {diff['score']}/100)")
    print(f"  상위 {diff['result_count']}개 중 본문 분석 성공 {diff['analyzed_posts']}개")
    print(f"  인플루언서: {diff['influencers']}/{diff['result_count']}")
    if diff["median_age_days"] is not None:
        print(f"  최신성: 7일 이내 글 {diff['fresh7']}개 · 중간 나이 {diff['median_age_days']}일")
    if diff["median_chars"] is not None:
        print(f"  글자수: 중앙값 {diff['median_chars']:,}자 "
              f"(최소 {diff['min_chars']:,} / 최대 {diff['max_chars']:,})")
    if diff["median_images"] is not None:
        print(f"  이미지: 중앙값 {diff['median_images']}장")
    if title_pat:
        print(f"  제목 패턴: 숫자 {title_pat['with_number']}/{title_pat['count']} · "
              f"괄호 {title_pat['with_bracket']}/{title_pat['count']} · "
              f"질문형 {title_pat['question']}/{title_pat['count']} · "
              f"평균 {title_pat['avg_len']}자")
        if title_pat["common_words"]:
            words = ", ".join(f"{w}({c})" for w, c in title_pat["common_words"])
            print(f"  자주 쓰인 제목 단어: {words}")

    print(f"\n  {'#':>2} {'날짜':<8} {'인플':<4} {'글자수':>7} {'이미지':>4}  제목")
    for i, (s, p) in enumerate(zip(serp, posts), 1):
        date = (s["date_text"] or "-")[:8]
        infl = "✔" if s["is_influencer"] else "·"
        chars = f"{p['chars']:,}" if p else "-"
        imgs = str(p["images"]) if p else "-"
        title = (s["title"] or s["url"])[:34]
        print(f"  {i:>2} {date:<8} {infl:<4} {chars:>7} {imgs:>4}  {title}")

    if diff["target_chars"]:
        print(f"\n  → 이기려면: 최소 {diff['target_chars']:,}자"
              + (f" + 이미지 {diff['target_images']}장" if diff["target_images"] else ""))
    for tip in diff["tips"]:
        print(f"  → 팁: {tip}")

    return {
        "keyword": keyword,
        "analyzed_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "difficulty": diff,
        "title_pattern": title_pat,
        "top_posts": [
            {**{k: s[k] for k in ("url", "title", "date_text", "days_ago", "is_influencer")},
             **(p or {})}
            for s, p in zip(serp, posts)
        ],
    }


# ══════════════════════════════════════════════════════════
#  6. 💎황금 키워드 불러오기 (--gold)
# ══════════════════════════════════════════════════════════

def load_gold_keywords(limit):
    """latest.json에서 💎황금 라벨이 붙은 복합키워드를 기회점수순으로 추출."""
    if not os.path.exists(LATEST_PATH):
        print(f"latest.json이 없습니다: {LATEST_PATH}")
        return []
    with open(LATEST_PATH, encoding="utf-8") as f:
        data = json.load(f)
    gold = {}
    for r in data.get("roots", []):
        for c in r.get("compounds", []):
            label = c.get("opportunity_label") or ""
            if label.startswith("💎") or "💎황금" in (c.get("labels") or []):
                kw = c["keyword"]
                score = c.get("opportunity_score") or 0
                if kw not in gold or score > gold[kw]:
                    gold[kw] = score
    ranked = sorted(gold, key=gold.get, reverse=True)
    return ranked[:limit] if limit else ranked


def main():
    ap = argparse.ArgumentParser(description="네이버 블로그 상위노출 경쟁 분석기")
    ap.add_argument("keywords", nargs="*", help="분석할 키워드 (여러 개 가능)")
    ap.add_argument("--gold", action="store_true",
                    help="latest.json의 💎황금 키워드를 자동으로 분석")
    ap.add_argument("--limit", type=int, default=10,
                    help="--gold 사용 시 기회점수 상위 N개만 (기본 10)")
    ap.add_argument("--save", action="store_true",
                    help=f"결과를 data/compete_latest.json에 저장")
    args = ap.parse_args()

    keywords = list(args.keywords)
    if args.gold:
        gold = load_gold_keywords(args.limit)
        if gold:
            print(f"💎황금 키워드 {len(gold)}개 분석: {', '.join(gold)}")
        keywords += [k for k in gold if k not in keywords]
    if not keywords:
        ap.print_help()
        sys.exit(1)

    results = []
    for i, kw in enumerate(keywords):
        res = analyze_keyword(kw)
        if res:
            results.append(res)
        if i < len(keywords) - 1:
            time.sleep(KEYWORD_DELAY)

    if results:
        print(f"\n{'═' * 58}")
        print("📊 요약 (쉬운 순)")
        for r in sorted(results, key=lambda x: x["difficulty"]["score"]):
            d = r["difficulty"]
            print(f"  [{d['label']}] {d['score']:>5}/100  {r['keyword']}"
                  f"  (인플루언서 {d['influencers']}/{d['result_count']})")

    if args.save and results:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump({"analyzed_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                       "results": results}, f, ensure_ascii=False, indent=2)
        print(f"\n저장됨: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
