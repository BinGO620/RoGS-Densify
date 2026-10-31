#!/usr/bin/env python
"""summarize_three_arms.py — 三臂交付表（跟踪 / 渲染 / 剂量），数字零手抄。

读取指定 run 目录的 `tracking_raw.csv` / `mapping_raw.csv` / `efficiency_raw.csv`
与 console.log 的 `[bpw]` 事件行，输出一张 markdown 表 + 一份 JSON。

口径（与 `paper3/PREREGISTRATION.md` §3.1 一致）：
  - ATE = tracking_raw.csv 的 `ate_rmse_cm`（全帧，**不是** keyframe_ate_rmse_cm）
  - 渲染 = mapping_raw.csv 的 `mask_type=static` 行（全帧行在 Bonn 上恒 NaN，
    根因见 scripts/02_analysis/render_compare.py 文件头：run 内 eval 采样网格
    interval=5 与关键帧网格重合）
  - 剂量 = 每事件 `budget`；首事件单列，Σk 与终态高斯数作报告项

用法：
  python scripts/paper3_bpw/summarize_three_arms.py \
      --run off=results/.../2026-10-28-17-01-27 \
      --run on=... --run negctl=...
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "paper3_bpw"))

from judge_p0a import parse_events, read_last_row  # noqa: E402


def arm_metrics(run: Path) -> dict:
    track = read_last_row(run / "tracking_raw.csv") or {}
    eff = read_last_row(run / "efficiency_raw.csv") or {}
    mapping: dict[str, dict] = {}
    mp = run / "mapping_raw.csv"
    if mp.is_file():
        with open(mp, newline="") as fh:
            for row in csv.DictReader(fh):
                mapping[row.get("mask_type", "?")] = row
    events = parse_events(run / "console.log")
    static = mapping.get("static", {})
    return {
        "run": run.name,
        "status": track.get("status") or eff.get("status"),
        "frames": _i(eff.get("num_frames")),
        "ate_cm": _f(track.get("ate_rmse_cm")),
        "ate_std_cm": _f(track.get("ate_error_std_cm")),
        "kf_ate_cm": _f(track.get("keyframe_ate_rmse_cm")),
        "num_gaussians": _i(eff.get("num_gaussians")),
        "online_time_s": _f(eff.get("online_time_s")),
        "peak_gb": _f(eff.get("online_peak_gpu_memory_gb")),
        "static_psnr": _f(static.get("psnr")),
        "static_ssim": _f(static.get("ssim")),
        "static_depth_l1_cm": _f(static.get("depth_l1_cm")),
        "static_ghost_excess_cm": _f(static.get("static_ghost_excess_depth_l1_cm")),
        "render_frames": _i(static.get("static_frames_scored")),
        "n_events": len(events),
        "first_k": events[0]["budget"] if events else None,
        "sum_k": sum(e["budget"] for e in events) if events else None,
        "events": events,
    }


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def fmt(v, nd=4):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", required=True, metavar="ARM=PATH")
    ap.add_argument("--json", default="")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    arms: dict[str, dict] = {}
    for spec in args.run:
        if "=" not in spec:
            ap.error(f"--run 需要 ARM=PATH，收到 {spec!r}")
        arm, path = spec.split("=", 1)
        p = Path(path)
        if not p.is_absolute():
            p = REPO / p
        if not p.is_dir():
            ap.error(f"run 目录不存在: {p}")
        arms[arm] = arm_metrics(p)

    order = [a for a in ("off", "on", "negctl") if a in arms] + [
        a for a in arms if a not in ("off", "on", "negctl")
    ]

    print(f"# 三臂交付表{f' — {args.tag}' if args.tag else ''}\n")
    print("## 跟踪")
    print("| 臂 | run | status | 帧数 | ATE (cm) | ATE std | keyframe ATE (cm) | 高斯数 |")
    print("|---|---|---|---:|---:|---:|---:|---:|")
    for a in order:
        m = arms[a]
        print(
            f"| {a} | {m['run']} | {m['status']} | {fmt(m['frames'])} | "
            f"{fmt(m['ate_cm'])} | {fmt(m['ate_std_cm'])} | {fmt(m['kf_ate_cm'])} | "
            f"{fmt(m['num_gaussians'])} |"
        )

    print("\n## 渲染（mask_type=static；全帧行在 Bonn 上恒 NaN，不入表）")
    print("| 臂 | static PSNR | static SSIM | static depth-L1 (cm) | ghost excess (cm) | 评分帧数 |")
    print("|---|---:|---:|---:|---:|---:|")
    for a in order:
        m = arms[a]
        print(
            f"| {a} | {fmt(m['static_psnr'])} | {fmt(m['static_ssim'])} | "
            f"{fmt(m['static_depth_l1_cm'])} | {fmt(m['static_ghost_excess_cm'])} | "
            f"{fmt(m['render_frames'])} |"
        )

    print("\n## 剂量（报告项；判据见 §3.1）")
    print("| 臂 | densify 事件数 | 首事件 k | Σk | 终态高斯数 |")
    print("|---|---:|---:|---:|---:|")
    for a in order:
        m = arms[a]
        print(
            f"| {a} | {fmt(m['n_events'])} | {fmt(m['first_k'])} | {fmt(m['sum_k'])} | "
            f"{fmt(m['num_gaussians'])} |"
        )

    # 差值读数
    print("\n## 差值（噪声地板 0.62 cm）")
    if "on" in arms and "negctl" in arms:
        d = None
        if arms["on"]["ate_cm"] is not None and arms["negctl"]["ate_cm"] is not None:
            d = arms["on"]["ate_cm"] - arms["negctl"]["ate_cm"]
        print(f"- ΔATE(on − negctl) = {fmt(d)} cm")
    if "on" in arms and "off" in arms:
        d = None
        if arms["on"]["ate_cm"] is not None and arms["off"]["ate_cm"] is not None:
            d = arms["on"]["ate_cm"] - arms["off"]["ate_cm"]
        print(f"- ΔATE(on − off)    = {fmt(d)} cm")
    for a, b in (("on", "negctl"), ("on", "off")):
        if a in arms and b in arms:
            ga, gb = arms[a]["num_gaussians"], arms[b]["num_gaussians"]
            if ga and gb:
                print(f"- 高斯数 {a} vs {b} = {100*(ga-gb)/gb:+.2f}%")
            ka, kb = arms[a]["sum_k"], arms[b]["sum_k"]
            if ka and kb:
                print(f"- Σk {a} vs {b} = {100*(ka-kb)/kb:+.2f}%")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"tag": args.tag, "arms": arms}, indent=2, ensure_ascii=False))
        print(f"\nJSON → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
