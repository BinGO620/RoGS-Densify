#!/usr/bin/env python3
"""剂量过供给验证批判读器（prereg_dose_oversupply_2026-11-07 §4，机械执行）。

H1（churn→增益同序）路由：
  PREDICTION_CONFIRMED   三序列 gain 均可判、严格同序（crowd > mnobox > balloon）
                         且三序列 gain 全 > 0.5cm
                         （注：比 prereg §4 字面更严——prereg 只要求 crowd > 0.5；
                         2026-11-08 G2-次要③ 登记为已知偏差，未触发前不改码）
  GAIN_NO_PREDICTOR      三序列均可判且都 > 0.5cm 但排序错乱
  SEQUENCE_DEPENDENT     部分序列可判为正、部分未判/无增益
  NO_GENERALIZATION      三序列均可判但都 < 0.5cm 或为负
  INSTRUMENT_INVALID     硬门不过（帧数/rc/缺 run）。注：R-valid 逐位比对不在本
                         判读器——它由 run_instrument.sh 的 R1 门（exit 6）承担；
                         本判读器只做 rc 闸 + 帧数闸 + 读数可解析闸。

gain(seq) = −median{Δ(tau4x − off) per seed}（越大越好）；某序列两 seed 异号 ⇒
该序列 gain 记「未判」（UNJUDGED），不取中位假装有值。

H2（左端点位置）为报告项：dose_zero vs pt 默认的 seed 中位差，前沿形状分类在判决文档做。
H2 fail-closed（G3-C5 整改 2026-11-08）：三 seed 任一缺失 ⇒ 不出中位（旧版部分
seed 缺失仍出 median = 静默 n=1 降级）。

用法（Amendment A1 落纸命令，roots 为实测目录；G3-C5）:
  python scripts/paper3_bpw/judge_dose_oversupply.py \
    --pair crowd:results/paper3_bpw/instr_off_crowd/datasets_bonn/instr_off_crowd:results/paper3_bpw/instrument_dose_tau4x_crowd/datasets_bonn/instrument_dose_tau4x_crowd:928 \
    --pair balloon:results/paper3_bpw/instr_off_balloon/datasets_bonn/instr_off_balloon:results/paper3_bpw/instrument_dose_tau4x_balloon/datasets_bonn/instrument_dose_tau4x_balloon:439 \
    --pair mnobox:results/paper3_bpw/instr_off_moving_nonobstructing_box/datasets_bonn/instr_off_moving_nonobstructing_box:results/paper3_bpw/instrument_dose_tau4x_moving_nonobstructing_box/datasets_bonn/instrument_dose_tau4x_moving_nonobstructing_box:778 \
    --seeds 0 1 2 \
    --zero-root results/paper3_bpw/instrument_dose_zero_person_tracking/datasets_bonn/instrument_dose_zero_person_tracking \
    --zero-default-root results/paper3_bpw/instrument_maskstat_off/datasets_bonn/instrument_maskstat_off \
    --zero-frames 580 \
    --out paper3/results/evidence/dose_oversupply_judge_seed3_2026-11-08.json
"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

CLAIM_FLOOR_CM = 0.5
# H1 的预测排序（gain 从大到小）；键 = 传参名
PREDICTED_ORDER = ("crowd", "mnobox", "balloon")


def _finite(x):
    return x is not None and isinstance(x, (int, float)) and statistics.isfinite(x) \
        if False else (x is not None and isinstance(x, (int, float)) and x == x and abs(x) != float("inf"))


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


def collect(root, seed, prefer_frames):
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
    try:
        ate = float(tr["ate_rmse_cm"])
        gauss = int(float(er["online_num_gaussians"]))
    except (TypeError, ValueError, KeyError) as exc:
        return None, f"{chosen.name} 读数不可解析: {exc}"
    if not (_finite(ate) and gauss > 0):
        return None, f"{chosen.name} ATE/高斯数非有限或非正"
    out = {"run": chosen.name, "ate_cm": ate, "gaussians": gauss, "frames": prefer_frames}
    mp = chosen / "mapping_raw.csv"
    if mp.is_file():
        rows = list(csv.DictReader(open(mp)))
        by_mask = {r.get("mask_type"): r for r in rows}
        for mask_type, prefix in (("static", "static"), ("full", "full")):
            r = by_mask.get(mask_type)
            if r is None:
                out[f"{prefix}_psnr_db"] = None
                out[f"{prefix}_depth_l1_cm"] = None
                continue
            for key, suffix2 in (("psnr", "psnr_db"), ("depth_l1_cm", "depth_l1_cm")):
                v = r.get(key)
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    fv = None
                out[f"{prefix}_{suffix2}"] = fv if _finite(fv) else None
    return out, None


def judge_sequence(off_root, tau_root, frames, seeds):
    """返回 (status, payload)。status ∈ {ok, invalid}。"""
    per, errs = {}, []
    for s in seeds:
        o, eo = collect(off_root, s, frames)
        a, ea = collect(tau_root, s, frames)
        if o is None or a is None:
            errs.append(f"seed{s}: {eo or ea}")
            continue
        rec = {"off": o, "tau4x": a,
               "delta_ate_cm": round(a["ate_cm"] - o["ate_cm"], 4),
               "gauss_ratio": round(a["gaussians"] / o["gaussians"], 4) if o["gaussians"] else None}
        if a.get("refined") is not None and o.get("refined") is not None:
            pass
        if a.get("static_psnr_db") is not None and o.get("static_psnr_db") is not None:
            rec["psnr_delta_db"] = round(a["static_psnr_db"] - o["static_psnr_db"], 4)
        per[s] = rec
    if errs or len(per) < len(seeds):
        return "invalid", {"per_seed": per, "reasons": errs or ["有效 seed 不足"]}
    deltas = [v["delta_ate_cm"] for v in per.values()]
    ratios = [v["gauss_ratio"] for v in per.values()]
    if not all(_finite(x) for x in deltas) or not all(_finite(x) for x in ratios):
        return "invalid", {"per_seed": per, "reasons": ["Δ 或 ratio 非有限"]}
    signs = {d > 0 for d in deltas}
    payload = {"per_seed": per, "deltas": deltas, "gauss_ratios": ratios,
               "same_sign": len(signs) == 1, "reasons": []}
    if len(signs) > 1:
        payload["gain_cm"] = None
        payload["judged"] = False
        payload["reasons"] = [f"两 seed 异号（未判，不取中位）：{deltas}"]
    else:
        med = statistics.median(deltas)
        payload["gain_cm"] = round(-med, 4)   # gain = −Δ（改善为正）
        payload["judged"] = True
        payload["median_delta_ate_cm"] = round(med, 4)
    return "ok", payload


def route_h1(per_seq):
    """H1 机械路由（prereg §4）。

    输入形状 = main() 的摊平存储（{"status":..., **payload}）——2026-11-08 修复：
    原实现按嵌套 "payload" 读，与 main 的实际存储不一致（单测构造了嵌套形状
    ⇒ 没抓到接线 bug；真实数据首跑即 KeyError）。单测已改为摊平形状。
    """
    invalid = [s for s, v in per_seq.items() if v["status"] == "invalid"]
    if invalid:
        return "INSTRUMENT_INVALID", [f"序列 {invalid} 硬门不过 ⇒ 整批作废"]
    judged = {s: v.get("judged") for s, v in per_seq.items()}
    gains = {s: v.get("gain_cm") for s, v in per_seq.items()}
    unjudged = [s for s, j in judged.items() if not j]
    positives = [s for s, g in gains.items() if g is not None and g > CLAIM_FLOOR_CM]
    if unjudged:
        if positives:
            return "SEQUENCE_DEPENDENT", [
                f"可判为正: {positives}；未判(异号): {unjudged} ⇒ 剂量处方需按序列诊断"]
        return "SEQUENCE_DEPENDENT", [f"可判序列均无增益；未判: {unjudged}"]
    # 三序列均可判
    if all(g > CLAIM_FLOOR_CM for g in gains.values()):
        order = tuple(sorted(gains, key=lambda s: -gains[s]))
        if order == PREDICTED_ORDER and gains["crowd"] > CLAIM_FLOOR_CM:
            return "PREDICTION_CONFIRMED", [
                f"增益严格同序 {dict((s, gains[s]) for s in order)}，"
                f"churn→增益预测成立（crowd={gains['crowd']:.3f} > {CLAIM_FLOOR_CM}）"]
        return "GAIN_NO_PREDICTOR", [
            f"三序列均改善但排序错乱: 实测 {dict((s, gains[s]) for s in order)} vs "
            f"预测 {PREDICTED_ORDER} ⇒ churn 不预测增益（标定研究退守）"]
    if all(g <= CLAIM_FLOOR_CM for g in gains.values()):
        return "NO_GENERALIZATION", [
            f"三序列均无 ≥{CLAIM_FLOOR_CM} 增益: {gains} ⇒ pt 读数不泛化"]
    # 混合：部分 >0.5 部分非正
    pos = [s for s in positives]
    return "SEQUENCE_DEPENDENT", [
        f"部分序列可判为正（{pos}）、其余无增益 ⇒ 剂量处方按序列诊断"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pair", action="append", required=True,
                    help="NAME:OFF_ROOT:TAU_ROOT:FRAMES（如 crowd:...:...:928），可重复")
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1])
    ap.add_argument("--zero-root", default="",
                    help="dose_zero 臂根（H2 报告项；需与 --zero-default-root 同给）")
    ap.add_argument("--zero-default-root", default="",
                    help="pt 默认臂根（H2 的对照）")
    ap.add_argument("--zero-frames", type=int, default=582)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    seeds = args.seeds
    report = {
        "prereg": "paper3/results/evidence/prereg_dose_oversupply_2026-11-07.md",
        "seeds": seeds,
        "claim_floor_cm": CLAIM_FLOOR_CM,
        "predicted_order": list(PREDICTED_ORDER),
        "per_seq": {},
        "h1_verdict": None,
        "h2": None,
        "reasons": [],
    }

    per_seq = {}
    for spec in args.pair:
        name, off_root, tau_root, frames = spec.split(":")
        frames = int(frames)
        status, payload = judge_sequence(Path(off_root), Path(tau_root), frames, seeds)
        per_seq[name] = {"status": status, **payload}

    # 命名归一：允许 mnobox 别名 → PREDICTED_ORDER 用 mnobox
    if "moving_nonobstructing_box" in per_seq:
        per_seq["mnobox"] = per_seq.pop("moving_nonobstructing_box")
    report["per_seq"] = per_seq

    h1, reasons = route_h1(per_seq)
    report["h1_verdict"] = h1
    report["reasons"] = reasons

    if args.zero_root and args.zero_default_root:
        zd, zerrs = [], []
        for s in (0, 1, 2):
            o, eo = collect(Path(args.zero_default_root), s, args.zero_frames)
            z, ez = collect(Path(args.zero_root), s, args.zero_frames)
            if o and z:
                zd.append(round(z["ate_cm"] - o["ate_cm"], 4))
            else:
                zerrs.append(f"seed{s}: {eo or ez}")
        # G3-C5 整改（2026-11-08）：三 seed 任一缺失 ⇒ 不出中位（旧版 zd 非空即出
        # median = 部分 seed 缺失静默降级为 n<3 读数）。H2 是报告项，但不能以
        # n=1 中位数冒充三 seed 中位。
        if len(zd) == 3:
            h2_median = round(statistics.median(zd), 4)
        else:
            h2_median = None
            zerrs.append("H2 seed 不全 ⇒ 不出中位（fail-closed）")
        report["h2"] = {"median_delta_vs_default_cm": h2_median,
                        "deltas": zd, "errors": zerrs,
                        "note": "H2 前沿形状分类在判决文档做（prereg §2 三形态）"}

    print(f"{'seq':>10} {'status':>8} {'gain_cm':>8} {'judged':>7} {'Δ':>22}")
    for name, v in per_seq.items():
        if v["status"] == "invalid":
            print(f"{name:>10} {'INVALID':>8} {'-':>8} {'-':>7}  {v.get('reasons')}")
            continue
        deltas = ",".join(f"{d:+.3f}" for d in v["deltas"])
        g = v.get("gain_cm")
        print(f"{name:>10} {v['status']:>8} "
              f"{(f'{g:.4f}' if g is not None else 'UNJUDGED'):>8} "
              f"{str(v.get('judged')):>7}  [{deltas}]")
        for r in v.get("reasons", []):
            print(f"          - {r}")
    print(f"\nH1 VERDICT: {report['h1_verdict']}")
    for r in report["reasons"]:
        print(f"  - {r}")
    if report["h2"]:
        print(f"H2 (zero vs pt default): median Δ = "
              f"{report['h2']['median_delta_vs_default_cm']} cm; deltas={report['h2']['deltas']}"
              + (f"; errors={report['h2']['errors']}" if report['h2']['errors'] else ""))

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    invalid = report["h1_verdict"] == "INSTRUMENT_INVALID"
    return 2 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
