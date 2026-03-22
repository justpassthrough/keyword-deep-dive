# 키워드 딥다이브 스캐너 — 전체 가이드 & 디버깅 레퍼런스

> **최종 업데이트: 2026-03-07**
> 이 파일을 Claude Code에게 주면 이 대시보드의 모든 맥락을 파악하고 디버깅할 수 있습니다.

---

## 1. 프로젝트 개요

약사 블로그 글감을 자동으로 찾아주는 도구. 두 가지 엔진이 독립적으로 동작합니다.

| 엔진 | 하는 일 | 실행 주기 |
|------|---------|----------|
| **Deep Dive** (dive.py) | 뿌리 키워드 → 네이버 블로그/뉴스에서 복합키워드 확장 → DataLab 검색량/변화율/전문가갭/약사가치 산출 | 하루 4회 |
| **Gold Mine** (longtail_goldmine.py) | 뿌리 키워드 + ㄱ~ㅎ 자동완성 → 롱테일 발굴 → 금맥 카테고리 5종 분류 → 약사가치 산출 | 주 1회 |

**GitHub**: `justpassthrough/keyword-deep-dive`
**대시보드**: https://justpassthrough.github.io/keyword-deep-dive/
**로컬 경로**: `C:\Users\Andy\OneDrive\Desktop\Fire\de_novo\Claude_code_output\keyword-deep-dive`

---

## 2. 파일 구조

```
keyword-deep-dive/
├── scripts/
│   ├── dive.py                    # 메인 분석 (복합키워드 확장 + DataLab + 약사가치)
│   ├── build_dashboard.py         # latest.json → HTML 대시보드 (다크 테마)
│   ├── discover_roots.py          # 뿌리 자동 발굴 (4소스)
│   ├── longtail_goldmine.py       # ㄱ~ㅎ 자동완성 롱테일 금맥 스캐너
│   └── build_goldmine_section.py  # 금맥 섹션 → 대시보드 삽입 or 독립 HTML
├── data/
│   ├── root_keywords.json         # 뿌리 키워드 풀 (status: active/watch/dormant/archived)
│   ├── known_products.json        # 제품/성분 고유명사 사전 (40개)
│   ├── latest.json                # Deep Dive 최근 분석 결과
│   ├── longtail_goldmine.json     # Gold Mine 최근 스캔 결과
│   └── history/                   # 과거 분석 결과 누적
├── docs/
│   ├── index.html                 # GitHub Pages 대시보드 (Deep Dive + Gold Mine 통합)
│   └── goldmine.html              # Gold Mine 독립 대시보드
├── .github/workflows/
│   ├── daily_dive.yml             # 하루 4회 (dive + dashboard + goldmine inject)
│   ├── weekly_discover.yml        # 3일마다 (discover + dive + dashboard + goldmine inject)
│   └── weekly_goldmine.yml        # 주 1회 (goldmine scan + dashboard inject)
├── requirements.txt
├── GUIDE.md                       # 이 파일
└── README.md
```

---

## 3. 자동 실행 스케줄

| 워크플로우 | cron (UTC) | 한국시간 | 하는 일 |
|-----------|-----------|---------|---------|
| daily_dive.yml | `30 22`, `0 4`, `0 10`, `0 15` | 07:30, 13:00, 19:00, 00:00 | dive.py → build_dashboard.py → build_goldmine_section.py --inject → 커밋 |
| weekly_discover.yml | `0 23 */3 * *` | 3일마다 08:00 | discover_roots.py → dive.py → build_dashboard.py → goldmine inject → 커밋 |
| weekly_goldmine.yml | `0 23 * * 0` | 월요일 08:00 | longtail_goldmine.py → build_goldmine_section.py → 커밋 |

**중요**: daily_dive가 build_dashboard.py를 실행하면 index.html이 처음부터 재생성됨. 그래서 **모든 워크플로우에 goldmine inject 단계가 포함**되어야 금맥 섹션이 유지됨. `|| true`로 감싸서 goldmine.json이 없어도 실패하지 않게 함.

**API 키**: GitHub Secrets에 `NAVER_CLIENT_ID_DIVE` / `NAVER_CLIENT_SECRET_DIVE` 등록. health-trend-scanner와 분리된 전용 키.

---

## 4. Deep Dive 엔진 (dive.py)

### 파이프라인

