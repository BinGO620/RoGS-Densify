#!/usr/bin/env python3
"""剂量轴反向扫判读器（prereg_dose_reverse_2026-11-06 §3，机械执行）。

对每个臂（tau2x / tau4x）独立判一次（§3.2 五条出口），再给汇合出口（§3.3）。

单臂出口：
  POSITIVE_DEFAULT_OVERDOSED  同号 且 med ≤ −0.5cm 且 0.5 ≤ ratio ≤ 1.5（三 seed 全在带内）
                              且 static_psnr 下降 ≤ 0.5dB
  DOSE_CONFOUND               同号 且 med ≤ −0.5cm 但 ratio 出带 或 PSNR 掉 > 0.5dB
  WORSE                       同号 且 med ≥ +0.5cm
  BELOW_CLAIM_FLOOR           同号 且 |med| < 0.5cm
  SEED_UNSTABLE               三 seed 异号
  INSTRUMENT_INVALID          §2 硬门不过（帧数 / rc / 缺 run）

汇合出口：BOTH_SIDES_WORSE / DOWN_SIDE_HAS_EFFECT / MONOTONE_WORSE_DOWN / INCONCLUSIVE

用法:
  python scripts/paper3_bpw/judge_dose_scan.py \
    --off-root results/paper3_bpw/instrument_maskstat_off/datasets_bonn/instrument_maskstat_off \
    --arm tau2x=results/paper3_bpw/instrument_dose_tau2x_person_tracking/datasets_bonn/\
instrument_dose_tau2x_person_tracking \
    --arm tau4x=results/paper3_bpw/instrument_dose_tau4x_person_tracking/datasets_bonn/\
instrument_dose_tau4x_person_tracking \
    --seeds 0 1 2 --out paper3/results/evidence/dose_scan_judge_2026-11-06.json
"""
import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

N_FRAMES_EXPECTED = 580
CLAIM_FLOOR_CM = 0.5
RATIO_LO = 0.5
RATIO_HI = 1.5
PSNR_DROP_DB = 0.5
# prereg §3 固定三 seed；判据机不得按更少的 seed 判出口（G3 审查 F2 同款守卫）。
SEEDS_EXPECTED = (0, 1, 2)


def _finite(x):
    """非有限（nan/inf/None）一律 False。

    2026-11-06 G3 审查 F1：没有这道守卫时 `median([nan,...])` 返回 nan，
    `nan >= 0.5` 与 `nan < 0.5` 同时为 False ⇒ 落进最后的正面出口。
    """
    return x is not None and isinstance(x, (int, float)) and math.isfinite(float(x))



def read_frames(path):
    with path.open(newline="") as fh:
        return len(list(csv.DictReader(fh)))


