#!/usr/bin/env python3
"""剂量轴 A4 仪器口径判读器（prereg_dose_a4_instrument_2026-11-06 §3，机械执行）。

四条互斥出口（prereg §3.3）：
  POSITIVE_ATE_DOSE_OK       三 seed 同号 且 median Δ ≤ −0.5cm 且 max gauss_ratio ≤ 1.5
  DOSE_CONFOUND              三 seed 同号 且 median Δ ≤ −0.5cm 且 max gauss_ratio > 1.5
  BELOW_CLAIM_FLOOR          三 seed 同号 且 |median Δ| < 0.5cm
  CLOSED_NEGATIVE_OR_UNSTABLE median Δ ≥ +0.5cm（同号）或三 seed 异号
  INSTRUMENT_INVALID         §3.2 硬门不过（帧数 / rc / 缺 run）

用法:
  python scripts/paper3_bpw/judge_dose_a4_instrument.py \
    --off-root results/paper3_bpw/instrument_maskstat_off/datasets_bonn/instrument_maskstat_off \
    --a4-root  results/paper3_bpw/instrument_dose_a4_person_tracking/datasets_bonn/\
instrument_dose_a4_person_tracking \
    --seeds 0 1 2 --out paper3/results/evidence/dose_a4_instrument_judge_2026-11-06.json
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
GAUSS_RATIO_CAP = 1.5
# prereg §3.3 字面固定「三 seed」。判据机不得接受更少的 seed 数——
# 2026-11-06 G3 审查 F2 实测：旧版传 `--seeds 0` 就按单 seed 判正面（fail-open）。
SEEDS_EXPECTED = (0, 1, 2)


def _finite(x):
    """非有限（nan/inf/None）一律 False。

    2026-11-06 G3 审查 F1：旧版没有这道守卫，`median([nan,nan,nan])` 返回 nan，
    而 `nan >= 0.5` 与 `nan < 0.5` 同时为 False ⇒ 落进最后的 else 判 POSITIVE。
    `mapping_raw.csv` 的 full 行在本管线恒为 nan，这不是理论风险。
    """
    return x is not None and isinstance(x, (int, float)) and math.isfinite(float(x))



def read_frames(path):
    with path.open(newline="") as fh:
        return len(list(csv.DictReader(fh)))


def read_done(run):
    """读 instrument_*.done 的 kv；无锚点返回 None。

    没有 .done 一律当 rc 未知 ⇒ 判读器按 INSTRUMENT_INVALID 处理（fail-closed），
    不得因为「表看起来完整」就放行——OOM 半程 run 曾照样写出完整表头。
    """
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
    """取该 seed 的合格 run。**选择规则（prereg §3.2 冻结）**：

    1. 若给了 `pin`（run 目录名），只认它——目录不存在、无 `.done`、rc≠0、帧数不符
       一律返回错误，不回落其它 run（防止「显式指定却悄悄换了 run」）。
    2. 否则在全部 run 里筛「有 `.done` 且 finished_rc0=yes 且帧数=580」，取**目录名最大
       （= 最新时间戳）**的一个。

    **不在 prereg 里冻结这条会出问题**（G3 审查 M3）：同一命令在本地与远程因目录集不同
    会选到不同 run，判决就不可复算。
    """
    base = root / f"seed_{seed}"
    if not base.is_dir():
        return None, f"缺 seed_{seed} 目录"
    if pin:
        d = base / pin
        if not d.is_dir():
            return None, f"seed_{seed} 指定的 run 不存在：{pin}"
        runs = [d]
    else:
        runs = sorted([dd for dd in base.iterdir() if dd.is_dir()], key=lambda dd: dd.name)
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
        # F1 守卫：NaN/Inf 的 ATE 是「读数不存在」，不是「读数很好」。
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
    # 报告项：refined 规模 + 渲染代价（不参与 PASS/FAIL，但必须并陈）
    rn = er.get("refined_num_gaussians")
    out["refined_gaussians"] = int(float(rn)) if rn not in (None, "", "None", "MISSING") else None
    mp = chosen / "mapping_raw.csv"
    if mp.is_file():
        rows = list(csv.DictReader(open(mp)))
        # **按 mask_type 选行（2026-11-06 G3 审查 M5）**：本管线 `mapping_raw.csv` 同时写
        # 两行 —— `full`（全图）与 `static`（P-A 静态背景）。仪器口径下 `full` 行恒为 nan
        # （三族实测），旧版取末行 = 恰好取到 static，却把结果叫 "psnr"，与历史 A4 的
        # full 口径（19.79/20.12）混引。此处显式分列，且 full 缺失如实记 None。
        by_mask = {r.get("mask_type"): r for r in rows}
        for mask_type, prefix in (("full", "full"), ("static", "static")):
            r = by_mask.get(mask_type)
            if r is None:
                out[f"{prefix}_psnr_db"] = None
                out[f"{prefix}_depth_l1_cm"] = None
                continue
            # 键名带 `_db` = 显式标注 dB 单位，与反向扫判读器同名（防两族混引）
            for key, suffix in (("psnr", "psnr_db"), ("depth_l1_cm", "depth_l1_cm")):
                v = r.get(key)
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    fv = None
                out[f"{prefix}_{suffix}"] = fv if _finite(fv) else None
        # 兼容旧键：`psnr` = full 行的值（历史 A4 就是这个口径）；缺失则 None。
        out["psnr"] = out.get("full_psnr_db")
        out["depth_l1_cm"] = out.get("full_depth_l1_cm")
    return out, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--off-root", required=True)
    ap.add_argument("--a4-root", required=True)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--off-run", nargs="*", default=None, metavar="SEED=RUNDIR",
                    help="钉住 off 臂的 run 目录（可重复，如 0=2026-11-05-22-12-05）。"
                         "不钉则按「最新时间戳合格 run」选（prereg §3.2 规则 2）。")
    ap.add_argument("--a4-run", nargs="*", default=None, metavar="SEED=RUNDIR",
                    help="钉住 A4 臂的 run 目录（同上）。")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    def _pins(spec):
        out = {}
        for item in (spec or []):
            k, _, v = item.partition("=")
            if not k.isdigit() or not v:
                ap.error(f"--off-run/--a4-run 需要 SEED=RUNDIR 形式，收到 {item!r}")
            out[int(k)] = v
        return out

    off_pins, a4_pins = _pins(args.off_run), _pins(args.a4_run)

    off_root, a4_root = Path(args.off_root), Path(args.a4_root)
    report = {
        "prereg": "paper3/results/evidence/prereg_dose_a4_instrument_2026-11-06.md",
        "seeds": args.seeds,
        "claim_floor_cm": CLAIM_FLOOR_CM,
        "gauss_ratio_cap": GAUSS_RATIO_CAP,
        "n_frames_expected": N_FRAMES_EXPECTED,
        "per_seed": {},
        "verdict": None,
        "reasons": [],
    }

    invalid = []
    # F2 守卫：prereg §3.3 固定三 seed。seed 集不符即 INVALID，不得按更少的 seed 判出口。
    seed_gate_err = None
    if tuple(sorted(args.seeds)) != SEEDS_EXPECTED:
        seed_gate_err = (f"seed 集 {sorted(args.seeds)} != prereg 固定的 "
                         f"{list(SEEDS_EXPECTED)}（§3.3 三 seed 判据）")
    for s in args.seeds:
        o, eo = collect(off_root, s, pin=off_pins.get(s))
        a, ea = collect(a4_root, s, pin=a4_pins.get(s))
        rec = {"off": o, "a4": a, "err_off": eo, "err_a4": ea}
        if o is None or a is None:
            invalid.append(f"seed{s}: {eo or ea}")
            report["per_seed"][s] = rec
            continue
        rec["delta_ate_cm"] = round(a["ate_cm"] - o["ate_cm"], 4)
        rec["gauss_ratio"] = round(a["gaussians"] / o["gaussians"], 4) if o["gaussians"] else None
        if a.get("refined_gaussians") and o.get("refined_gaussians"):
            rec["refined_gauss_ratio"] = round(
                a["refined_gaussians"] / o["refined_gaussians"], 4)
        report["per_seed"][s] = rec

    deltas = [v["delta_ate_cm"] for v in report["per_seed"].values() if "delta_ate_cm" in v]
    ratios = [v["gauss_ratio"] for v in report["per_seed"].values() if "gauss_ratio" in v]

    if seed_gate_err:
        report["verdict"] = "INSTRUMENT_INVALID"
        report["reasons"] = [seed_gate_err]
    elif invalid or len(deltas) < len(SEEDS_EXPECTED):
        report["verdict"] = "INSTRUMENT_INVALID"
        report["reasons"] = invalid or [f"有效 seed 数 {len(deltas)} < {len(SEEDS_EXPECTED)}"]
    elif not all(_finite(x) for x in deltas + ratios):
        # 双保险：collect 已逐个 guard，这里再断言一次（防将来改 collect 时绕过）
        bad = [f"seed{k}: Δ={v.get('delta_ate_cm')}, ratio={v.get('gauss_ratio')}"
               for k, v in report["per_seed"].items()
               if not _finite(v.get("delta_ate_cm")) or not _finite(v.get("gauss_ratio"))]
        report["verdict"] = "INSTRUMENT_INVALID"
        report["reasons"] = ["Δ 或 ratio 非有限（读数不存在，不得判出口）", *bad]
    else:
        med = statistics.median(deltas)
        report["median_delta_ate_cm"] = round(med, 4)
        report["deltas"] = deltas
        report["gauss_ratios"] = ratios
        report["max_gauss_ratio"] = round(max(ratios), 4)
        signs = {d > 0 for d in deltas}
        report["same_sign"] = len(signs) == 1
        if len(signs) > 1:
            report["verdict"] = "CLOSED_NEGATIVE_OR_UNSTABLE"
            report["reasons"] = [f"Δ 有正有负（跨 seed 不稳定）：{deltas}"]
        elif med >= CLAIM_FLOOR_CM:
            report["verdict"] = "CLOSED_NEGATIVE_OR_UNSTABLE"
            report["reasons"] = [f"三 seed 同号但 A4 更差：median Δ={med:+.3f}cm ≥ "
                                 f"+{CLAIM_FLOOR_CM}cm"]
        elif abs(med) < CLAIM_FLOOR_CM:
            report["verdict"] = "BELOW_CLAIM_FLOOR"
            report["reasons"] = [f"三 seed 同号，但 |median Δ|={abs(med):.3f}cm < "
                                 f"{CLAIM_FLOOR_CM}cm"]
        elif max(ratios) > GAUSS_RATIO_CAP:
            report["verdict"] = "DOSE_CONFOUND"
            report["reasons"] = [
                f"ATE 改善 median Δ={med:+.3f}cm，但高斯数膨胀 max ratio="
                f"{max(ratios):.3f} > {GAUSS_RATIO_CAP} ⇒ 剂量混杂，"
                f"「更多 vs 更对」不可区分"]
        else:
            report["verdict"] = "POSITIVE_ATE_DOSE_OK"
            report["reasons"] = [
                f"ATE 改善 median Δ={med:+.3f}cm 且高斯数受控 max ratio="
                f"{max(ratios):.3f} ≤ {GAUSS_RATIO_CAP} ⇒ 正面读数候选"
                f"（进 L2 前不算机制贡献）"]

    print(f"{'seed':>4} {'off_ATE':>9} {'a4_ATE':>9} {'ΔATE':>9} "
          f"{'g_off':>7} {'g_a4':>7} {'ratio':>7} {'psnr_a4':>8}")
    for s, v in report["per_seed"].items():
        if "delta_ate_cm" in v:
            o, a = v["off"], v["a4"]
            print(f"{s:>4} {o['ate_cm']:>9.4f} {a['ate_cm']:>9.4f} {v['delta_ate_cm']:>+9.4f} "
                  f"{o['gaussians']:>7d} {a['gaussians']:>7d} {v['gauss_ratio']:>7.4f} "
                  f"{(a.get('psnr') if a.get('psnr') is not None else float('nan')):>8.3f}")
            # **所用 run 必须打印**（G3 审查 M3）：否则判决不可复算——
            # seed 目录里混有冒烟/桥接/探针 run，选择规则不透明时同一命令可选出不同 run。
            print(f"       used: off={o['run']}  a4={a['run']}")
        else:
            print(f"{s:>4}  INVALID: {v['err_off'] or v['err_a4']}")
    print(f"\nVERDICT: {report['verdict']}")
    for r in report["reasons"]:
        print(f"  - {r}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    # **fail-closed 退出码（2026-11-06 G3 审查 M6）**：旧版 `return 0 if verdict else 1`
    # 使 INSTRUMENT_INVALID 也 rc=0 ⇒ 批次脚本以为成功。现在 INVALID 一律 rc=2，
    # 与 judge_maskstat.py 的惯例一致；正常出口 rc=0。
    return 2 if report["verdict"] == "INSTRUMENT_INVALID" else 0


if __name__ == "__main__":
    sys.exit(main())
