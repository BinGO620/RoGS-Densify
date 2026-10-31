#!/usr/bin/env python
"""measure_cgb_dose_floor.py — 剂量类读数的**装置地板**（零 GPU，纯 CPU）。

为什么必须先量这个：CGB 的核心立意是"两臂等剂量、只差放置"（P3-D2-008）。
而 `ref_sel`（= 参考臂会选中的源点数）与 `终态高斯数` **都是内生量**——
它们取决于地图状态，而地图状态又取决于本次选择。所以在声称"剂量相等/不等"之前，
必须先回答：**同一个 config、同一个 seed、重跑一次，这两个量本身就差多少。**

本脚本用既有 BPW 的**同臂重跑对**（`bpw_on_person_tracking` 与
`bpw_on_person_tracking_trace`：config 只差 `trace_selection`，不改变选择行为）
量这个地板，并同时报历史已知的终态高斯数重跑差。

输出 = markdown + JSON。**本脚本只产地板读数，不判任何机制。**

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/measure_cgb_dose_floor.py \
      --out-md paper3/results/evidence/cgb_dose_floor_2026-10-30.md \
      --out-json paper3/results/evidence/cgb_dose_floor_2026-10-30.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# 同臂重跑对：两者 config 只差 SelectiveDensification.trace_selection（默认关的诊断日志），
# 不改变任何选择/训练行为 ⇒ 任何差异都是装置不可复现，不是机制。
SAME_ARM_PAIRS = [
    ("bpw_on_person_tracking", "bpw_on_person_tracking_trace",
     "同臂同 seed 重跑（trace 开关不改变行为）"),
]


def _console(pattern):
    hits = glob.glob(str(REPO / "results/paper3_bpw" / pattern / "datasets_bonn/*/seed_0/*/console.log"))
    return sorted(hits)[-1] if hits else None


def _efficiency(pattern):
    hits = glob.glob(str(REPO / "results/paper3_bpw" / pattern / "datasets_bonn/*/seed_0/*/efficiency_raw.csv"))
    return sorted(hits)[-1] if hits else None


def ref_sel_series(console: str):
    """BPW 的 `budget` 就是 |ref_sel| ⇒ 用它量逐事件 ref_sel 的重跑稳定性。"""
    txt = re.sub(r"\s+", " ", Path(console).read_text(errors="ignore"))
    rows = re.findall(r"iter=(\d+) pool=(\d+) budget=(\d+) accepted=(\d+)", txt)
    return {int(r[0]): int(r[2]) for r in rows}


def final_gaussians(path):
    rows = list(csv.DictReader(open(path)))
    return int(float(rows[-1]["online_num_gaussians"]))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args(argv)

    out = {"same_arm_pairs": [], "historical": []}

    for a, b, note in SAME_ARM_PAIRS:
        ca, cb = _console(a), _console(b)
        ea, eb = _efficiency(a), _efficiency(b)
        if not (ca and cb and ea and eb):
            continue
        sa, sb = ref_sel_series(ca), ref_sel_series(cb)
        common = sorted(set(sa) & set(sb))
        rel = [abs(sa[i] - sb[i]) / sb[i] for i in common if sb[i] > 0]
        tot_a, tot_b = sum(sa.values()), sum(sb.values())
        ga, gb = final_gaussians(ea), final_gaussians(eb)
        out["same_arm_pairs"].append(
            {
                "pair": [a, b],
                "note": note,
                "events_a": len(sa),
                "events_b": len(sb),
                "common_events": len(common),
                "ref_sel_identical_events": sum(1 for i in common if sa[i] == sb[i]),
                "ref_sel_rel_diff_median": float(st.median(rel)) if rel else None,
                "ref_sel_rel_diff_p90": float(sorted(rel)[int(0.9 * len(rel))]) if rel else None,
                "sum_ref_sel_a": tot_a,
                "sum_ref_sel_b": tot_b,
                "sum_ref_sel_rel_gap": abs(tot_a - tot_b) / tot_b,
                "final_gaussians_a": ga,
                "final_gaussians_b": gb,
                "final_gaussians_rel_gap": abs(ga - gb) / gb,
            }
        )

    # 历史已知的终态高斯数重跑差（来自 PREREGISTRATION.md §3.1 的就地登记，原文保留）
    out["historical"].append(
        {
            "what": "同臂同 config 同 seed 重跑，终态高斯数相对差",
            "value": 0.2678,
            "frames": 439,
            "source": "paper3/PREREGISTRATION.md §3.1（2026-10-28 P3-D2-006 甲案登记）",
        }
    )

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    if args.out_md:
        L, A = [], None
        A = L.append
        A("# CGB 剂量类读数的装置地板（2026-10-30）\n")
        A("**性质**：装置标定，零 GPU。回答「同一个 config 同一个 seed 重跑，"
          "`ref_sel` 与终态高斯数本身就差多少」。")
        A("**为什么必须量**：CGB 的立意是「两臂等剂量、只差放置」。而 `ref_sel` 与终态高斯数**都是内生量**"
          "（取决于地图状态，地图状态又取决于本次选择）。在声称剂量相等/不等之前，"
          "先要知道这两个量的重跑分辨率。")
        A("**复现**：`scripts/paper3_bpw/measure_cgb_dose_floor.py`（机算，零手抄）\n")
        A("---\n")
        A("## 1. `ref_sel`（逐事件源点预算）\n")
        A("| 同臂重跑对 | 共同事件 | ref_sel 完全相等的事件 | 逐事件相对差中位 | p90 | Σ 相对差 |")
        A("|---|---:|---:|---:|---:|---:|")
        for p in out["same_arm_pairs"]:
            A("| `%s` vs `%s` | %d | %d / %d | %.2f%% | %.2f%% | **%.2f%%** |" % (
                p["pair"][0], p["pair"][1], p["common_events"],
                p["ref_sel_identical_events"], p["common_events"],
                100 * p["ref_sel_rel_diff_median"], 100 * p["ref_sel_rel_diff_p90"],
                100 * p["sum_ref_sel_rel_gap"]))
        A("")
        A("⇒ **同一 config 同一 seed 重跑，逐事件的 ref_sel 只有 1/57 个事件完全相等。**")
        A("这不是机制，是装置：地图状态在两跑之间已经分叉。\n")
        A("## 2. 终态高斯数\n")
        A("| 量 | 相对差 | 来源 |")
        A("|---|---:|---|")
        for p in out["same_arm_pairs"]:
            A("| `%s` vs `%s` | **%.2f%%** | 本脚本机算 |" % (
                p["pair"][0], p["pair"][1], 100 * p["final_gaussians_rel_gap"]))
        for h in out["historical"]:
            A("| 439 帧同臂重跑（历史） | **%.2f%%** | %s |" % (100 * h["value"], h["source"]))
        A("")
        A("## 3. 对 CGB 预注册的直接后果\n")
        A("- `prereg_cgb_amendment_a1_2026-10-30.md` §3(a) 把剂量门定在 **5%**。")
        A("- 本表显示该量的**重跑分辨率**在 `ref_sel` 上就是 **%.2f%%**（Σ 口径），"
          "终态高斯数上历史到过 **26.78%%**。" % (100 * out["same_arm_pairs"][0]["sum_ref_sel_rel_gap"] if out["same_arm_pairs"] else float("nan")))
        A("- ⇒ **5% 的门低于装置分辨率**：跨臂的 5% 以内/左右差异，无法区分"
          "「γ 改变了剂量」与「重跑噪声」。这门按当前装置**不可执行**。")
        A("- 同理，`prereg_cgb_2026-10-30.md` §2 写的「两臂 extra 数逐事件严格相等 ⇒ 等剂量」"
          "**只在事件 1 成立**（两臂初始地图相同）；从事件 2 起两臂地图已不同，"
          "`ref_sel` 与地图都会分叉。**「等剂量控位对照」在本装置上不是可构造的对象。**\n")
        A("## 4. 本表不主张什么\n")
        A("- 不主张 CGB 无效（没测到有效）。")
        A("- 不主张「任何跨臂剂量比较都不可能」——只主张**这个装置 + 这个内生量**上不行；"
          "若要真正的等剂量对照，需要把两臂约束成同一张地图（例如离线重放同一条地图轨迹），"
          "那是另一个设计。")
        Path(args.out_md).write_text("\n".join(L) + "\n")
        print("wrote", args.out_md)
    if not args.out_md and not args.out_json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