def read_done(run):
    """读 instrument_*.done；无锚点返回 None（⇒ fail-closed，不是默认通过）。"""
    hits = sorted(run.glob("instrument_*.done"))
    if not hits:
        return None
    kv = {}
    for line in hits[-1].read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def collect(root, seed, prefer_frames=N_FRAMES_EXPECTED, pin=None):
    """取该 seed 的合格 run。选择规则（M3，同 judge_dose_a4_instrument）：给了 pin 只认它
    （不存在/无锚点/rc≠0/帧数不符一律报错，不回落）；否则取最新时间戳的合格 run。"""
    base = root / f"seed_{seed}"
    if not base.is_dir():
        return None, f"缺 seed_{seed} 目录"
    if pin:
        d = base / pin
        if not d.is_dir():
            return None, f"seed_{seed} 指定的 run 不存在：{pin}"
        runs = [d]
    else:
        runs = sorted([d for d in base.iterdir() if d.is_dir()], key=lambda d: d.name)
    if not runs:
        return None, f"seed_{seed} 无 run 目录"
    candidates, chosen, failed = [], None, []
    for d in runs:
        pf = d / "per_frame_ape.csv"
        nf = read_frames(pf) if pf.is_file() else None
        candidates.append(f"{d.name}(frames={nf})")
        kv = read_done(d)
        if kv is None:
            failed.append(f"{d.name}(无 .done 锚点)")
            continue
        if kv.get("finished_rc0") != "yes":
            failed.append(f"{d.name}(rc={kv.get('rc')})")
            continue
        if nf == prefer_frames and (d / "tracking_raw.csv").is_file():
            chosen = d
    suffix = f"；不合格 run: {', '.join(failed)}" if failed else ""
    if chosen is None:
        return None, (f"seed_{seed} 无 {prefer_frames} 帧 rc0 run{suffix}；"
                      f"候选: {', '.join(candidates[-4:])}")
    tr = list(csv.DictReader(open(chosen / "tracking_raw.csv")))[0]
    er = list(csv.DictReader(open(chosen / "efficiency_raw.csv")))[0]
    ate_raw = tr.get("ate_rmse_cm")
    try:
        ate = float(ate_raw)
    except (TypeError, ValueError):
        return None, f"{chosen.name} ate_rmse_cm 不可解析：{ate_raw!r}"
    if not _finite(ate):
        return None, f"{chosen.name} ate_rmse_cm 非有限（{ate_raw!r}）"
    g_raw = er.get("online_num_gaussians")
    try:
        gauss = int(float(g_raw))
    except (TypeError, ValueError):
        return None, f"{chosen.name} online_num_gaussians 不可解析：{g_raw!r}"
    if gauss <= 0:
        return None, f"{chosen.name} online_num_gaussians={gauss} 非正"
    out = {
        "run": chosen.name,
        "ate_cm": ate,
        "gaussians": gauss,
        "frames": prefer_frames,
    }
    rn = er.get("refined_num_gaussians")
    out["refined_gaussians"] = int(float(rn)) if rn not in (None, "", "None", "MISSING") else None
    mp = chosen / "mapping_raw.csv"
    if mp.is_file():
        rows = list(csv.DictReader(open(mp)))
        # **按 mask_type 选行**（G3 审查 M5）：`static` 是 P-A 静态背景口径（本件 PSNR 闸
        # 就用它，prereg §3.2 已写死）；`full` 行在本管线恒 nan，如实记 None。
        by_mask = {r.get("mask_type"): r for r in rows}
        # 键名带 `_db` 后缀 = 显式标注 dB 单位，防止与旧版误标的 "psnr" 混引
        # （prereg §3.2 声明即用该名）。
        for mask_type, prefix in (("static", "static"), ("full", "full")):
            r = by_mask.get(mask_type)
            if r is None:
                out[f"{prefix}_psnr_db"] = None
                out[f"{prefix}_depth_l1_cm"] = None
                continue
            for key, suffix in (("psnr", "psnr_db"), ("depth_l1_cm", "depth_l1_cm")):
                v = r.get(key)
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    fv = None
                out[f"{prefix}_{suffix}"] = fv if _finite(fv) else None
    return out, None


def judge_arm(off_rows, arm_rows, seeds):
    """返回 (verdict, payload)。arm_rows/off_rows: {seed: rec}。"""
    per, invalid = {}, []
    for s in seeds:
        o, a = off_rows.get(s), arm_rows.get(s)
        if not o or not a:
            invalid.append(f"seed{s} 缺 run")
            continue
        rec = {
            "off": o, "arm": a,
            "delta_ate_cm": round(a["ate_cm"] - o["ate_cm"], 4),
            "gauss_ratio": round(a["gaussians"] / o["gaussians"], 4) if o["gaussians"] else None,
        }
        if a.get("refined_gaussians") and o.get("refined_gaussians"):
            rec["refined_gauss_ratio"] = round(
                a["refined_gaussians"] / o["refined_gaussians"], 4)
        if a.get("static_psnr_db") is not None and o.get("static_psnr_db") is not None:
            rec["psnr_delta_db"] = round(a["static_psnr_db"] - o["static_psnr_db"], 4)
        per[s] = rec

    if invalid or len(per) < len(SEEDS_EXPECTED):
        return "INSTRUMENT_INVALID", {"per_seed": per,
                                      "reasons": invalid or [f"有效 seed 数 {len(per)} < "
                                                             f"{len(SEEDS_EXPECTED)}"]}

    deltas = [v["delta_ate_cm"] for v in per.values()]
    ratios = [v["gauss_ratio"] for v in per.values() if v["gauss_ratio"] is not None]
    if not all(_finite(x) for x in deltas) or not all(_finite(x) for x in ratios):
        bad = [f"seed{k}: Δ={v.get('delta_ate_cm')}, ratio={v.get('gauss_ratio')}"
               for k, v in per.items()
               if not _finite(v.get("delta_ate_cm")) or not _finite(v.get("gauss_ratio"))]
        return "INSTRUMENT_INVALID", {"per_seed": per,
                                      "reasons": ["Δ 或 ratio 非有限（读数不存在，不得判出口）",
                                                  *bad]}
    med = statistics.median(deltas)
    signs = {d > 0 for d in deltas}
    same_sign = len(signs) == 1
    psnr_drops = [-(v.get("psnr_delta_db") or 0.0) for v in per.values()]
    max_psnr_drop = round(max(psnr_drops), 4) if psnr_drops else 0.0
    payload = {
        "per_seed": per,
        "deltas": deltas,
        "median_delta_ate_cm": round(med, 4),
        "same_sign": same_sign,
        "gauss_ratios": ratios,
        "min_gauss_ratio": round(min(ratios), 4) if ratios else None,
        "max_gauss_ratio": round(max(ratios), 4) if ratios else None,
        "max_psnr_drop_db": max_psnr_drop,
        "reasons": [],
    }
    if not same_sign:
        payload["reasons"] = [f"Δ 有正有负（跨 seed 不稳定）：{deltas}"]
        return "SEED_UNSTABLE", payload
    if med >= CLAIM_FLOOR_CM:
        payload["reasons"] = [f"三 seed 同号但该臂更差：median Δ={med:+.3f}cm ≥ +{CLAIM_FLOOR_CM}"]
        return "WORSE", payload
    if abs(med) < CLAIM_FLOOR_CM:
        payload["reasons"] = [f"三 seed 同号，但 |median Δ|={abs(med):.3f}cm < {CLAIM_FLOOR_CM}"]
        return "BELOW_CLAIM_FLOOR", payload
    # 剩下是 med ≤ −0.5cm（改善）⇒ 过三关才判正面
    bad = []
    if min(ratios) < RATIO_LO:
        bad.append(f"min gauss_ratio={min(ratios):.3f} < {RATIO_LO}（地图可能退化）")
    if max(ratios) > RATIO_HI:
        bad.append(f"max gauss_ratio={max(ratios):.3f} > {RATIO_HI}（剂量膨胀）")
    if max_psnr_drop > PSNR_DROP_DB:
        bad.append(f"static PSNR 最多掉 {max_psnr_drop:.3f}dB > {PSNR_DROP_DB}dB")
    if bad:
        payload["reasons"] = [f"ATE 改善 median Δ={med:+.3f}cm，但", *bad,
                              "⇒ 剂量/质量混杂，不可区分"]
        return "DOSE_CONFOUND", payload
    payload["reasons"] = [
        f"ATE 改善 median Δ={med:+.3f}cm 且 ratio ∈ [{min(ratios):.3f}, {max(ratios):.3f}] "
        f"在 [{RATIO_LO}, {RATIO_HI}] 内、static PSNR 掉 {max_psnr_drop:.3f}dB ≤ {PSNR_DROP_DB}dB "
        f"⇒ 默认剂量过量（配置结论，非机制贡献）"]
    return "POSITIVE_DEFAULT_OVERDOSED", payload


