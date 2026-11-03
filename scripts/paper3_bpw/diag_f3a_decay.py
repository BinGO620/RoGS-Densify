#!/usr/bin/env python
"""diag_f3a_decay.py — F3a γ 对比度随事件序数衰减的零 GPU 诊断（只读 trace+console）。

背景：580 帧 seed0 装置门 F3a FAIL（mean 1.1107 < 1.15），衰减随序数单调
（init 段 1.201 → ord40-49 = 1.007）。本脚本量化四个候选机制并给出净对比：

  H1 选择自由度耗尽（否证）：freedom = 1 − K_i/|pool|（池规模取自 **console** 的
     `pool=` 字段；trace 默认 `trace_pool: False` 不落池成员，只落选中点）。
     实测 freedom 全程 0.49–0.69 ⇒ 键有充分排序余地。
  H2 池 s 同质化（否证）：选中点 s-CV 不降反升（G 臂 0.68 → 1.07）。
  H3 同键跨图方差（**新发现，晚段主导**）：k0/G 零对照比（两臂同为 γ=0 键、
     消费同一计划、只差各自地图）在 ord<31 紧贴 1.00（0.998–1.003），
     map41+ 起漂移（1.03–1.12）⇒ F3a 的跨臂统计量晚段失去判别力。
  H4 g–s 信号收敛（弱证据）：G 臂（键=g）选中集内 rankcorr(g,s) 0.08 → 0.19，
     有上升趋势但远不足以解释衰减。

  **净对比** = observed(S/G) ÷ null(k0/G)：init 1.23 → map11 1.16 → map21 1.13
  → map31 1.04 → map41 0.99 → map51 0.94 ⇒ γ 对放置 s 剖面的效应**早段真实、
  晚段死亡**。F3a 全局门 1.15 的标定被两个伪影抬高：冒烟 65% 事件是 init 段
  （全长只有 19%）+ 冒烟地图年轻（零对照未漂移）。

  池成员（未选候选的 g/s）不在任何盘上工件里 ⇒ 「键在晚段池上是否还有排序杠杆」
  需一次 `trace_pool: true` 重跑才能分解（日志开关，不改选择行为）。

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/diag_f3a_decay.py \
      --g-trace <G trace> --s-trace <S trace> --k0-trace <k0 trace> \
      --g-console <G console.log> --s-console <S console.log> --k0-console <k0 console.log> \
      --label seed0_580f --out-md … --out-json …
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
from pathlib import Path

N_INIT_DEFAULT = 11
_CONSOLE_PAT = re.compile(
    r"iter=(\d+) ord=(\d+) gamma=([\d.]+) ref=(\d+) pool=(\d+) k_plan=(\d+) sel=(\d+)")


def read_selections(trace: Path):
    """→ {event: {"s": [选中点 sparsity…], "g": [mean_grad…]}}（只读 sel 行）。"""
    per = {}
    with open(trace) as fh:
        for r in csv.DictReader(fh):
            if r["kind"] != "sel":
                continue
            d = per.setdefault(int(r["event"]), {"s": [], "g": []})
            d["s"].append(float(r["sparsity"]))
            d["g"].append(float(r["mean_grad"]))
    return per


def read_console(console: Path):
    """→ {event: {"pool": int, "k_plan": int}}（console 的 `iter=… ord=… pool=…` 行）。"""
    per = {}
    for line in open(console, errors="ignore"):
        m = _CONSOLE_PAT.search(line)
        if m:
            e = int(m.group(2))
            per.setdefault(e, {"pool": int(m.group(5)), "k_plan": int(m.group(6))})
    return per


def _ms(vals):
    return sum(vals) / len(vals) if vals else None


def _median_or_none(vals):
    vals = [v for v in vals if v is not None]
    return st.median(vals) if vals else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--g-trace", required=True)
    ap.add_argument("--s-trace", required=True)
    ap.add_argument("--k0-trace", required=True)
    ap.add_argument("--g-console", required=True)
    ap.add_argument("--s-console", required=True)
    ap.add_argument("--k0-console", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--n-init", type=int, default=N_INIT_DEFAULT)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args(argv)

    sg = read_selections(Path(args.g_trace))
    ss = read_selections(Path(args.s_trace))
    sk = read_selections(Path(args.k0_trace))
    cg = read_console(Path(args.g_console))
    ck = read_console(Path(args.k0_console))

    common = sorted(set(sg) & set(ss) & set(sk))
    per_event = {}
    for e in common:
        ms_g, ms_s, ms_k = _ms(sg[e]["s"]), _ms(ss[e]["s"]), _ms(sk[e]["s"])
        pool_g = cg.get(e, {}).get("pool")
        k_plan = ck.get(e, {}).get("k_plan", len(sk[e]["s"]))
        item = {
            "mean_s_G": ms_g, "mean_s_S": ms_s, "mean_s_k0": ms_k,
            "observed": (ms_s / ms_g) if (ms_g and ms_g > 0 and ms_s) else None,
            "null": (ms_k / ms_g) if (ms_g and ms_g > 0 and ms_k) else None,
            "s_cv_G": (st.pstdev(sg[e]["s"]) / ms_g) if (ms_g and ms_g > 0
                                                       and len(sg[e]["s"]) > 1) else None,
        }
        item["net"] = (item["observed"] / item["null"]) if (item.get("observed")
                                                            and item.get("null")) else None
        item["freedom"] = (1 - k_plan / pool_g) if (pool_g and pool_g > 0) else None
        per_event[e] = item

    bounds = [(0, args.n_init, "init(ord<%d)" % args.n_init)]
    last = common[-1] + 1 if common else 0
    for lo in range(args.n_init, last, 10):
        bounds.append((lo, min(lo + 10, last),
                       "map(%d-%d)" % (lo, min(lo + 9, last - 1))))
    segs = []
    for lo, hi, name in bounds:
        ms = [per_event[e] for e in common if lo <= e < hi]
        if not ms:
            continue
        segs.append({
            "seg": name, "n_events": len(ms),
            "observed_median": _median_or_none(m["observed"] for m in ms),
            "null_median": _median_or_none(m["null"] for m in ms),
            "net_median": _median_or_none(m["net"] for m in ms),
            "net_mean": _ms([m["net"] for m in ms if m["net"] is not None]),
            "freedom_median": _median_or_none(m["freedom"] for m in ms),
            "s_cv_G_median": _median_or_none(m["s_cv_G"] for m in ms),
        })

    report = {
        "generated_by": "scripts/paper3_bpw/diag_f3a_decay.py",
        "label": args.label,
        "inputs": {"g_trace": args.g_trace, "s_trace": args.s_trace,
                   "k0_trace": args.k0_trace, "g_console": args.g_console,
                   "s_console": args.s_console, "k0_console": args.k0_console},
        "n_common_events": len(common),
        "segments": segs,
        "per_event": {str(e): per_event[e] for e in common},
    }

    L = []
    A = L.append
    A("# F3a 衰减诊断（%s）——零 GPU，只读 trace + console\n" % args.label)
    A("")
    A("- observed = S/G 选中 mean_s 比；null = k0/G 同键跨图零对照比（同计划、γ=0、只差地图）；")
    A("- **net = observed ÷ null**（γ 净对比）；freedom = 1 − k_plan/pool（池规模取 console）。")
    A("")
    A("| 段 | n | observed | null | **net** | freedom | s-CV(G) |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for sgmt in segs:

        def _f(v):
            return "n/a" if v is None else "%.3f" % v

        A("| %s | %d | %s | %s | **%s** | %s | %s |" % (
            sgmt["seg"], sgmt["n_events"], _f(sgmt["observed_median"]),
            _f(sgmt["null_median"]), _f(sgmt["net_median"]),
            _f(sgmt["freedom_median"]), _f(sgmt["s_cv_G_median"])))
    A("")
    A("> 判读：net ≥1.15 的段 = γ 有真对比；net ≈1 且 null 开始漂移的段 = 统计量")
    A("> 失去判别力（同键跨图方差 ≥ γ 信号）；net <1 = γ 净效应消失/反转。")
    md_text = "\n".join(L) + "\n"

    Path(args.out_md).write_text(md_text, encoding="utf-8")
    Path(args.out_json).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    print(md_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
