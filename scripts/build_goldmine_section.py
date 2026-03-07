#!/usr/bin/env python3
"""
build_goldmine_section.py — 롱테일 금맥 대시보드 섹션 생성기

기존 build_dashboard.py가 생성한 docs/index.html에
하단 섹션을 추가하거나, 독립 HTML로 생성.

사용법 1 (기존 대시보드에 삽입):
  python scripts/build_goldmine_section.py --inject

사용법 2 (독립 HTML 생성):
  python scripts/build_goldmine_section.py --standalone

사용법 3 (둘 다):
  python scripts/build_goldmine_section.py
"""

import json
import argparse
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "longtail_goldmine.json"
DASHBOARD_PATH = BASE_DIR / "docs" / "index.html"
STANDALONE_PATH = BASE_DIR / "docs" / "goldmine.html"

# ─── CSS (다크 테마 — 기존 대시보드와 통일) ───────────────────

GOLDMINE_CSS = """
/* ── 롱테일 금맥 섹션 ── */
.goldmine-wrapper {
    margin: 40px 0;
}
.goldmine-header {
    border-top: 3px solid #d4a017;
    padding-top: 24px;
    margin-bottom: 24px;
}
.goldmine-header h2 {
    font-size: 1.4em;
    color: #d4a017;
    margin: 0 0 6px;
}
.goldmine-header .subtitle {
    color: #8b949e;
    font-size: 0.88em;
}
.goldmine-header .scan-time {
    color: #6e7681;
    font-size: 0.8em;
    margin-top: 4px;
}

/* 금맥 카테고리 요약 카드 */
.gm-category-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    gap: 10px;
    margin-bottom: 28px;
}
.gm-cat-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px 14px;
    text-align: center;
}
.gm-cat-card .cat-icon { font-size: 1.6em; }
.gm-cat-card .cat-name {
    font-size: 0.78em;
    color: #8b949e;
    margin: 4px 0 2px;
    line-height: 1.3;
}
.gm-cat-card .cat-count {
    font-size: 1.3em;
    font-weight: 700;
    color: #d4a017;
}

/* 금맥 TOP 키워드 테이블 */
.gm-section-title {
    font-size: 1.1em;
    font-weight: 700;
    color: #f0f6fc;
    margin: 28px 0 12px;
    padding-bottom: 6px;
    border-bottom: 2px solid #30363d;
}
.gm-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
    margin-bottom: 20px;
}
.gm-table th {
    text-align: left;
    padding: 8px 10px;
    background: #0d1117;
    color: #8b949e;
    font-weight: 600;
    font-size: 0.85em;
    border-bottom: 1px solid #30363d;
}
.gm-table td {
    padding: 10px;
    border-bottom: 1px solid #21262d;
    vertical-align: top;
}
.gm-table tr:hover { background: #1c2128; }

.gm-keyword {
    font-weight: 600;
    color: #f0f6fc;
}
.gm-root-tag {
    display: inline-block;
    background: #21262d;
    color: #8b949e;
    font-size: 0.75em;
    padding: 1px 6px;
    border-radius: 3px;
    margin-left: 6px;
}
.gm-badge {
    display: inline-block;
    font-size: 0.75em;
    padding: 2px 7px;
    border-radius: 4px;
    margin: 2px 2px 2px 0;
    font-weight: 600;
}
.gm-badge.drug_nutrient { background: #f8514920; color: #f85149; }
.gm-badge.supplement_vs_drug { background: #58a6ff20; color: #58a6ff; }
.gm-badge.ingredient_analysis { background: #3fb95020; color: #3fb950; }
.gm-badge.pharma_news { background: #f0883e20; color: #f0883e; }
.gm-badge.pharmacist_faq { background: #d2a8ff20; color: #d2a8ff; }

.gm-demand {
    color: #58a6ff;
    font-weight: 600;
    font-size: 0.92em;
    white-space: nowrap;
}
.gm-value {
    font-weight: 700;
    color: #d4a017;
    font-size: 1.05em;
}
.gm-gap-label {
    font-size: 0.78em;
    padding: 2px 6px;
    border-radius: 3px;
}
.gm-gap-label.gap-high { background: #3fb95020; color: #3fb950; }
.gm-gap-label.gap-mid { background: #f0883e20; color: #f0883e; }
.gm-gap-label.gap-low { background: #f8514920; color: #f85149; }
.gm-gap-label.gap-none { background: #21262d; color: #6e7681; }

.gm-stars { color: #d4a017; letter-spacing: 1px; }

/* 뿌리별 롱테일 아코디언 */
.gm-root-section {
    margin-bottom: 16px;
    border: 1px solid #30363d;
    border-radius: 8px;
    overflow: hidden;
}
.gm-root-header {
    background: #161b22;
    padding: 12px 16px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    user-select: none;
    color: #c9d1d9;
}
.gm-root-header:hover { background: #1c2128; }
.gm-root-header .root-name {
    font-weight: 700;
    font-size: 1em;
    color: #f0f6fc;
}
.gm-root-header .root-count {
    font-size: 0.82em;
    color: #8b949e;
}
.gm-root-body {
    display: none;
    padding: 0;
    background: #0d1117;
}
.gm-root-body.open { display: block; }
.gm-root-body table { margin-bottom: 0; }
.gm-root-body .gm-table td { padding: 8px 10px; }

/* 반응형 */
@media (max-width: 640px) {
    .gm-category-grid { grid-template-columns: repeat(2, 1fr); }
    .gm-table { font-size: 0.82em; }
    .gm-table th, .gm-table td { padding: 6px 8px; }
}
"""

