"""점수 식 되짚어 보기(2026-09-20): 이미 글을 쓴 키워드에서, 점수가 높았던 쪽이 실제로 검색 유입을 가져왔나.

대상: latest.json 에서 '쓴 적 있음(previously_written)' + 점수 내역(score_parts)이 있는 복합키워드.
결과: 최근 N일 유입 검색어 기록(inflow-keyword-analyzer 의 inflow_history.json)에서 그 키워드의 말이 전부 든 검색어가
      며칠 나왔고 유입 비율(%)을 얼마나 차지했나.
보는 것: 점수 식의 각 배수(자리·쇼핑 덮임·포화도·약사 보정·검색량)가 '유입 있음/없음'을 가르는가.
        모멘텀은 그날그날 바뀌는 값이라 빼고, 나머지를 곱한 '고정 점수'로 본다.
한계: 검색 화면은 글 쓸 당시가 아니라 지금 모습이고, 내 글이 이미 그 화면에 들어가 있다. 표본도 100개 안팎이라 방향만 본다.

실행: python scripts/backtest_inflow.py [--inflow 경로|URL] [--serp-extra a.json b.json] [--days 90] [--out data/backtest.json]
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(__file__))
import dive  # noqa: E402  (_norm_match·serp_for 를 그대로 쓴다)

INFLOW_URL = "https://raw.githubusercontent.com/justpassthrough/inflow-keyword-analyzer/main/data/inflow_history.json"


def load_json(src):
    if src.startswith("http"):
        r = requests.get(src, timeout=30)
        r.raise_for_status()
        return r.json()
    with open(src, "r", encoding="utf-8") as f:
        return json.load(f)


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                rk[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return rk
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return round(num / den, 3) if den else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inflow", default=INFLOW_URL)
    ap.add_argument("--serp-extra", nargs="*", default=[])
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--out", default=os.path.join(dive.DATA_DIR, "backtest.json"))
    a = ap.parse_args()

    latest = load_json(os.path.join(dive.DATA_DIR, "latest.json"))
    serp = dive.load_serp()
    for p in a.serp_extra:
        serp.update(load_json(p))
    hist = load_json(a.inflow)
    cut = (datetime.now() - timedelta(days=a.days)).strftime("%Y-%m-%d")
    inflow = []   # (정규화한 검색어, 날짜, 비율)
    for day, rows in hist.items():
        if not day[:4].isdigit() or day < cut or not isinstance(rows, list):
            continue
        for r in rows:
            inflow.append((dive._norm_match(r.get("keyword", "")), day, float(r.get("ratio") or 0)))

    rows = []
    for root in latest["roots"]:
        for c in root["compounds"]:
            parts = c.get("score_parts")
            if not (c.get("previously_written") and parts):
                continue
            sp = dive.serp_for(serp, c["keyword"])
            tokens = [dive._norm_match(t) for t in c["keyword"].split() if t]
            hits = [(d, ratio) for kw, d, ratio in inflow if all(t in kw for t in tokens)]
            y = sp.get("first_blog_y") if sp else None
            pos = (1.1 if y < 1000 else 1.05 if y < 2500 else 1.0 if y < 5000 else 0.95) if isinstance(y, (int, float)) else None
            shop = (0.97 if sp.get("shop_above_blog") else 1.0) if sp else None
            static = None
            if pos is not None:
                static = round(parts["volume"] * pos * shop * parts["saturation"] * parts["fit"], 3)
            rows.append({
                "keyword": c["keyword"], "root": root["keyword"], "search_volume": c.get("search_volume"), "intent": c.get("intent"),
                "days_since_written": c.get("days_since_written"),
                "volume": parts["volume"], "saturation": parts["saturation"], "fit": parts["fit"],
                "first_blog_y": y, "position": pos, "shop_above_blog": sp.get("shop_above_blog") if sp else None,
                "my_rank": sp.get("my_rank") if sp else None, "static_score": static,
                "inflow_days": len({d for d, _ in hits}), "inflow_ratio_sum": round(sum(r for _, r in hits), 2),
            })

    def table(title, key, buckets):
        print(f"\n[{title}]  구간 · 개수 · 유입 있음 비율 · 평균 유입 일수 · 내 글이 화면에 보임")
        out = []
        for label, fn in buckets:
            g = [r for r in rows if r.get(key) is not None and fn(r[key])]
            if not g:
                continue
            hit = sum(1 for r in g if r["inflow_days"] > 0)
            seen = sum(1 for r in g if r["my_rank"])
            line = {"bucket": label, "n": len(g), "hit_rate": round(hit / len(g) * 100), "avg_days": round(sum(r["inflow_days"] for r in g) / len(g), 1), "my_rank_seen": seen}
            out.append(line)
            print(f"  {label:<14} {len(g):>3}  {line['hit_rate']:>3}%  {line['avg_days']:>5}  {seen}")
        return out

    n = len(rows)
    ver = [r for r in rows if r["static_score"] is not None]
    print(f"대상 {n}개(화면 확인 {len(ver)}개) · 유입 기록 최근 {a.days}일 · 유입 있음 {sum(1 for r in rows if r['inflow_days'] > 0)}개")
    res = {
        "generated_at": datetime.now().isoformat(timespec="minutes"), "days": a.days, "n": n, "n_verified": len(ver),
        "position": table("자리(블로그 영역 y)", "first_blog_y", [("<1,000px", lambda v: v < 1000), ("<2,500px", lambda v: 1000 <= v < 2500), ("<5,000px", lambda v: 2500 <= v < 5000), ("5,000px↓", lambda v: v >= 5000)]),
        "shop": table("쇼핑이 블로그 위를 덮음", "shop_above_blog", [("안 덮음", lambda v: v is False), ("덮음", lambda v: v is True)]),
        "saturation": table("포화도 배수", "saturation", [("1.2 (문서 적음)", lambda v: v == 1.2), ("1.0", lambda v: v == 1.0), ("0.8 (문서 많음)", lambda v: v == 0.8)]),
        "fit": table("약사 보정", "fit", [("1.1↑", lambda v: v >= 1.1), ("1.05", lambda v: v == 1.05), ("1.0", lambda v: v == 1.0), ("<1.0", lambda v: v < 1.0)]),
        "volume": table("월 검색량", "search_volume", [("<1,000", lambda v: v < 1000), ("1,000~5,000", lambda v: 1000 <= v < 5000), ("5,000~20,000", lambda v: 5000 <= v < 20000), ("20,000↑", lambda v: v >= 20000)]),
    }
    if ver:
        q = sorted(r["static_score"] for r in ver)
        t1, t2 = q[len(q) // 3], q[2 * len(q) // 3]
        res["score_thirds"] = table("고정 점수 3등분", "static_score", [("하위 1/3", lambda v: v < t1), ("중간", lambda v: t1 <= v < t2), ("상위 1/3", lambda v: v >= t2)])
        res["spearman_score_vs_days"] = spearman([r["static_score"] for r in ver], [r["inflow_days"] for r in ver])
        res["spearman_volume_only_vs_days"] = spearman([r["volume"] for r in ver], [r["inflow_days"] for r in ver])
        print(f"\n순위 상관(스피어만): 고정 점수↔유입 일수 {res['spearman_score_vs_days']} · 검색량만↔유입 일수 {res['spearman_volume_only_vs_days']}")
    res["rows"] = sorted(rows, key=lambda r: -r["inflow_days"])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