def joint(verdicts, payloads):
    """§3.3 汇合出口。路由顺序写死：先判更具体的 MONOTONE，再判 BOTH_SIDES_WORSE。

    （两个条件有包含关系——两臂都 WORSE 且越低越差，同时满足 MONOTONE 与 BOTH_SIDES_WORSE
    ⇒ 必须定死优先级，否则判据机行为取决于代码书写顺序，不可复核。）
    """
    vals = list(verdicts.values())
    works = [v == "WORSE" for v in vals]
    below = [v == "BELOW_CLAIM_FLOOR" for v in vals]

    # 仪器无效优先：任一侧 INVALID 时不得再判任何效应出口（否则 rc 与结论脱钩）
    if any(v == "INSTRUMENT_INVALID" for v in vals):
        bad = [a for a, v in verdicts.items() if v == "INSTRUMENT_INVALID"]
        return "INSTRUMENT_INVALID", [f"臂 {bad} 仪器闸未过 ⇒ 整批作废，不判效应"]

    meds = {a: payloads[a].get("median_delta_ate_cm") for a in ("tau2x", "tau4x")
            if a in payloads}
    monotone = (all(works) and len(meds) == 2
                and meds.get("tau2x") is not None and meds.get("tau4x") is not None
                and meds["tau4x"] > meds["tau2x"])

    if monotone:
        return "MONOTONE_WORSE_DOWN", [
            f"剂量越低越差：med(tau2x)={meds['tau2x']:+.3f} < med(tau4x)={meds['tau4x']:+.3f}"
            f" ⇒ 剂量轴两侧闭合且单向"]
    if all(works) or all(below) or (any(works) and any(below)):
        reason = ("剂量轴两侧闭合：更少也不改善（两臂均更差）" if all(works)
                  else "剂量轴两侧闭合：更少侧无改善（一臂更差/一臂低于可主张下限）")
        return "BOTH_SIDES_WORSE", [f"{reason}：{verdicts}"]
    if any(v == "POSITIVE_DEFAULT_OVERDOSED" for v in vals):
        pos = [a for a, v in verdicts.items() if v == "POSITIVE_DEFAULT_OVERDOSED"]
        return "DOWN_SIDE_HAS_EFFECT", [f"{pos} 判正面 ⇒ 默认剂量过量（配置结论）"]
    return "INCONCLUSIVE", [f"出口组合未落任何机械分支：{verdicts}"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--off-root", required=True)
    ap.add_argument("--arm", action="append", required=True,
                    help="name=path，可重复（如 tau2x=... tau4x=...）")
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--off-run", nargs="*", default=None, metavar="SEED=RUNDIR",
                    help="钉住 off 臂的 run 目录（可重复）。不钉则取最新合格 run。")
    ap.add_argument("--arm-run", nargs="*", default=None, metavar="ARM:SEED=RUNDIR",
                    help="钉住某臂的 run 目录（可重复，如 tau2x:0=2026-11-06-22-54-31）。")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    def _pins(spec, sep):
        out = {}
        for item in (spec or []):
            head, _, v = item.rpartition("=")
            if sep == ":":
                a, _, k = head.partition(":")
                if not a or not k.isdigit() or not v:
                    ap.error(f"--arm-run 需要 ARM:SEED=RUNDIR 形式，收到 {item!r}")
                out.setdefault(a, {})[int(k)] = v
            else:
                if not head.isdigit() or not v:
                    ap.error(f"--off-run 需要 SEED=RUNDIR 形式，收到 {item!r}")
                out[int(head)] = v
        return out

    off_pins = _pins(args.off_run, "=")
    arm_pins = _pins(args.arm_run, ":")

    off_root = Path(args.off_root)
    arms = {}
    for spec in args.arm:
        name, _, path = spec.partition("=")
        if not name or not path:
            ap.error(f"--arm 需要 name=path 形式，收到 {spec!r}")
        arms[name] = Path(path)

    report = {
        "prereg": "paper3/results/evidence/prereg_dose_reverse_2026-11-06.md",
        "seeds": args.seeds,
        "claim_floor_cm": CLAIM_FLOOR_CM,
        "gauss_ratio_band": [RATIO_LO, RATIO_HI],
        "psnr_drop_cap_db": PSNR_DROP_DB,
        "n_frames_expected": N_FRAMES_EXPECTED,
        "per_arm": {},
        "joint_verdict": None,
        "reasons": [],
    }

    off_rows = {}
    off_errs = {}
    seed_gate_err = None
    if tuple(sorted(args.seeds)) != SEEDS_EXPECTED:
        seed_gate_err = (f"seed 集 {sorted(args.seeds)} != prereg 固定的 "
                         f"{list(SEEDS_EXPECTED)}（§3 三 seed 判据）")
    for s in args.seeds:
        rec, err = collect(off_root, s, pin=off_pins.get(s))
        off_rows[s] = rec
        if err:
            off_errs[s] = err

    verdicts, payloads = {}, {}
    for name, root in arms.items():
        arm_rows, errs = {}, {}
        for s in args.seeds:
            rec, err = collect(root, s, pin=arm_pins.get(name, {}).get(s))
            arm_rows[s] = rec
            if err:
                errs[s] = err
        if seed_gate_err:
            v, payload = "INSTRUMENT_INVALID", {"per_seed": {}, "reasons": [seed_gate_err]}
        else:
            v, payload = judge_arm(off_rows, arm_rows, args.seeds)
        if errs:
            payload.setdefault("reasons", []).extend(f"{k}: {e}" for k, e in errs.items())
        payloads[name] = payload
        verdicts[name] = v
        report["per_arm"][name] = {"verdict": v, **payload}
    if off_errs:
        report["off_errors"] = off_errs

    report["joint_verdict"], report["reasons"] = joint(verdicts, payloads)

    # 打印
    for name in arms:
        p = report["per_arm"][name]
        print(f"=== arm {name}: {p['verdict']} ===")
        print(f"{'seed':>4} {'off_ATE':>9} {'arm_ATE':>9} {'ΔATE':>9} {'ratio':>7} "
              f"{'psnrΔ':>8}")
        for s, v in p.get("per_seed", {}).items():
            if isinstance(v, dict) and "off" in v and v.get("off"):
                pass  # run 名在行内打印
            if "delta_ate_cm" in v:
                print(f"{s:>4} {v['off']['ate_cm']:>9.4f} {v['arm']['ate_cm']:>9.4f} "
                      f"{v['delta_ate_cm']:>+9.4f} {v['gauss_ratio']:>7.4f} "
                      f"{v.get('psnr_delta_db', float('nan')):>+8.3f}")
                print(f"       used: off={v['off']['run']}  {name}={v['arm']['run']}")
            else:
                print(f"{s:>4}  INVALID")
        for r in p.get("reasons", []):
            print(f"  - {r}")
        print()
    print(f"JOINT VERDICT: {report['joint_verdict']}")
    for r in report["reasons"]:
        print(f"  - {r}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    # fail-closed（G3 审查 M6）：任一臂 INSTRUMENT_INVALID ⇒ rc=2，批次脚本据此中止。
    return 2 if any(v == "INSTRUMENT_INVALID" for v in verdicts.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
