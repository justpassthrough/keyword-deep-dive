#!/usr/bin/env python3
"""
키워드 딥다이브 스캐너 — 메인 분석 스크립트
뿌리 키워드에서 복합키워드를 자동 확장하고 약사 블로그 글감 가치를 판단.
"""

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta

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
HISTORY_DIR = os.path.join(DATA_DIR, "history")

# ── 약사 가치 판단 상수 ──────────────────────────────────
HIGH_PHARMA = ["부작용", "상호작용", "같이", "복용", "금기", "용량", "처방",
               "성분", "원리", "차이", "비교", "위험", "주의"]
MID_PHARMA = ["효과", "감량", "다이어트", "흡수", "품절", "품귀", "대체",
              "추천", "진짜", "가짜", "논란"]
LOW_PHARMA = ["후기", "경험", "기간", "결과", "전후"]
WEAK_PHARMA = ["가격", "최저가", "병원", "약국", "할인", "구매", "택배", "성지"]

# ── SEO 스팸 필터용 지역명 ────────────────────────────────
REGIONS = {
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "수원", "성남", "고양", "용인", "창원", "통영", "제주", "서귀포",
    "김해", "거제", "양산", "밀양", "사천", "진주", "포항", "경주",
    "안동", "영주", "상주", "문경", "김천", "구미", "영천", "마산",
    "전주", "익산", "군산", "목포", "여수", "순천", "천안", "아산", "청주",
    "강남", "홍대", "신촌", "잠실", "판교", "분당", "일산", "동탄",
    "해운대", "서면", "남포동", "동성로", "충장로", "둔산동",
}

# ── 불용어 ────────────────────────────────────────────────
STOPWORDS = {
    "그리고", "하지만", "그래서", "그런데", "또한", "이런", "저런",
    "있는", "하는", "되는", "않는", "없는", "같은", "많은", "좋은",
    "진짜", "정말", "완전", "역대급", "대박", "최고", "강추", "필수",
    "네이버", "블로그", "포스팅", "리뷰", "후기", "추천", "소개",
    "오늘", "지금", "최근", "요즘", "이번", "올해", "작년",
    "나는", "제가", "우리", "저희", "여러분",
}

# ── 미확인 후보에서 제외할 일반 단어 ─────────────────────
# 의도 키워드 + 카테고리어 + 마케팅 수식어 + 일반 의약 용어
# (제품/성분 고유명사가 아닌 것들)
_INTENT_WORDS = set(HIGH_PHARMA + MID_PHARMA + LOW_PHARMA + WEAK_PHARMA)
CANDIDATE_EXCLUDE = _INTENT_WORDS | {
    # 카테고리/분류어
    "비만약", "비만", "영양제", "건기식", "건강기능식품", "일반의약품", "전문의약품",
    "의약품", "처방약", "약품", "보충제", "건강식품", "기능식품", "식품",
    "치료제", "치료약", "주사제", "주사", "경구약", "내복약", "외용약",
    "다이어트약", "살빠지는약", "식욕억제제",
    # 마케팅/수식어
    "프리미엄", "골드", "플러스", "플래티넘", "스페셜", "울트라",
    "마시는", "씹어먹는", "고함량", "저용량", "고용량", "순수", "천연",
    "국산", "수입", "직구", "정품", "리뉴얼", "신제품",
    # 유통/기업 일반어
    "출시", "발매", "판매", "입고", "재입고", "예약", "예판",
    "제약", "제약사", "바이오", "헬스케어", "팜",
    # 일반 동사/형용사
    "먹는", "먹고", "먹으면", "드시는", "섭취", "복용법",
    "좋은", "나쁜", "좋다", "좋아요", "싫어요",
    "안전한", "위험한", "중요한", "필요한", "인기",
    # 단위/수량
    "정도", "이상", "이하", "미만", "이내", "하루", "매일",
    "한달", "개월", "시간", "분량", "용법",
    # 일반 의약/건강 용어
    "비만치료제", "비만치료", "항노화", "역노화", "노화방지",
    "효능", "효과적", "물질", "성분명", "앰플", "캡슐", "정제", "시럽",
    "융복합", "임상", "임상시험", "논문", "연구", "연구결과",
    # 기업/유통 고유명 (제품이 아닌 회사/매장명)
    "대원제약", "종근당", "유한양행", "동아제약", "한미약품", "광동제약",
    "일동제약", "녹십자", "보령제약", "JW중외", "대웅제약",
    "이랜드", "풀무원", "킴스클럽", "올리브영", "다이소",
    "CJ", "GC녹십자", "HK이노엔",
    # 기타 노이즈
    "AI", "김석훈", "박수지", "오한진",
    # 일반 명사/동사 (제품명 아닌 것)
    "건강", "이유", "진행", "시작", "방법", "종류", "크림", "필름",
    "런칭", "백세", "시누이", "미나", "경북대", "홈앤쇼핑",
    "단백질", "아미노산", "지방", "탄수화물", "칼로리", "혈당",
    "체중", "체지방", "근육", "면역", "면역력", "피로", "간수치",
}


