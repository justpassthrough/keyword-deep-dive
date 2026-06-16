#!/usr/bin/env python3
"""
build_hot_section.py — 화제 조합 대시보드 섹션 생성기

data/hot_combos.json (hot_combo.py 출력)을 읽어 docs/index.html에
'🔥 화제 조합' 섹션을 주입한다. (build_goldmine_section.py와 동일 패턴)

사용법:
  python scripts/build_hot_section.py --inject       # 대시보드에 삽입
  python scripts/build_hot_section.py --standalone   # 독립 HTML
  python scripts/build_hot_section.py                # 둘 다
"""
import json
import argparse
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "hot_combos.json"
DASHBOARD_PATH = BASE_DIR / "docs" / "index.html"
STANDALONE_PATH = BASE_DIR / "docs" / "hot_combos.html"

HOT_CSS = """
/* ── 화제 조합 섹션 ── */
.hc-wrapper { margin: 40px 0; }
.hc-header { border-top: 3px solid #f85149; padding-top: 24px; margin-bottom: 16px; }
.hc-header h2 { font-size: 1.4em; color: #f85149; margin: 0 0 6px; }
.hc-header .subtitle { color: #8b949e; font-size: 0.88em; line-height: 1.5; }
.hc-header .scan-time { color: #6e7681; font-size: 0.8em; margin-top: 4px; }
.hc-legend {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 10px 14px; margin-bottom: 20px; font-size: 0.8em; color: #8b949e; line-height: 1.7;
}
.hc-legend b { color: #c9d1d9; }
.hc-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
.hc-table th {
    text-align: left; padding: 8px 10px; background: #0d1117; color: #8b949e;
    font-weight: 600; border-bottom: 1px solid #30363d; position: sticky; top: 0;
}
.hc-table td { padding: 9px 10px; border-bottom: 1px solid #21262d; vertical-align: middle; }
.hc-table tr:hover { background: #1c2128; }
.hc-kw { font-weight: 600; color: #f0f6fc; }
.hc-person-ic { color: #d2a8ff; }
.hc-fire { margin-right: 2px; }
.hc-today { color: #3fb950; font-weight: 600; font-size: 0.85em; }
.hc-seen { color: #6e7681; font-size: 0.82em; }
.hc-cnt { color: #8b949e; font-size: 0.78em; }
.hc-seed { display: inline-block; background: #21262d; color: #6e7681;
           font-size: 0.72em; padding: 1px 6px; border-radius: 3px; margin-left: 6px; }
.hc-vol { color: #58a6ff; font-weight: 600; white-space: nowrap; }
.hc-comp-낮음 { color: #3fb950; } .hc-comp-중간 { color: #d29922; } .hc-comp-높음 { color: #f85149; }
.hc-tag { display: inline-block; font-size: 0.75em; padding: 2px 7px; border-radius: 4px; font-weight: 600; white-space: nowrap; }
.hc-ok       { background: #3fb95020; color: #3fb950; }   /* 화제(안전) */
.hc-person   { background: #d2a8ff20; color: #d2a8ff; }   /* 인물 */
.hc-ingredient { background: #58a6ff20; color: #58a6ff; } /* 성분·약물 비교 */
.hc-caution  { background: #f0883e20; color: #f0883e; }   /* 확인필요 */
.hc-warn     { background: #f8514920; color: #f85149; }   /* 제품/브랜드 경고 */
.hc-row-warn td { opacity: 0.72; }
@media (max-width: 640px) {
    .hc-table { font-size: 0.8em; } .hc-table th, .hc-table td { padding: 6px 7px; }
    .hc-seed { display: none; }
}
"""


def load_data():
    if not DATA_PATH.exists():
        print(f"[SKIP] {DATA_PATH} 없음. 화제 조합 섹션 생략.")
        return None
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _fmt_vol(v):
    if v is None:
        return '<span style="color:#6e7681">-</span>'
    if v >= 10000:
        return f"{v/10000:.1f}만"
    if v >= 1000:
        return f"{v/1000:.1f}천"
    return f"{v}"


def build_rows(items, limit=60):
    rows = ""
    for it in items[:limit]:
        today = it.get("today")
        fire = '<span class="hc-fire">🔥</span>' if today else ""
        comp = it.get("comp_idx", "") or ""
        comp_html = f'<span class="hc-comp-{comp}">{comp}</span>' if comp else "-"
        # 발견 정보: 오늘이면 '오늘', 아니면 마지막 발견일 + 누적 횟수
        cnt = it.get("seen_count", 1)
        if today:
            seen = f'<span class="hc-today">오늘</span>'
        else:
            seen = f'<span class="hc-seen">{it.get("last_seen","")}</span>'
        if cnt > 1:
            seen += f' <span class="hc-cnt">·{cnt}회</span>'
        rows += (
            f'<tr>'
            f'<td>{fire}<span class="hc-person-ic">👤</span> '
            f'<span class="hc-kw">{it["keyword"]}</span>'
            f'<span class="hc-seed">{it.get("seed","")}</span></td>'
            f'<td class="hc-vol">{_fmt_vol(it.get("search_volume"))}</td>'
            f'<td>{comp_html}</td>'
            f'<td>{seen}</td>'
            f'</tr>\n'
        )
    return rows


