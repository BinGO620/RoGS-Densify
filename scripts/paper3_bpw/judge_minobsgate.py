#!/usr/bin/env python3
"""MinObsGate 四门判读器（prereg_minobs_gate_2026-11-06 §3，机械执行）。

M1 效应门   |median ΔATE| >= 0.5cm 且三 seed 同号
M2 预算门   |gauss_ratio - 1| <= 0.10（不守恒机制的硬性混杂门）
M3 质量门   on PSNR >= off - 0.5dB
M4 出口     M1过+方向负+M2+M3 ⇒ 正面读数候选；M1过+方向正 ⇒ 负向关闭；
            M1不过 ⇒ 关闭；任何出口不产生协议贡献主张。

用法:
  python scripts/paper3_bpw/judge_minobsgate.py \
    --off-root results/paper3_bpw/minobsgate_off/datasets_bonn/minobsgate_off \
    --on-root  results/paper3_bpw/minobsgate_on/datasets_bonn/minobsgate_on \
    --seeds 0 1 2 --out paper3/results/evidence/minobsgate_judge.json
"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

N_FRAMES_EXPECTED = 580
CLAIM_FLOOR_CM = 0.5
BUDGET_RATIO_TOL = 0.10
PSNR_TOLERANCE_DB = 0.5


def read_frames(path):
    with path.open(newline="") as fh:
        return len(list(csv.DictReader(fh)))


def read_done(run):
    hits = sorted(run.glob("instrument_*.done"))
    if not hits:
        return None
    kv = {}
    for line in hits[-1].read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def collect(root, seed, prefer_frames=N_FRAMES_EXPECTED):
    base = root / f"seed_{seed}"
    if not base.is_dir():
        return None, f"缺 seed_{seed} 目录"
    runs = sorted([d for d in base.iterdir() if d.is_dir()], key=lambda d: d.name)
    if not runs:
        return None, f"seed_{seed} 无 run 目录"
    candidates, chosen, failed = [], None, []
    for d in runs:
        pf = d / "per_frame_ape.csv"
        nf = read_frames(pf) if pf.is_file() else None
        candidates.append(f"{d.name}(frames={nf})")
        kv = read_done(d)
        if kv is not None and kv.get("finished_rc0") != "yes":
            failed.append(f"{d.name}(rc={kv.get('rc')})")
            continue
        if nf == prefer_frames and (d / "tracking_raw.csv").is_file():
            chosen = d
    suffix = f"；rc!=0 的 run: {', '.join(failed)}" if failed else ""
    if chosen is None:
        return None, (f"seed_{seed} 无 {prefer_frames} 帧完成 run{suffix}；"
                      f"候选: {', '.join(candidates[-4:])}")
    tr = list(csv.DictReader(open(chosen / "tracking_raw.csv")))[0]
    er = list(csv.DictReader(open(chosen / "efficiency_raw.csv")))[0]
    mr = None
    mp = chosen / "mapping_raw.csv"
    if mp.is_file():
        rows = list(csv.DictReader(open(mp)))
        if rows:
            mr = rows[-1]
    out = {
        "run": chosen.name,
        "ate_cm": float(tr["ate_rmse_cm"]),
        "gaussians": int(float(er["online_num_gaussians"])),
        "psnr": float(mr["psnr"]) if mr and mr.get("psnr") not in (None, "", "nan") else None,
        "depth_l1_cm": (float(mr["depth_l1_cm"])
                        if mr and mr.get("depth_l1_cm") not in (None, "", "None", "nan") else None),
        "frames": prefer_frames,
    }
    return out, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--off-root", required=True)
    ap.add_argument("--on-root", required=True)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    off_root, on_root = Path(args.off_root), Path(args.on_root)
    report = {"gate_results": {}, "per_seed": {}, "verdict": None, "reasons": []}

    invalid = []
    for s in args.seeds:
        o, eo = collect(off_root, s)
        n, en = collect(on_root, s)
        report["per_seed"][s] = {"off": o, "on": n, "err_off": eo, "err_on": en}
        if o is None or n is None:
            invalid.append(f"seed{s}: {eo or en}")

    if invalid:
        report["verdict"] = "INVALID"
        report["reasons"] = invalid
    else:
        deltas = [v["on"]["ate_cm"] - v["off"]["ate_cm"] for v in report["per_seed"].values()]
        ratios = [v["on"]["gaussians"] / v["off"]["gaussians"] for v in report["per_seed"].values()]
        med = statistics.median(deltas)
        same_sign = len({d > 0 for d in deltas}) == 1

        # M1 效应门
        m1 = same_sign and abs(med) >= CLAIM_FLOOR_CM
        report["gate_results"]["M1"] = {
            "deltas": [round(d, 4) for d in deltas], "median_delta": round(med, 4),
            "same_sign": same_sign, "pass": m1}
        # M2 预算门
        m2 = all(abs(r - 1.0) <= BUDGET_RATIO_TOL for r in ratios)
        report["gate_results"]["M2"] = {
            "ratios": [round(r, 4) for r in ratios],
            "tol": BUDGET_RATIO_TOL, "pass": m2}
        # M3 质量门
        psnr_pairs = [(v["off"]["psnr"], v["on"]["psnr"]) for v in report["per_seed"].values()]
        if all(p is not None and q is not None for p, q in psnr_pairs):
            worst = min(q - p for p, q in psnr_pairs)
            m3 = worst >= -PSNR_TOLERANCE_DB
            report["gate_results"]["M3"] = {
                "psnr_worst_drop_db": round(worst, 3),
                "tol": PSNR_TOLERANCE_DB, "pass": m3}
        else:
            m3 = None
            report["gate_results"]["M3"] = {"note": "PSNR 缺失，跳过（不阻塞 M4 判读）"}

        # M4 出口
        if not m1:
            report["verdict"] = "CLOSED_NO_EFFECT"
            report["reasons"] = [f"M1 不过（median Δ={med:+.3f}cm，同号={same_sign}）⇒ 机制无读数，关闭"]
        elif med > 0:
            report["verdict"] = "CLOSED_NEGATIVE"
            report["reasons"] = [f"M1 过但方向为正（on 更差，median {med:+.3f}cm）⇒ 负向，关闭"]
        else:
            if m2 and (m3 is None or m3):
                report["verdict"] = "POSITIVE_CANDIDATE"
                report["reasons"] = [f"M1+M2+M3 全过（median Δ={med:+.3f}cm）⇒ 正面读数候选，进 9 序列扩展"]
            elif m3 is False:
                report["verdict"] = "TRADEOFF"
                report["reasons"] = [f"M1 过且方向负但 M3 质量门不过 ⇒ L-TRADEOFF，不得只报 ATE"]
            else:
                report["verdict"] = "BUDGET_CONFOUND"
                report["reasons"] = [f"M1 过且方向负但 M2 预算门不过 ⇒ 效应与预算混杂，只记边界读数"]

    print(f"{'seed':>4} {'off_ATE':>9} {'on_ATE':>9} {'Δ':>9} {'gauss比':>8} {'off_PSNR':>9} {'on_PSNR':>9}")
    for s, v in report["per_seed"].items():
        if v["off"] and v["on"]:
            o, n = v["off"], v["on"]
            ratio = n["gaussians"] / o["gaussians"]
            op = f"{o['psnr']:.3f}" if o["psnr"] else "—"
            np_ = f"{n['psnr']:.3f}" if n["psnr"] else "—"
            print(f"{s:>4} {o['ate_cm']:>9.4f} {n['ate_cm']:>9.4f} "
                  f"{n['ate_cm']-o['ate_cm']:>+9.4f} {ratio:>8.4f} {op:>9} {np_:>9}")
        else:
            print(f"{s:>4}  INVALID: {v['err_off'] or v['err_on']}")
    print()
    for g, r in report["gate_results"].items():
        print(f"  {g}: {'PASS' if r.get('pass') else ('FAIL' if r.get('pass') is False else 'SKIP')}  {r}")
    print(f"\nVERDICT: {report['verdict']}")
    for r in report["reasons"]:
        print(f"  - {r}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
