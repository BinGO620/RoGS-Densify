#!/usr/bin/env python
"""analyze_p0_sweep.py — p0 扫描结果汇总（数字零手抄）。

扫描 runs/sweep_p0_<P> 下的所有 run，按 p0 排序输出 ATE / 高斯数 /
事件数 / Σk，并与 off 基线给出配对差。

用法：
  python scripts/paper3_bpw/analyze_p0_sweep.py \
      --off results/.../seed_0/2026-...
"""
from __future__ import annotations

import argparse
import csv
import glob
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def last_row(p: Path) -> dict:
    rows = list(csv.DictReader(open(p)))
    return rows[-1] if rows else {}


def read_run(d: Path) -> dict:
    tr = last_row(d / "efficiency_raw.csv")
    ate_row = last_row(d / "tracking_raw.csv")
    events = 0
    sum_k = 0
    console = d / "console.log"
    if console.is_file():
        pat = re.compile(r"iter=(\d+)\s+pool=(\d+)\s+budget=(\d+)")
        for line in console.read_text(errors="replace").splitlines():
            m = pat.search(line)
            if m:
                events += 1
                sum_k += int(m.group(3))
    return {
        "run": d.name,
        "path": str(d),
        "ate_cm": _f(ate_row.get("ate_rmse_cm")),
        "frames": _f(ate_row.get("num_frames") or tr.get("num_frames")),
        "gauss": _f(tr.get("online_num_gaussians")),
        "events": events,
        "sum_k": sum_k,
    }


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v, nd=4):
    if v is None:
        return "—"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", default="", help="基线 run 目录")
    ap.add_argument("--sweep-root", default="results/paper3_bpw")
    ap.add_argument("--pattern", default="sweep_p0_*")
    args = ap.parse_args()

    root = Path(args.sweep_root)
    if not root.is_absolute():
        root = REPO / root

    # 真实布局：<root>/<run>/datasets_bonn/<run>/seed_<s>/<timestamp>/efficiency_raw.csv
    # （中间那层 datasets_bonn 是 MonoGS 的产物结构，不能漏）
    dirs = []
    for pat in (
        str(root / args.pattern / "datasets_bonn" / "*" / "seed_*" / "*" / "efficiency_raw.csv"),
        str(root / args.pattern / "*" / "seed_*" / "*" / "efficiency_raw.csv"),
    ):
        dirs = [Path(g).parent for g in sorted(glob.glob(pat))]
        if dirs:
            break
    if not dirs:
        print(f"未找到匹配 {args.pattern} 的 run（root={root}）", file=sys.stderr)
        return 1

    rows = []
    for d in dirs:
        r = read_run(d)
        m = re.search(r"_p0(\d+)", str(d))
        r["p0"] = int(m.group(1)) if m else None
        rows.append(r)

    base = None
    if args.off:
        od = Path(args.off)
        if not od.is_absolute():
            od = REPO / od
        base = read_run(od)

    print("# p0 扫描结果\n")
    hdr = "| p0 | ATE (cm) | 高斯数 | 事件数 | Σk |"
    sep = "|---:|---:|---:|---:|---:|"
    if base:
        hdr += " ΔATE vs off |"
        sep += "---:|"
    print(hdr)
    print(sep)
    for r in sorted(rows, key=lambda x: (x["p0"] is None, x["p0"])):
        line = (
            f"| {r['p0']} | {_fmt(r['ate_cm'])} | {_fmt(r['gauss'], 0)} | "
            f"{r['events']} | {r['sum_k']} |"
        )
        if base:
            d = (
                None
                if (r["ate_cm"] is None or base["ate_cm"] is None)
                else r["ate_cm"] - base["ate_cm"]
            )
            line += f" {_fmt(d)} |"
        print(line)

    if base:
        print(
            f"\n基线 (off): ATE {_fmt(base['ate_cm'])} cm, "
            f"高斯 {_fmt(base['gauss'], 0)}, 事件 {base['events']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