뿌리 키워드 하나마다:
1. **복합키워드 마이닝**: 네이버 블로그 100개 + 뉴스 100개 제목에서 "뿌리+X" 패턴 추출
2. **cosearch 1차 수집**: 뿌리 키워드로 네이버 모바일 "함께 많이 찾는" 키워드 수집 → 복합키워드 풀에 합류
3. **SEO 스팸 필터**: 지역명/숫자 마스킹 → 동일 패턴 3건↑ = 스팸, 1건으로 축소
4. **DataLab 비교**: 4개씩 배치, 1초 간격. 뿌리 대비 상대 검색량 산출
5. **변화율 계산 (듀얼)**:
   - `change_rate` (메인): 최근 3일 vs 직전 3일 → 급등 감지
   - `trend_rate` (보조): 최근 7일 vs 이전 7일 → 추세 참고
6. **롱테일**: DataLab에 없는 키워드 → 블로그 totalCount로 수요 판단
7. **전문가 갭**: `전체블로그 / (약사블로그 + 1)` 비율
8. **약사 가치**: `의도점수(1~4) × 전문가갭배수(0.7~1.3) × 변화율보너스(1.0~1.4)`
9. **미확인 후보 수집**: known_products에 없는 빈도 높은 단어 (다중 필터 적용)
10. **추이 비교**: 이전 latest.json과 비교 → 새 급등/새 복합키워드/변화율 변동
11. **생명주기 업데이트**: active/watch/dormant 상태 전환
12. **cosearch 2차 심층 탐색**: 🔥급등 복합키워드(change_rate ≥ 20%)로 추가 cosearch → 더 깊은 트렌딩 발굴
13. **API 사용량 추적**: DataLab 호출 수 카운트 → 하루 4회 기준 80% 초과 시 경고

### 약사 가치 공식

```
약사가치 = 의도점수 × 전문가갭배수 × 변화율보너스
```

**의도점수** (키워드에 포함된 단어로 판단):
- 4점: 부작용, 상호작용, 복용, 금기, 용량, 처방, 성분, 원리, 차이, 비교, 위험, 주의
- 3점: 효과, 감량, 품절, 대체, 추천, 논란
- 2점: 후기, 경험, 결과, 전후
- 1점: 가격, 최저가, 약국, 할인, 구매

**전문가갭배수**: 전체블로그/(약사블로그+1) 비율
- ×1.3: 30배↑ (전문가 갭 큼)
- ×1.1: 10배↑ (전문가 부족)
- ×1.0: 3배↑ (보통)
- ×0.7: 3배 미만 (전문가 포화)

**변화율보너스**: 3일 단기 변화율 기준
- ×1.4: +50%↑
- ×1.2: +20%↑
- ×1.0: 기본

**고정값이 아님** — 전문가갭과 변화율이 매 실행마다 바뀌므로 점수도 변동.

### 대시보드 라벨
| 라벨 | 의미 |
|------|------|
| ★★★★ ~ ★ | 의도점수 4~1 |
| 🔥급등 | 3일 변화율 +20%↑ |
| 🔍네이버인기 | 네이버 "함께 많이 찾는"에서 "요즘 인기" 배지가 붙은 키워드 |
| 🔗비교형 | 다른 뿌리 키워드를 포함 ("마운자로 위고비 차이") |
| 📎롱테일 | DataLab에 없지만 블로그 수요 있음 |

### 검색량 표시
- **숫자 (예: 17.6)**: DataLab 상대 검색량
- **블로그 230**: 롱테일, 블로그 검색 totalCount

---

## 4.5. Cosearch 트렌딩 (함께 많이 찾는 — 요즘 인기)

### 개요

네이버 모바일 검색 결과에 나타나는 "함께 많이 찾는" 연관검색어 중 `"요즘 인기"` 배지가 붙은 키워드를 수집하는 기능. 네이버가 직접 판별한 실시간 급상승 연관 키워드.

### 데이터 수집 방식 (2-step, requests만 사용)

1. **Step 1**: 네이버 모바일 검색 HTML에서 `apiURL` 추출 (정규식으로 `s.search.naver.com/p/qra/` URL 파싱)
2. **Step 2**: apiURL 호출 → JSON 응답에서 `badge.text == "요즘 인기"` 여부 확인

### 함수: `fetch_cosearch_trending(keyword)`

- 입력: 키워드 (뿌리 or 복합키워드)
- 출력: `[{"query": "...", "is_trending": True/False}, ...]`
- 실패 시: 빈 리스트 반환 (try/except로 감싸져 있어 Actions에서 차단되어도 안전)

### 파이프라인 통합