# ─── JS ──────────────────────────────────────────────────

GOLDMINE_JS = """
function toggleGmRoot(el) {
    var body = el.nextElementSibling;
    var arrow = el.querySelector('.arrow');
    if (body.classList.contains('open')) {
        body.classList.remove('open');
        arrow.textContent = '▸';
    } else {
        body.classList.add('open');
        arrow.textContent = '▾';
    }
}
"""

# ─── HTML 생성 ───────────────────────────────────────────

def load_data():
    if not DATA_PATH.exists():
        print(f"[SKIP] {DATA_PATH} 없음. goldmine 섹션 생략.")
        return None
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def gap_class(label):
    if label in ("전문가 전무", "전문가 갭 큼"):
        return "gap-high"
    elif label in ("전문가 부족", "보통"):
        return "gap-mid"
    elif label == "전문가 포화":
        return "gap-low"
    return "gap-none"


def stars_html(score):
    full = int(score)
    return "★" * full + "☆" * (4 - full)


def build_category_cards(summary):
    """금맥 카테고리 요약 카드 그리드"""
    all_cats = [
        ("💊", "①처방약+영양제<br>병용", "drug_nutrient"),
        ("⚖️", "②건기식 vs<br>의약품", "supplement_vs_drug"),
        ("🔬", "③성분표<br>분석", "ingredient_analysis"),
        ("📰", "④신약/정책<br>뉴스 해설", "pharma_news"),
        ("🗣️", "⑤약사<br>FAQ", "pharmacist_faq"),
    ]
    cats = summary.get("categories", {})
    cards = ""
    for icon, name_html, cat_id in all_cats:
        count = 0
        for cat_key, cnt in cats.items():
            if cat_id == "drug_nutrient" and "병용" in cat_key:
                count = cnt
            elif cat_id == "supplement_vs_drug" and "vs" in cat_key:
                count = cnt
            elif cat_id == "ingredient_analysis" and "성분" in cat_key:
                count = cnt
            elif cat_id == "pharma_news" and "신약" in cat_key:
                count = cnt
            elif cat_id == "pharmacist_faq" and "FAQ" in cat_key:
                count = cnt

        cards += (
            f'<div class="gm-cat-card">'
            f'<div class="cat-icon">{icon}</div>'
            f'<div class="cat-name">{name_html}</div>'
            f'<div class="cat-count">{count}개</div>'
            f'</div>\n'
        )
    return f'<div class="gm-category-grid">{cards}</div>'


