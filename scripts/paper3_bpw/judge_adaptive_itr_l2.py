#!/usr/bin/env python3
"""E 轴 L2 判读器：Adaptive itr 三 seed 确认批（Amd A3 §2 机械执行）。

预注册：`paper3/results/evidence/prereg_adaptive_itr_amendment_a3_2026-11-10.md`
（判据锁定于本批任何 run 之前）。

每 seed ∈ {0,1,2}：Δ_s = ATE_C(s) − ATE_B(s)（前置门：.done rc0 + 580 帧 + 读数有限，
三臂同规，A2 后无 .done 豁免）。

四条互斥出口（按序路由；rc=2 = INVALID/止损外的一切失败）：
  L2_SIGN_UNSTABLE     任两 seed Δ 异号 ⇒ 止损（E 轴降级配置结论）
  L2_CONFIRMED_TRADEOFF 三 seed 全负 ∧ median Δ≤−0.5 ∧ 渲染代价闸触发
  L2_CONFIRMED         三 seed 全负 ∧ median Δ≤−0.5 ∧ 渲染中性
  L2_DIRECTION_ONLY    三 seed 全负 ∧ |median Δ|<0.5cm（方向级，不主张）

用法（L2 批实测命令落纸，roots 见 Amd A3 §4；在派发机执行）:
  python scripts/paper3_bpw/judge_adaptive_itr_l2.py \
    --b-root results/paper3_bpw/itrsweep50_maskstat_off/datasets_bonn/itrsweep50_maskstat_off \
    --c-root results/paper3_bpw/adaptive_itr_person_tracking/datasets_bonn/adaptive_itr_person_tracking \
    --seeds 0 1 2 \
    --b-pin 0=2026-11-09-21-03-01 \
    --c-pin 0=2026-11-09-19-17-31 \
    --out paper3/results/evidence/adaptive_itr_l2_judge_2026-11-10.json

注（2026-11-10 更正）：旧版 docstring 与 Amd A3 §4 写的 `--b-pin-0/--c-pin-0` 不可执行，
解析器只接受 `--b-pin SEED=RUNDIR`（下方 argparse 与 runner 落纸形式为准）。
"""
import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts/paper3_bpw"))

from judge_adaptive_itr_l1 import (  # 复用 L1 的收集与解析（同口径，防两套漂移）
    N_FRAMES_EXPECTED,
    collect,
    run_params,
)

PSNR_TRADEOFF_DB = 0.5
DEPTH_TRADEOFF_CM = 1.0
CLAIM_FLOOR_CM = 0.5
SEEDS_EXPECTED = (0, 1, 2)


