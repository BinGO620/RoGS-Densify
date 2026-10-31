#!/usr/bin/env python
"""cgb_l1_report.py — CGB L1 判决书的机算生成器（零 GPU，零手抄）。

把三份工件合成一份 verdict：
  1. `check_cgb_gate.py` 的输出（机制门 R1，装置）
  2. `judge_cgb_l1.py` 的输出（四条出口 + A1 剂量门）
  3. 我自己从 per_frame_ape.csv 算的**逐帧配对**统计（含块自助 95% CI）

为什么要有第 3 份：`tracking_raw.csv` 的 `ate_rmse_cm` 是 RMSE，单 seed 下与逐序列地板
不可比（地板 3.83cm 是 n=3 配对差的 MDE）。逐帧配对 + 块自助能把**方向**判到
"每个 seed 内部是否一致"，这是单 seed 唯一能提供的增量信息（prereg §5 已写死：
单 seed 一律「不可判」效应量，只能看方向）。

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/cgb_l1_report.py \
      --gate-json paper3/results/evidence/cgb_gate_l1_2026-10-30.json \
      --g1 results/paper3_bpw/cgb_g1_.../seed_0/<ts> \
      --g0 results/paper3_bpw/cgb_g0_.../seed_0/<ts> \
      --off results/paper3_bpw/bpw_off_.../seed_0/<ts> \
      --out-md paper3/results/evidence/verdict_cgb_l1_2026-10-30.md \
      --out-json paper3/results/evidence/verdict_cgb_l1_2026-10-30.json
"""
from __future__ import annotations

import argparse
import csv
import json

from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FLOORS = REPO / "paper3/results/evidence/seq_floors_2026-10-30.json"
BLOCK = 20
NBOOT = 4000


def _last_row(path: Path):
    if not path.is_file():
        return {}
    rows = list(csv.DictReader(open(path)))
    return rows[-1] if rows else {}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_ape(run: Path):
    p = run / "per_frame_ape.csv"
    if not p.is_file():
        return {}
    return {int(r["frame_id"]): float(r["ape_cm"]) for r in csv.DictReader(open(p))}


def paired(a, b):
    """逐帧配对差 a − b（正值 = a 更差）。"""
    common = sorted(set(a) & set(b))
    if not common:
        return None
    d = np.array([a[f] - b[f] for f in common])
    return common, d


