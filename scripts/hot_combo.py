# -*- coding: utf-8 -*-
"""
화제 조합 스캐너 (hot_combo.py)
────────────────────────────────────────────────────────────
'지금 막 검색이 터지는' 화제성 조합 키워드를 발굴한다.
기존 dive.py(정보성·기회점수)는 그대로 두고, 이 모듈은 화제성 전용 칸을 채운다.

파이프라인:
  1) 수확   : '요즘 인기' 배지 cosearch + 우산 시드 자동완성 + 뿌리 제목 바이그램
  2) 정제   : Kiwi 형태소 분석으로 동사/부사/문장조각 제거 (명사만)
  3) 분류   : 사전으로 성분·제형·정보·브랜드 1차 구분
  4) 인물검증: 미확인 고유명사를 네이버 검색페이지 '인물 프로필 마커'로 인물 vs 신생브랜드 판별
  5) 검색량 : 검색광고 API로 월간 절대검색수 부여 (유입 가치 판단용)
  6) 랭킹   : 요즘인기 배지 → 인물·화제 → 검색량 순

비용: Anthropic 미사용(토큰 0). 네이버 검색/검색광고 API만 사용.
출력: data/hot_combos.json
"""
import os, sys, re, time, json, base64, hmac, hashlib, urllib.parse, urllib.request
from datetime import datetime
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ── 환경변수 (.env 로컬 + Actions os.environ 둘 다 지원) ──
def _load_env():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
_load_env()

NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID") or os.environ.get("NAVER_CLIENT_ID_DIVE")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET") or os.environ.get("NAVER_CLIENT_SECRET_DIVE")
NAVER_AD_CUSTOMER_ID = os.environ.get("NAVER_AD_CUSTOMER_ID")
NAVER_AD_API_KEY = os.environ.get("NAVER_AD_API_KEY")
NAVER_AD_SECRET_KEY = os.environ.get("NAVER_AD_SECRET_KEY")
SEARCHAD_BASE = "https://api.searchad.naver.com"

SEARCH_HDR = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
MOBILE_UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"

# 막힘(Actions IP 스로틀링) 대비: 짧은 타임아웃 + 전체 시간 예산.
# 스크래핑(cosearch/자동완성/인물검증)은 막힐 수 있고, 공식 API(검색/쇼핑/검색광고)는 안전.
REQUEST_TIMEOUT = 6
MAX_RUNTIME = float(os.environ.get("HOTCOMBO_MAX_SEC", "600"))  # 10분 — 넘으면 중단·저장

# ── Kiwi 형태소 분석기 (지연 로드) ──
_kiwi = None
def get_kiwi():
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi()
    return _kiwi

# ══════════════════════════════════════════════════════════
#  사전
# ══════════════════════════════════════════════════════════
def _load_sets():
    kp = json.load(open(os.path.join(DATA_DIR, "known_products.json"), encoding="utf-8"))
    rk = json.load(open(os.path.join(DATA_DIR, "root_keywords.json"), encoding="utf-8"))
    ingredient = set(kp["products"]) | {r["keyword"] for r in rk["roots"]}
    ingredient |= {"오메가3", "비타민c", "비타민d", "비타민", "지아잔틴", "아스타잔틴", "아연"}
    return ingredient, rk

INGREDIENT, _ROOTS_DATA = _load_sets()

INFO = {"부작용", "상호작용", "복용", "금기", "용량", "처방", "성분", "원리", "차이", "비교", "위험",
        "주의", "효과", "효능", "감량", "흡수", "품절", "대체", "추천", "진짜", "가짜", "논란", "후기",
        "경험", "기간", "결과", "전후", "가격", "최저가", "병원", "약국", "구매", "성지", "종류", "방법",
        "뜻", "급여", "보험", "직구", "사용법", "함량", "권장량", "식단", "음주", "요요", "내성", "당뇨",
        "두통", "구토", "설사", "변비", "임신", "생리", "건강", "피로", "눈건강", "원료", "선택", "누적"}
