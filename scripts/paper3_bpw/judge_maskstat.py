#!/usr/bin/env python
"""judge_maskstat.py — MaskStat L1 判据机（prereg_maskstat_2026-11-04 §2–§4 机械应用）。

只消费 run 工件（tracking_raw.csv / efficiency_raw.csv / maskstat_trace.csv / .done），
缺失或帧数不符 ⇒ rc=2 拒判（fail-closed，禁止从 console 自救——FDose G2 同款纪律）。

用法：
    python scripts/paper3_bpw/judge_maskstat.py --manifest <manifest.json> \
        --out-md <path.md> --out-json <path.json>

manifest 格式：
{
  "sequence": "person_tracking",
  "expect_frames": 580,
  "floor_cm": 3.83,
  "pairs": [{"seed": 0, "off": "<run_dir>", "on": "<run_dir>"}, ...]
}

出口（prereg §4，n 为 manifest 内 pair 数；按 prereg 顺序机械应用）：
  rule 1 装置失效：G6 非爆炸门不过（on 臂高斯膨胀 >10%）；G1–G5 由 tests/densification/
          test_maskstat_stats.py 守护，其 pytest 工件见 evidence/maskstat_gates_pytest_*.txt
  rule 2 机制死：on 臂 trace 无作用量（share_w_lt_1 均值 < 0.05 或 mean_w > 0.98）
  rule 0 n=1：机制门过但单 seed 一律不可判（prereg §3）
  rule 3 晋级：机制门全过 + 方向一致 + mean < −floor/2（n=2 为候选；n≥3 且 |mean|≥MDE(3) 为确认）
  rule 4 延长区：n=2 方向一致 + |mean| < floor/2 ⇒ 扩 n=3 重判一次
  rule 5 不可判：方向不一致；或 n≥3 方向一致但 |mean| < MDE(3)
n=2 的 ATE 一律是方向参考（MDE(2)≈13.4cm，prereg §3 如实声明），不构成效果结论。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

# sd 来源 A（prereg_maskstat §3）：bpw_on−off 逐 seed 配对差，3 seeds，580 帧。
SD_SOURCES = {
    "A_paired_on_off": {
        "sd": 1.491,
        "n_seed": 3,
        "src": "bpw_on vs bpw_off, person_tracking, 3 seeds",
    }
}
# t(0.975, df) 表（df = n−1；n≤4 覆盖 L1/扩批需要）
MDE_T = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 7: 2.365}

MECH_SHARE_MIN = 0.05   # prereg §4 rule 2：share_w_lt_1 均值 < 5% ⇒ 无作用量
MECH_MEAN_W_MAX = 0.98  # 或 mean_w > 0.98
DOSE_RATIO_MAX = 1.10   # prereg §3 G6：on 终态高斯 ≤ off × 1.10


def mde(sd: float, n: int) -> float:
    return MDE_T[n - 1] * sd / math.sqrt(n)


def _read_last_row(path: str, required_cols: list[str]) -> dict:
    if not os.path.isfile(path):
        raise RuntimeError(f"missing artifact: {path}")
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty artifact: {path}")
    last = rows[-1]
    for col in required_cols:
        if col not in last or last[col] in ("", "MISSING", None):
            raise RuntimeError(f"missing column {col} in {path}")
    return last


def read_run(run_dir: str, expect_frames: int) -> dict:
    track = _read_last_row(os.path.join(run_dir, "tracking_raw.csv"), ["ate_rmse_cm"])
    eff = _read_last_row(
        os.path.join(run_dir, "efficiency_raw.csv"),
        ["num_frames", "online_num_gaussians", "refined_num_gaussians", "num_gaussians"],
    )
    frames = int(float(eff["num_frames"]))
    if frames != int(expect_frames):
        raise RuntimeError(
            f"frame gate: {run_dir} has {frames} frames, expect {expect_frames}"
            "（冒烟 run 不得混入全长判读）"
        )
    return {
        "run_dir": run_dir,
        "ate_cm": float(track["ate_rmse_cm"]),
        "num_frames": frames,
        "online_gaussians": int(float(eff["online_num_gaussians"])),
        "refined_gaussians": int(float(eff["refined_num_gaussians"])),
        "final_gaussians": int(float(eff["num_gaussians"])),
    }


def read_maskstat_trace(run_dir: str) -> dict:
    """机制激活证据（prereg §2 G4 / §4 rule 2）。off 臂无此文件是预期（tracer 只在 on 建）。"""
    path = os.path.join(run_dir, "maskstat_trace.csv")
    if not os.path.isfile(path):
        return {"present": False}
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty maskstat_trace: {path}")
    n = len(rows)
    share_lt1 = sum(float(r["share_w_lt_1"]) for r in rows) / n
    share_eq0 = sum(float(r["share_w_eq_0"]) for r in rows) / n
    mean_ws = [float(r["mean_w"]) for r in rows]
    mean_mask = [float(r["mean_mask_ratio"]) for r in rows]
    mean_mask = [v for v in mean_mask if not math.isnan(v)]
    return {
        "present": True,
        "path": path,
        "n_calls": n,
        "share_w_lt_1_mean": share_lt1,
        "share_w_eq_0_mean": share_eq0,
        "mean_w_mean": sum(mean_ws) / n,
        "mean_mask_ratio_mean": sum(mean_mask) / len(mean_mask) if mean_mask else None,
    }


def check_done(run_dir: str, arm: str, seed: int) -> str:
    done = os.path.join(run_dir, f"maskstat_{arm}_seed{seed}.done")
    if not os.path.isfile(done):
        raise RuntimeError(f"missing .done anchor: {done}（只认 finished rc=0 的 run）")
    info = {}
    with open(done, encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                info[k] = v
    if info.get("finished_rc0") != "yes":
        raise RuntimeError(f".done says finished_rc0={info.get('finished_rc0')}: {done}")
    return done


def judge(manifest: dict) -> dict:
    seq = manifest["sequence"]
    expect_frames = int(manifest.get("expect_frames", 580))
    floor_cm = float(manifest["floor_cm"])
    sd = SD_SOURCES["A_paired_on_off"]["sd"]

    pairs = []
    for p in manifest["pairs"]:
        seed = int(p["seed"])
        off_dir, on_dir = p["off"], p["on"]
        off_done = check_done(off_dir, "off", seed)
        on_done = check_done(on_dir, "on", seed)
        off_run = read_run(off_dir, expect_frames)
        on_run = read_run(on_dir, expect_frames)
        trace = read_maskstat_trace(on_dir)
        dose_ratio = on_run["refined_gaussians"] / max(off_run["refined_gaussians"], 1)
        pair = {
            "seed": seed,
            "off": off_run,
            "on": on_run,
            "done": {"off": off_done, "on": on_done},
            "on_minus_off": on_run["ate_cm"] - off_run["ate_cm"],
            "gauss_ratio_on_over_off_refined": dose_ratio,
            "maskstat_trace": trace,
        }
        # 机制门（prereg §4 rule 2 的作用量判据，两个分支都实现 + §3 G6 非爆炸门）：
        # 无作用量 ⇔ share_w_lt_1 均值 < 5% 或 mean_w > 0.98（加权形同虚设）。
        mech_action = (
            trace.get("present")
            and trace["n_calls"] > 0
            and trace["share_w_lt_1_mean"] >= MECH_SHARE_MIN
            and trace["mean_w_mean"] <= MECH_MEAN_W_MAX
        )
        pair["mech_trace_present"] = bool(trace.get("present"))
        pair["mech_action"] = bool(mech_action)
        pair["mech_mean_w_mean"] = trace.get("mean_w_mean")
        pair["g6_dose_ok"] = bool(dose_ratio <= DOSE_RATIO_MAX)
        pairs.append(pair)

    n = len(pairs)
    deltas = [p["on_minus_off"] for p in pairs]
    mean_d = sum(deltas) / n
    consistent = all(d > 0 for d in deltas) or all(d < 0 for d in deltas)
    # n=1（如时间盒截断下只有 seed0）⇒ 预注册 §3：单 seed 一律不可判，不产 MDE。
    mde_val = mde(sd, n) if n >= 2 else None

    # ---- 出口规则（prereg §4，按 prereg 顺序机械应用：装置门(含 G6)最先，rule 2 次之）----
    # G2 整改（2026-11-04）：① rule 1 = 装置门（含 G6 非爆炸）先于 rule 2，纠正原实现
    # 的槽位倒置；② rule 5 补第二臂：n≥3 方向一致但 |mean| < MDE(3) ⇒ 仍不可判
    # （prereg §4 rule 5 原文「n=3 仍 |Δ| < MDE(3) ⇒ 不可判」，原实现漏掉会误报继续扩批）。
    if not all(p["g6_dose_ok"] for p in pairs):
        rule, verdict = 1, "DEVICE_FAIL — 装置门未过（G6 剂量非爆炸：on 臂高斯膨胀 >10%）"
    elif not all(p["mech_action"] for p in pairs):
        rule, verdict = 2, "MECHANISM_DEAD — 机制无作用量（w 分布与基线不可区分），止损"
    elif n < 2:
        rule, verdict = 0, "SINGLE_SEED_UNJUDGEABLE — 机制门通过，n=1 按预注册一律不可判（等 seed1）"
    elif not consistent:
        rule, verdict = 5, "INCONCLUSIVE — 方向不一致，不可判（记「已排除方向」，n 扩满再收口）"
    elif n == 2 and mean_d < -floor_cm / 2.0:
        rule, verdict = 3, "PROMOTE_CANDIDATE — 机制门全过 + 方向一致且超地板半幅，晋级 3 seeds 候选"
    elif n == 2:
        rule, verdict = 4, "EXTEND_N3 — 方向一致但落在延长区，扩 seed2（n=3）重判一次"
    elif abs(mean_d) < mde(sd, 3):
        rule, verdict = 5, "INCONCLUSIVE — n≥3 方向一致但 |mean| < MDE(3)，按 prereg rule 5 不可判"
    elif mean_d < 0:
        rule, verdict = 3, "PROMOTE_CONFIRMED — 机制门全过 + 方向一致 + |mean| ≥ MDE(3)，晋级确认"
    else:
        rule, verdict = 3, "REGRESS_CONFIRMED — 机制门全过 + 方向一致 + |mean| ≥ MDE(3)（正向退化）"

    mde_note = "—" if mde_val is None else f"{mde_val:.3f}cm"
    caveats = [
        f"n={n} 的 ATE 是方向参考：MDE({n})={mde_note}（sd=1.491 固定口径），"
        "不构成效果结论（prereg §3）。",
        "本批若产自本地 2060 ⇒ 非权威 provisional，不得进论文表（G-算力条）。",
        "剂量下降本身不是收益（P3-D2-004）；终态高斯比只作机制作用量量化。",
        "机制输入 = 运行期 MaskRCNN 掩码（机制输入，非评测仪器）；判决不消费掩码。",
        "负结果、评测协议与「不退化」不得作论文贡献或 headline（DISCIPLINE 论文叙事纪律）。",
    ]
    return {
        "prereg": ["paper3/results/evidence/prereg_maskstat_2026-11-04.md"],
        "sequence": seq,
        "n_pairs": n,
        "pairs": pairs,
        "deltas_on_minus_off": deltas,
        "mean_on_minus_off": mean_d,
        "direction_consistent": consistent,
        "sd_used": sd,
        "sd_sources": SD_SOURCES,
        "mde_cm": mde_val,
        "floor_cm": floor_cm,
        "rule_applied": rule,
        "verdict": verdict,
        "gates": {
            "mech_share_min": MECH_SHARE_MIN,
            "mech_mean_w_max": MECH_MEAN_W_MAX,
            "dose_ratio_max": DOSE_RATIO_MAX,
        },
        "caveats": caveats,
    }


def render_md(rep: dict) -> str:
    L = []
    L.append(f"# MaskStat L1 出口判定（n={rep['n_pairs']}；机械应用 prereg §4）")
    L.append("")
    L.append(
        f"**判据**：`paper3/results/evidence/prereg_maskstat_2026-11-04.md` §2–§4；"
        f"地板 {rep['floor_cm']:.2f} cm（固定口径）；sd={rep['sd_used']:.3f}"
        f"（{rep['sd_sources']['A_paired_on_off']['src']}）"
    )
    L.append("")
    L.append("## 每 seed 双臂读数（机读，不手填）")
    L.append("")
    L.append("| seed | off ATE | on ATE | Δ(on−off) | 高斯比(on/off, refined) | 机制作用量(share_w<1) | G6 |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for p in rep["pairs"]:
        tr = p["maskstat_trace"]
        share = (
            f"{tr['share_w_lt_1_mean']:.3f}"
            if tr.get("present")
            else "missing"
        )
        L.append(
            f"| {p['seed']} | {p['off']['ate_cm']:.4f} | {p['on']['ate_cm']:.4f} | "
            f"{p['on_minus_off']:+.4f} | {p['gauss_ratio_on_over_off_refined']:.3f} | "
            f"{share} | {'PASS' if p['g6_dose_ok'] else 'FAIL'} |"
        )
    L.append("")
    mde_txt = "—" if rep["mde_cm"] is None else f"{rep['mde_cm']:.3f}"
    L.append(f"**mean Δ = {rep['mean_on_minus_off']:+.4f} cm；方向一致 = {rep['direction_consistent']}；"
             f"MDE(n) = {mde_txt} cm（n=2 时仅方向参考）**")
    L.append("")
    L.append("## 判定")
    L.append("")
    L.append(f"> **规则 {rep['rule_applied']} — {rep['verdict']}**")
    L.append("")
    prov = rep.get("provenance") or {}
    if prov:
        L.append(
            f"**批次 provenance**：manifest=`{prov.get('manifest')}`；"
            f"judge 时 HEAD={prov.get('head_at_judge')}；机器={prov.get('machine')}；"
            f"判决时刻={prov.get('judged_at')}。"
        )
        if prov.get("manifest_note"):
            L.append(f"> 批次说明：{prov['manifest_note']}")
        L.append("")
    L.append("## 出口后续动作")
    L.append("")
    L.append(
        "- rule 1（DEVICE_FAIL）⇒ 冻结读数、不加 run；装置门阈值是否需按机标定由"
        "装置自差诊断批（device_floor）定，结论入账本。"
    )
    L.append(
        "- rule 5（INCONCLUSIVE）⇒ 记「已排除方向」（NOTES），n 扩满再收口。"
    )
    L.append("- rule 3（PROMOTE）⇒ 按 prereg §4 晋级流程扩 seed。")
    L.append("")
    L.append("## Caveats")
    L.append("")
    for c in rep["caveats"]:
        L.append(f"- {c}")
    L.append("")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args()
    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    try:
        rep = judge(manifest)
    except RuntimeError as e:
        print(f"JUDGE-REJECTED: {e}", file=sys.stderr)
        return 2
    # G2-3090 重大①：判决本体必须带批次 provenance（机器/HEAD/清单），可审计。
    head = os.popen("git rev-parse --short HEAD").read().strip() or "unknown"
    rep["provenance"] = {
        "manifest": args.manifest,
        "head_at_judge": head,
        "machine": os.environ.get("MONOGS_MACHINE", "local"),
        "manifest_note": manifest.get("note"),
        "judged_at": os.popen("date +'%F %T %z'").read().strip(),
    }
    for path, text in ((args.out_md, render_md(rep)), (args.out_json, json.dumps(rep, indent=1, ensure_ascii=False))):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    print(f"rule={rep['rule_applied']} verdict={rep['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