def build_top_table(longtails, limit=15):
    """금맥 TOP 키워드 테이블 (약사가치 상위)"""
    # 금맥 매칭된 것 우선, 그 다음 약사가치 순
    goldmine_items = [lt for lt in longtails if lt.get("goldmine")]
    non_goldmine = [lt for lt in longtails if not lt.get("goldmine")]
    items = (goldmine_items + non_goldmine)[:limit]

    if not items:
        return '<p style="color:#8b949e;">데이터가 아직 없습니다.</p>'

    rows = ""
    for lt in items:
        kw = lt["keyword"]
        root = lt["root"]

        # 금맥 뱃지
        badges = ""
        for gm in lt.get("goldmine", []):
            badges += f'<span class="gm-badge {gm["id"]}">{gm["icon"]} {gm["category"]}</span>'

        # 전문가 갭
        gap = lt.get("expert_gap", {})
        gap_label = gap.get("label", "미조회")
        gap_cls = gap_class(gap_label)

        # 약사가치
        pv = lt.get("pharma_value", 0)

        # 의도 별점
        intent = lt.get("intent_score", 1)

        # 수요 (블로그 총 건수)
        blog_total = gap.get("total", 0)
        if blog_total >= 10000:
            demand_str = f'{blog_total/10000:.1f}만'
        elif blog_total >= 1000:
            demand_str = f'{blog_total/1000:.1f}천'
        elif blog_total > 0:
            demand_str = f'{blog_total}'
        else:
            demand_str = '-'

        rows += (
            f'<tr>'
            f'<td><span class="gm-keyword">{kw}</span>'
            f'<span class="gm-root-tag">{root}</span>'
            f'<br>{badges}</td>'
            f'<td class="gm-demand">{demand_str}</td>'
            f'<td class="gm-stars">{stars_html(intent)}</td>'
            f'<td><span class="gm-gap-label {gap_cls}">{gap_label}</span></td>'
            f'<td class="gm-value">{pv}</td>'
            f'</tr>\n'
        )

    return (
        '<table class="gm-table"><thead><tr>'
        '<th>키워드</th><th>수요</th><th>전문성</th><th>전문가 갭</th><th>약사가치</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
    )


def build_root_accordions(longtails, roots_scanned):
    """뿌리별 롱테일 아코디언"""
    by_root = {}
    for lt in longtails:
        root = lt["root"]
        if root not in by_root:
            by_root[root] = []
        by_root[root].append(lt)

    html = ""
    for root in roots_scanned:
        items = by_root.get(root, [])
        if not items:
            continue

        goldmine_count = sum(1 for lt in items if lt.get("goldmine"))
        total = len(items)

        rows = ""
        for lt in sorted(items, key=lambda x: -x.get("pharma_value", 0)):
            kw = lt["keyword"]
            badges = ""
            for gm in lt.get("goldmine", []):
                badges += f' <span class="gm-badge {gm["id"]}">{gm["icon"]}</span>'

            gap = lt.get("expert_gap", {})
            gap_label = gap.get("label", "")
            gap_cls = gap_class(gap_label)
            pv = lt.get("pharma_value", 0)
            intent = lt.get("intent_score", 1)

            # 수요 (블로그 총 건수)
            blog_total = gap.get("total", 0)
            if blog_total >= 10000:
                demand_str = f'{blog_total/10000:.1f}만'
            elif blog_total >= 1000:
                demand_str = f'{blog_total/1000:.1f}천'
            elif blog_total > 0:
                demand_str = f'{blog_total}'
            else:
                demand_str = '-'

            rows += (
                f'<tr>'
                f'<td><span class="gm-keyword">{kw}</span>{badges}</td>'
                f'<td class="gm-demand">{demand_str}</td>'
                f'<td class="gm-stars">{stars_html(intent)}</td>'
                f'<td><span class="gm-gap-label {gap_cls}">{gap_label}</span></td>'
                f'<td class="gm-value">{pv}</td>'
                f'</tr>\n'
            )

        goldmine_tag = f' · 금맥 {goldmine_count}' if goldmine_count else ""
        html += (
            f'<div class="gm-root-section">'
            f'<div class="gm-root-header" onclick="toggleGmRoot(this)">'
            f'<span class="root-name"><span class="arrow">▸</span> {root}</span>'
            f'<span class="root-count">{total}개{goldmine_tag}</span>'
            f'</div>'
            f'<div class="gm-root-body">'
            f'<table class="gm-table"><thead><tr>'
            f'<th>키워드</th><th>수요</th><th>전문성</th><th>전문가 갭</th><th>약사가치</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>'
            f'</div></div>\n'
        )

    return html