FORM = {"먹는", "마시는", "씹어먹는", "저분자", "초저분자", "고함량", "리포좀", "가루", "분말", "젤리",
        "액상", "필름", "붙이는", "츄어블", "캡슐", "앰플", "정제", "시럽", "스틱", "파우더", "순수",
        "천연", "모발", "올인원"}
# 인구통계·범주어 (화제성 아님 — 평범한 수식어)
GENERIC = {"어린이", "어른", "성인", "노인", "임산부", "임신부", "수유부", "남성", "여성", "남자", "여자",
           "아기", "유아", "아이", "청소년", "가족", "직장인", "학생", "주부", "중년", "갱년기",
           "운동", "체질", "기준", "간식", "식단", "음식", "관리", "방법", "효과", "추천", "비교", "순위",
           "가성비", "정리", "총정리", "주의사항", "장단점", "필요", "선택", "고민", "차이점", "기능"}
# 증상·질환·부작용어 (정보성 영역 — 기존 dive.py가 담당)
SYMPTOM = {"췌장염", "담석", "담낭", "탈모", "변비", "설사", "두통", "구토", "부종", "근육통", "갑상선",
           "당뇨", "고혈압", "통풍", "위염", "역류", "메스꺼움", "어지럼", "복통", "발진", "가려움",
           "불면", "피로감", "탈수", "저혈당", "간수치", "신장", "근손실"}
# 화제성에서 제외할 전체 어휘
EXCLUDE = INFO | GENERIC | SYMPTOM
COMPANY = {"고려아연", "영풍", "풍산", "대원제약", "종근당", "유한양행", "동아제약", "한미약품", "광동제약",
           "일동제약", "녹십자", "보령제약", "대웅제약", "GC녹십자", "HK이노엔", "풀무원", "올리브영",
           "다이소", "안국건강", "안국약품", "뉴트리원", "뉴벨라", "라이필", "에버콜라겐", "종근당건강",
           "일라이릴리", "릴리", "더마", "에버", "뉴트리코어", "고려은단", "코스맥스"}
BRAND_SUFFIX = ("건강", "제약", "바이오", "팜", "헬스", "케어", "약품", "랩", "파마")
# dive.py REGIONS 일부 (지역명 오분류 방지)
REGIONS = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "수원", "성남", "고양", "용인",
           "창원", "통영", "제주", "서귀포", "김해", "거제", "양산", "진주", "포항", "경주", "안동", "구미",
           "전주", "익산", "군산", "목포", "여수", "순천", "천안", "아산", "청주", "강남", "홍대", "신촌",
           "잠실", "판교", "분당", "일산", "동탄", "해운대", "일본", "미국", "중국", "국내", "한국"}

# 인물/브랜드/지역 판별 마커 (검색페이지 텍스트에 등장)
PERSON_MARK = ["출생", "데뷔", "소속사", "본명", "직업", "수상", "학력", "신체", "혈액형", "띠 "]
BRAND_MARK = ["설립", "대표자", "본사", "업종", "기업", "상장", "매출", "설립일"]
PLACE_MARK = ["행정구역", "면적", "인구", "시청", "도청", "위도", "경도"]