| 단계 | 대상 | 설명 |
|------|------|------|
| **1차 cosearch** | 뿌리 키워드 | 복합키워드 마이닝 직후 호출, 수집된 키워드를 복합키워드 풀에 합류 |
| **2차 cosearch (심층)** | 🔥급등 복합키워드 | 전체 분석 완료 후, change_rate ≥ 20% 키워드에 대해 추가 cosearch |

### API 부담

- **네이버 공식 API 한도에 영향 없음** (DataLab/블로그/뉴스 API 안 씀)
- 네이버 모바일 웹 크롤링 (비공식), 금맥 스캐너의 `mac.search.naver.com`과 같은 패턴
- 뿌리당 2회 요청 (검색 HTML 1회 + apiURL 1회) + 급등 키워드당 2회 추가
- 1.5초 딜레이 적용으로 차단 방지

### 대시보드 표시

- **대시보드 위치**: 추천 글감 TOP 5 **위**에 별도 섹션
- **"뿌리 키워드 연관"**: 1차 cosearch에서 수집된 요즘인기 키워드 (약사가치 포함)
- **"🔥 급등 키워드에서 추가 발견"**: 2차 심층 cosearch 결과 (출처 급등 키워드 표시)
- 각 복합키워드 테이블의 라벨 열에도 `🔍네이버인기` 배지 표시

### latest.json 필드

- 각 복합키워드 항목: `"cosearch_trending": true/false`
- 최상위 레벨: `"deep_cosearch_trending": [{"query": "...", "source_keyword": "...", "root": "..."}, ...]`

### 주의사항

- **User-Agent 필수**: 모바일 UA (`Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36`)
- **apiURL의 암호화 파라미터**: 세션/쿼리마다 바뀜 → 매번 Step 1에서 추출 필요
- **apiURL이 없을 수 있음**: 키워드에 따라 "함께 많이 찾는" 섹션 자체가 안 나올 수 있음
- **비공식 엔드포인트**: 네이버가 변경하면 깨질 수 있음 (자동완성 API와 동일한 리스크)

---

## 5. Gold Mine 엔진 (longtail_goldmine.py)

### 파이프라인

1. root_keywords.json에서 active/watch 뿌리 로드
2. 각 뿌리에 ㄱ~ㅎ 14자음을 붙여 **네이버 모바일 자동완성** 수집
3. 금맥 카테고리 5개에 정규식 패턴 매칭
4. 매칭된 키워드 or 의도점수 3+만 전문가 갭 API 조회 (API 절약)
5. 약사가치 = 의도점수 × 전문가갭배수 × 금맥보너스(1.3)

### 금맥 카테고리 5종
| 카테고리 | 설명 | 예시 패턴 |
|---------|------|----------|
| ①처방약+영양제 병용 | 약사 아니면 답 못 하는 병용 질문 | "혈압약 오메가3", "같이 먹어도" |
| ②건기식 vs 의약품 | 건기식과 의약품 차이 | "밀크씨슬 처방 차이" |
| ③성분표 분석 | 성분/함량 해석 | "성분", "함량", "몇mg" |
| ④신약/정책 뉴스 해설 | 시사 해설 | "허가", "출시", "FDA" |
| ⑤약사 FAQ | 현장 FAQ | "같이 먹어도 되나요", "공복 복용" |

### 자동완성 API 주의사항
- **`ac.search.naver.com/nx/ac`는 빈 결과를 반환** (로컬/GitHub Actions 모두)
- **`mac.search.naver.com/mobile/ac`를 사용해야 함** (모바일 자동완성)
- User-Agent: Android, Referer: `m.search.naver.com`

