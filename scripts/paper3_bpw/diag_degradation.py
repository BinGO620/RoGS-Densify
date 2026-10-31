#!/usr/bin/env python
"""diag_degradation.py — person_tracking 三臂劣化的分层诊断（纯 CPU，读盘工件）。

回答两个问题：
  ① 劣化是全程性的还是集中在某类帧？（按 mask 覆盖率 / 关键帧 / 轨迹位置分层）
  ② placebo 键相对 on 的差异是不是"低观测 + 高瞬时梯度"的噪声点选择？

用法：
  python scripts/paper3_bpw/diag_degradation.py \
      --run off=results/.../2026-... \
      --run on=... --run negctl=...
输出：markdown 表 + JSON。
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load_ape(run: Path) -> dict[int, dict]:
    rows = list(csv.DictReader(open(run / "per_frame_ape.csv")))
    return {int(r["frame_id"]): r for r in rows}


def med(xs):
    xs = list(xs)
    return statistics.median(xs) if xs else float("nan")


def boot_paired_median_diff(a: dict[int, float], b: dict[int, float], ids, n=2000, seed=0):
    """配对 bootstrap：逐帧差 d_i = a_i − b_i，返回 (median(d), lo, hi)。

    注意：median(a−b) 与 median(a)−median(b) 不是同一个量，两者必须分开报。
    """
    import random

    rng = random.Random(seed)
    d = [a[i] - b[i] for i in ids]
    meds = sorted(statistics.median([rng.choice(d) for _ in d]) for _ in range(n))
    return statistics.median(d), meds[int(0.025 * n)], meds[int(0.975 * n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", required=True, metavar="ARM=PATH")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    runs = {}
    for spec in args.run:
        arm, path = spec.split("=", 1)
        p = Path(path)
        runs[arm] = p if p.is_absolute() else REPO / p

    data = {a: load_ape(p) for a, p in runs.items()}
    arms = [a for a in ("off", "on", "negctl") if a in data]
    ids = sorted(set.intersection(*[set(d) for d in data.values()]))
    print(f"# 劣化分层诊断 — {len(ids)} 共同帧\n")

    # 0. 总览
    print("## 0. 总览（median APE, cm）\n")
    print("| 臂 | median | mean | p90 |")
    print("|---|---:|---:|---:|")
    raw = {}
    for a in arms:
        xs = [float(data[a][i]["ape_cm"]) for i in ids]
        raw[a] = xs
        q = statistics.quantiles(xs, n=10)[8]
        print(f"| {a} | {statistics.median(xs):.3f} | {statistics.mean(xs):.3f} | {q:.3f} |")

    # 1. 两两配对 bootstrap
    print("\n## 1. 配对 bootstrap（逐帧差的中位, 2000 次）\n")
    print("| 比较 | median(d) (cm) | 95% CI | median(a)−median(b) (cm) |")
    print("|---|---:|---|---:|")
    boot = {}
    for i, a in enumerate(arms):
        for b in arms[i + 1 :]:
            da = {k: float(data[a][k]["ape_cm"]) for k in ids}
            db = {k: float(data[b][k]["ape_cm"]) for k in ids}
            dmed, lo, hi = boot_paired_median_diff(da, db, ids)
            separate = statistics.median(da.values()) - statistics.median(db.values())
            boot[f"{a}-{b}"] = {
                "paired_median_cm": dmed,
                "ci95": [lo, hi],
                "separate_median_diff_cm": separate,
            }
            print(f"| {a} − {b} | {dmed:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {separate:+.3f} |")

    # 2. 按 mask 覆盖率分层（用 on 臂的覆盖率作为共同分层依据）
    print("\n## 2. 按 mask 覆盖率分层（分箱依据取 on 臂）\n")
    cov = {k: float(data["on"][k]["mask_coverage"]) for k in ids}
    edges = [(0.0, 0.01), (0.01, 0.05), (0.05, 0.15), (0.15, 0.40), (0.40, 1.01)]
    print("| 覆盖率分箱 | n | " + " | ".join(f"{a} median" for a in arms) + " |")
    print("|---|---:|" + "---:|" * len(arms))
    strata = {}
    for lo, hi in edges:
        g = [k for k in ids if lo <= cov[k] < hi]
        if len(g) < 5:
            continue
        vals = [statistics.median([float(data[a][k]["ape_cm"]) for k in g]) for a in arms]
        strata[f"[{lo:.2f},{hi:.2f})"] = {"n": len(g), **{a: v for a, v in zip(arms, vals)}}
        print(f"| [{lo:.2f},{hi:.2f}) | {len(g)} | " + " | ".join(f"{v:.3f}" for v in vals) + " |")

    # 3. 按轨迹时间十等分
    print("\n## 3. 按轨迹时间十等分（median APE, cm）\n")
    print("| 段 | 帧范围 | " + " | ".join(arms) + " | " + " | ".join(f"Δ{a}−off" for a in arms if a != "off") + " |")
    print("|---|---:|" + "---:|" * len(arms) + "---:|" * (len(arms) - 1))
    n = len(ids)
    segsize = max(1, n // 10)
    for s in range(10):
        part = ids[s * segsize : (s + 1) * segsize] if s < 9 else ids[9 * segsize :]
        if not part:
            continue
        row = [statistics.median([float(data[a][k]["ape_cm"]) for k in part]) for a in arms]
        deltas = [row[arms.index(a)] - row[arms.index("off")] for a in arms if a != "off"]
        print(
            f"| {s} | {part[0]}–{part[-1]} | "
            + " | ".join(f"{v:.3f}" for v in row)
            + " | "
            + " | ".join(f"{v:+.3f}" for v in deltas)
            + " |"
        )

    # 4. 关键帧 vs 非关键帧
    print("\n## 4. 关键帧 vs 非关键帧（median APE, cm）\n")
    print("| 臂 | 关键帧 | 非关键帧 |")
    print("|---|---:|---:|")
    for a in arms:
        kf = [float(data[a][k]["ape_cm"]) for k in ids if data[a][k]["is_keyframe"] == "1"]
        nk = [float(data[a][k]["ape_cm"]) for k in ids if data[a][k]["is_keyframe"] != "1"]
        print(f"| {a} | {med(kf):.3f} (n={len(kf)}) | {med(nk):.3f} (n={len(nk)}) |")

    payload = {"strata_coverage": strata, "bootstrap": boot}
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\nJSON → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