def build_hot_html(data):
    items = data.get("items", [])
    scan_time = data.get("updated_at", "")
    total = data.get("count", len(items))
    today_n = data.get("today_count", sum(1 for it in items if it.get("today")))
    rows = build_rows(items, limit=60)
    if not rows:
        rows = '<tr><td colspan="4" style="color:#8b949e">아직 쌓인 인물 조합이 없습니다.</td></tr>'
    return (
        '<div class="hc-wrapper" id="hot-section">'
        '<div class="hc-header">'
        '<h2>👤 인물 화제 조합</h2>'
        '<div class="subtitle">내 성분·약물 키워드에 <b>지금 엮여 검색되는 유명인</b> 조합. '
        '셀럽 다이어트·건강 글감으로, 기존 리스트엔 안 나오는 새 소재입니다. '
        '매 스캔 결과를 <b>최근 3주간 누적</b>해서 보여줍니다.</div>'
        f'<div class="scan-time">마지막 스캔: {scan_time} · 누적 {total}명 · 🔥오늘 {today_n}명</div>'
        '</div>'
        '<div class="hc-legend">'
        '<b>🔥오늘</b> 이번 스캔에 잡힘 &nbsp;|&nbsp; '
        '<b><span style="color:#58a6ff">월검색량</span></b> 네이버 검색광고 기준 &nbsp;|&nbsp; '
        '인물명은 네이버 인물검증으로 자동 선별 — '
        '<b>드물게 오탐(일반어가 인물로)이 있으니 작성 전 확인하세요.</b>'
        '</div>'
        '<table class="hc-table"><thead><tr>'
        '<th>키워드</th><th>월검색량</th><th>경쟁</th><th>발견</th>'
        '</tr></thead><tbody>'
        f'{rows}'
        '</tbody></table>'
        '</div>'
    )


def build_standalone(data):
    section = build_hot_html(data)
    return (
        '<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>화제 조합 — 키워드 딥다이브</title>\n<style>\n'
        '* { box-sizing: border-box; margin: 0; padding: 0; }\n'
        "body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "
        "'Segoe UI', sans-serif; padding: 20px; max-width: 1100px; margin: 0 auto; }\n"
        f'{HOT_CSS}\n</style>\n</head>\n<body>\n{section}\n</body>\n</html>'
    )


def inject_into_dashboard(data):
    if not DASHBOARD_PATH.exists():
        print(f"[ERROR] {DASHBOARD_PATH} 없음.")
        return False
    html = DASHBOARD_PATH.read_text(encoding="utf-8")
    html = re.sub(r'<!-- HOTCOMBO_START -->.*?<!-- HOTCOMBO_END -->', '', html, flags=re.DOTALL)
    section = build_hot_html(data)
    injection = (
        '<!-- HOTCOMBO_START -->\n'
        f'<style>{HOT_CSS}</style>\n{section}\n'
        '<!-- HOTCOMBO_END -->'
    )
    # 화제 조합은 상단 관심사 → goldmine보다 앞(먼저)에 오도록 GOLDMINE_START 앞에 삽입,
    # 없으면 </body> 직전.
    if '<!-- GOLDMINE_START -->' in html:
        html = html.replace('<!-- GOLDMINE_START -->', f'{injection}\n<!-- GOLDMINE_START -->')
    elif '</body>' in html:
        html = html.replace('</body>', f'{injection}\n</body>')
    else:
        html += injection
    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    print(f"화제 조합 섹션 삽입 완료: {DASHBOARD_PATH}")
    return True


def main():
    parser = argparse.ArgumentParser(description="화제 조합 대시보드 섹션 생성")
    parser.add_argument("--inject", action="store_true")
    parser.add_argument("--standalone", action="store_true")
    args = parser.parse_args()
    data = load_data()
    if not data:
        return
    do_inject = args.inject or (not args.inject and not args.standalone)
    do_standalone = args.standalone or (not args.inject and not args.standalone)
    if do_standalone:
        STANDALONE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STANDALONE_PATH.write_text(build_standalone(data), encoding="utf-8")
        print(f"독립 HTML 생성 완료: {STANDALONE_PATH}")
    if do_inject:
        inject_into_dashboard(data)


if __name__ == "__main__":
    main()