### 대시보드 삽입 구조
- `build_goldmine_section.py --inject`: 기존 index.html의 `</body>` 앞에 삽입
- `<!-- GOLDMINE_START -->` ~ `<!-- GOLDMINE_END -->` 마커로 감싸서 재실행 시 교체
- CSS는 **다크 테마** (#0d1117 기반, 기존 대시보드와 통일)

---

## 6. 뿌리 키워드 관리

### 생명주기

```
watch →(복합키워드 5개↑)→ active →(28일 급등0)→ dormant →(56일)→ archived
                               ↑                      │
                               └──(급등 재등장)────────┘
```

- **날짜 기반**: last_active에서 경과일 ÷ 7 = 주수. 실행 횟수와 무관.
- **watch도 분석은 동일**: 대시보드에 탭+테이블로 표시 (👀 구분)
- **현실적으로 dormant 잘 안 일어남**: 복합키워드가 수십 개인데 28일간 하나도 +20% 안 뜰 확률 낮음. 뿌리 40개↑ 되면 기준 강화 예정.

### 자동 발굴 (discover_roots.py)
4가지 소스:
- **A**: active 뿌리 블로그에서 known_products 사전 매칭
- **B**: 카테고리 시드 쿼리 ("비만치료제 신약" 등)
- **C**: 약업계 뉴스
- **D**: health-trend-scanner latest.json 연동

검증: DataLab 검색량 있음 + 복합키워드 5종↑ → watch 등록

**한계**: known_products에 없는 완전 새 제품은 미확인 후보로만 노출. 사람이 사전에 추가해야 함.

### 수동 추가

**뿌리 추가** — `data/root_keywords.json`:
```json
{"keyword": "글루타치온", "category": "영양제", "status": "active", "source": "manual",
 "parent": null, "added": "2026-03-07", "last_active": "2026-03-07", "consecutive_dormant_weeks": 0}
```

**제품 사전 추가** — `data/known_products.json`의 products 배열에 이름 추가

---

## 7. API 한도 관리

| API | 일일 한도 | 주 사용처 |
|-----|----------|----------|
| DataLab | 1,000회 | dive.py (뿌리당 ~6회/실행) — **병목** |
| 블로그/뉴스 검색 | 25,000회 | dive.py + longtail_goldmine.py |
| 자동완성 | 제한 없음 (비공식) | longtail_goldmine.py (뿌리당 14회) |

**현재 사용량** (2026-03-07 기준):
- 뿌리 13개 × DataLab ~6회 × 4회/일 = ~312회 (31%)
- 한도 도달 예상: 뿌리 ~40개

**경고 시스템**: dive.py가 매 실행마다 DataLab 호출 수를 세서 api_usage에 저장.
- `usage_pct >= 80%` → 대시보드 최상단에 빨간 경고 배너
- latest.json의 `api_usage` 필드: `{datalab_this_run, estimated_daily, daily_limit, usage_pct, warning}`

---

## 8. 미확인 후보 필터

블로그 제목에서 추출된 단어 중 known_products에 없는 것을 걸러내는 4중 필터:

1. **의도 키워드 자동 제외**: HIGH/MID/LOW/WEAK_PHARMA 단어들
2. **CANDIDATE_EXCLUDE**: 카테고리어(비만약, 영양제), 마케팅수식어(프리미엄, 골드), 기업명(대원제약, 종근당), 일반건강용어(건강, 체중, 단백질)
3. **뿌리 합성어 제외**: "위고비마운자로" 같은 뿌리끼리 합쳐진 단어
4. **조사 제거**: "킴스클럽과" → "킴스클럽" 매칭 (은/는/이/가/을/를/과/와/의 등)

---

## 9. git 충돌 대응

- Actions가 하루 4회+ data/ docs/를 자동 커밋
- 로컬 수정 후 push 시 높은 확률로 충돌

**항상**: `git pull --rebase` 후 push
**data/ docs/ 충돌**: 보통 `--theirs` (리모트 자동생성 데이터 수용)
**scripts/ 충돌**: `--ours` (로컬 코드 수정 우선)

---

## 10. 수정 이력 (전체)

| 날짜 | 내용 |
|------|------|
| 03-04 | 프로젝트 생성 (dive.py, build_dashboard.py, discover_roots.py, 뿌리 6개) |
| 03-04 | CSS f-string 이스케이프 버그 수정 → CSS를 별도 상수로 분리 |
| 03-04 | calc_pharma_value에서 >=50이 >=20 elif 뒤 → 순서 교정 |
| 03-04 | 실행 스케줄 하루 2회 → 4회 (07:30/13:00/19:00/00:00 KST) |
| 03-04 | 듀얼 변화율 도입 (3일 단기 메인 + 7일 추세 보조) |
| 03-04 | 추이 비교 기능 추가 (compare_with_previous) |
| 03-05 | 미확인 후보 노이즈 필터링 (CANDIDATE_EXCLUDE + 합성어 + 조사) |
| 03-05 | **dormant 폭주 버그 (치명적)**: 실행마다 +1 → 날짜 기반 계산으로 수정 |
| 03-05 | 뿌리 발굴 주기: 매주 → 3일마다 |
| 03-06 | dormant 버그로 사라진 키워드 복구 |
| 03-07 | 첫 뿌리 자동 발굴 실행 → 7개 새 뿌리 (루테인, 콜라겐 등) |
| 03-07 | watch 키워드를 active와 동일한 탭+테이블로 대시보드 통합 |
| 03-07 | API 한도 경고 시스템 (DataLab 호출 카운터, 80% 경고) |
| 03-07 | **롱테일 금맥 스캐너 추가** (longtail_goldmine.py + build_goldmine_section.py) |
| 03-07 | 금맥 스캐너 호환성 수정 5건: API키 _DIVE, CSS 다크테마, inject 유지, argparse, permissions |
| 03-07 | **자동완성 API 빈 결과 버그**: ac.search → mac.search 모바일 엔드포인트로 교체 |
| 03-22 | **cosearch 트렌딩 기능 추가**: 네이버 "함께 많이 찾는 — 요즘 인기" 키워드 수집 (1차: 뿌리, 2차: 급등 키워드 심층) |
| 03-22 | 대시보드에 🔍네이버인기 배지 + 별도 섹션 (추천 글감 위) 추가 |
| 03-22 | latest.json에 `cosearch_trending`, `deep_cosearch_trending` 필드 추가 |

---

## 11. 알려진 한계 & 향후 개선 가능

1. **discover_roots.py는 known_products에 있는 이름만 뿌리로 등록** → 새 제품은 미확인 후보로만 노출, 사람이 사전에 추가
2. **dormant 강등이 현실적으로 안 일어남** → 뿌리 많아지면 기준 강화 필요
3. **카테고리 자동 추정 부정확** → 유산균이 "비만치료제"로 분류된 사례. 수동 수정 가능
4. **금맥 카테고리 ①②는 매칭이 어려움** → 자동완성에서 "혈압약 오메가3 같이 먹어도"처럼 나오는 경우가 드물 수 있음. 패턴 확장 고려
5. **자동완성 API가 비공식** → 네이버가 변경하면 깨질 수 있음. 그때 엔드포인트 확인 필요
6. **cosearch apiURL도 비공식** → `s.search.naver.com/p/qra/` 패턴이 변경되면 정규식 수정 필요
7. **cosearch 2차 탐색은 급등 키워드 수에 비례** → 급등 키워드가 많으면 실행시간 증가 (키워드당 ~3초)

---

## 12. 디버깅 체크리스트

### 대시보드가 안 나옴
1. Actions 탭에서 최근 실행 확인 (`gh run list --limit=5`)
2. 실패한 워크플로우 로그 확인 (`gh run view <ID> --log`)
3. GitHub Pages 설정 확인 (Settings → Pages → Source: Deploy from branch, /docs)

### 금맥 섹션이 안 보임
1. `data/longtail_goldmine.json` 존재 여부 확인
2. daily_dive.yml에 `build_goldmine_section.py --inject || true` 단계 있는지 확인
3. index.html에 `<!-- GOLDMINE_START -->` 마커 검색

### 자동완성 결과가 0개
1. `mac.search.naver.com/mobile/ac` 엔드포인트 사용 중인지 확인
2. `ac.search.naver.com/nx/ac`는 빈 결과 반환하므로 사용 금지
3. 로컬 테스트: `python -c "from scripts.longtail_goldmine import fetch_autocomplete; print(fetch_autocomplete('마운자로 ㄱ'))"`

### 키워드가 갑자기 사라짐 (dormant)
1. `data/root_keywords.json`에서 해당 키워드의 status 확인
2. `last_active` 날짜와 현재 날짜 차이 확인 (28일 이상 → dormant)
3. 복구: status를 "active"로, last_active를 오늘 날짜로 수정

### API 한도 경고
1. `data/latest.json`의 `api_usage` 확인
2. 뿌리 수 줄이기: 약사가치 낮은 뿌리를 "archived"로 변경
3. 또는 daily_dive 실행 횟수 줄이기 (4회 → 2회)

### cosearch 결과가 0개
1. Actions 로그에서 `[cosearch]` 로그 확인
2. "apiURL 없음" → 해당 키워드에 "함께 많이 찾는" 섹션 자체가 없음 (정상)
3. "모바일 검색 실패" → GitHub Actions IP에서 네이버가 차단했을 수 있음 (try/except로 스킵됨)
4. 로컬 테스트: `python -c "from scripts.dive import fetch_cosearch_trending; print(fetch_cosearch_trending('오메가3'))"`

### git push 실패 (충돌)
1. `git pull --rebase` 먼저 실행
2. 충돌 시: data/ docs/ → `git checkout --theirs`, scripts/ → `git checkout --ours`
3. `git rebase --continue` → `git push`
