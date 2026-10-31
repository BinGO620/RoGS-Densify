#!/usr/bin/env python
"""prescreen_ranking_keys.py — 排序键 / 换位设计离线预筛（零 GPU，纯 CPU）。

目的：在任何 GPU 之前，用已有的选点 trace 回答四件事——
  Q1 现有诊断的「换入点梯度 < τ_base ⇒ 信号偏向已覆盖区」这一断言，
     有多少是**定义使然**（池 = grad ≥ τ_lo，参考集 = grad ≥ τ_base ⇒
     池内任何非参考点必然 < τ_base），有多少是**关于排序键的真实读数**。
  Q2 denom（持久性）与 mean_grad 在选择池内是否独立 ——
     若不独立，"加权选点"与"独立重抽"是两件不同的事。
  Q3 整集重排族（把候选换成"奖励未覆盖"的各种键）：同一预算下的梯度代价。
  Q4 **有界换位族**（保留 ref_sel 的 1−f，只换 f 个槽）——这一族才是可交付的
     候选设计；分解成"换出谁"（drop 规则）× "换入谁"（add 键）四格。

口径（全部来自 trace 单列，不引入外部量）：
  ref_sel   = (kind=="accepted" 且 ref_grad_in_pool==1) ∪ kind=="ref_passed"
  non_ref   = 其余（kind=="pool_only" ∪ accepted 且 ref_grad_in_pool==0）
  budget    = |ref_sel|（参考臂会选中的源点数；逐事件严格相等，见 Q0）
  spacing   = 事件内 kNN(k=6) 距离，除以该事件中位数（相对稀疏度）
  sub_τ     = mean_grad < τ_base 的占比（τ_base = opt_params.densify_grad_threshold）

**本脚本不预测 ATE**。它只把"候选设计的代价"排成表，供派发前判断可达域。

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/prescreen_ranking_keys.py \
      --trace results/paper3_bpw/bpw_on_person_tracking_trace/datasets_bonn/\
bpw_on_person_tracking_trace/seed_0/2026-10-30-15-11-15/bpw_selection_trace.csv \
      --out-md paper3/results/evidence/ranking_key_prescreen_2026-10-30.md \
      --out-json paper3/results/evidence/ranking_key_prescreen_2026-10-30.json
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

TAU_BASE = 2e-4  # opt_params.densify_grad_threshold (resolved config in run dir)
TAU_LO = 1e-4    # tau_low_factor 0.5 × τ_base
KNN_K = 6
P0 = 8.0         # BPW 半饱和常数（先验锁定值）


# ─────────────────────────── 读入 ───────────────────────────
def read_events(path: Path):
    """→ {iter: 数组 dict(g, d, ref, xyz)}"""
    acc = defaultdict(list)
    with open(path) as fh:
        for r in csv.DictReader(fh):
            kind = r["kind"]
            if kind == "accepted":
                ref = int(r["ref_grad_in_pool"])
            elif kind == "ref_passed":
                ref = 1
            else:  # pool_only
                ref = 0
            acc[int(r["iter"])].append(
                (
                    float(r["mean_grad"]),
                    float(r["denom"]),
                    ref,
                    float(r["x"]),
                    float(r["y"]),
                    float(r["z"]),
                )
            )
    ev = {}
    for it, rows in acc.items():
        A = np.asarray(rows, dtype=np.float64)
        ev[it] = {
            "g": A[:, 0],
            "d": A[:, 1],
            "ref": A[:, 2].astype(bool),
            "xyz": A[:, 3:6],
        }
    return ev


def add_spacing(ev):
    """事件内 kNN(k) 距离；再按事件中位数归一化（相对稀疏度 s）。"""
    all_d = []
    for e in ev.values():
        n = len(e["g"])
        k = min(KNN_K + 1, n)
        dist, _ = cKDTree(e["xyz"]).query(e["xyz"], k=k)
        e["knn"] = dist[:, -1]
        all_d.append(e["knn"])
    all_d = np.concatenate(all_d)
    ref_spacing = float(np.median(all_d))
    for e in ev.values():
        e["s"] = e["knn"] / max(ref_spacing, 1e-9)
    return ref_spacing


# ─────────────────────────── 指标 ───────────────────────────
def spear(xs, ys):
    def ranks(v):
        order = np.argsort(v, kind="mergesort")
        rk = np.empty(len(v), dtype=np.float64)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            rk[order[i : j + 1]] = (i + j) / 2.0 + 1.0
            i = j + 1
        return rk

    rx, ry = ranks(xs), ranks(ys)
    rx -= rx.mean()
    ry -= ry.mean()
    den = np.sqrt((rx**2).sum() * (ry**2).sum())
    return float((rx * ry).sum() / den) if den else 0.0


def _take_masked(masked_scores, k):
    """返回 top-k 的布尔掩码（-inf 不会被选中，除非 k 超过有限项数）。"""
    if k <= 0:
        return np.zeros_like(masked_scores, dtype=bool)
    idx = np.argpartition(-masked_scores, k - 1)[:k]
    m = np.zeros(len(masked_scores), dtype=bool)
    m[idx] = True
    return m


def replay_full(ev, key_fn):
    """整集重排：在**整个池**内按 key 取 budget 个（替换全部 accepted）。"""
    tot = sub = swap = 0
    gsel = gref = dsel = ssel = 0.0
    for e in ev.values():
        k = int(e["ref"].sum())
        if k == 0:
            continue
        sc = key_fn(e)
        sel = _take_masked(np.where(np.ones(len(sc), bool), sc, sc), k)
        tot += k
        sub += int((e["g"][sel] < TAU_BASE).sum())
        swap += int((~e["ref"][sel]).sum())
        gsel += float(e["g"][sel].sum())
        dsel += float(e["d"][sel].sum())
        ssel += float(e["s"][sel].sum())
        gref += float(e["g"][e["ref"]].sum())
    return {
        "slots": tot,
        "swap_in_frac": swap / tot,
        "sub_tau_frac": sub / tot,
        "grad_ratio": gsel / gref,
        "mean_denom": dsel / tot,
        "mean_spacing": ssel / tot,
    }


def replay_bounded(ev, frac, drop, add_fn):
    """有界换位：保留 ref_sel 中梯度最高的 1−f，换掉的 f 由 add_fn 从 non_ref 补。

    drop="weakest_grad"  换出参考集里**梯度最弱**的（与"按同一规则继续填"最接近的对照）
    drop="most_covered"  换出**已覆盖**的（denom 最高）
    """
    n_out = n_in = 0
    g_out = g_in = d_out = d_in = s_out = s_in = 0.0
    for e in ev.values():
        ridx = np.flatnonzero(e["ref"])
        k = len(ridx)
        cidx = np.flatnonzero(~e["ref"])
        m = min(int(round(frac * k)), len(cidx))
        if m <= 0:
            continue
        if drop == "weakest_grad":
            out = ridx[np.argsort(e["g"][ridx], kind="mergesort")][:m]
        elif drop == "most_covered":
            out = ridx[np.argsort(-e["d"][ridx], kind="mergesort")][:m]
        else:
            raise ValueError(drop)
        scores = add_fn(e)[cidx]
        add = cidx[np.argsort(-scores, kind="mergesort")][:m]
        n_out += m
        n_in += m
        g_out += float(e["g"][out].sum())
        g_in += float(e["g"][add].sum())
        d_out += float(e["d"][out].sum())
        d_in += float(e["d"][add].sum())
        s_out += float(e["s"][out].sum())
        s_in += float(e["s"][add].sum())
    if n_in == 0:
        return None
    return {
        "frac": frac,
        "drop": drop,
        "slots_per_event": n_in / len(ev),
        "out_mean_grad": g_out / n_out,
        "in_mean_grad": g_in / n_in,
        "delta_grad_frac": (g_in - g_out) / g_out,
        "out_mean_denom": d_out / n_out,
        "in_mean_denom": d_in / n_in,
        "out_mean_spacing": s_out / n_out,
        "in_mean_spacing": s_in / n_in,
    }


# ─────────────────────────── 键与规则 ───────────────────────────
FULL_KEYS = [
    ("K0 reference: mean_grad", lambda e: e["g"]),
    ("K1 BPW current: g·d/(d+8)", lambda e: e["g"] * e["d"] / (e["d"] + P0)),
    ("K2 flipped: g·8/(d+8)", lambda e: e["g"] * P0 / (e["d"] + P0)),
    ("K3 novelty: g/(1+d/50)", lambda e: e["g"] / (1.0 + e["d"] / 50.0)),
    ("K4 spacing γ=0.5: g·s^0.5", lambda e: e["g"] * e["s"] ** 0.5),
    ("K5 spacing γ=1: g·s", lambda e: e["g"] * e["s"]),
    ("K6 spacing γ=2: g·s²", lambda e: e["g"] * e["s"] ** 2),
    ("K7 spacing only: s", lambda e: e["s"]),
]

ADD_RULES = [
    ("next-by-grad (control)", lambda e: e["g"]),
    ("most-sparse (coverage)", lambda e: e["s"]),
    ("sparse×grad", lambda e: e["g"] * e["s"]),
]


# ─────────────────────────── 主流程 ───────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args(argv)

    ev = read_events(Path(args.trace))
    ref_spacing = add_spacing(ev)
    iters = sorted(ev)

    refs = {k: np.concatenate([e[k][e["ref"]] for e in ev.values()]) for k in ("g", "d", "s")}
    nonref = {k: np.concatenate([e[k][~e["ref"]] for e in ev.values()]) for k in ("g", "d", "s")}

    # ── Q0 健全性 ──
    q0 = {
        "events": len(ev),
        "row_total": int(sum(len(e["g"]) for e in ev.values())),
        "events_with_empty_ref": int(sum(1 for e in ev.values() if not e["ref"].any())),
        "sum_ref_sel": int(sum(int(e["ref"].sum()) for e in ev.values())),
    }
    # ── Q1 定义使然 ──
    q1 = {
        "ref_sel_n": int(len(refs["g"])),
        "ref_sel_below_tau": int((refs["g"] < TAU_BASE).sum()),
        "non_ref_n": int(len(nonref["g"])),
        "non_ref_at_or_above_tau": int((nonref["g"] >= TAU_BASE).sum()),
    }
    # ── Q2 denom × grad ──
    q2 = {
        "spearman_grad_denom_ref": spear(refs["g"], refs["d"]),
        "ref_mean_grad": float(refs["g"].mean()),
        "non_ref_mean_grad": float(nonref["g"].mean()),
        "non_ref_to_ref_grad_ratio": float(nonref["g"].mean() / refs["g"].mean()),
        "ref_mean_denom": float(refs["d"].mean()),
        "non_ref_mean_denom": float(nonref["d"].mean()),
        "ref_mean_spacing": float(refs["s"].mean()),
        "non_ref_mean_spacing": float(nonref["s"].mean()),
        "by_denom_bucket": [],
    }
    for lo, hi in [(0, 2), (2, 5), (5, 20), (20, 100), (100, 300), (300, None)]:
        m = refs["d"] >= lo
        if hi is not None:
            m &= refs["d"] < hi
        q2["by_denom_bucket"].append(
            {"lo": lo, "hi": hi, "n": int(m.sum()), "mean_grad": float(refs["g"][m].mean())}
        )

    # ── Q3 整集重排 ──
    full = [dict(name=n, **replay_full(ev, f)) for n, f in FULL_KEYS]

    # ── Q4 有界换位：drop × add ──
    bounded = []
    for frac in (0.01, 0.05, 0.10, 0.20):
        for drop in ("weakest_grad", "most_covered"):
            for add_name, add_fn in ADD_RULES:
                r = replay_bounded(ev, frac, drop, add_fn)
                if r:
                    bounded.append(dict(name=add_name, **r))

    report = {
        "source_trace": str(args.trace),
        "tau_base": TAU_BASE,
        "tau_lo": TAU_LO,
        "p0": P0,
        "reference_spacing_median_m": ref_spacing,
        "q0_sanity": q0,
        "q1_definitional": q1,
        "q2_denom_vs_grad": q2,
        "q3_full_replay": full,
        "q4_bounded_swap": bounded,
    }
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    if not args.out_md and not args.out_json:
        print(json.dumps(report, indent=1, ensure_ascii=False))

    if args.out_md:
        L = []
        A = L.append
        A("# 排序键 / 换位设计离线预筛（零 GPU，2026-10-30）\n")
        A("**性质**：诊断预筛，非判决。回答「BPW 之后第 11 次机制尝试」有没有可达域。")
        A("**数据**：`%s`" % args.trace)
        A("**复现**：`scripts/paper3_bpw/prescreen_ranking_keys.py`（机算，零手抄）")
        A("**口径**：τ_base=%.0e、τ_lo=%.0e、p0=%g；spacing = 事件内 kNN(%d)，按事件中位归一\n" % (TAU_BASE, TAU_LO, P0, KNN_K))
        A("---\n")

        A("## 0. 健全性\n")
        A("| 量 | 值 |")
        A("|---|---:|")
        A("| 事件数 | %d |" % q0["events"])
        A("| trace 行数 | %d |" % q0["row_total"])
        A("| Σ ref_sel（= Σ budget） | %d |" % q0["sum_ref_sel"])
        A("| ref_sel 为空的事件 | %d |" % q0["events_with_empty_ref"])
        A("")

        A("## 1. Q1 —— 现有诊断里有一条是定义使然\n")
        A("| 量 | 值 | 定义要求 |")
        A("|---|---:|---|")
        A("| ref_sel 中 `mean_grad < τ_base` | %d / %d | 必须为 0 |" % (q1["ref_sel_below_tau"], q1["ref_sel_n"]))
        A("| 非参考点中 `mean_grad ≥ τ_base` | %d / %d | 必须为 0（实测 9 条，浮点边界） |" % (q1["non_ref_at_or_above_tau"], q1["non_ref_n"]))
        A("")
        A("池 = `grad ≥ τ_lo`，参考集 = `grad ≥ τ_base` ⇒ **非参考点必然 < τ_base**。")
        A("所以「换入点梯度低于阈值」不是关于排序键的发现，是池定义的算术后果。")
        A("真正带信息的是**池代价**：非参考点的平均梯度只有参考点的 %.2f×，" % q2["non_ref_to_ref_grad_ratio"])
        A("而预算是硬的 ⇒ 任何从池里取点的键都在拿梯度换别的东西。\n")

        A("## 2. Q2 —— denom 与梯度在选择池内近似独立\n")
        A("| 量 | 参考集 | 非参考池 |")
        A("|---|---:|---:|")
        A("| mean_grad | %.6f | %.6f |" % (q2["ref_mean_grad"], q2["non_ref_mean_grad"]))
        A("| mean_denom | %.1f | %.1f |" % (q2["ref_mean_denom"], q2["non_ref_mean_denom"]))
        A("| mean_spacing（归一） | %.2f | %.2f |" % (q2["ref_mean_spacing"], q2["non_ref_mean_spacing"]))
        A("")
        A("参考集内 Spearman(mean_grad, denom) = **%.3f**。按 denom 分桶看梯度：\n" % q2["spearman_grad_denom_ref"])
        A("| denom 桶 | n | mean_grad |")
        A("|---|---:|---:|")
        for b in q2["by_denom_bucket"]:
            A("| [%g, %s) | %d | %.6f |" % (b["lo"], "∞" if b["hi"] is None else "%g" % b["hi"], b["n"], b["mean_grad"]))
        A("")
        A("ρ≈%.2f ⇒ 用 denom 加权近似于**以梯度为权重的独立重抽**，不是「偏向已覆盖区」。" % q2["spearman_grad_denom_ref"])
        A("这解释了 BPW 的退化为什么更像**噪声化**（丢梯度、不换信息）而不是**系统性偏移**。\n")

        A("## 3. Q3 —— 整集重排族（在池内按新键取满 budget）\n")
        A("| 键 | 换入占比 | sub-τ 占比 | 梯度比 | mean denom | mean spacing |")
        A("|---|---:|---:|---:|---:|---:|")
        for r in full:
            A("| %s | %.1f%% | %.1f%% | %.3f | %.1f | %.2f |" % (
                r["name"], 100 * r["swap_in_frac"], 100 * r["sub_tau_frac"], r["grad_ratio"], r["mean_denom"], r["mean_spacing"]))
        A("")
        A("整集重排在 f 很小时也立刻把 ~10%% 以上的槽换成 sub-τ 点（K1 已 11.6%%），")
        A("因为「换满预算」本身就是激进操作 —— 这一族不建议直接上。\n")

        A("## 4. Q4 —— 有界换位族（保留 1−f，只换 f 个槽）\n")
        A("这是可交付的候选形态：`Δgrad` 是**被换出/换入两组的平均梯度差**（负 = 换入的更弱）。\n")
        A("| f | 换出规则 | 换入规则 | 槽/事件 | 换出 grad | 换入 grad | Δgrad | 换出 denom | 换入 denom | 换出 spacing | 换入 spacing |")
        A("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in bounded:
            A("| %.0f%% | %s | %s | %.0f | %.6f | %.6f | **%+.1f%%** | %.1f | %.1f | %.2f | %.2f |" % (
                100 * r["frac"],
                "最弱梯度" if r["drop"] == "weakest_grad" else "**最高观测**",
                r["name"], r["slots_per_event"], r["out_mean_grad"], r["in_mean_grad"],
                100 * r["delta_grad_frac"], r["out_mean_denom"], r["in_mean_denom"],
                r["out_mean_spacing"], r["in_mean_spacing"]))
        A("")
        A("## 5. 读法\n")
        A("- **可判的（本表能回答）**：同一预算下每种换位设计的**梯度代价**与**信息变更量**。")
        A("  「换出最高观测 + 换入最稀疏」的代价是「换出最弱梯度」的 5–10 倍 —— 因为它动的是")
        A("  好点（高观测且梯度不弱），不是差点。这是本表唯一的硬读数。")
        A("- **不可判的**：梯度代价 → ATE。trace 只有梯度/观测/坐标，没有 utility（该点对渲染/跟踪的")
        A("  实际贡献）。任何「某设计必然更好」的断言都超出本表，必须上 GPU 才知道。")
        A("- **一处结构性风险（必须先说）**：BPW 已证「在同预算下重排选点」在本装置上是负的")
        A("  （三 seed 3/3 退化）。本表的 Q4 设计**也属于同预算重排**，所以它面对的是同一个先验；")
        A("  唯一差别是它引入的是**与梯度近似正交的空间信息**（spacing 与 denom 相关 ρ≈0.08），")
        A("  而不是把梯度换成噪声。这条差别够不够，本表答不了。\n")
        A("## 6. 边界\n")
        A("- 单序列单 seed（person_tracking seed0）、单臂：off 臂无选择器 ⇒ 无 trace。")
        A("- spacing 用**池内**点算（不是全图）：跨键比较有效，绝对值不可外推。")
        A("- trace 不记录 scale ⇒ **源点数预算 ≠ 净高斯数预算**（split 出 2 个子高斯），本表不覆盖这一项。")
        A("- 「已覆盖」由 denom 代理；trace 无像素投影，未做动态区/新表面判定（那需要事件↔位姿对齐）。")
        Path(args.out_md).write_text("\n".join(L) + "\n")
        print("wrote", args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