# ══════════════════════════════════════════════════════════
#  1) 수확
# ══════════════════════════════════════════════════════════
def cosearch_trending(seed):
    """'함께 많이 찾는' + '요즘 인기' 배지 수집. [(query, is_hot), ...]"""
    enc = urllib.parse.quote(seed)
    try:
        r = requests.get(f"https://m.search.naver.com/search.naver?query={enc}",
                         headers={"User-Agent": MOBILE_UA}, timeout=REQUEST_TIMEOUT)
        m = re.search(r'"apiURL":"(https://s\.search\.naver\.com/p/qra/[^"]+)"', r.text)
        if not m:
            return []
        api = m.group(1).replace("\\u002F", "/").replace("\\u0026", "&")
        time.sleep(1.0)
        h = {"User-Agent": MOBILE_UA,
             "Referer": f"https://m.search.naver.com/search.naver?query={enc}",
             "Accept": "application/json, text/plain, */*",
             "Accept-Language": "ko-KR,ko;q=0.9",
             "Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "cors"}
        r2 = requests.get(api, headers=h, timeout=REQUEST_TIMEOUT)
        if r2.status_code != 200:
            return []
        out = []
        for it in r2.json().get("result", {}).get("contents", []):
            q = it.get("query", "").strip()
            b = it.get("badge")
            if q:
                out.append((q, bool(b and b.get("text") == "요즘 인기")))
        return out
    except Exception as e:
        print(f"  [cosearch 경고] {seed}: {e}")
        return []

def autocomplete(query):
    enc = urllib.parse.quote(query)
    url = (f"https://mac.search.naver.com/mobile/ac?q={enc}"
           f"&st=100&r_lt=100&q_enc=UTF-8&r_format=json&r_enc=UTF-8&r_unicode=0")
    req = urllib.request.Request(url, headers={"User-Agent": MOBILE_UA,
                                               "Referer": "https://m.search.naver.com/"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            items = json.loads(r.read().decode("utf-8")).get("items", [[]])[0]
            return [it[0] for it in items if it and it[0]]
    except Exception:
        return []

def fetch_titles(kind, query, n=100):
    url = f"https://openapi.naver.com/v1/search/{kind}.json"
    try:
        r = requests.get(url, headers=SEARCH_HDR,
                         params={"query": query, "display": n, "sort": "sim"}, timeout=REQUEST_TIMEOUT)
        return [re.sub(r"<[^>]+>", "", it.get("title", "")) for it in r.json().get("items", [])]
    except Exception:
        return []

def _clean(w):
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", w).strip()

def bigrams_from_titles(titles, root):
    from collections import Counter
    c = Counter()
    for t in titles:
        ws = [_clean(w) for w in t.split() if _clean(w)]
        for i, w in enumerate(ws):
            if root in w:
                if i + 1 < len(ws) and len(ws[i + 1]) >= 2:
                    c[f"{root} {ws[i + 1]}"] += 1
                if i - 1 >= 0 and len(ws[i - 1]) >= 2:
                    c[f"{ws[i - 1]} {root}"] += 1
    return {kw: f for kw, f in c.items() if f >= 2}

# ══════════════════════════════════════════════════════════
#  2~3) Kiwi 정제 + 사전 분류
# ══════════════════════════════════════════════════════════
def content_nouns(phrase):
    """명사(NNG/NNP)만 추출. 동사/부사/조사/어미/조각은 버림."""
    return [(t.form, t.tag) for t in get_kiwi().tokenize(phrase) if t.tag in ("NNG", "NNP")]

def _mk(kind, warn, token, needs_verify):
    return {"kind": kind, "warn": warn, "token": token, "needs_verify": needs_verify}

def classify(phrase, root):
    """1차 분류 → dict(kind, warn, token, needs_verify).

    핵심: Kiwi는 '위고비'를 '위'+'고비'로 쪼개므로 토큰 동등성에 의존하면 안 됨.
    뿌리·성분명을 '문자열'로 먼저 제거한 잔여물을 후보(token)로 삼는다.
    """
    # 1) 교차 성분·약물 (위고비 마운자로, 루테인 오메가3 — 안전한 비교 글감)
    ings = sorted({i for i in INGREDIENT if i in phrase}, key=len, reverse=True)
    if len(ings) >= 2:
        return _mk("성분·약물", "", "", False)

    # 2) 뿌리 + 성분명을 문자열로 제거한 잔여물
    residual = phrase
    for t in sorted(set(ings) | ({root} if root else set()), key=len, reverse=True):
        if t:
            residual = residual.replace(t, " ")
    residual = re.sub(r"\s+", " ", residual).strip()

    # 3) 잔여물의 품사 — 명사가 있어야 화제 후보 (동사/부사/조각이면 노이즈)
    toks = get_kiwi().tokenize(residual) if residual else []
    nouns = [t.form for t in toks if t.tag in ("NNG", "NNP")]
    content = [f for f in nouns if f not in EXCLUDE and f not in FORM and len(f) >= 2]
    if not content:
        if any(w in residual for w in FORM) or any(f in FORM for f in nouns):
            return _mk("제형", "", "", False)
        return _mk("정보성", "", "", False)

    # 4) 후보 토큰 = 잔여물에서 정보성/범주/증상/제형어 제거한 깨끗한 고유명사 후보
    cand = residual
    for w in sorted(EXCLUDE | FORM, key=len, reverse=True):
        cand = re.sub(re.escape(w), " ", cand)
    cand = re.sub(r"\s+", " ", cand).strip()
    if not cand:
        cand = content[0]

    # 지역명
    if cand in REGIONS:
        return _mk("지역", "", cand, False)
    # 사전 브랜드/회사
    if cand in COMPANY or any(c in phrase for c in COMPANY):
        return _mk("제품브랜드", "⚠️제품(사전)", cand, False)
    # 미확인 고유명사 → 인물검증 대상
    warn = "⚠️제품의심(붙은형)" if " " not in phrase else (
        "⚠️제품의심" if cand.endswith(BRAND_SUFFIX) else "⚠️확인필요")
    return _mk("화제(미확인)", warn, cand, True)

# ══════════════════════════════════════════════════════════
#  4) 네이버 인물검증
# ══════════════════════════════════════════════════════════
def verify_entity(token):
    """검색페이지 마커로 엔티티 추정. 반환: ('인물'|'브랜드'|'불명', 점수dict).

    주의: 인물 마커(출생/직업 등)는 일반명사 검색페이지에도 우연히 섞여
    3~4점이 나옴 → 인물 판정은 보수적으로(≥5 & 브랜드보다 우세). 화제성 노출은
    인물 여부로 게이트하지 않으므로(트래픽 기준), 이 함수의 핵심 역할은
    '신생 브랜드(소송 위험) 안전 플래그'다. 브랜드는 b≥4에서 신뢰.
    """
    enc = urllib.parse.quote(token)
    try:
        r = requests.get(f"https://m.search.naver.com/search.naver?query={enc}",
                         headers={"User-Agent": MOBILE_UA}, timeout=REQUEST_TIMEOUT)
        t = r.text
        p = sum(1 for m in PERSON_MARK if m in t)
        b = sum(1 for m in BRAND_MARK if m in t)
        pl = sum(1 for m in PLACE_MARK if m in t)
    except Exception:
        return "불명", {"p": -1, "b": -1, "pl": -1}
    score = {"p": p, "b": b, "pl": pl}
    if b >= 4 and b > p:         # 회사/브랜드 (인물보다 우세할 때만)
        return "브랜드", score
    if p >= 4 and p >= b:        # 인물 (이순실=4 같은 캐릭터도 포함)
        return "인물", score
    return "불명", score

# ══════════════════════════════════════════════════════════
#  5) 검색광고 검색량
# ══════════════════════════════════════════════════════════
def _searchad_signature(timestamp, method, path):
    msg = f"{timestamp}.{method}.{path}"
    digest = hmac.new(NAVER_AD_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()

def _parse_qc(v):
    if isinstance(v, int): return v
    if isinstance(v, str):
        s = v.replace("<", "").replace(",", "").strip()
        return int(s) if s.isdigit() else 9
    return 0

def fetch_search_volume(keywords):
    result = {}
    if not (NAVER_AD_CUSTOMER_ID and NAVER_AD_API_KEY and NAVER_AD_SECRET_KEY):
        return result
    path = "/keywordstool"
    for i in range(0, len(keywords), 5):
        batch = keywords[i:i + 5]
        hint = ",".join(k.replace(" ", "") for k in batch)
        ts = str(int(time.time() * 1000))
        headers = {"X-Timestamp": ts, "X-API-KEY": NAVER_AD_API_KEY,
                   "X-Customer": str(NAVER_AD_CUSTOMER_ID),
                   "X-Signature": _searchad_signature(ts, "GET", path)}
        try:
            r = requests.get(SEARCHAD_BASE + path, headers=headers,
                             params={"hintKeywords": hint, "showDetail": "1"}, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                time.sleep(0.5); continue
            for item in r.json().get("keywordList", []):
                key = item.get("relKeyword", "").replace(" ", "").upper()
                pc = _parse_qc(item.get("monthlyPcQcCnt", 0))
                mo = _parse_qc(item.get("monthlyMobileQcCnt", 0))
                result[key] = {"total": pc + mo, "comp_idx": item.get("compIdx", "")}
        except Exception as e:
            print(f"  [검색광고 경고] {e}")
        time.sleep(0.2)
    return result

def lookup_volume(vmap, kw):
    return vmap.get(kw.replace(" ", "").upper())

def shop_count(keyword):
    """네이버 쇼핑 상품수. 제품/브랜드는 수천~수만, 인물·토픽은 0~1천.
    소송 위험 제품명 판별의 결정적 신호."""
    try:
        r = requests.get("https://openapi.naver.com/v1/search/shop.json",
                         headers=SEARCH_HDR, params={"query": keyword, "display": 1}, timeout=REQUEST_TIMEOUT)
        return r.json().get("total", 0)
    except Exception:
        return -1

# ── 광고모델 vs 진짜화제 판별 (행동 신호) ──
# 실측(2026-07-04): 남진 쏘팔메토·오한진 프로바이오틱스 같은 '광고모델'은 인물검증을
# 통과하지만(실제 사람이므로) 뉴스가 없거나 전부 광고성이고 쇼핑 상품수가 수십~수백.
# 반대로 조현아 위고비 같은 '진짜 화제'는 쇼핑수 0 + 상업어 없는 실제 뉴스가 다수.
# → 쇼핑수 상한 + '진짜 뉴스 N건' 게이트로 광고모델을 걸러낸다.
TOPIC_WORDS = ["근황", "화제", "공개", "고백", "인터뷰", "감량", "다이어트", "방송", "출연",
               "투병", "논란", "몸무게", "몸매", "폭로", "복귀", "컴백", "열애", "결혼",
               "임신", "출산", "별세", "은퇴", "비결", "요요", "중단", "습관", "식단"]
COMMERCE_WORDS = ["최저가", "정품", "구매", "판매", "할인", "쿠팡", "증정", "프로모션", "1위",
                  "파는곳", "정품몰", "세일", "특가", "광고", "브랜드", "출시", "런칭",
                  "만족지수", "인증", "전문", "후기", "추천", "효능", "성분", "가격"]

def genuine_news_count(phrase):
    """뉴스 제목 중 '상업어 없이 인물 스토리 어휘(화제어)를 담은' 진짜 화제 기사 수.
    광고성 advertorial(증정/1위/구매…)은 화제어가 있어도 상업어 때문에 제외된다."""
    titles = fetch_titles("news", phrase, 20)
    return sum(1 for t in titles
               if any(w in t for w in TOPIC_WORDS) and not any(c in t for c in COMMERCE_WORDS))

# 광고모델 필터 임계값 (실측 튜닝 2026-07-04: shop<50 AND 진짜뉴스>=2)
PERSON_SHOP_MAX = 50
MIN_GENUINE_NEWS = 2

def is_genuine_person_combo(phrase):
    """누적 항목 재검증용: (통과여부, shop, 진짜뉴스). 광고모델·제품·가짜인물을 걸러냄."""
    sc = shop_count(phrase); time.sleep(0.2)
    if sc >= PERSON_SHOP_MAX:
        return False, sc, None
    gn = genuine_news_count(phrase); time.sleep(0.2)
    return (gn >= MIN_GENUINE_NEWS), sc, gn

# 이름 형태(2~4자 한글)지만 인물이 아닌 흔한 일반어 — 인물 후보에서 제외
NAME_STOPLIST = {
    "하루", "스토리", "레드", "골드", "블랙", "화이트", "그린", "오리지널", "프리미엄",
    "스페셜", "에디션", "플러스", "데일리", "오늘", "내일", "이번", "최신", "신상",
    "정품", "공식", "국내", "수입", "대용량", "소용량", "리얼", "퓨어", "내돈내산",
}

def is_name_shaped(token):
    """인물명 형태(2~4자 순수 한글)인지. 인물 후보를 이 형태로 좁혀 노이즈·긴토큰 제거.
    이름처럼 보이는 흔한 일반어(하루·스토리·레드 등)는 제외."""
    t = (token or "").strip()
    if t in NAME_STOPLIST:
        return False
    return bool(re.fullmatch(r"[가-힣]{2,4}", t))


# ══════════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════════
def load_active_roots():
    rk = json.load(open(os.path.join(DATA_DIR, "root_keywords.json"), encoding="utf-8"))
    return [r["keyword"] for r in rk["roots"] if r["status"] in ("active", "watch")]

# 분야를 가로지르는 우산 시드 (시드 밖 인물×건강 조합 포착)
UMBRELLA_SEEDS = ["연예인 다이어트", "다이어트약", "감량 성공", "다이어트 성공"]

# 테스트용 다양한 분야 대표 뿌리 (다이어트약+영양제+탈모 등)
TEST_ROOTS = ["위고비", "마운자로", "루테인", "콜라겐", "글루타치온",
              "유산균", "오메가3", "미녹시딜", "쏘팔메토"]

def run(roots=None, verify=True, min_volume=30, verify_limit=200, limit=None):
    if roots is None:
        roots = load_active_roots()
    print("=" * 60)
    print(f" 화제 조합 스캐너 (hot_combo) — 뿌리 {len(roots)}개")
    print("=" * 60)

    t0 = time.time()
    def over_budget():
        if time.time() - t0 > MAX_RUNTIME:
            print(f"  [예산초과] {MAX_RUNTIME:.0f}초 경과 → 남은 작업 중단하고 저장")
            return True
        return False

    cands = {}   # phrase -> {"seed":, "hot":bool}
    def add(phrase, seed, hot=False):
        phrase = phrase.strip()
        if phrase:
            c = cands.setdefault(phrase, {"seed": seed, "hot": False})
            if hot:
                c["hot"] = True

    print("\n[1] '요즘 인기' 배지 cosearch 수확 (뿌리 전체 + 우산)")
    cosearch_fail = 0
    for s in roots + ["다이어트약", "비만약", "다이어트"]:
        if over_budget():
            break
        res = cosearch_trending(s)
        if not res:
            cosearch_fail += 1
            if cosearch_fail >= 6:   # 연속 빈 결과 = IP 차단 추정 → 스크래핑 수확 중단
                print("  [차단추정] cosearch 연속 실패 → 수확 단계 축소(공식 API 위주로 진행)")
                break
        else:
            cosearch_fail = 0
        for q, hot in res:
            if q != s:
                add(q, s, hot)
        time.sleep(0.4)
    print(f"    누적 {len(cands)}개")

    print("[2] 우산 시드 자동완성 수확")
    for u in UMBRELLA_SEEDS:
        for q in autocomplete(u):
            if q != u:
                add(q, u)
        time.sleep(0.4)
    print(f"    누적 {len(cands)}개")

    print("[3] 뿌리 제목 바이그램 수확 (공식 API — 안전)")
    for root in roots:
        if over_budget():
            break
        titles = fetch_titles("blog", root, 100) + fetch_titles("news", root, 100)
        for kw in bigrams_from_titles(titles, root):
            add(kw, root)
        time.sleep(0.2)
    print(f"    누적 {len(cands)}개")

    # 분류 (사전만 — 검증은 뒤에서 상위 후보만)
    print("\n[4] Kiwi 정제 + 사전 분류")
    rows = []
    for phrase, meta in cands.items():
        root = meta["seed"] if meta["seed"] in phrase else \
            next((i for i in INGREDIENT if i in phrase), meta["seed"])
        rows.append({"phrase": phrase, "hot": meta["hot"], "seed": meta["seed"],
                     **classify(phrase, root)})
    # 인물 전용: '미확인 고유명사' 중 이름 형태(2~4자 한글)만 → 노이즈·긴토큰 제거.
    # (검색량/검증을 이 후보들에만 돌려 시간 절약 + 인물 비율↑)
    hotrows = [r for r in rows if r.get("needs_verify") and is_name_shaped(r["token"])]
    print(f"    인물 후보(이름형 토큰) {len(hotrows)}개")

    # 검색량 (인물 후보만 — 트래픽순 검증 우선순위용)
    print("[5] 검색광고 월검색량 조회")
    vmap = fetch_search_volume([r["phrase"] for r in hotrows])
    for r in hotrows:
        v = lookup_volume(vmap, r["phrase"])
        r["search_volume"] = v["total"] if v else None
        r["comp_idx"] = v["comp_idx"] if v else ""

    # 인물 전용 검증: 미확인 후보 → 인물 판정 → 인물만 생존.
    # 단, '광고모델·제품 파는 인물'(남진 쏘팔메토, 여에스더 등)은
    #   쇼핑 상품수(≥PERSON_SHOP_MAX) 또는 진짜뉴스 부족(<MIN_GENUINE_NEWS)으로 제외.
    #   실측 튜닝(2026-07-04): shop<50 AND 진짜뉴스>=2 → 광고모델 4명 전멸, 진짜화제 6명 전원 생존.
    PERSON_SHOP_MAX = 50
    MIN_GENUINE_NEWS = 2
    if verify:
        targets = sorted([r for r in hotrows if r.get("needs_verify")
                          and (r["search_volume"] or 0) >= min_volume],
                         key=lambda r: -(r["search_volume"] or 0))[:verify_limit]
        print(f"[6] 인물 검증 ({len(targets)}건)")
        verify_fail = 0
        for r in targets:
            if over_budget():
                break
            ent, esc = verify_entity(r["token"]); time.sleep(0.8)  # 스크래핑 — 차단 회피용 충분한 딜레이
            r["entity"] = ent; r["entity_score"] = esc
            # 인물검증은 스크래핑 → 연속 실패(점수 -1)면 IP 차단 추정 → 중단
            if esc.get("p", 0) < 0:
                verify_fail += 1
                if verify_fail >= 5:
                    print("  [차단추정] 인물검증 연속 실패 → 검증 중단")
                    break
                continue
            verify_fail = 0
            if ent != "인물":
                continue                          # 인물 아님 → 탈락
            sc = shop_count(r["phrase"]); time.sleep(0.2)   # 공식 API — 안전
            r["shop_count"] = sc
            if sc >= PERSON_SHOP_MAX:
                r["entity"] = "제품인물"           # 제품 많이 파는 인물 → 탈락
                continue
            gn = genuine_news_count(r["phrase"]); time.sleep(0.2)  # 공식 API — 안전
            r["genuine_news"] = gn
            if gn < MIN_GENUINE_NEWS:
                r["entity"] = "광고모델"           # 쇼핑수는 낮아도 진짜 화제기사가 없음 → 탈락
                continue
            r["kind"] = "화제(인물)"; r["warn"] = "👤인물"
    else:
        print("[6] 검증 스킵 (--no-verify)")

    # 인물 전용: 검증된 인물 조합만 남기고 전부 제거
    persons = [r for r in hotrows if r.get("kind") == "화제(인물)"]
    print(f"    → 인물 조합 {len(persons)}개 생존")
    hotrows = persons

    # ── 누적 병합 ──
    # 매번 덮어쓰지 않고, 기존 누적에 이번 발견을 합침. 셀럽×건강은 에버그린 글감이라
    # 영구 누적(안 지움). 대시보드는 상위 N명만 표시하므로 화면은 안 지저분해짐.
    today = time.strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, "hot_combos.json")

    existing = {}
    if os.path.exists(path):
        try:
            for it in json.load(open(path, encoding="utf-8")).get("items", []):
                existing[it["keyword"]] = it
        except Exception:
            existing = {}
    for it in existing.values():
        it["today"] = False   # 일단 전부 '오늘 아님'으로

    for r in hotrows:
        kw = r["phrase"]
        if kw in existing:
            it = existing[kw]
            it.setdefault("first_seen", today)   # 옛 데이터 전환 보정
            it["last_seen"] = today
            it["seen_count"] = it.get("seen_count", 1) + 1
            it["today"] = True
            it["is_hot_badge"] = r["hot"]
            it["seed"] = r["seed"]
            if r.get("search_volume") is not None:
                it["search_volume"] = r["search_volume"]
            it["comp_idx"] = r.get("comp_idx", "")
        else:
            existing[kw] = {
                "keyword": kw, "search_volume": r.get("search_volume"),
                "comp_idx": r.get("comp_idx", ""), "seed": r["seed"],
                "is_hot_badge": r["hot"], "first_seen": today, "last_seen": today,
                "seen_count": 1, "today": True,
            }

    def _days_since(dstr):
        try:
            return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(dstr, "%Y-%m-%d")).days
        except Exception:
            return 0
    # last_seen 있는 것만 유지(옛 형식·정체불명 자동 정리). 보존기간 제한 없음(영구 누적).
    merged = [it for it in existing.values() if it.get("last_seen")]
    # 정렬: 오늘 발견 먼저 → 최근 발견 → 트래픽 큰 순
    merged.sort(key=lambda it: (0 if it.get("today") else 1,
                                _days_since(it.get("last_seen", today)),
                                -(it.get("search_volume") or 0)))

    today_n = sum(1 for it in merged if it.get("today"))
    out = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M"),
        "today_count": today_n,
        "count": len(merged),
        "items": merged[:limit] if limit else merged,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {path}  (누적 {len(merged)}개 · 오늘 {today_n}개 · 이번 인물 {len(hotrows)}개)")

    print("\n" + "=" * 60)
    print(" 누적 인물 미리보기 (오늘 발견 먼저)")
    print("=" * 60)
    for it in out["items"][:30]:
        badge = "🔥오늘" if it.get("today") else "     "
        vol = it.get("search_volume")
        vol_s = f"{vol:>6}/월" if vol is not None else "  -   "
        seen = f"{it.get('first_seen','?')}~{it.get('last_seen','?')}({it.get('seen_count',1)}회)"
        print(f"  {badge} {vol_s} {it['keyword']:<20} {seen}")
    return out

def revalidate_existing(apply=False):
    """누적된 인물 조합을 현재 필터(쇼핑수+진짜뉴스)로 다시 검증.
    필터를 바꿨을 때 옛 항목(광고모델·가짜인물)을 청소하는 용도.
    apply=False면 판정만 출력(dry-run), True면 탈락자를 실제로 제거·저장."""
    path = os.path.join(DATA_DIR, "hot_combos.json")
    data = json.load(open(path, encoding="utf-8"))
    items = data.get("items", [])
    print(f"재검증: 누적 {len(items)}명  (기준: shop<{PERSON_SHOP_MAX} AND 진짜뉴스>={MIN_GENUINE_NEWS})")
    keep, drop = [], []
    for it in items:
        ok, sc, gn = is_genuine_person_combo(it["keyword"])
        (keep if ok else drop).append(it)
        mark = "유지" if ok else "탈락"
        print(f"  [{mark}] {it['keyword']:<22} shop={sc} 진짜뉴스={gn}")
    print(f"\n유지 {len(keep)}명 / 탈락 {len(drop)}명")
    if drop:
        print("탈락:", ", ".join(d["keyword"] for d in drop))
    if apply and drop:
        keep.sort(key=lambda it: (0 if it.get("today") else 1, -(it.get("search_volume") or 0)))
        data["items"] = keep
        data["count"] = len(keep)
        data["today_count"] = sum(1 for it in keep if it.get("today"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"→ 저장 완료 (누적 {len(keep)}명)")
    elif drop:
        print("(dry-run — 실제 제거하려면 --apply 추가)")


if __name__ == "__main__":
    if "--revalidate" in sys.argv:
        revalidate_existing(apply="--apply" in sys.argv)
    else:
        verify = "--no-verify" not in sys.argv
        roots = TEST_ROOTS if "--test" in sys.argv else None
        run(roots=roots, verify=verify)
