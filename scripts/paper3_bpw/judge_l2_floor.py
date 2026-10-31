#!/usr/bin/env python
"""judge_l2_floor.py — 同臂重跑的逐事件 k 复现地板（L2 门）

用途：区分两种完全不同的解释——
  (a) 机制内生量：on 与 negctl 的 k 逐事件分叉，是因为两臂地图不同（机制在生效）；
  (b) 装置不可复现：同一臂同 config 同 seed 重复跑，k 序列本身就变。

判别方法：取同一臂的两个 run 目录，按 iteration 对齐比较 pool / budget / accepted。
若同臂两次**逐位相同** ⇒ (b) 排除，跨臂分叉可归因于机制；
若同臂两次**就不同** ⇒ 任何「逐事件 k 相等」的判据在 2060 上都不成立，
           分叉不能归因于机制，该判据不可用。

⚠ 只在**同 config** 的两个 run 之间比较。截断帧数不同（如 80 vs 439）、
  eval_rendering 开关不同（--fast vs --eval）都算不同 config，不得当 L2 用
  ——2026-10-28 实测：80 帧冒烟与 439 帧全长的 on 臂事件序列不同，但两者
  `Dataset.max_frames` 与 `Results.eval_rendering` 都不同，属跨 config 比较。

用法：
  python scripts/paper3_bpw/judge_l2_floor.py --arm on --run 2026-... --run 2026-...
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "paper3_bpw"))

from judge_p0a import ARM_ROOT, compare, summarize_arm  # noqa: E402


def arm_dir(arm: str, run: str) -> Path:
    return REPO / ARM_ROOT.format(arm=arm) / run


def config_diff(a: Path, b: Path) -> list[str]:
    """Return config keys that differ (empty ⇒ 同 config，L2 合法）。"""
    import yaml

    def flat(d, p=""):
        out = {}
        if isinstance(d, dict):
            for k, v in d.items():
                out.update(flat(v, f"{p}.{k}" if p else str(k)))
        else:
            out[p] = d
        return out

    fa = flat(yaml.safe_load((a / "config.yml").read_text()))
    fb = flat(yaml.safe_load((b / "config.yml").read_text()))
    keys = sorted(set(fa) | set(fb))
    # 这三个键每次跑必然不同，不构成配置差异
    ignore = ("Results.save_dir",)
    return [
        k
        for k in keys
        if fa.get(k, "<missing>") != fb.get(k, "<missing>") and k not in ignore
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="on", choices=["off", "on", "negctl"])
    ap.add_argument("--run", action="append", required=True, help="run 目录名（可两次）")
    args = ap.parse_args()

    if len(args.run) != 2:
        ap.error("需要恰好两个 --run")

    pa, pb = arm_dir(args.arm, args.run[0]), arm_dir(args.arm, args.run[1])
    for p in (pa, pb):
        if not (p / "console.log").is_file():
            print(f"ERROR: 缺 console.log: {p}")
            return 1

    diff = config_diff(pa, pb)
    print("=" * 74)
    print(f"L2 逐事件 k 复现地板 — arm={args.arm}")
    print("=" * 74)
    print(f"  A = {args.run[0]}")
    print(f"  B = {args.run[1]}")
    print(f"  配置差异键（排除 save_dir）: {diff if diff else '无 ⇒ 同 config，L2 合法'}")
    if diff:
        print("  ⚠ 配置不同 ⇒ 本比较不是 L2（只能作诊断读数，不得当复现地板）")

    ra = summarize_arm(args.arm, pa)
    rb = summarize_arm(args.arm, pb)
    print(f"\n  A: frames={ra['num_frames']} gauss={ra['num_gaussians']} ATE={ra['ate_cm']} events={ra['n_events']}")
    print(f"  B: frames={rb['num_frames']} gauss={rb['num_gaussians']} ATE={rb['ate_cm']} events={rb['n_events']}")

    cmp = compare(ra, rb)
    print(f"\n  共同 iteration 事件数 = {cmp['shared_iters']}")
    print(f"  budget 不等事件数     = {cmp['n_budget_mismatch']}")
    if cmp["only_in_first"]:
        print(f"  仅 A 有的事件 iter    = {cmp['only_in_first']}")
    if cmp["only_in_second"]:
        print(f"  仅 B 有的事件 iter    = {cmp['only_in_second']}")

    if cmp["mismatch_rows"]:
        deltas = [abs(r["delta"]) for r in cmp["mismatch_rows"]]
        print(f"  |Δk| 中位 = {statistics.median(deltas):.1f}  最大 = {max(deltas)}")
        print(f"  首个不等事件: {cmp['mismatch_rows'][0]}")
    else:
        print("  ⇒ 逐事件 k 序列逐位相同（同臂重跑可复现）")

    # 一致率
    same = cmp["shared_iters"] - cmp["n_budget_mismatch"]
    if cmp["shared_iters"]:
        print(f"\n  一致率 = {same}/{cmp['shared_iters']} = {100*same/cmp['shared_iters']:.1f}%")

    # 终态对照（供判断同臂差是否可忽略）
    if ra["num_gaussians"] and rb["num_gaussians"]:
        pct = 100 * (rb["num_gaussians"] - ra["num_gaussians"]) / ra["num_gaussians"]
        print(f"  最终高斯数 Δ = {pct:+.2f}%")
    if ra["ate_cm"] is not None and rb["ate_cm"] is not None:
        print(f"  ATE Δ = {rb['ate_cm'] - ra['ate_cm']:+.4f} cm（噪声地板 0.62 cm）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
