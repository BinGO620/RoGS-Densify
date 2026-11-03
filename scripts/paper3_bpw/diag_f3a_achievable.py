#!/usr/bin/env python
"""diag_f3a_achievable.py — 用 trace_pool 落盘的池成员分解 F3a 晚段死因（P3-D2-013 甲案②）。

前置：诊断重跑（config `trace_pool: true`，纯日志开关）产出的 trace 含
`pool_only` 行（未选池候选，带 mean_grad/mean_grad 键所需的全部列）。

对每个事件（**各自臂自己的池**，同 run 内配对）：
  K_i         = |sel|（F1 保证 == k_plan）
  sel_γ0      = top-K by g          （γ=0 键，stable，平局按 idx 升序）
  sel_γ1      = top-K by g·s        （γ=1 键）
  achievable  = mean_s(sel_γ1) / mean_s(sel_γ0)   ← 同池同 K 下 γ 键的**理论**对比度
  observed    = mean_s(sel_S) / mean_s(sel_G)     ← 两臂实际选中集之比（跨臂）

判读（对照 `fdose_f3a_decay_diagnosis_2026-11-01.md` 的净对比衰减）：
  achievable 晚段仍 ≥1.15 而 observed →1 ⇒ 键有杠杆、**跨臂统计量失判**（H3 主导）
    ⇒ A4 形态 = 统计量改造（零对照引用/臂内可达对比），不是分段弃判；
  achievable 晚段也 →1 ⇒ 键在晚段池上**无排序杠杆**（池构成使然，H2' 成立）
    ⇒ A4 形态 = 分段门（早段硬门 + 晚段报告项）。

用法：
  $PY scripts/paper3_bpw/diag_f3a_achievable.py \
      --g-trace <G trace 含 pool_only> --s-trace <S trace 含 pool_only> \
      --label diag_rerun --out-md … --out-json …
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from pathlib import Path

N_INIT_DEFAULT = 11


def read_pool_trace(path: Path):
    """→ {event: {"rows": [(idx, g, s)…全池], "sel": [(idx, g, s)…]}}。"""
    per = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            kind = r["kind"]
            if kind not in ("sel", "pool_only"):
                continue
            e = int(r["event"])
            d = per.setdefault(e, {"rows": [], "sel": []})
            item = (int(r["gauss_idx"]), float(r["mean_grad"]), float(r["sparsity"]))
            d["rows"].append(item)
            if kind == "sel":
                d["sel"].append(item)
    return per


def _topk(rows, key, k):
    return sorted(rows, key=lambda t: (-key(t), t[0]))[:k]


def _ms(items):
    return sum(s for _, _, s in items) / len(items) if items else None


def _spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    rx = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: xs[i]))}
    ry = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: ys[i]))}
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--g-trace", required=True)
    ap.add_argument("--s-trace", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--n-init", type=int, default=N_INIT_DEFAULT)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args(argv)

    g = read_pool_trace(Path(args.g_trace))
    s = read_pool_trace(Path(args.s_trace))

    n_pool_only = sum(len(d["rows"]) - len(d["sel"]) for d in g.values())
    if n_pool_only == 0:
        raise SystemExit("ERROR: G trace 无 pool_only 行 —— 该 trace 不是 trace_pool=true "
                         "的重跑产物，本分析不适用")

    common = sorted(set(g) & set(s))
    per_event = {}
    for e in common:
        rows = g[e]["rows"]
        k = len(g[e]["sel"])
        pool_s = [x[2] for x in rows]
        ms_pool = st.mean(pool_s) if pool_s else 0
        sel0 = _topk(rows, lambda t: t[1], k)
        sel1 = _topk(rows, lambda t: t[1] * t[2], k)
        a0, a1 = _ms(sel0), _ms(sel1)
        og, os_ = _ms(g[e]["sel"]), _ms(s[e]["sel"])
        # 2×2 分解（P3-D2-013 甲案②）：把跨臂观测比拆成「键效应」×「池基线漂移」。
        #   A = ms(g-topK on pool_G)（=G 实测选中）；B = ms(g·s-topK on pool_G)
        #   C = ms(g-topK on pool_S)（S 臂的反事实 γ=0 基线）；D = ms(g·s-topK on pool_S)（=S 实测）
        #   observed = D/A = achievable_S(D/C) × 池基线(C/A)
        rows_s = s[e]["rows"]
        k_s = len(s[e]["sel"])
        c_ms = _ms(_topk(rows_s, lambda t: t[1], k_s))
        per_event[e] = {
            "n_pool": len(rows), "k": k,
            "freedom": (1 - k / len(rows)) if rows else None,
            "s_cv_pool": (st.pstdev(pool_s) / ms_pool) if (ms_pool > 0 and len(pool_s) > 1) else None,
            "rankcorr_g_gs_pool": _spearman([x[1] for x in rows],
                                            [x[1] * x[2] for x in rows]),
            "achievable": (a1 / a0) if (a0 and a0 > 0 and a1 is not None) else None,
            "observed": (os_ / og) if (og and og > 0 and os_ is not None) else None,
            "baseline_g_G": a0, "key_g_s_G": a1,
            "baseline_g_S": c_ms, "key_g_s_S": os_,
            "achievable_S": (os_ / c_ms) if (c_ms and c_ms > 0 and os_ is not None) else None,
            "pool_baseline_ratio": (c_ms / a0) if (a0 and a0 > 0 and c_ms is not None) else None,
        }

    last = common[-1] + 1 if common else 0
    bounds = [(0, args.n_init, "init(ord<%d)" % args.n_init)]
    for lo in range(args.n_init, last, 10):
        bounds.append((lo, min(lo + 10, last),
                       "map(%d-%d)" % (lo, min(lo + 9, last - 1))))
    segs = []
    for lo, hi, name in bounds:
        ms = [per_event[e] for e in common if lo <= e < hi]
        if not ms:
            continue

        def _med(key):
            vals = [m[key] for m in ms if m.get(key) is not None]
            return st.median(vals) if vals else None

        segs.append({
            "seg": name, "n_events": len(ms),
            "observed_median": _med("observed"),
            "achievable_median": _med("achievable"),
            "achievable_mean": (lambda v: st.mean(v) if v else None)(
                [m["achievable"] for m in ms if m.get("achievable") is not None]),
            "achievable_S_median": _med("achievable_S"),
            "achievable_S_mean": (lambda v: st.mean(v) if v else None)(
                [m["achievable_S"] for m in ms if m.get("achievable_S") is not None]),
            "pool_baseline_median": _med("pool_baseline_ratio"),
            "freedom_median": _med("freedom"),
            "s_cv_pool_median": _med("s_cv_pool"),
            "rankcorr_median": _med("rankcorr_g_gs_pool"),
        })

    all_ach_s = [m["achievable_S"] for m in per_event.values()
                 if m.get("achievable_S") is not None]
    report_extra = {
        "achievable_S_mean_all": st.mean(all_ach_s) if all_ach_s else None,
        "achievable_S_share_ge_110": (sum(1 for v in all_ach_s if v >= 1.10) / len(all_ach_s))
                                     if all_ach_s else None,
        "achievable_S_share_ge_115": (sum(1 for v in all_ach_s if v >= 1.15) / len(all_ach_s))
                                     if all_ach_s else None,
    }

    report = {
        "generated_by": "scripts/paper3_bpw/diag_f3a_achievable.py",
        "label": args.label,
        "inputs": {"g_trace": args.g_trace, "s_trace": args.s_trace},
        "n_common_events": len(common),
        "n_pool_rows_G": sum(len(d["rows"]) for d in g.values()),
        "segments": segs,
        "summary": report_extra,
        "per_event": {str(e): per_event[e] for e in common},
    }

    L = []
    A = L.append
    A("# F3a 池成员可达对比（%s）——trace_pool 诊断重跑\n" % args.label)
    A("")
    A("- achievable = 同池同 K 下 top-K by `g·s` vs by `g` 的 mean_s 比（γ 键的理论对比度）；")
    A("- observed = 两臂实际选中集 mean_s 比（跨臂）。二者之差 = 跨臂地图分叉的稀释。")
    A("")
    A("| 段 | n | observed | **achievable(G池)** | **achievable_S(S池)** | 池基线 C/A | freedom | rankcorr |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for sgmt in segs:

        def _f(v):
            return "n/a" if v is None else "%.3f" % v

        A("| %s | %d | %s | **%s** | **%s** | %s | %s | %s |" % (
            sgmt["seg"], sgmt["n_events"], _f(sgmt["observed_median"]),
            _f(sgmt["achievable_median"]), _f(sgmt["achievable_S_median"]),
            _f(sgmt["pool_baseline_median"]), _f(sgmt["freedom_median"]),
            _f(sgmt["rankcorr_median"])))
    A("")
    A("**同池键对比（F3a′ 候选统计量，S 臂反事实）**：均值 %s，事件 ≥1.10 占比 %s，"
      "≥1.15 占比 %s（共 %d 事件）。" % (
          _f(report_extra["achievable_S_mean_all"]),
          "%.2f" % report_extra["achievable_S_share_ge_110"],
          "%.2f" % report_extra["achievable_S_share_ge_115"],
          len(all_ach_s)))
    A("")
    A("> 判读：achievable 晚段 ≥1.15 而 observed →1 ⇒ 键有杠杆、跨臂统计失判（A4=统计量改造）；")
    A("> achievable 晚段也 →1 ⇒ 键在晚段池上无杠杆（A4=分段门）。")
    md_text = "\n".join(L) + "\n"

    Path(args.out_md).write_text(md_text, encoding="utf-8")
    Path(args.out_json).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    print(md_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