def _finite(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(float(x))


def static_render(run_dir):
    """static 行的 psnr / depth_l1_cm（陷阱闸报告项；full 行本管线恒 nan 不读）。"""
    mp = Path(run_dir) / "mapping_raw.csv"
    if not mp.is_file():
        return None, None
    rows = list(csv.DictReader(open(mp)))
    s = next((r for r in rows if r.get("mask_type") == "static"), None)
    if s is None:
        return None, None
    def _f(k):
        try:
            v = float(s.get(k))
        except (TypeError, ValueError):
            return None
        return v if _finite(v) else None
    return _f("psnr"), _f("depth_l1_cm")


def collect_b(root, seed, pin):
    """B 臂收集：collect + 渲染读数（无机制检查——B 是 fixed-50 对照臂）。"""
    rec, err = collect(root, seed, pin, N_FRAMES_EXPECTED)
    if rec is None:
        return None, err
    rec["static_psnr_db"], rec["static_depth_l1_cm"] = static_render(rec["dir"])
    return rec, None


def collect_c(root, seed, pin):
    """C 臂收集：collect + 渲染读数 + 机制门随行（真调度才有效）。"""
    rec, err = collect(root, seed, pin, N_FRAMES_EXPECTED)
    if rec is None:
        return None, err
    rec["static_psnr_db"], rec["static_depth_l1_cm"] = static_render(rec["dir"])
    params, perr = run_params(rec["dir"])
    if params is None:
        return None, f"C 臂 seed{seed}: {perr}"
    rec["schedule_params"] = params
    if rec.get("backend_early_calls", 0) == 0 and rec.get("backend_late_calls", 0) == 0:
        return None, f"C 臂 seed{seed}: backend 计数为 0 ⇒ 机制未触发"
    return rec, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--b-root", required=True)
    ap.add_argument("--c-root", required=True)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--b-pin", nargs="*", default=[], metavar="SEED=RUNDIR")
    ap.add_argument("--c-pin", nargs="*", default=[], metavar="SEED=RUNDIR")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    def _pins(spec):
        out = {}
        for item in spec:
            k, _, v = item.partition("=")
            if not k.isdigit() or not v:
                ap.error(f"--b-pin/--c-pin 需要 SEED=RUNDIR 形式，收到 {item!r}")
            out[int(k)] = v
        return out

    b_pins, c_pins = _pins(args.b_pin), _pins(args.c_pin)

    report = {
        "prereg": "paper3/results/evidence/prereg_adaptive_itr_schedule_2026-11-08.md",
        "amendments": [
            "paper3/results/evidence/prereg_adaptive_itr_amendment_a1_2026-11-09.md",
            "paper3/results/evidence/prereg_adaptive_itr_amendment_a2_2026-11-09.md",
            "paper3/results/evidence/prereg_adaptive_itr_amendment_a3_2026-11-10.md"],
        "seeds": args.seeds,
        "claim_floor_cm": CLAIM_FLOOR_CM,
        "tradeoff_gates": {"psnr_db": PSNR_TRADEOFF_DB, "depth_l1_cm": DEPTH_TRADEOFF_CM},
        "per_seed": {}, "deltas": [], "verdict": None, "reasons": [],
    }

    if tuple(sorted(args.seeds)) != SEEDS_EXPECTED:
        report["verdict"] = "L2_INSTRUMENT_INVALID"
        report["reasons"] = [f"seed 集 {sorted(args.seeds)} != {list(SEEDS_EXPECTED)}"
                             "（Amd A3 §2 固定三 seed）"]
        return _emit(report, args.out)

    invalid = []
    for s in args.seeds:
        b, eb = collect_b(args.b_root, s, b_pins.get(s))
        c, ec = collect_c(args.c_root, s, c_pins.get(s))
        report["per_seed"][s] = {"B": b, "C": c}
        if b is None or c is None:
            invalid.append(f"seed{s}: {eb or ec}")
            continue
        rec = report["per_seed"][s]
        rec["delta_ate_cm"] = round(c["ate_cm"] - b["ate_cm"], 4)
        rec["saving_iterations"] = b["mapping_iterations"] - c["mapping_iterations"]
        report["deltas"].append(rec["delta_ate_cm"])

    if invalid:
        report["verdict"] = "L2_INSTRUMENT_INVALID"
        report["reasons"] = invalid
        return _emit(report, args.out)

    signs = set(1 if d < 0 else 0 for d in report["deltas"])
    med = statistics.median(report["deltas"])
    med_c_psnr = statistics.median([report["per_seed"][s]["C"]["static_psnr_db"]
                                    for s in args.seeds])
    med_b_psnr = statistics.median([report["per_seed"][s]["B"]["static_psnr_db"]
                                    for s in args.seeds])
    med_c_dl1 = statistics.median([report["per_seed"][s]["C"]["static_depth_l1_cm"]
                                   for s in args.seeds])
    med_b_dl1 = statistics.median([report["per_seed"][s]["B"]["static_depth_l1_cm"]
                                   for s in args.seeds])
    tradeoff = (med_c_psnr < med_b_psnr - PSNR_TRADEOFF_DB
                or med_c_dl1 > med_b_dl1 + DEPTH_TRADEOFF_CM)
    report["render_report"] = {
        "median_C_psnr_db": round(med_c_psnr, 4), "median_B_psnr_db": round(med_b_psnr, 4),
        "median_C_depth_l1_cm": round(med_c_dl1, 4), "median_B_depth_l1_cm": round(med_b_dl1, 4),
        "tradeoff_triggered": tradeoff,
    }
    report["median_delta_ate_cm"] = round(med, 4)

    if len(signs) > 1:
        report["verdict"] = "L2_SIGN_UNSTABLE"
        report["reasons"] = [f"Δ 跨 seed 异号：{report['deltas']}（Amd A3 §2 出口 1 = 止损）"]
    elif med > -CLAIM_FLOOR_CM:
        report["verdict"] = "L2_DIRECTION_ONLY"
        report["reasons"] = [f"三 seed 同号负但 |median Δ|={abs(med):.4f} < 0.5cm"
                             "（方向级，不主张）"]
    elif tradeoff:
        report["verdict"] = "L2_CONFIRMED_TRADEOFF"
        report["reasons"] = [f"三 seed 同号负 ∧ median Δ={med:+.4f} ≤ −0.5，"
                             "但渲染代价闸触发（判决须并陈代价，不得主张无代价）"]
    else:
        report["verdict"] = "L2_CONFIRMED"
        report["reasons"] = [f"三 seed 同号负 ∧ median Δ={med:+.4f} ≤ −0.5 ∧ 渲染中性"]
    return _emit(report, args.out)


def _emit(report, out):
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(payload)
    print(payload)
    return 2 if report["verdict"] in ("L2_INSTRUMENT_INVALID",) else 0


if __name__ == "__main__":
    sys.exit(main())
