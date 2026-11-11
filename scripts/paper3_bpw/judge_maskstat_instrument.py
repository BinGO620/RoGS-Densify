#!/usr/bin/env python3
"""MaskStat 仪器模式判读器（P3-D2-031 / prereg_maskstat_instrument_2026-11-05 §3）。

读 3 seeds × 2 臂的全长 run，按 prereg §3.2 的机械规则出判决。

用法：
  python scripts/paper3_bpw/judge_maskstat_instrument.py \
      --off-root results/paper3_bpw/instrument_maskstat_off/datasets_bonn/instrument_maskstat_off \
      --on-root  results/paper3_bpw/instrument_maskstat_on/datasets_bonn/instrument_maskstat_on \
      --seeds 0 1 2 --out paper3/results/evidence/maskstat_instrument_judge_2026-11-05.json

出口（prereg §3.2）：
  DIRECTIONAL_EFFECT     方向一致且 |median ΔATE| >= 0.5cm
  BELOW_CLAIM_FLOOR      方向一致但 |median ΔATE| < 0.5cm
  SEED_UNSTABLE          方向不一致（有正有负）
  INSTRUMENT_INVALID     缺 run / rc!=0 / 帧数不足
"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

N_FRAMES_EXPECTED = 580
CLAIM_FLOOR_CM = 0.5


def read_row(path):
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[0] if rows else None


def read_frames(path):
    with path.open(newline="") as fh:
        return len(list(csv.DictReader(fh)))


def read_done(run):
    """读 run 目录里的 instrument_*.done，返回 (kv dict, path)；无则 (None, None)。

    项目 .done 惯例（run_maskstat_l1.sh / run_fdose_l1.sh 同款）要求写
    `finished_rc0=yes|no`。2026-11-05 on/seed0 在 KF430 因显存耗尽退出（rc=1）
    却仍写了 .done，说明只看「有没有 per_frame_ape.csv」不足以防半程 run 混入。
    """
    hits = sorted(run.glob("instrument_*.done"))
    if not hits:
        return None, None
    kv = {}
    for line in hits[-1].read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv, hits[-1]


def collect(root, seed, prefer_frames=N_FRAMES_EXPECTED):
    """返回该 seed 的**符合帧数期望且 rc=0** 的最新 run，及读数。

    一个 arm 目录里会混有冒烟/P2 的短 run 和正式的全长 run。取「最新」会拿到
    尚未跑完的空目录（本轮实测），所以按「帧数符合期望」筛选后再取最新；
    一个都没有 ⇒ 明确报出候选及其帧数，便于人看清是「还没跑完」还是「跑挂了」。

    另加一道 rc 闸：有 .done 但 finished_rc0 != yes（如 OOM 半程）⇒ 直接排除并写明，
    绝不因为「帧数恰好对上」就把它当数据。
    """
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
        kv, _ = read_done(d)
        if kv is not None and kv.get("finished_rc0") != "yes":
            failed.append(f"{d.name}(rc={kv.get('rc')})")
            continue
        if nf == prefer_frames and (d / "tracking_raw.csv").is_file():
            chosen = d
    if failed:
        # 有失败的完成锚点：即使另有可用 run，也要让人看见「这条臂挂过一次」。
        suffix = f"；rc!=0 的 run: {', '.join(failed)}"
    else:
        suffix = ""
    if chosen is None:
        return None, (f"seed_{seed} 无 {prefer_frames} 帧的完成 run{suffix}；"
                      f"候选: {', '.join(candidates[-4:])}")
    run = chosen
    t = run / "tracking_raw.csv"
    e = run / "efficiency_raw.csv"
    if not t.is_file() or not e.is_file():
        return None, f"{run.name} 缺 tracking_raw/efficiency_raw"
    tr = read_row(t)
    er = read_row(e)
    if tr is None or er is None:
        return None, f"{run.name} 表为空"
    out = {
        "run": run.name,
        "ate_cm": float(tr["ate_rmse_cm"]),
        "kf_ate_cm": float(tr["keyframe_ate_rmse_cm"]),
        "rpe_cm": float(tr["rpe_trans_rmse_cm"]),
        "gaussians": int(float(er["num_gaussians"])),
        "map_iterations": int(float(er["mapping_iterations"])),
        "frames": None,
    }
    pf = run / "per_frame_ape.csv"
    if pf.is_file():
        out["frames"] = read_frames(pf)
    return out, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--off-root", required=True)
    ap.add_argument("--on-root", required=True)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    # 帧数期望必须随序列变（pt=580、crowd=928…）：Bonn 各序列全长不同。
    # 2026-11-07 crowd L2 事故：判读器硬编码 580 ⇒ crowd 全长 run（928 帧，全 rc0）
    # 被误判 INSTRUMENT_INVALID。默认保持 580（pt 族向后兼容），其它序列显式传。
    ap.add_argument("--expect-frames", type=int, default=N_FRAMES_EXPECTED,
                    help="该序列的全长期望帧数（pt=580、crowd=928）；须与 run 实际一致")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    expect = args.expect_frames

    off_root, on_root = Path(args.off_root), Path(args.on_root)
    report = {"seeds": args.seeds, "claim_floor_cm": CLAIM_FLOOR_CM,
              "n_frames_expected": expect, "per_seed": {}, "verdict": None,
              "reasons": []}

    invalid = []
    for s in args.seeds:
        o, eo = collect(off_root, s, prefer_frames=expect)
        n, en = collect(on_root, s, prefer_frames=expect)
        rec = {"off": o, "on": n, "err_off": eo, "err_on": en}
        if o is None or n is None:
            invalid.append(f"seed{s}: {eo or en}")
            report["per_seed"][s] = rec
            continue
        rec["delta_ate_cm"] = round(n["ate_cm"] - o["ate_cm"], 4)
        rec["gauss_ratio"] = round(n["gaussians"] / o["gaussians"], 4) if o["gaussians"] else None
        for tag, r in (("off", o), ("on", n)):
            if r["frames"] is not None and r["frames"] != expect:
                invalid.append(f"seed{s} {tag}: 帧数 {r['frames']} != {expect}")
        report["per_seed"][s] = rec

    deltas = [v["delta_ate_cm"] for v in report["per_seed"].values() if "delta_ate_cm" in v]
    if invalid:
        report["verdict"] = "INSTRUMENT_INVALID"
        report["reasons"] = invalid
    elif len(deltas) < 2:
        report["verdict"] = "INSTRUMENT_INVALID"
        report["reasons"] = ["有效 seed 少于 2 个"]
    else:
        med = statistics.median(deltas)
        report["median_delta_ate_cm"] = round(med, 4)
        report["deltas"] = deltas
        signs = {d > 0 for d in deltas}
        if len(signs) > 1:
            report["verdict"] = "SEED_UNSTABLE"
            report["reasons"] = [f"Δ 有正有负：{deltas}"]
        elif abs(med) >= CLAIM_FLOOR_CM:
            report["verdict"] = "DIRECTIONAL_EFFECT"
            report["reasons"] = [f"三 seed 同号，|median Δ|={abs(med):.3f}cm >= {CLAIM_FLOOR_CM}cm"]
        else:
            report["verdict"] = "BELOW_CLAIM_FLOOR"
            report["reasons"] = [f"三 seed 同号，但 |median Δ|={abs(med):.3f}cm < {CLAIM_FLOOR_CM}cm"]

    # 打印
    print(f"{'seed':>4} {'off_ATE':>9} {'on_ATE':>9} {'ΔATE':>9} {'gauss_off':>10} {'gauss_on':>9} {'ratio':>7}")
    for s, v in report["per_seed"].items():
        if "delta_ate_cm" in v:
            o, n = v["off"], v["on"]
            print(f"{s:>4} {o['ate_cm']:>9.4f} {n['ate_cm']:>9.4f} {v['delta_ate_cm']:>+9.4f} "
                  f"{o['gaussians']:>10d} {n['gaussians']:>9d} {v['gauss_ratio']:>7.4f}")
        else:
            print(f"{s:>4}  INVALID: {v['err_off'] or v['err_on']}")
    print(f"\nVERDICT: {report['verdict']}")
    for r in report["reasons"]:
        print(f"  - {r}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    # fail-closed（2026-11-07 G2 对 crowd L2 的复现件暴露：INVALID 也 rc=0，
    # 与 G3-M6 同款）：INSTRUMENT_INVALID ⇒ rc=2，与 judge_dose 族一致。
    return 2 if report["verdict"] == "INSTRUMENT_INVALID" else 0


if __name__ == "__main__":
    sys.exit(main())