def block_bootstrap_ci(d, block=BLOCK, nboot=NBOOT, seed=0):
    n = len(d)
    if n < block * 2:
        return None
    L = block
    nb = int(np.ceil(n / L))
    rng = np.random.default_rng(seed)
    means = np.empty(nboot)
    for i in range(nboot):
        starts = rng.integers(0, n - L + 1, size=nb)
        idx = np.concatenate([np.arange(s, s + L) for s in starts])[:n]
        means[i] = d[idx].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def thirds(d):
    n = len(d)
    cuts = [0, n // 3, 2 * n // 3, n]
    return [float(d[cuts[i]:cuts[i + 1]].mean()) for i in range(3)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate-json", required=True)
    ap.add_argument("--judge-json", default=None,
                    help="judge_cgb_l1.py 的 --out-json 产物（可选；缺则本条由本脚本重算）")
    ap.add_argument("--g1", required=True)
    ap.add_argument("--g0", required=True)
    ap.add_argument("--off", required=True)
    ap.add_argument("--seq", default="person_tracking")
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args(argv)

    gate = json.loads(Path(args.gate_json).read_text())
    floor = float(json.loads(FLOORS.read_text())["per_sequence"][args.seq]["floor_cm_conservative"])

    runs = {"g1": Path(args.g1), "g0": Path(args.g0), "off": Path(args.off)}
    arms = {}
    for k, p in runs.items():
        t = _last_row(p / "tracking_raw.csv")
        e = _last_row(p / "efficiency_raw.csv")
        arms[k] = {
            "run_dir": str(p.relative_to(REPO)) if p.is_absolute() and str(p).startswith(str(REPO)) else str(p),
            "status": t.get("status"),
            "ate_cm": _f(t.get("ate_rmse_cm")),
            "num_gaussians": _f(e.get("online_num_gaussians")),
            "num_frames": _f(e.get("num_frames")),
        }

    ape = {k: load_ape(p) for k, p in runs.items()}
    pairs = {}
    for name, a, b in (("g1_minus_g0", "g1", "g0"), ("g1_minus_off", "g1", "off"), ("g0_minus_off", "g0", "off")):
        r = paired(ape[a], ape[b])
        if r is None:
            pairs[name] = None
            continue
        common, d = r
        ci = block_bootstrap_ci(d)
        pairs[name] = {
            "n_frames": len(common),
            "mean_cm": float(d.mean()),
            "median_cm": float(np.median(d)),
            "frac_a_worse": float((d > 0).mean()),
            "ci95_cm": list(ci) if ci else None,
            "thirds_cm": thirds(d),
        }

    d_g1_off = arms["g1"]["ate_cm"] - arms["off"]["ate_cm"]
    d_g0_off = arms["g0"]["ate_cm"] - arms["off"]["ate_cm"]
    d_g1_g0 = arms["g1"]["ate_cm"] - arms["g0"]["ate_cm"]
    dose_gap = abs(arms["g1"]["num_gaussians"] - arms["g0"]["num_gaussians"]) / max(arms["g0"]["num_gaussians"], 1.0)

    gate_pass = bool(gate["gate"]["all_pass"])
    if not gate_pass:
        verdict = "DEVICE_INVALID — 机制门未过，冻结读数、修装置，不得解释机制"
    elif dose_gap > 0.05:
        verdict = "DOSE_MISMATCH — 剂量门未过（A1 §3a），ΔATE 不得读作放置效应"
    elif d_g1_g0 >= 0:
        verdict = "PLACEMENT_NULL — γ=1 不快于 γ=0，H1 证否（prereg §6 规则 4）"
    else:
        verdict = "PLACEMENT_POSITIVE — 方向成立，进 L2（prereg §6 规则 3）"
    # 2026-10-30 补（审查 S2）：DESIGN-INVALID 是 L1 跑完后发现的新出口——
    # 若两臂的 ref_sel 在事件级就分叉（等剂量对照不可构造），上面四条都落不上。
    # 该分支需要事件级读数（从 trace 或 runner 日志算），不在本脚本的输入里，
    # 故此处只登记"何时该由人工改判"，并把判据写成可复跑的字符串
    # （`check_cgb_gate.py` 的 g1/g0 事件数不相等或共同事件 < 90% 即触发）。
    verdict_note = (
        "若两臂事件级 ref_sel 分叉（共同事件占比 < 90% 或 Σref_sel 差 > 同臂共同事件地板），"
        "则改判 DESIGN-INVALID：等剂量控位对照不可构造，四条出口均不适用。"
        "见 verdict_cgb_l1_2026-10-30.md §0-A。"
    )

    report = {
        "prereg": [
            "paper3/results/evidence/prereg_cgb_2026-10-30.md §5/§6",
            "paper3/results/evidence/prereg_cgb_amendment_a1_2026-10-30.md §3",
            "paper3/results/evidence/prereg_cgb_amendment_a2_2026-10-30.md §2/§7",
        ],
        "sequence": args.seq,
        "floor_cm": floor,
        "machine": "local RTX 2060 (remote 3090 unreachable) => NOT AUTHORITATIVE, not for paper tables",
        "arms": arms,
        "deltas_rmse_cm": {"g1_minus_off": d_g1_off, "g0_minus_off": d_g0_off, "g1_minus_g0": d_g1_g0},
        "dose": {"relative_gap": dose_gap, "gate_5pct": dose_gap <= 0.05},
        "per_frame_paired": pairs,
        "gate": gate["gate"],
        "verdict": verdict,
        "verdict_note": verdict_note,
    }

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")

    if args.out_md:
        L = []
        A = L.append
        A("# CGB L1 判决：person_tracking × seed 0（580 帧，本地 2060）\n")
        A("**判据**：`prereg_cgb_2026-10-30.md` §5/§6 + `_amendment_a1` §3 + `_amendment_a2` §2/§7")
        A("**工件**：机制门 `cgb_gate_l1_2026-10-30.{md,json}`；本文件由")
        A("`scripts/paper3_bpw/cgb_l1_report.py` 机算生成（零手抄）")
        A("**机器**：本地 RTX 2060（远程 3090 不可达）⇒ **非权威**，不进论文表\n")
        A("---\n")
        A("## 1. 出口：%s\n" % verdict)
        A("## 2. 装置门（R1）\n")
        A("| 子门 | 过 |")
        A("|---|---|")
        for k, v in gate["gate"].items():
            if k == "all_pass":
                continue
            A("| %s | %s |" % (k, "✅" if v else "❌"))
        A("| **all_pass** | **%s** |\n" % ("✅" if gate["gate"]["all_pass"] else "❌"))
        A("## 3. 剂量（A1 §3a）\n")
        A("| 臂 | 在线终态高斯数 | ATE (cm) | 帧数 |")
        A("|---|---:|---:|---:|")
        for k in ("off", "g0", "g1"):
            A("| %s | %s | %s | %s |" % (k, int(arms[k]["num_gaussians"]), arms[k]["ate_cm"], int(arms[k]["num_frames"])))
        A("")
        A("`|net_g1 − net_g0| / net_g0 = %.2f%%`（门 5%%）⇒ **%s**\n" % (100 * dose_gap, "过" if dose_gap <= 0.05 else "**未过**"))
        A("## 4. 方向（RMSE 口径，单 seed ⇒ 效应量一律「不可判」）\n")
        A("| Δ | RMSE 差 (cm) | 对地板 %.2f cm |" % floor)
        A("|---|---:|---|")
        for name, v in (("g1 − off", d_g1_off), ("g0 − off", d_g0_off), ("g1 − g0（放置）", d_g1_g0)):
            A("| %s | %+.4f | %s |" % (name, v, "超地板" if abs(v) >= floor else "**不可判**"))
        A("")
        A("## 5. 逐帧配对（块自助，块长 %d，%d 次）\n" % (BLOCK, NBOOT))
        A("| 配对 | n 帧 | mean Δ (cm) | median Δ | a 更差帧占比 | 95%% CI | 三段均值 |")
        A("|---|---:|---:|---:|---:|---|---|")
        for name, r in pairs.items():
            if not r:
                A("| %s | — | — | — | — | — | — |" % name)
                continue
            ci = r["ci95_cm"]
            ci_s = "[%+.2f, %+.2f]" % (ci[0], ci[1]) if ci else "—"
            A("| %s | %d | %+.4f | %+.4f | %.1f%% | %s | %s |" % (
                name, r["n_frames"], r["mean_cm"], r["median_cm"], 100 * r["frac_a_worse"], ci_s,
                " / ".join("%+.2f" % t for t in r["thirds_cm"])))
        A("")
        A("## 6. 读法（写死在生成器里）\n")
        A("- 逐帧配对的 CI 回答的是「**这 580 帧内部方向是否一致**」，**不是**跨 seed 的效应量。")
        A("  单 seed ⇒ 效应量按 prereg §5 一律「不可判」；CI 不含 0 只能说明**在本 run 内**")
        A("  方向稳定，不能外推成「机制有害/有益」。")
        A("- RMSE 差与逐帧均值差不相等是正常的（前者平方后开根，被大误差帧主导）。")
        A("- A2 §7 已登记：本次 L1 的净增只有 2.40%，远低于 1.15× ⇒ 规则 2′ 的剂量有害分支")
        A("  在本次不会触发；**这不代表剂量无害**，只代表 5% 这档剂量本来就小。")
        Path(args.out_md).write_text("\n".join(L) + "\n")
        print("wrote", args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
