#!/usr/bin/env python3
"""
키워드 딥다이브 스캐너 — HTML 대시보드 생성
latest.json → docs/index.html
"""

import json
import os
from html import escape

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")

# CSS는 f-string 밖에서 정의 (중괄호 이스케이프 불필요)
CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; max-width: 1200px; margin: 0 auto; }
  h1 { color: #58a6ff; margin-bottom: 5px; font-size: 1.6em; }
  h3 { color: #58a6ff; margin: 20px 0 10px; }
  h4 { color: #8b949e; margin: 10px 0 5px; }
  .updated { color: #8b949e; font-size: 0.85em; margin-bottom: 20px; }

  .rec-card { display: flex; align-items: center; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
  .rec-rank { font-size: 1.5em; font-weight: bold; color: #f0883e; min-width: 45px; }
  .rec-keyword { font-size: 1.15em; font-weight: 600; color: #f0f6fc; }
  .rec-meta { margin-top: 5px; display: flex; gap: 10px; flex-wrap: wrap; }
  .rec-meta span { background: #21262d; padding: 2px 8px; border-radius: 4px; font-size: 0.82em; }
  .rec-root { color: #58a6ff; }
  .rec-intent { color: #d2a8ff; }
  .rec-value { color: #f0883e; font-weight: 600; }
  .rec-gap { color: #8b949e; font-size: 0.82em; margin-top: 4px; }

  .tab-bar { display: flex; gap: 5px; margin: 20px 0 0; flex-wrap: wrap; }
  .tab-btn { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 8px 16px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 0.9em; }
  .tab-btn.active { background: #161b22; border-bottom-color: #161b22; color: #58a6ff; font-weight: 600; }
  .tab-content { background: #161b22; border: 1px solid #30363d; border-radius: 0 8px 8px 8px; padding: 20px; }

  .section-header { font-size: 1.2em; font-weight: 600; color: #f0f6fc; margin-bottom: 15px; }
  .category-badge { background: #21262d; color: #8b949e; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: normal; }

  .rising-section { margin-bottom: 15px; }
  .rising-badge { display: inline-block; background: #f8514926; color: #f85149; border: 1px solid #f8514950; padding: 4px 10px; border-radius: 20px; margin: 3px; font-size: 0.85em; }

  .news-section { margin-bottom: 15px; }
  .news-item { background: #0d1117; padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 0.85em; }
  .news-trigger { color: #f0883e; font-weight: 600; }

  .kw-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
  .kw-table th { background: #0d1117; color: #8b949e; padding: 8px; text-align: left; border-bottom: 1px solid #30363d; }
  .kw-table td { padding: 8px; border-bottom: 1px solid #21262d; }
  .kw-table tr:hover { background: #1c2128; }
  .kw-cell { color: #f0f6fc; font-weight: 500; }
  .value-cell { color: #f0883e; font-weight: 600; }
  .positive { color: #f85149; }
  .negative { color: #3fb950; }
  .trend-sub { color: #8b949e; font-size: 0.8em; }

  .watch-badge { background: #d2a8ff20; color: #d2a8ff; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: normal; margin-left: 6px; }
  .api-warning { background: #f8514930; border: 1px solid #f85149; color: #f85149; padding: 12px 16px; border-radius: 8px; margin-bottom: 15px; font-weight: 600; }

  .unid-section { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-top: 20px; }
  .unid-desc { color: #8b949e; font-size: 0.85em; margin-bottom: 10px; }

  .changes-section { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-top: 20px; margin-bottom: 10px; }
  .changes-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
  .change-box { background: #0d1117; border-radius: 6px; padding: 12px; }
  .change-box h4 { margin-bottom: 8px; }
  .change-item { padding: 3px 0; font-size: 0.85em; }
  .change-item .kw { color: #f0f6fc; font-weight: 500; }
  .change-item .root-tag { color: #8b949e; font-size: 0.8em; }
  .change-item .up { color: #f85149; }
  .change-item .down { color: #3fb950; }
  .change-item .new-badge { background: #1f6feb33; color: #58a6ff; padding: 1px 6px; border-radius: 3px; font-size: 0.8em; }
  .prev-time { color: #8b949e; font-size: 0.82em; }

  @media (max-width: 768px) {
    .kw-table { font-size: 0.75em; }
    .rec-meta { flex-direction: column; gap: 4px; }
    .changes-grid { grid-template-columns: 1fr; }
  }
"""

# JS도 f-string 밖에서 정의
JS = """
function showTab(keyword) {
  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  const tab = document.getElementById('tab-' + keyword);
  if (tab) tab.style.display = 'block';
  event.target.classList.add('active');
}
"""


def load_latest():
    path = os.path.join(DATA_DIR, "latest.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_html(data):
    if not data:
        return "<html><body><h1>데이터 없음</h1></body></html>"

    updated = escape(data.get("updated_at", ""))
    roots = data.get("roots", [])
    top_recs = data.get("top_recommendations", [])
    unidentified = data.get("unidentified_candidates", [])

    changes = data.get("changes", {})
    api_usage = data.get("api_usage", {})

    active_roots = [r for r in roots if r.get("status") == "active"]
    watch_roots = [r for r in roots if r.get("status") == "watch"]

    # ── API 경고 배너 ──
    api_warning_html = ""
    if api_usage.get("warning"):
        pct = api_usage.get("usage_pct", 0)
        daily = api_usage.get("estimated_daily", 0)
        limit = api_usage.get("daily_limit", 1000)
        api_warning_html = (
            '<div class="api-warning">'
            f'⚠️ API 한도 경고: 일 예상 DataLab {daily}회 / {limit}회 ({pct}%) '
            '— 뿌리 키워드 정리가 필요합니다!'
            '</div>'
        )

    # ── 추이 비교 섹션 ──
    changes_html = ""
    if changes.get("prev_time"):
        # 새 급등
        new_rising_items = ""
        for c in changes.get("new_rising", []):
            cr = c.get("change_rate")
            cr_str = f"+{cr:.0f}%" if cr is not None else ""
            new_rising_items += (
                f'<div class="change-item">'
                f'<span class="new-badge">NEW</span> '
                f'<span class="kw">{escape(c.get("keyword", ""))}</span> '
                f'<span class="up">{cr_str}</span> '
                f'<span class="root-tag">{escape(c.get("root", ""))}</span>'
                f'</div>\n'
            )

        # 새 복합키워드
        new_compound_items = ""
        for c in changes.get("new_compounds", [])[:5]:
            new_compound_items += (
                f'<div class="change-item">'
                f'<span class="new-badge">NEW</span> '
                f'<span class="kw">{escape(c.get("keyword", ""))}</span> '
                f'<span class="root-tag">{escape(c.get("root", ""))}</span>'
                f'</div>\n'
            )

        # 변화율 상승
        rising_up_items = ""
        for c in changes.get("rising_up", [])[:5]:
            rising_up_items += (
                f'<div class="change-item">'
                f'<span class="kw">{escape(c.get("keyword", ""))}</span> '
                f'<span class="up">{c.get("prev", 0):+.1f}% → {c.get("curr", 0):+.1f}%</span> '
                f'<span class="root-tag">{escape(c.get("root", ""))}</span>'
                f'</div>\n'
            )

        # 변화율 하락
        rising_down_items = ""
        for c in changes.get("rising_down", [])[:5]:
            rising_down_items += (
                f'<div class="change-item">'
                f'<span class="kw">{escape(c.get("keyword", ""))}</span> '
                f'<span class="down">{c.get("prev", 0):+.1f}% → {c.get("curr", 0):+.1f}%</span> '
                f'<span class="root-tag">{escape(c.get("root", ""))}</span>'
                f'</div>\n'
            )

        # 약사가치 상승
        value_up_items = ""
        for c in changes.get("value_up", [])[:5]:
            value_up_items += (
                f'<div class="change-item">'
                f'<span class="kw">{escape(c.get("keyword", ""))}</span> '
                f'<span class="up">{c.get("prev", 0)} → {c.get("curr", 0)}</span> '
                f'<span class="root-tag">{escape(c.get("root", ""))}</span>'
                f'</div>\n'
            )

        has_any = (new_rising_items or new_compound_items or rising_up_items
                   or rising_down_items or value_up_items)

        if has_any:
            boxes = ""
            if new_rising_items:
                boxes += f'<div class="change-box"><h4>🔥 새로 급등</h4>{new_rising_items}</div>'
            if new_compound_items:
                boxes += f'<div class="change-box"><h4>🆕 새 복합키워드</h4>{new_compound_items}</div>'
            if rising_up_items:
                boxes += f'<div class="change-box"><h4>📈 변화율 상승</h4>{rising_up_items}</div>'
            if rising_down_items:
                boxes += f'<div class="change-box"><h4>📉 변화율 하락</h4>{rising_down_items}</div>'
            if value_up_items:
                boxes += f'<div class="change-box"><h4>⬆ 약사가치 상승</h4>{value_up_items}</div>'

            changes_html = (
                '<div class="changes-section">'
                f'<h3>📊 이전 대비 변화</h3>'
                f'<div class="prev-time">이전 스캔: {escape(changes.get("prev_time", ""))}</div>'
                f'<div class="changes-grid">{boxes}</div>'
                '</div>'
            )

    # ── 추천 글감 TOP 3 ──
    top_html = ""
    for i, rec in enumerate(top_recs[:3], 1):
        labels_str = " ".join(rec.get("labels", []))
        gap = rec.get("expert_gap", {})
        top_html += (
            '<div class="rec-card">'
            f'<div class="rec-rank">#{i}</div>'
            '<div class="rec-content">'
            f'<div class="rec-keyword">{escape(rec.get("keyword", ""))}</div>'
            '<div class="rec-meta">'
            f'<span class="rec-root">{escape(rec.get("root", ""))}</span>'
            f'<span class="rec-intent">{escape(rec.get("intent", ""))}</span>'
            f'<span class="rec-value">약사가치 {rec.get("pharma_value", 0)}</span>'
            f'<span class="rec-labels">{labels_str}</span>'
            '</div>'
            f'<div class="rec-gap">전문가갭: {gap.get("label", "")} '
            f'(전체 {gap.get("total", 0)} / 약사 {gap.get("expert", 0)})</div>'
            '</div></div>\n'
        )

    # ── 뿌리별 탭 버튼 (active + watch 통합) ──
    all_display_roots = active_roots + watch_roots
    tab_buttons = ""
    for i, r in enumerate(all_display_roots):
        active_cls = " active" if i == 0 else ""
        kw = r["keyword"]
        watch_tag = " 👀" if r.get("status") == "watch" else ""
        tab_buttons += (
            f'<button class="tab-btn{active_cls}" '
            f"onclick=\"showTab('{kw}')\">{escape(kw)}{watch_tag}</button>\n"
        )

    # ── 뿌리별 탭 내용 (active + watch 통합) ──
    tab_contents = ""
    for i, r in enumerate(all_display_roots):
        display = "block" if i == 0 else "none"
        kw = r["keyword"]

        # 급등 알림
        rising_html = ""
        for rk in r.get("rising", []):
            rising_html += f'<span class="rising-badge">🔥 {escape(rk)}</span>\n'

        # 뉴스 이벤트
        news_html = ""
        for ev in r.get("news_events", []):
            news_html += (
                '<div class="news-item">'
                f'<span class="news-trigger">{escape(ev.get("trigger", ""))}</span> '
                f'{escape(ev.get("title", ""))}</div>\n'
            )

        # 복합키워드 테이블
        rows_html = ""
        for c in r.get("compounds", []):
            labels = " ".join(c.get("labels", []))
            vol = c.get("volume")
            cr = c.get("change_rate")  # 단기 3일
            tr = c.get("trend_rate")   # 추세 7일
            cr_str = f"{cr:+.1f}%" if cr is not None else "-"
            tr_str = f"{tr:+.1f}%" if tr is not None else ""
            cr_cls = "positive" if cr is not None and cr >= 20 else (
                "negative" if cr is not None and cr <= -20 else ""
            )
            # 추세는 작게 회색으로 표시
            trend_display = f'<br><span class="trend-sub">7일 {tr_str}</span>' if tr_str else ""
            gap = c.get("expert_gap", {})
            blog_count = c.get("blog_count")
            if vol is not None:
                vol_display = str(vol)
            elif blog_count:
                vol_display = f"블로그 {blog_count}"
            else:
                vol_display = "-"
            bridge = f' → {escape(c.get("bridge_target", ""))}' if c.get("is_bridge") else ""

            rows_html += (
                "<tr>"
                f'<td class="kw-cell">{escape(c.get("keyword", ""))}{bridge}</td>'
                f"<td>{labels}</td>"
                f"<td>{vol_display}</td>"
                f'<td class="{cr_cls}">{cr_str}{trend_display}</td>'
                f'<td>{escape(c.get("intent", ""))}</td>'
                f'<td>{gap.get("label", "")}</td>'
                f'<td class="value-cell">{c.get("pharma_value", 0)}</td>'
                "</tr>\n"
            )

        rising_block = (
            f'<div class="rising-section">{rising_html}</div>' if rising_html else ""
        )
        news_block = (
            f'<div class="news-section"><h4>📰 이벤트 뉴스</h4>{news_html}</div>'
            if news_html else ""
        )

        status_badge = (' <span class="watch-badge">👀 관찰중</span>'
                        if r.get("status") == "watch" else "")
        tab_contents += (
            f'<div class="tab-content" id="tab-{kw}" style="display:{display}">'
            f'<div class="section-header">{escape(kw)} '
            f'<span class="category-badge">{escape(r.get("category", ""))}</span>'
            f'{status_badge}</div>'
            f'{rising_block}'
            f'{news_block}'
            '<table class="kw-table"><thead><tr>'
            '<th>복합키워드</th><th>라벨</th><th>검색량</th><th>변화율(3일)</th>'
            '<th>의도</th><th>전문가갭</th><th>약사가치</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table>'
            '</div>\n'
        )

    # ── Watch 섹션 (탭에 통합되었으므로 별도 표시 불필요) ──
    watch_html = ""

    # ── 미확인 후보 섹션 ──
    unid_html = ""
    if unidentified:
        unid_rows = ""
        for u in unidentified:
            sources = ", ".join(u.get("found_from", []))
            unid_rows += (
                "<tr>"
                f'<td>{escape(u.get("word", ""))}</td>'
                f'<td>{u.get("count", 0)}</td>'
                f'<td>{escape(sources)}</td>'
                f'<td>{escape(u.get("first_seen", ""))}</td>'
                "</tr>\n"
            )
        unid_html = (
            '<div class="unid-section">'
            '<h3>🔍 미확인 후보</h3>'
            '<p class="unid-desc">이번 분석에서 자주 등장했지만 known_products.json에 없는 단어입니다. '
            '제품/성분이 맞다면 사전에 추가해 주세요.</p>'
            '<table class="kw-table">'
            '<thead><tr><th>단어</th><th>빈도</th><th>출처 뿌리</th><th>최초 발견</th></tr></thead>'
            f'<tbody>{unid_rows}</tbody></table></div>'
        )

    # 최종 조합 (CSS/JS는 상수이므로 중괄호 충돌 없음)
    top_section = top_html if top_html else '<div style="color:#8b949e">추천 글감이 없습니다.</div>'

    html = (
        '<!DOCTYPE html>\n<html lang="ko">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>키워드 딥다이브 스캐너</title>\n'
        f'<style>{CSS}</style>\n'
        '</head>\n<body>\n'
        '<h1>키워드 딥다이브 스캐너</h1>\n'
        f'<div class="updated">마지막 업데이트: {updated}</div>\n'
        f'{api_warning_html}\n'
        f'{changes_html}\n'
        '<h3>📝 오늘의 추천 글감 TOP 3</h3>\n'
        f'{top_section}\n'
        f'<div class="tab-bar">{tab_buttons}</div>\n'
        f'{tab_contents}\n'
        f'{watch_html}\n'
        f'{unid_html}\n'
        f'<script>{JS}</script>\n'
        '</body>\n</html>'
    )

    return html


def main():
    data = load_latest()
    if not data:
        print("latest.json이 없습니다. dive.py를 먼저 실행하세요.")
        return

    os.makedirs(DOCS_DIR, exist_ok=True)
    html = build_html(data)
    output_path = os.path.join(DOCS_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"대시보드 생성: {output_path}")


if __name__ == "__main__":
    main()