def build_goldmine_html(data):
    """전체 금맥 섹션 HTML 생성"""
    scan_time = data.get("scan_time", "")
    summary = data.get("summary", {})
    longtails = data.get("longtails", [])
    roots = data.get("roots_scanned", [])

    # 시간 포맷
    try:
        dt = datetime.fromisoformat(scan_time)
        time_str = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        time_str = scan_time

    total = summary.get("total_longtails", 0)
    goldmine_count = summary.get("goldmine_matches", 0)

    category_cards = build_category_cards(summary)
    top_table = build_top_table(longtails, limit=15)
    root_accordions = build_root_accordions(longtails, roots)

    return (
        '<div class="goldmine-wrapper" id="goldmine-section">'
        '<div class="goldmine-header">'
        '<h2>롱테일 금맥 스캐너</h2>'
        f'<div class="subtitle">'
        f'ㄱ~ㅎ 자동완성 롱테일 <strong>{total}</strong>개 발굴'
        f' · 금맥 카테고리 매칭 <strong>{goldmine_count}</strong>개'
        f'</div>'
        f'<div class="scan-time">마지막 스캔: {time_str}</div>'
        '</div>'
        f'{category_cards}'
        '<div class="gm-section-title">금맥 TOP 키워드 (약사가치 상위)</div>'
        f'{top_table}'
        '<div class="gm-section-title">뿌리별 롱테일 전체</div>'
        f'{root_accordions}'
        '</div>'
    )


def build_standalone(data):
    """독립 HTML 페이지 생성 (다크 테마)"""
    section = build_goldmine_html(data)
    return (
        '<!DOCTYPE html>\n<html lang="ko">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>롱테일 금맥 스캐너 — 키워드 딥다이브</title>\n'
        '<style>\n'
        '* { box-sizing: border-box; margin: 0; padding: 0; }\n'
        'body { background: #0d1117; color: #c9d1d9; '
        "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; "
        'padding: 20px; max-width: 1200px; margin: 0 auto; }\n'
        f'{GOLDMINE_CSS}\n'
        '</style>\n</head>\n<body>\n'
        f'{section}\n'
        f'<script>{GOLDMINE_JS}</script>\n'
        '</body>\n</html>'
    )


def inject_into_dashboard(data):
    """기존 docs/index.html의 </body> 직전에 금맥 섹션 삽입"""
    if not DASHBOARD_PATH.exists():
        print(f"[ERROR] {DASHBOARD_PATH} 없음.")
        return False

    html = DASHBOARD_PATH.read_text(encoding="utf-8")

    # 이전에 삽입된 금맥 섹션 제거 (재실행 시 중복 방지)
    html = re.sub(
        r'<!-- GOLDMINE_START -->.*?<!-- GOLDMINE_END -->',
        '',
        html,
        flags=re.DOTALL
    )

    section = build_goldmine_html(data)

    injection = (
        '<!-- GOLDMINE_START -->\n'
        f'<style>{GOLDMINE_CSS}</style>\n'
        f'{section}\n'
        f'<script>{GOLDMINE_JS}</script>\n'
        '<!-- GOLDMINE_END -->'
    )

    # </body> 직전에 삽입
    if '</body>' in html:
        html = html.replace('</body>', f'{injection}\n</body>')
    else:
        html += injection

    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    print(f"금맥 섹션 삽입 완료: {DASHBOARD_PATH}")
    return True


def main():
    parser = argparse.ArgumentParser(description="롱테일 금맥 대시보드 섹션 생성")
    parser.add_argument("--inject", action="store_true", help="기존 대시보드에 삽입")
    parser.add_argument("--standalone", action="store_true", help="독립 HTML 생성")
    args = parser.parse_args()

    data = load_data()
    if not data:
        return

    # 둘 다 지정하거나 아무것도 안 지정하면 둘 다 실행
    do_inject = args.inject or (not args.inject and not args.standalone)
    do_standalone = args.standalone or (not args.inject and not args.standalone)

    if do_standalone:
        html = build_standalone(data)
        STANDALONE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STANDALONE_PATH.write_text(html, encoding="utf-8")
        print(f"독립 HTML 생성 완료: {STANDALONE_PATH}")

    if do_inject:
        inject_into_dashboard(data)


if __name__ == "__main__":
    main()
