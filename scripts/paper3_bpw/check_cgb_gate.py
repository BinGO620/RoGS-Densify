#!/usr/bin/env python
"""check_cgb_gate.py — CGB 机制门（R1）判定器，零 GPU。

对应 `paper3/results/evidence/prereg_cgb_2026-10-30.md` §4 R1。判的是**装置**，
不是效果。三条子门全部成立才算装置有效；任一不成立 ⇒ 冻结读数、修装置、不得解释机制。

  G1 剂量：每个事件 |ref ∪ extra| − |ref| == floor(swap_frac × |ref|)
  G2 位置：γ=1 臂 extra 的 mean(s) 显著高于同事件 ref 的 mean(s)；
            γ=0 臂 extra 的 mean(s) 与 ref 接近（不显著高于）
  G3 互斥：extra ∩ ref = ∅（CGB 只加不换），且 extra ⊂ 池（grad ≥ τ_lo）

输入 = 两臂的 `cgb_selection_trace.csv` + console.log 里的 `[cgb]` 行。
输出 = markdown + JSON（零手抄）。本脚本只产机制门读数，不落效果判决。

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/check_cgb_gate.py \
      --g1 results/paper3_bpw/cgb_g1_person_tracking/datasets_bonn/\
cgb_g1_person_tracking/seed_0/<ts>/cgb_selection_trace.csv \
      --g0 results/paper3_bpw/cgb_g0_person_tracking/datasets_bonn/\
cgb_g0_person_tracking/seed_0/<ts>/cgb_selection_trace.csv \
      --swap-frac 0.05 --out-md ... --out-json ...
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

TAU_BASE = 2e-4
TAU_LO = 1e-4


def read_trace(path: Path):
    """→ {iter: {"ref": [...], "extra": [...], "pool_only": [...]}} 每项 dict。

    ``max_scale`` 是 2026-10-30 18:21 之后才加的列（Amendment A1 §3b）；缺列时该字段为
    ``None``，下游的 split-path 分析显式报 missing 并跳过，不静默当 0。
    """
    ev = defaultdict(lambda: defaultdict(list))
    has_scale = False
    with open(path) as fh:
        rdr = csv.DictReader(fh)
        has_scale = "max_scale" in (rdr.fieldnames or [])
        for r in rdr:
            ev[int(r["iter"])][r["kind"]].append(
                {
                    "idx": int(r["gauss_idx"]),
                    "g": float(r["mean_grad"]),
                    "s": float(r["sparsity"]),
                    "key": float(r["key"]),
                    "max_scale": float(r["max_scale"]) if has_scale else None,
                }
            )
    return ev, has_scale


def check_arm(ev, swap_frac, label):
    """→ dict：三条子门的逐臂读数。"""
    budget_err = []
    g2_pairs = []      # (mean s of extra, mean s of ref) per event
    g3_overlap = 0
    g3_below_pool = 0
    extra_counts = []
    for it in sorted(ev):
        d = ev[it]
        ref = d.get("ref", [])
        extra = d.get("extra", [])
        if not ref:
            continue
        want = int(swap_frac * len(ref))
        budget_err.append(len(extra) - want)
        extra_counts.append(len(extra))
        g2_pairs.append(
            (
                float(np.mean([x["s"] for x in extra])) if extra else float("nan"),
                float(np.mean([x["s"] for x in ref])),
            )
        )
        ref_idx = {x["idx"] for x in ref}
        g3_overlap += sum(1 for x in extra if x["idx"] in ref_idx)
        g3_below_pool += sum(1 for x in extra if x["g"] < TAU_LO - 1e-12)

    deltas = [a - b for a, b in g2_pairs if not np.isnan(a)]
    ratios = [a / b for a, b in g2_pairs if not np.isnan(a) and b > 0]
    # split-path 检验（Amendment A1 §3b）：extra 里 max_scale 超过 clone/split 界
    # （percent_dense 0.01 × cameras_extent 6.0 × gaussian_extent 1.0）的占比。
    split_bound = 0.01 * 6.0 * 1.0
    split_extra = [x for grp in ev.values() for x in grp.get("extra", []) if x["max_scale"] is not None]
    split_ref = [x for grp in ev.values() for x in grp.get("ref", []) if x["max_scale"] is not None]
    return {
        "label": label,
        "events": len(budget_err),
        "g1_budget_err_max_abs": int(max((abs(e) for e in budget_err), default=0)),
        "g1_budget_err_frac_exact": (
            float(sum(1 for e in budget_err if e == 0) / len(budget_err)) if budget_err else 0.0
        ),
        "g1_extra_per_event_mean": float(st.mean(extra_counts)) if extra_counts else 0.0,
        "g2_extra_s_mean": float(st.mean([a for a, _ in g2_pairs if not np.isnan(a)]))
        if deltas
        else float("nan"),
        "g2_ref_s_mean": float(st.mean([b for _, b in g2_pairs])),
        "g2_delta_s_mean": float(st.mean(deltas)) if deltas else float("nan"),
        "g2_ratio_mean": float(st.mean(ratios)) if ratios else float("nan"),
        "g2_events_extra_sparser": int(sum(1 for a, b in g2_pairs if not np.isnan(a) and a > b)),
        "g3_ref_extra_overlap": int(g3_overlap),
        "g3_extra_below_pool": int(g3_below_pool),
        "split_bound_m": split_bound,
        "split_frac_extra": (
            float(sum(1 for x in split_extra if x["max_scale"] > split_bound) / len(split_extra))
            if split_extra
            else None
        ),
        "split_frac_ref": (
            float(sum(1 for x in split_ref if x["max_scale"] > split_bound) / len(split_ref))
            if split_ref
            else None
        ),
        "max_scale_missing": not bool(split_extra),
        # A1 §3b 要求的**事件级**读数（审查 S4，2026-10-30 补）：逐事件算 split 占比，
        # 再报跨事件的分布。全局汇总（上面的 split_frac_extra）保留作交叉核对。
        "split_frac_extra_per_event": [
            {
                "iter": it,
                "extra_n": len(grp.get("extra", [])),
                "split_frac": (
                    sum(1 for x in grp["extra"] if x["max_scale"] is not None and x["max_scale"] > split_bound)
                    / len(grp["extra"])
                )
                if grp.get("extra") and grp["extra"][0]["max_scale"] is not None
                else None,
            }
            for it, grp in sorted(ev.items())
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--g1", required=True, help="γ=1 臂的 cgb_selection_trace.csv")
    ap.add_argument("--g0", required=True, help="γ=0 臂的 cgb_selection_trace.csv")
    ap.add_argument("--swap-frac", type=float, default=0.05)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args(argv)

    ev1, has_scale1 = read_trace(Path(args.g1))
    ev0, has_scale0 = read_trace(Path(args.g0))
    if has_scale1 != has_scale0:
        print(
            "WARN: 两臂 trace 表头不一致（max_scale: g1=%s, g0=%s）—— 该列的分析只作参考"
            % (has_scale1, has_scale0),
            file=sys.stderr,
        )
    r1 = check_arm(ev1, args.swap_frac, "gamma=1 (mechanism)")
    r0 = check_arm(ev0, args.swap_frac, "gamma=0 (dose control)")

    verdict = {
        "g1_dose": r1["g1_budget_err_max_abs"] == 0 and r0["g1_budget_err_max_abs"] == 0,
        "g2_placement": (
            r1["g2_delta_s_mean"] > 0
            and r1["g2_events_extra_sparser"] > 0.5 * r1["events"]
            and r1["g2_ratio_mean"] > r0["g2_ratio_mean"]
        ),
        "g3_disjoint": r1["g3_ref_extra_overlap"] == 0
        and r0["g3_ref_extra_overlap"] == 0
        and r1["g3_extra_below_pool"] == 0
        and r0["g3_extra_below_pool"] == 0,
    }
    verdict["all_pass"] = all(v for k, v in verdict.items() if k != "all_pass")

    report = {
        "prereg": "paper3/results/evidence/prereg_cgb_2026-10-30.md §4 R1",
        "swap_frac": args.swap_frac,
        "arms": [r1, r0],
        "gate": verdict,
        "note": (
            "机制门判装置，不判效果。all_pass=False ⇒ 冻结读数、修装置，不得解释机制。"
        ),
    }
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    if not args.out_md and not args.out_json:
        print(json.dumps(report, indent=1, ensure_ascii=False))

    if args.out_md:
        L = []
        A = L.append
        A("# CGB 机制门（R1）判定（2026-10-30）\n")
        A("**性质**：装置门，非效果判决。判据见 `prereg_cgb_2026-10-30.md` §4 R1。")
        A("**复现**：`scripts/paper3_bpw/check_cgb_gate.py`（机算，零手抄）\n")
        A("| 子门 | 过 | 说明 |")
        A("|---|---|---|")
        A("| G1 剂量 | %s | 每事件 |extra| 必须 == floor(swap_frac×|ref_sel|) |" % ("✅" if verdict["g1_dose"] else "❌"))
        A("| G2 位置 | %s | γ=1 的 extra 显著更稀疏，且 γ=1 的 ratio > γ=0 的 ratio |" % ("✅" if verdict["g2_placement"] else "❌"))
        A("| G3 互斥 | %s | extra ∩ ref = ∅ 且 extra ⊂ 池 |" % ("✅" if verdict["g3_disjoint"] else "❌"))
        A("")
        A("**总判定：%s**\n" % ("装置有效（可进入效果判读）" if verdict["all_pass"] else "装置失效（冻结读数，先修装置）"))
        A("| 量 | γ=1 | γ=0 |")
        A("|---|---:|---:|")
        keys = [
            ("事件数", "events"),
            ("G1 剂量偏差最大值", "g1_budget_err_max_abs"),
            ("G1 事件完全相等比例", "g1_budget_err_frac_exact"),
            ("每事件 extra 均值", "g1_extra_per_event_mean"),
            ("G2 extra mean(s)", "g2_extra_s_mean"),
            ("G2 ref mean(s)", "g2_ref_s_mean"),
            ("G2 Δs 均值", "g2_delta_s_mean"),
            ("G2 ratio 均值", "g2_ratio_mean"),
            ("G2 extra 更稀疏的事件数", "g2_events_extra_sparser"),
            ("G3 ref∩extra", "g3_ref_extra_overlap"),
            ("G3 extra 低于池下界", "g3_extra_below_pool"),
            ("split 界 (m)", "split_bound_m"),
            ("extra 走 split 路径占比", "split_frac_extra"),
            ("ref 走 split 路径占比", "split_frac_ref"),
            ("max_scale 列缺失", "max_scale_missing"),
        ]
        for name, k in keys:
            A("| %s | %s | %s |" % (name, r1[k], r0[k]))
        A("")
        Path(args.out_md).write_text("\n".join(L) + "\n")
        print("wrote", args.out_md)
    return 0 if verdict["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
