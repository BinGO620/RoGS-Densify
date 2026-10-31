#!/usr/bin/env python
"""calibrate_budget_threshold.py — 为「同预算对照臂」标定标量梯度阈值。

背景：Phase 0 发现 persistence 排序在**同等预算**下没有 ATE 收益。剩下唯一
诚实的问题是「更少高斯能否达到相当 ATE」。要回答它，必须有一个同预算的
对照臂；但 off 臂没有选择器，只能靠提高标量阈值 τ 来减少通过的点数。

本脚本读一个已完成 run 的 console.log，取出每事件的 budget 序列，
并给出把 τ 提高到什么倍数才能把平均 budget 压到目标比例。

⚠ 这是**离线近似**：τ 与通过点数不是线性关系，倍数只作初值，
   实际以 config 扫描后的真实 budget 为准。

用法：
  python scripts/paper3_bpm/calibrate_budget_threshold.py \
      --run results/.../2026-10-28-21-37-02 --target-scale 0.5
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "paper3_bpw"))

BPW_RE = re.compile(r"iter=(\d+)\s+pool=(\d+)\s+budget=(\d+)\s+accepted=(\d+)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="已完成 run 目录")
    ap.add_argument("--target-scale", type=float, default=0.5)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    run = Path(args.run)
    if not run.is_absolute():
        run = REPO / run
    console = run / "console.log"
    if not console.is_file():
        print(f"ERROR: 缺 {console}", file=sys.stderr)
        return 1

    rows = []
    for line in console.read_text(errors="replace").splitlines():
        m = BPW_RE.search(line)
        if m:
            rows.append(
                {"iter": int(m.group(1)), "pool": int(m.group(2)), "budget": int(m.group(3))}
            )

    if not rows:
        print("ERROR: 未解析到 [bpw] 事件行", file=sys.stderr)
        return 1

    budgets = [r["budget"] for r in rows]
    total = sum(budgets)
    print(f"run: {run}")
    print(f"事件数: {len(rows)}")
    print(f"budget 中位: {statistics.median(budgets):.1f}")
    print(f"Σbudget: {total}")
    print(f"目标比例: {args.target_scale}")
    print(f"目标 Σbudget: {int(total * args.target_scale)}")
    print()
    print("⚠ τ→budget 非线性，须迭代标定；起始建议把 densify_grad_threshold 上调 ≥1.5×，")
    print("  跑一个短序列看真实 budget，再回调。不要直接相信这里的线性外推。")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        import json

        out.write_text(
            json.dumps(
                {
                    "run": str(run),
                    "n_events": len(rows),
                    "budget_median": statistics.median(budgets),
                    "budget_total": total,
                    "target_scale": args.target_scale,
                    "note": "τ→budget 非线性；本值是标定起点不是结论",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"JSON → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