# ══════════════════════════════════════════════════════════
#  데이터 로드
# ══════════════════════════════════════════════════════════

def load_roots():
    """root_keywords.json에서 active + watch 뿌리만 로드."""
    path = os.path.join(DATA_DIR, "root_keywords.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [r for r in data["roots"] if r["status"] in ("active", "watch")]


def load_all_roots():
    """root_keywords.json 전체 로드 (저장용)."""
    path = os.path.join(DATA_DIR, "root_keywords.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_roots(data):
    """root_keywords.json 저장."""
    path = os.path.join(DATA_DIR, "root_keywords.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_known_products():
    """known_products.json 로드."""
    path = os.path.join(DATA_DIR, "known_products.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data["products"])


def load_previous():
    """이전 latest.json 로드 (추이 비교용)."""
    path = os.path.join(DATA_DIR, "latest.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
#  네이버 API 호출
# ══════════════════════════════════════════════════════════

def _naver_search(endpoint, params, timeout=10):
    """네이버 검색 API 공통 호출."""
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


def fetch_blog_titles(root, count=100):
    """블로그 검색에서 제목 수집 (50개씩 2페이지)."""
    titles = []
    for start in [1, 51]:
        display = min(50, count - len(titles))
        if display <= 0:
            break
        data = _naver_search("blog", {
            "query": root, "display": display, "start": start, "sort": "date"
        })
        for item in data.get("items", []):
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            titles.append(title)
        time.sleep(0.15)
    return titles


def fetch_news_titles(root, count=100):
    """뉴스 검색에서 제목 수집 (50개씩 2페이지)."""
    titles = []
    for start in [1, 51]:
        display = min(50, count - len(titles))
        if display <= 0:
            break
        data = _naver_search("news", {
            "query": root, "display": display, "start": start, "sort": "date"
        })
        for item in data.get("items", []):
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            titles.append(title)
        time.sleep(0.15)
    return titles


def get_blog_total_count(query):
    """블로그 검색 totalCount 조회."""
    data = _naver_search("blog", {"query": query, "display": 1})
    return data.get("total", 0)


def datalab_search(keyword_groups, start_date=None, end_date=None):
    """DataLab 검색량 조회. keyword_groups: [{"groupName": k, "keywords": [k]}, ...]"""
    if not NAVER_CLIENT_ID:
        return None
    if not start_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
    url = "https://openapi.naver.com/v1/datalab/search"
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": keyword_groups,
    }
    headers = {**NAVER_HEADERS, "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            time.sleep(5)
            r = requests.post(url, headers=headers, json=body, timeout=10)
            if r.status_code == 200:
                return r.json()
        return None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
#  복합키워드 마이닝
# ══════════════════════════════════════════════════════════

def _clean_word(w):
    """단어 정제: HTML 태그, 특수문자 제거."""
    w = re.sub(r"<[^>]+>", "", w)
    w = re.sub(r"[^가-힣a-zA-Z0-9]", "", w)
    return w.strip()


def extract_bigrams(titles, root):
    """제목에서 '뿌리+X' / 'X+뿌리' 바이그램 추출."""
    counter = Counter()
    for title in titles:
        words = title.split()
        words = [_clean_word(w) for w in words if _clean_word(w)]
        for i, w in enumerate(words):
            if root in w:
                # 뒤따르는 단어
                if i + 1 < len(words):
                    nxt = words[i + 1]
                    if nxt not in STOPWORDS and len(nxt) >= 2:
                        compound = f"{root} {nxt}"
                        counter[compound] += 1
                # 앞선 단어
                if i - 1 >= 0:
                    prev = words[i - 1]
                    if prev not in STOPWORDS and len(prev) >= 2:
                        compound = f"{prev} {root}"
                        counter[compound] += 1
    return counter


def extract_cooccurrence(titles, root):
    """제목에서 뿌리와 동시에 등장하는 주요 단어 추출."""
    counter = Counter()
    for title in titles:
        if root not in title:
            continue
        words = title.split()
        words = [_clean_word(w) for w in words if _clean_word(w)]
        for w in words:
            if w == root or root in w or w in root:
                continue
            if w in STOPWORDS or len(w) < 2:
                continue
            counter[w] += 1
    return counter


def filter_seo_spam(titles):
    """SEO 스팸 템플릿 감지: 지역명/숫자 마스킹 후 동일 패턴 3건 이상 → 1건."""
    def mask(title):
        t = title
        for region in REGIONS:
            t = t.replace(region, "[지역]")
        t = re.sub(r"\d+", "[N]", t)
        return t

    pattern_groups = {}
    for title in titles:
        masked = mask(title)
        pattern_groups.setdefault(masked, []).append(title)

    cleaned = []
    for masked, group in pattern_groups.items():
        if len(group) >= 3:
            cleaned.append(group[0])  # 스팸 그룹 → 대표 1건만
        else:
            cleaned.extend(group)
    return cleaned


def mine_compound_keywords(root):
    """블로그+뉴스 제목에서 복합키워드 추출."""
    blog_titles = fetch_blog_titles(root, 100)
    news_titles = fetch_news_titles(root, 100)
    all_titles = filter_seo_spam(blog_titles + news_titles)

    bigrams = extract_bigrams(all_titles, root)
    cooccurrence = extract_cooccurrence(all_titles, root)

    # 바이그램 기반 복합키워드
    compounds = set()
    for kw, cnt in bigrams.most_common(30):
        if cnt >= 2:
            compounds.add(kw)

    # 동시 출현 단어 → "뿌리 X" 형태로 추가
    for word, cnt in cooccurrence.most_common(20):
        if cnt >= 3:
            compound = f"{root} {word}"
            compounds.add(compound)

    return list(compounds), all_titles, news_titles


# ══════════════════════════════════════════════════════════
#  DataLab 비교 + 롱테일 판단
# ══════════════════════════════════════════════════════════

def compare_datalab(root, compounds):
    """DataLab으로 검색량 비교. 5개씩 배치, 1초 간격."""
    results = {}
    batches = [compounds[i:i+4] for i in range(0, len(compounds), 4)]

    for batch in batches:
        keyword_groups = [{"groupName": root, "keywords": [root]}]
        for kw in batch:
            keyword_groups.append({"groupName": kw, "keywords": [kw]})

        data = datalab_search(keyword_groups)
        time.sleep(1.0)  # DataLab 429 방지

        if not data or "results" not in data:
            for kw in batch:
                results[kw] = {"volume": None, "change_rate": None, "trend_rate": None, "type": "longtail"}
            continue

        root_avg = _calc_recent_avg(data["results"][0]) if data["results"] else 0

        for result in data["results"][1:]:
            kw = result["title"]
            avg = _calc_recent_avg(result)
            change_short = _calc_change_rate_short(result)
            change_trend = _calc_change_rate_trend(result)
            results[kw] = {
                "volume": round(avg, 1) if avg else None,
                "change_rate": round(change_short, 1) if change_short is not None else None,
                "trend_rate": round(change_trend, 1) if change_trend is not None else None,
                "type": "datalab" if avg and avg > 0 else "longtail",
            }

        # DataLab에 데이터 없는 키워드
        found_names = {r["title"] for r in data["results"]}
        for kw in batch:
            if kw not in found_names and kw not in results:
                results[kw] = {"volume": None, "change_rate": None, "trend_rate": None, "type": "longtail"}

    return results


def _calc_recent_avg(result):
    """최근 7일 평균 검색 비율."""
    ratios = [d["ratio"] for d in result.get("data", [])]
    if not ratios:
        return 0
    recent = ratios[-7:]
    return sum(recent) / len(recent) if recent else 0


def _calc_change_rate_short(result):
    """단기 변화율: (최근3일 - 직전3일) / 직전3일 × 100. 빠른 급등 감지용."""
    ratios = [d["ratio"] for d in result.get("data", [])]
    if len(ratios) < 6:
        return None
    prev = ratios[-6:-3]
    recent = ratios[-3:]
    avg_prev = sum(prev) / len(prev) if prev else 0
    avg_recent = sum(recent) / len(recent) if recent else 0
    if avg_prev == 0:
        return 100.0 if avg_recent > 0 else 0.0
    return (avg_recent - avg_prev) / avg_prev * 100


def _calc_change_rate_trend(result):
    """추세 변화율: (최근7일 - 이전7일) / 이전7일 × 100. 지속성 판단용."""
    ratios = [d["ratio"] for d in result.get("data", [])]
    if len(ratios) < 14:
        return None
    prev = ratios[-14:-7]
    recent = ratios[-7:]
    avg_prev = sum(prev) / len(prev) if prev else 0
    avg_recent = sum(recent) / len(recent) if recent else 0
    if avg_prev == 0:
        return 100.0 if avg_recent > 0 else 0.0
    return (avg_recent - avg_prev) / avg_prev * 100


def evaluate_longtail(compound):
    """DataLab 없는 키워드 → 블로그 totalCount로 대체 판단."""
    total = get_blog_total_count(compound)
    time.sleep(0.15)
    return {"blog_count": total, "has_demand": total >= 50}


# ══════════════════════════════════════════════════════════
#  브릿지 키워드 감지
# ══════════════════════════════════════════════════════════

def detect_bridge(compound, active_roots):
    """복합키워드가 다른 active 뿌리를 포함하면 브릿지."""
    words = compound.split()
    for root_info in active_roots:
        rk = root_info["keyword"]
        if rk in words and rk != words[0]:
            return True, rk
    return False, None


# ══════════════════════════════════════════════════════════
#  전문가 갭 + 약사 가치
# ══════════════════════════════════════════════════════════

def calc_expert_gap(compound):
    """전문가 갭: 전체 블로그 vs '약사' 포함 블로그."""
    total = get_blog_total_count(compound)
    time.sleep(0.15)
    expert = get_blog_total_count(f"{compound} 약사")
    time.sleep(0.15)
    if total < 5:
        return {"total": total, "expert": expert, "ratio": 0, "label": "수요 없음"}
    ratio = total / (expert + 1)
    if ratio >= 30:
        label = "전문가 갭 큼"
    elif ratio >= 10:
        label = "전문가 부족"
    elif ratio >= 3:
        label = "보통"
    else:
        label = "전문가 포화"
    return {"total": total, "expert": expert, "ratio": round(ratio, 1), "label": label}


def _classify_intent(compound):
    """복합키워드의 의도 분류 + 점수."""
    for word in HIGH_PHARMA:
        if word in compound:
            return _intent_label(word), 4
    for word in MID_PHARMA:
        if word in compound:
            return _intent_label(word), 3
    for word in LOW_PHARMA:
        if word in compound:
            return _intent_label(word), 2
    for word in WEAK_PHARMA:
        if word in compound:
            return _intent_label(word), 1
    return "일반", 2


def _intent_label(word):
    """의도 키워드 → 의도 카테고리."""
    mapping = {
        "부작용": "안전성", "상호작용": "안전성", "금기": "안전성", "위험": "안전성", "주의": "안전성",
        "같이": "복용법", "복용": "복용법", "용량": "복용법",
        "처방": "전문지식", "성분": "전문지식", "원리": "전문지식",
        "차이": "비교", "비교": "비교",
        "효과": "효능", "감량": "효능", "다이어트": "효능", "흡수": "효능",
        "품절": "공급", "품귀": "공급", "대체": "공급",
        "추천": "선택", "진짜": "진위", "가짜": "진위", "논란": "진위",
        "후기": "경험담", "경험": "경험담", "기간": "경험담", "결과": "경험담", "전후": "경험담",
        "가격": "구매", "최저가": "구매", "할인": "구매", "구매": "구매", "택배": "구매",
        "병원": "접근성", "약국": "접근성", "성지": "접근성",
    }
    return mapping.get(word, "일반")


def calc_pharma_value(compound, intent_score, expert_gap, change_rate):
    """약사 가치 = 의도점수 × 전문가갭배수 × 변화율보너스."""
    # 전문가 갭 배수
    ratio = expert_gap.get("ratio", 0)
    if ratio >= 30:
        gap_mult = 1.3
    elif ratio >= 10:
        gap_mult = 1.1
    elif ratio >= 3:
        gap_mult = 1.0
    else:
        gap_mult = 0.7

    # 변화율 보너스
    change_bonus = 1.0
    if change_rate is not None and change_rate >= 50:
        change_bonus = 1.4
    elif change_rate is not None and change_rate >= 20:
        change_bonus = 1.2

    value = intent_score * gap_mult * change_bonus
    return round(value, 1)


def _make_labels(intent_score, change_rate, is_bridge, datalab_type):
    """라벨 리스트 생성."""
    labels = []
    stars = {4: "★★★★", 3: "★★★", 2: "★★", 1: "★"}
    if intent_score in stars:
        labels.append(stars[intent_score])
    if change_rate is not None and change_rate >= 20:
        labels.append("🔥급등")
    if is_bridge:
        labels.append("🔗비교형")
    if datalab_type == "longtail":
        labels.append("📎롱테일")
    return labels


# ══════════════════════════════════════════════════════════
#  뉴스 이벤트 감지
# ══════════════════════════════════════════════════════════

NEWS_TRIGGERS = ["품절", "리콜", "허가", "승인", "보험", "급여", "부작용", "사망",
                 "소송", "가격인상", "인하", "출시", "발매", "FDA", "식약처"]

def detect_news_events(news_titles, root):
    """뉴스 제목에서 트리거 키워드 매칭."""
    events = []
    for title in news_titles[:20]:
        for trigger in NEWS_TRIGGERS:
            if trigger in title:
                events.append({"title": title, "trigger": trigger})
                break
    return events


# ══════════════════════════════════════════════════════════
#  이웃 발견 → 미확인 후보
# ══════════════════════════════════════════════════════════

def find_unidentified_candidates(all_titles, root, known_products, active_roots):
    """제목에서 빈도 높지만 known_products에 없는 단어 → 미확인 후보."""
    root_keywords = {r["keyword"] for r in active_roots}
    word_counter = Counter()

    for title in all_titles:
        words = title.split()
        for w in words:
            cleaned = _clean_word(w)
            if len(cleaned) >= 2 and cleaned not in STOPWORDS:
                if cleaned != root and cleaned not in root:
                    word_counter[cleaned] += 1

    # 뿌리 키워드가 포함된 합성어 제외용
    all_root_words = root_keywords | {root}

    candidates = []
    for word, cnt in word_counter.most_common(100):
        if cnt >= 3 and word not in known_products and word not in root_keywords:
            if word in CANDIDATE_EXCLUDE:
                continue
            # 뿌리 키워드가 포함된 합성어 제외 (예: "위고비마운자로")
            if any(rk in word for rk in all_root_words):
                continue
            # CANDIDATE_EXCLUDE 부분 매칭 (예: "킴스클럽과" ← "킴스클럽" 포함)
            if any(ex in word for ex in CANDIDATE_EXCLUDE if len(ex) >= 3):
                continue
            # 조사 붙은 단어 제외 (예: "킴스클럽과", "알부민을")
            stripped = re.sub(r"[은는이가을를과와의에서도만로]$", "", word)
            if stripped != word and (stripped in known_products or stripped in CANDIDATE_EXCLUDE):
                continue
            # 2글자 한글 명사 or 영문 약어만 후보로
            if re.match(r"^[가-힣]{2,}$", word) or re.match(r"^[A-Za-z0-9]{2,}$", word):
                candidates.append({"word": word, "count": cnt})

    return candidates[:10]  # 상위 10개


# ══════════════════════════════════════════════════════════
#  생명주기 관리
# ══════════════════════════════════════════════════════════

def update_lifecycle(root_data, results_by_root):
    """뿌리 생명주기 상태 업데이트.
    dormant 판단은 날짜 기반: last_active로부터 경과 일수로 계산.
    (하루 여러 번 실행해도 중복 카운트 방지)
    """
    today = datetime.now().strftime("%Y-%m-%d")

    for root_info in root_data["roots"]:
        kw = root_info["keyword"]
        result = results_by_root.get(kw)

        if result is None:
            continue

        has_rising = len(result.get("rising", [])) > 0

        if root_info["status"] == "watch":
            # watch → active: 유의미한 복합키워드 발견 시
            if len(result.get("compounds", [])) >= 5:
                root_info["status"] = "active"
                root_info["last_active"] = today
                root_info["consecutive_dormant_weeks"] = 0

        elif root_info["status"] == "active":
            if has_rising:
                root_info["last_active"] = today
                root_info["consecutive_dormant_weeks"] = 0
            else:
                # 날짜 기반 경과 주수 계산 (실행 횟수와 무관)
                last_active = root_info.get("last_active", today)
                try:
                    days_since = (datetime.strptime(today, "%Y-%m-%d")
                                  - datetime.strptime(last_active, "%Y-%m-%d")).days
                except ValueError:
                    days_since = 0
                weeks_dormant = days_since // 7
                root_info["consecutive_dormant_weeks"] = weeks_dormant
                if weeks_dormant >= 4:
                    root_info["status"] = "dormant"

        elif root_info["status"] == "dormant":
            if has_rising:
                root_info["status"] = "active"
                root_info["last_active"] = today
                root_info["consecutive_dormant_weeks"] = 0

    return root_data


# ══════════════════════════════════════════════════════════
#  추이 비교
# ══════════════════════════════════════════════════════════

def compare_with_previous(previous, current_roots):
    """이전 결과와 비교하여 변화 감지."""
    if not previous:
        return {"prev_time": None, "new_compounds": [], "gone_compounds": [],
                "rising_up": [], "rising_down": [], "new_rising": [],
                "value_up": [], "value_down": []}

    prev_time = previous.get("updated_at", "")

    # 이전 데이터를 {root: {compound_kw: detail}} 형태로 인덱싱
    prev_by_root = {}
    for r in previous.get("roots", []):
        prev_by_root[r["keyword"]] = {
            c["keyword"]: c for c in r.get("compounds", [])
        }

    new_compounds = []     # 이번에 새로 등장한 복합키워드
    gone_compounds = []    # 이전에 있었는데 사라진 복합키워드
    rising_up = []         # 변화율이 상승한 키워드
    rising_down = []       # 변화율이 하락한 키워드
    new_rising = []        # 이번에 새로 급등(🔥)된 키워드
    value_up = []          # 약사가치가 올라간 키워드
    value_down = []        # 약사가치가 내려간 키워드

    for r in current_roots:
        root = r["keyword"]
        prev_compounds = prev_by_root.get(root, {})
        curr_compounds = {c["keyword"]: c for c in r.get("compounds", [])}

        for kw, curr in curr_compounds.items():
            if kw not in prev_compounds:
                new_compounds.append({"keyword": kw, "root": root,
                                      "pharma_value": curr.get("pharma_value", 0)})
            else:
                prev = prev_compounds[kw]
                # 변화율 비교
                prev_cr = prev.get("change_rate")
                curr_cr = curr.get("change_rate")
                if prev_cr is not None and curr_cr is not None:
                    diff = curr_cr - prev_cr
                    if diff >= 10:
                        rising_up.append({"keyword": kw, "root": root,
                                          "prev": round(prev_cr, 1), "curr": round(curr_cr, 1),
                                          "diff": round(diff, 1)})
                    elif diff <= -10:
                        rising_down.append({"keyword": kw, "root": root,
                                            "prev": round(prev_cr, 1), "curr": round(curr_cr, 1),
                                            "diff": round(diff, 1)})

                # 새로 급등
                prev_labels = prev.get("labels", [])
                curr_labels = curr.get("labels", [])
                if "🔥급등" in curr_labels and "🔥급등" not in prev_labels:
                    new_rising.append({"keyword": kw, "root": root,
                                       "change_rate": curr_cr})

                # 약사가치 비교
                prev_val = prev.get("pharma_value", 0)
                curr_val = curr.get("pharma_value", 0)
                if curr_val - prev_val >= 0.5:
                    value_up.append({"keyword": kw, "root": root,
                                     "prev": prev_val, "curr": curr_val})
                elif prev_val - curr_val >= 0.5:
                    value_down.append({"keyword": kw, "root": root,
                                       "prev": prev_val, "curr": curr_val})

        # 사라진 키워드
        for kw in prev_compounds:
            if kw not in curr_compounds:
                gone_compounds.append({"keyword": kw, "root": root})

    # 중요도 순 정렬
    new_compounds.sort(key=lambda x: x["pharma_value"], reverse=True)
    rising_up.sort(key=lambda x: x["diff"], reverse=True)
    rising_down.sort(key=lambda x: x["diff"])

    return {
        "prev_time": prev_time,
        "new_compounds": new_compounds[:10],
        "gone_compounds": gone_compounds[:10],
        "rising_up": rising_up[:10],
        "rising_down": rising_down[:10],
        "new_rising": new_rising[:5],
        "value_up": value_up[:10],
        "value_down": value_down[:10],
    }


# ══════════════════════════════════════════════════════════
#  메인 파이프라인
# ══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("키워드 딥다이브 스캐너 시작")
    print("=" * 60)

    if not NAVER_CLIENT_ID:
        print("[경고] NAVER_CLIENT_ID 환경변수가 없습니다. 빈 결과로 진행합니다.")

    previous = load_previous()
    roots = load_roots()
    known_products = load_known_products()
    root_data = load_all_roots()

    all_results = []
    results_by_root = {}
    all_unidentified = {}  # word → {count, found_from}

    for root_info in roots:
        root = root_info["keyword"]
        print(f"\n── 뿌리: {root} ({root_info['status']}) ──")

        # 1. 복합키워드 마이닝
        compounds, all_titles, news_titles = mine_compound_keywords(root)
        print(f"  발견된 복합키워드: {len(compounds)}개")

        if not compounds:
            results_by_root[root] = {"compounds": [], "rising": [], "news_events": []}
            continue

        # 2. DataLab 비교
        datalab_results = compare_datalab(root, compounds)

        # 3. 각 복합키워드 분석
        compound_details = []
        rising = []

        for kw in compounds:
            dl = datalab_results.get(kw, {"volume": None, "change_rate": None, "trend_rate": None, "type": "longtail"})
            intent, intent_score = _classify_intent(kw)

            # 롱테일: DataLab 데이터 없으면 블로그 카운트로 판단
            blog_count = None
            if dl["type"] == "longtail":
                lt = evaluate_longtail(kw)
                blog_count = lt["blog_count"]
                if not lt["has_demand"]:
                    continue  # 수요 없는 롱테일 스킵

            # 전문가 갭
            expert_gap = calc_expert_gap(kw)

            # 브릿지 감지
            is_bridge, bridge_target = detect_bridge(kw, roots)

            # 약사 가치
            pharma_value = calc_pharma_value(kw, intent_score, expert_gap, dl.get("change_rate"))

            # 라벨
            labels = _make_labels(intent_score, dl.get("change_rate"), is_bridge, dl["type"])

            detail = {
                "keyword": kw,
                "volume": dl["volume"],
                "change_rate": dl["change_rate"],
                "trend_rate": dl.get("trend_rate"),
                "type": dl["type"],
                "intent": intent,
                "intent_score": intent_score,
                "expert_gap": expert_gap,
                "pharma_value": pharma_value,
                "labels": labels,
                "is_bridge": is_bridge,
                "bridge_target": bridge_target,
            }
            if blog_count is not None:
                detail["blog_count"] = blog_count

            compound_details.append(detail)

            # 급등 감지
            if dl.get("change_rate") is not None and dl["change_rate"] >= 20:
                rising.append(kw)

        # 약사가치순 정렬
        compound_details.sort(key=lambda x: x["pharma_value"], reverse=True)

        # 4. 뉴스 이벤트
        news_events = detect_news_events(news_titles, root)

        # 5. 미확인 후보
        candidates = find_unidentified_candidates(all_titles, root, known_products, roots)
        for c in candidates:
            word = c["word"]
            if word in all_unidentified:
                all_unidentified[word]["count"] += c["count"]
                if root not in all_unidentified[word]["found_from"]:
                    all_unidentified[word]["found_from"].append(root)
            else:
                all_unidentified[word] = {
                    "count": c["count"],
                    "found_from": [root],
                    "first_seen": datetime.now().strftime("%Y-%m-%d"),
                }

        result = {
            "keyword": root,
            "status": root_info["status"],
            "category": root_info.get("category", ""),
            "compounds": compound_details[:20],  # 상위 20개
            "rising": rising,
            "news_events": news_events[:5],
        }
        all_results.append(result)
        results_by_root[root] = result

        print(f"  분석 완료: {len(compound_details)}개 복합키워드, {len(rising)}개 급등")

    # ── 전체 통합 추천 ──
    all_compounds = []
    for r in all_results:
        for c in r["compounds"]:
            c["root"] = r["keyword"]
            all_compounds.append(c)
    all_compounds.sort(key=lambda x: x["pharma_value"], reverse=True)
    top_recommendations = all_compounds[:3]

    # ── 미확인 후보 정리 ──
    unidentified_list = [
        {"word": w, "count": info["count"], "found_from": info["found_from"],
         "first_seen": info["first_seen"]}
        for w, info in sorted(all_unidentified.items(), key=lambda x: x[1]["count"], reverse=True)
    ][:15]

    # ── 추이 비교 ──
    changes = compare_with_previous(previous, all_results)
    if changes["prev_time"]:
        print(f"\n── 이전({changes['prev_time']}) 대비 변화 ──")
        print(f"  새 복합키워드: {len(changes['new_compounds'])}개")
        print(f"  새 급등: {len(changes['new_rising'])}개")
        print(f"  변화율 상승: {len(changes['rising_up'])}개")
        print(f"  변화율 하락: {len(changes['rising_down'])}개")

    # ── 생명주기 업데이트 ──
    root_data = update_lifecycle(root_data, results_by_root)
    save_roots(root_data)

    # ── 결과 저장 ──
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "roots": all_results,
        "top_recommendations": top_recommendations,
        "unidentified_candidates": unidentified_list,
        "changes": changes,
    }

    latest_path = os.path.join(DATA_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장: {latest_path}")

    # 히스토리 저장
    os.makedirs(HISTORY_DIR, exist_ok=True)
    history_name = datetime.now().strftime("%Y%m%d_%H%M") + ".json"
    history_path = os.path.join(HISTORY_DIR, history_name)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"히스토리 저장: {history_path}")

    print("\n" + "=" * 60)
    print("딥다이브 스캐너 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
