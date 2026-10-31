#!/usr/bin/env python
"""judge_cgb_l1.py — CGB L1 出口判定（机械应用预注册 §6 四条规则），零 GPU。

输入：两臂（g1/g0）+ off 基线的 run 目录（**显式路径**，不用 latest_run 隐式查找）。
输出：markdown + JSON，逐条给出 §6 的四条规则是否命中，以及命中的是哪一条。

判据来源（不得在此改）：
  `paper3/results/evidence/prereg_cgb_2026-10-30.md` §4/§6
  `paper3/results/evidence/prereg_cgb_amendment_a1_2026-10-30.md` §3（R2′ 剂量门）

口径（DISCIPLINE「测量口径」#12）：
  ATE   = `tracking_raw.csv` 的 `ate_rmse_cm` 列（全帧口径；不是 console 的 RMSE ATE）
  净增  = `efficiency_raw.csv` 的 `online_num_gaussians`（线上阶段终态）
  地板  = `paper3/results/evidence/seq_floors_2026-10-30.json` 的逐序列值

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/judge_cgb_l1.py \
      --g1 results/paper3_bpw/cgb_g1_person_tracking/datasets_bonn/cgb_g1_person_tracking/seed_0/<ts> \
      --g0 results/paper3_bpw/cgb_g0_person_tracking/datasets_bonn/cgb_g0_person_tracking/seed_0/<ts> \
      --off results/paper3_bpw/bpw_off_person_tracking/datasets_bonn/bpw_off_person_tracking/seed_0/<ts> \
      --seq person_tracking --out-md ... --out-json ...
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLOORS = REPO / "paper3/results/evidence/seq_floors_2026-10-30.json"


def _read_one(path: Path, column: str):
    if not path.is_file():
        return None
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return None
    last = rows[-1]
    try:
        return float(last[column])
    except (KeyError, TypeError, ValueError):
        return None


def read_arm(run_dir: Path):
    return {
        "run_dir": str(run_dir),
        "ate_cm": _read_one(run_dir / "tracking_raw.csv", "ate_rmse_cm"),
        "num_gaussians": _read_one(run_dir / "efficiency_raw.csv", "online_num_gaussians"),
        "refined_gaussians": _read_one(run_dir / "efficiency_raw.csv", "refined_num_gaussians"),
        "num_frames": _read_one(run_dir / "efficiency_raw.csv", "num_frames"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--g1", required=True, help="γ=1 臂 run 目录（时间戳目录）")
    ap.add_argument("--g0", required=True, help="γ=0 等剂量控位 run 目录")
    ap.add_argument("--off", required=True, help="off 基线 run 目录（复用既有）")
    ap.add_argument("--seq", default="person_tracking")
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args(argv)

    arms = {
        "g1": read_arm(Path(args.g1)),
        "g0": read_arm(Path(args.g0)),
        "off": read_arm(Path(args.off)),
    }
    missing = [k for k, v in arms.items() if v["ate_cm"] is None or v["num_gaussians"] is None]
    if missing:
        print("ERROR: 缺读数 %s —— 检查路径与 status" % missing, file=sys.stderr)
        return 2

    floors = json.loads(FLOORS.read_text())["per_sequence"]
    floor = float(floors[args.seq]["floor_cm_conservative"])

    # 帧数一致性闸：三臂必须在同一帧数上比较。冒烟（--max-frames 40）与全长
    # （580 帧）的 ATE 不是同一个量，混读会得到荒谬的 −10cm"改善"。
    frame_counts = {k: v["num_frames"] for k, v in arms.items()}
    frames_equal = len({int(f) for f in frame_counts.values() if f is not None}) == 1
    if not frames_equal:
        print(
            "ERROR: 三臂帧数不一致 %s —— 跨帧数比较无效（冒烟 vs 全长不是同一个量）"
            % frame_counts,
            file=sys.stderr,
        )
        return 2

    d_g1_off = arms["g1"]["ate_cm"] - arms["off"]["ate_cm"]
    d_g0_off = arms["g0"]["ate_cm"] - arms["off"]["ate_cm"]
    d_g1_g0 = arms["g1"]["ate_cm"] - arms["g0"]["ate_cm"]
    # 剂量门两列并陈（2026-10-30 slam-critic F1）：online 与 refined 可能给出相反符号。
    # g0 的 L1 臂实测 online=64,340 / refined=69,340（差恰好 +5,000 = 一个 KF 插入，
    # 末端竞态）。两列符号不一致 ⇒ 该门「不可判」，不得按单列判「未过」。
    def _gap(col):
        a, b = arms["g1"][col], arms["g0"][col]
        if a is None or b is None:
            return None
        return abs(a - b) / max(b, 1.0)

    dose_gap_online = _gap("num_gaussians")
    dose_gap_refined = _gap("refined_gaussians")
    def _sign(v):
        return 0 if v is None or v == 0 else (1 if v > 0 else -1)

    s_online = _sign(arms["g1"]["num_gaussians"] - arms["g0"]["num_gaussians"])
    s_refined = _sign(arms["g1"]["refined_gaussians"] - arms["g0"]["refined_gaussians"])
    # 只有"两列都非零且相反"才算竞态矛盾；任一列为 0（差为零）不构成矛盾。
    both_reported = dose_gap_online is not None and dose_gap_refined is not None
    same_sign = both_reported and not (s_online * s_refined < 0)
    gaps = [g for g in (dose_gap_online, dose_gap_refined) if g is not None]
    dose_gap = max(gaps) if gaps else 0.0
    dose_ambiguous = not same_sign and len(gaps) == 2

    # §6 规则 2′（Amendment A2，取代原规则 2）：剂量有害 ⇒ 关族，需 (i)∧(ii)
    #   (i)  两臂都 >= off + 1.0cm（剂量代价真实）
    #   (ii) g1 >= g0（放置没有正向效应，即规则 4 已判空）
    # 原规则只看 (i)，而 (i) 的"膨胀"那一半按构造必过（Σextra ≈ 0.05·Σ|ref_sel| ⇒ ~1.20×），
    # 等于用设计常量关族，会让唯一可比的 g1−g0 永远读不到。
    both_worse_1cm = d_g1_off >= 1.0 and d_g0_off >= 1.0
    both_inflated = (
        arms["g1"]["num_gaussians"] > 1.15 * arms["off"]["num_gaussians"]
        and arms["g0"]["num_gaussians"] > 1.15 * arms["off"]["num_gaussians"]
    )
    placement_positive = d_g1_g0 < 0  # 负 = γ=1 的 ATE 更低（更好）
    rule_dose_harmful = both_worse_1cm and both_inflated and not placement_positive
    # Amendment A1 §3(a)：剂量 gate（g1 vs g0 的净增相对差）；两列符号不一致 ⇒ 不可判
    dose_gate_pass = (dose_gap <= 0.05) and not dose_ambiguous

    if rule_dose_harmful:
        verdict = "DOSE_HARMFUL — 本族关闭（§6 规则 2′：剂量有害 且 放置无效）"
    elif dose_ambiguous:
        verdict = (
            "DOSE_AMBIGUOUS — online/refined 两列给出相反符号（末端竞态），剂量门不可判；"
            "ΔATE 不得读作放置效应（A1 §3a + 测量口径 #12）"
        )
    elif not dose_gate_pass:
        verdict = "DOSE_MISMATCH — 剂量门未过（A1 §3a），ΔATE 不得读作放置效应"
    elif placement_positive:
        if both_worse_1cm and both_inflated:
            verdict = (
                "PLACEMENT_POSITIVE_WITH_DOSE_COST — 进 L2，且必须并陈 on−off 的剂量代价"
                "（A2 §2：这是唯一允许的正面结论形态）"
            )
        else:
            verdict = "PLACEMENT_POSITIVE — 进 L2（补 seed 1/2 + 异构序列；§6 规则 3）"
    else:
        verdict = "PLACEMENT_NULL — H1 证否，本族关闭（§6 规则 4）"

    report = {
        "prereg": [
            "paper3/results/evidence/prereg_cgb_2026-10-30.md §6",
            "paper3/results/evidence/prereg_cgb_amendment_a1_2026-10-30.md §3",
            "paper3/results/evidence/prereg_cgb_amendment_a2_2026-10-30.md §2",
        ],
        "sequence": args.seq,
        "floor_cm": floor,
        "arms": arms,
        "deltas_cm": {
            "g1_minus_off": d_g1_off,
            "g0_minus_off": d_g0_off,
            "g1_minus_g0": d_g1_g0,
        },
        "dose": {
            "relative_gap": dose_gap,
            "relative_gap_online": dose_gap_online,
            "relative_gap_refined": dose_gap_refined,
            "columns_agree_in_sign": same_sign,
            "ambiguous": dose_ambiguous,
            "gate_5pct": dose_gate_pass,
            "both_worse_than_off_by_1cm": both_worse_1cm,
            "both_inflated_above_1.15x": both_inflated,
        },
        "verdict": verdict,
        "caveats": [
            "单 seed ⇒ 按 §5 一切 |ΔATE| < floor_cm 的读数一律「不可判」；"
            "本判定的方向项只用于决定是否补 seed，不是效应量证据。",
            "本地 2060 产物（远程不可达）⇒ 按 G-算力条标注「非权威」，不得进论文表。",
        ],
    }

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    if not args.out_md and not args.out_json:
        print(json.dumps(report, indent=1, ensure_ascii=False))

    if args.out_md:
        L = []
        A = L.append
        A("# CGB L1 出口判定（机械应用预注册）（2026-10-30）\n")
        A("**序列**：`%s`（逐序列地板 **%.2f cm**，n=3 口径）" % (args.seq, floor))
        A("**判据**：`prereg_cgb_2026-10-30.md` §6 + `prereg_cgb_amendment_a1_2026-10-30.md` §3\n")
        A("| 臂 | ATE (cm) | 在线终态高斯数 |")
        A("|---|---:|---:|")
        for k in ("off", "g0", "g1"):
            A("| %s | %.4f | %d |" % (k, arms[k]["ate_cm"], int(arms[k]["num_gaussians"])))
        A("")
        A("| Δ | 值 (cm) | 可判性 |")
        A("|---|---:|---|")
        for name, v in (
            ("g1 − off", d_g1_off),
            ("g0 − off", d_g0_off),
            ("g1 − g0（放置）", d_g1_g0),
        ):
            A("| %s | %+.4f | %s |" % (name, v, "超地板" if abs(v) >= floor else "**不可判**（< 地板）"))
        A("")
        A("| 剂量门（两列并陈，2026-10-30 F1） | 值 | 过 |")
        A("|---|---:|---|")
        A("| online 口径 \\|Δ\\|/net_g0 | %.2f%% | %s |" % (
            100 * (dose_gap_online or 0.0),
            "✅" if (dose_gap_online is not None and dose_gap_online <= 0.05) else "❌"))
        A("| refined 口径 \\|Δ\\|/net_g0 | %.2f%% | %s |" % (
            100 * (dose_gap_refined or 0.0),
            "✅" if (dose_gap_refined is not None and dose_gap_refined <= 0.05) else "❌"))
        A("| 两列符号一致 | %s | %s |" % (
            "是" if same_sign else "**否**", "✅" if same_sign else "❌ **不可判**"))
        A("")
        A("> 判据：`测量口径` #12 —— 同一名称的两列口径不得混引，符号相反时以「不可判」报。")
        A("")
        A("## 判定：%s\n" % verdict)
        A("## 注意事项\n")
        for c in report["caveats"]:
            A("- %s" % c)
        Path(args.out_md).write_text("\n".join(L) + "\n")
        print("wrote", args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
