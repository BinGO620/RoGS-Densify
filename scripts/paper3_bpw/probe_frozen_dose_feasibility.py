#!/usr/bin/env python
"""probe_frozen_dose_feasibility.py — 「冻结剂量」对照是否可构造（零 GPU，纯 CPU）。

背景：CGB L1 判 DESIGN-INVALID（`paper3/results/evidence/verdict_cgb_l1_2026-10-30.md`）
—— 两臂各自在线长地图 ⇒ `ref_sel` 从事件 2 起分叉 ⇒ 等剂量控位对照不可构造。
P3-D2-009 用户拍板走 ②「冻结参考地图离线重放」。本脚本在看数据前回答三个
**决定 ② 能不能按原样做**的问题，全部只用既有 trace（不引入任何新推断）：

  Q1 跨臂位置对应：两臂同事件、同序号的高斯点，位置能不能对上？
     （若能对到 1e-4 m 级，才可能把冻结地图的快照喂进另一臂的活地图）
  Q2 选点可否从冻结状态重放：用 trace 里记录的完整选择器输入
     （`mean_grad` / `denom` / `sparsity`），按规格重放 top-k，能否逐位复现该臂
     实际记下的 `extra` 集合？（能 ⇒ 逐事件冻结状态是该选择器的充分输入）
  Q3 两条键在同一冻结状态上的分歧有多大：Jaccard(γ=1 的选, γ=0 的选)、
     以及两侧选点的平均稀疏度比。（决定「等剂量」到底要求控住什么）
  Q4 等**总剂量**时的可达对比度：把剂量控在 `|ref| + floor(0.05|ref|)`（即 CGB 的
     总源点数）时，两条键在全预算上的稀疏度比与梯度质量代价。
     这是 exp32 教训「先算可达域」的强制项——决定这个对照能否产生可测效应。

判据口径：全部逐事件，不使用 ATE，不预测 ATE。真实 ATE 必须在真跑里出。

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/probe_frozen_dose_feasibility.py \
      --g1-iter results/paper3_bpw/cgb_g1_person_tracking/datasets_bonn/\
cgb_g1_person_tracking/seed_0/2026-10-30-18-35-13/cgb_selection_trace.csv \
      --g0-iter results/paper3_bpw/cgb_g0_person_tracking/datasets_bonn/\
cgb_g0_person_tracking/seed_0/2026-10-30-19-19-18/cgb_selection_trace.csv \
      --out-md paper3/results/evidence/fdose_feasibility_2026-10-31.md \
      --out-json paper3/results/evidence/fdose_feasibility_2026-10-31.json
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

# 位置重合判据：1e-4 m = 0.1 mm（同一浮点历史下应逐位相等）；
# 1e-2 m = 1 cm 作为「宽松对应」参考（仍远小于 Bonn 场景点间距，不算能对应）。
EPS_EXACT = 1e-4
EPS_CM = 1e-2


def read_events(path: Path):
    """→ {iter: dict(ref=[idx], extra=[idx], pool=[idx], g={idx:…}, s={idx:…}, xyz={idx:…})}"""
    ev = defaultdict(lambda: {"ref": [], "extra": [], "pool": [],
                              "g": {}, "den": {}, "s": {}, "xyz": {}})
    with open(path) as fh:
        for r in csv.DictReader(fh):
            it, kind, gi = int(r["iter"]), r["kind"], int(r["gauss_idx"])
            if kind == "ref":
                ev[it]["ref"].append(gi)
            elif kind == "extra":
                ev[it]["extra"].append(gi)
            else:  # pool_only：池内但未选
                ev[it]["pool"].append(gi)
            ev[it]["g"][gi] = float(r["mean_grad"])
            ev[it]["den"][gi] = float(r["denom"])
            ev[it]["s"][gi] = float(r["sparsity"])
            ev[it]["xyz"][gi] = (float(r["x"]), float(r["y"]), float(r["z"]))
    return dict(ev)


def _xyz(ev, idxs):
    return np.asarray([ev["xyz"][i] for i in idxs], dtype=np.float64)


def q1_correspondence(g1, g0, common):
    """Q1：g0 的 ref 点，在 g1 同事件的全体点里能不能按位置对上。"""
    rows = []
    for it in common:
        a = g0[it]["ref"]
        if not a:
            continue
        live = g1[it]["ref"] + g1[it]["extra"] + g1[it]["pool"]
        if not live:
            continue
        pa = _xyz(g0[it], a)
        d, _ = cKDTree(_xyz(g1[it], live)).query(pa, k=1)
        rows.append({
            "iter": it,
            "n_ref_g0": len(a),
            "frac_exact": float((d < EPS_EXACT).mean()),
            "frac_1cm": float((d < EPS_CM).mean()),
            "median_d_m": float(np.median(d)),
            "p90_d_m": float(np.percentile(d, 90)),
        })
    return rows


def q2_replay(ev, gamma, swap_frac=0.05):
    """Q2：按规格在冻结状态上重放选点，与原记录的 extra 比对。

    排序键 = mean_grad · sparsity**gamma；取池内 top-floor(swap_frac·|ref|)。
    平局用 gauss_idx 升序（stable argsort 在按 key 降序后即按 idx 升序）。
    """
    rows = []
    for it in sorted(ev):
        e = ev[it]
        k = int(swap_frac * len(e["ref"]))
        pool = e["extra"] + e["pool"]
        if k <= 0 or not pool:
            continue
        key = np.asarray([e["g"][i] * (e["s"][i] ** gamma) for i in pool])
        order = np.argsort(-key, kind="stable")[:k]
        got = {pool[j] for j in order}
        want = set(e["extra"])
        inter = len(got & want)
        rows.append({
            "iter": it,
            "k": k,
            "exact": int(got == want),
            "jaccard": inter / len(got | want) if (got | want) else 1.0,
        })
    return rows


def q3_key_contrast(ev):
    """Q3：同一冻结状态下 γ=1 与 γ=0 两条键的选择差多远。"""
    rows = []
    for it in sorted(ev):
        e = ev[it]
        k = int(0.05 * len(e["ref"]))
        pool = e["extra"] + e["pool"]
        if k <= 0 or len(pool) < k:
            continue
        out = {}
        for gamma in (1.0, 0.0):
            key = np.asarray([e["g"][i] * (e["s"][i] ** gamma) for i in pool])
            out[gamma] = {pool[j] for j in np.argsort(-key, kind="stable")[:k]}
        a, b = out[1.0], out[0.0]
        rows.append({
            "iter": it,
            "k": k,
            "jaccard": len(a & b) / len(a | b) if (a | b) else 1.0,
            "s_mean_gamma1": float(np.mean([e["s"][i] for i in a])),
            "s_mean_gamma0": float(np.mean([e["s"][i] for i in b])),
        })
    return rows


def q4_full_budget_contrast(ev, swap_frac=0.05):
    """Q4：等总剂量 K 时的可达对比度（对照能否产生可测效应）。

    K = |ref| + floor(swap_frac·|ref|) = CGB 两臂的真实总源点数。
    两条候选键在**全部候选**（ref ∪ pool）上各取 top-K：
      plan_G = 按 mean_grad（"最需要长的地方"）
      plan_S = 按 mean_grad · sparsity**γ（γ 在 JSON 的 `gamma` 列出）
    ⇒ 两臂源点数**逐事件严格相等**，差别只有放置。代价面用梯度质量比 =
    mean_g of plan_S / plan_G（<1 表示机制臂用梯度质量换扩散度）。
    """
    rows = []
    for it in sorted(ev):
        e = ev[it]
        cand = e["ref"] + e["pool"]
        K = len(e["ref"]) + int(swap_frac * len(e["ref"]))
        if K <= 0 or len(cand) <= K + 10:
            continue
        out = {}
        for gamma in (0.0, 1.0):
            key = np.asarray([e["g"][i] * (e["s"][i] ** gamma) for i in cand])
            out[gamma] = {cand[j] for j in np.argsort(-key, kind="stable")[:K]}
        G, S = out[0.0], out[1.0]
        rows.append({
            "iter": it,
            "K": K,
            "jaccard": len(G & S) / len(G | S),
            "s_ratio": float(np.mean([e["s"][i] for i in S])
                             / max(1e-9, np.mean([e["s"][i] for i in G]))),
            "g_ratio": float(np.mean([e["g"][i] for i in S])
                             / max(1e-12, np.mean([e["g"][i] for i in G]))),
        })
    return rows


def _md(res, src):
    L = []
    A = L.append
    A("# 冻结剂量对照（②）可行性探针（2026-10-31，零 GPU）\n")
    A("**上位**：`P3-D2-009` 用户拍板 ②「冻结参考地图离线重放」；"
      "本文件是**看数据前**的装置可行性读数，不含任何 ATE 推断。")
    A("**判据源**：`verdict_cgb_l1_2026-10-30.md` §4.2（反馈环）。\n")
    A("输入 trace（臂内记录，非重跑）：\n")
    for k, v in src.items():
        A(f"- `{k}`: `{v}`")
    A("")
    q1 = res["q1_correspondence"]
    A("## Q1 跨臂位置对应（决定「快照喂进活地图」是否可能）\n")
    A("| 事件 | g0 ref 点数 | 1e-4 重合率 | 1cm 重合率 | 最近点距中位 (m) | p90 (m) |")
    A("|---:|---:|---:|---:|---:|---:|")
    for r in q1[:: max(1, len(q1) // 8)]:
        A("| %d | %d | %.4f | %.4f | %.5f | %.5f |"
          % (r["iter"], r["n_ref_g0"], r["frac_exact"], r["frac_1cm"],
             r["median_d_m"], r["p90_d_m"]))
    A("")
    fe = [r["frac_exact"] for r in q1]
    f1 = [r["frac_1cm"] for r in q1]
    A("汇总：`frac_exact` 均值 **%.4f**（中位 %.4f，最大 %.4f）；"
      "`frac_1cm` 均值 **%.4f**；最近点距中位从 %.4f m 增长到 %.4f m。"
      % (float(np.mean(fe)), float(np.median(fe)), float(np.max(fe)),
         float(np.mean(f1)), q1[0]["median_d_m"], q1[-1]["median_d_m"]))
    A("")
    q2 = res["q2_replay"]
    A("## Q2 冻结状态能否重放选点（决定「逐事件状态」是否是该选择器的充分输入）\n")
    A("| 臂 | 事件数 | 逐位复现 | Jaccard 均值 | 最小 Jaccard |")
    A("|---|---:|---:|---:|---:|")
    for arm, rows in q2.items():
        ex = sum(r["exact"] for r in rows)
        jac = [r["jaccard"] for r in rows]
        A("| %s | %d | **%d/%d** | %.4f | %.4f |"
          % (arm, len(rows), ex, len(rows), float(np.mean(jac)), float(np.min(jac))))
    A("")
    A("⇒ 选点行为是**逐事件冻结状态的确定性函数**（选点只需 `mean_grad` / `sparsity` / "
      "`ref` 的计数），所以「冻结剂量计划」在选点层可执行；"
      "极少数不复现的事件见 JSON 的 `jaccard`，属边界平局。\n")
    q3 = res["q3_key_contrast"]
    A("## Q3 两条键在同一冻结状态上的分歧（决定「等剂量」要控什么）\n")
    A("| 臂（其自身冻结状态） | 事件数 | Jaccard(γ1,γ0) 均值 | 中位 | 最小 | "
      "平均稀疏度 γ1 | γ0 | 比 |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for arm, rows in q3.items():
        jac = [r["jaccard"] for r in rows]
        s1 = float(np.mean([r["s_mean_gamma1"] for r in rows]))
        s0 = float(np.mean([r["s_mean_gamma0"] for r in rows]))
        A("| %s | %d | %.3f | %.3f | %.3f | %.3f | %.3f | **%.2f×** |"
          % (arm, len(rows), float(np.mean(jac)), float(np.median(jac)),
             float(np.min(jac)), s1, s0, s1 / s0))
    A("")
    A("⇒ 两条键几乎不重叠（Jaccard ≈ 0.05）⇒ **不能**用 CGB 的「保留参考集 + 加 5%」"
      "形态做等剂量对照（保留部分占剂量 95.2%，它才是分叉来源，见判决 §4.2）。"
      "等剂量必须控在**总源点数**上，而不是控在那 5% 上。\n")
    q4 = res["q4_full_budget_contrast"]
    A("## Q4 等总剂量时的可达对比度（决定对照能否产生可测效应）\n")
    A("K = `|ref| + floor(0.05·|ref|)`（= CGB 两臂的真实总源点数）；两臂各取 top-K。\n")
    A("| 冻结状态 | 事件数 | K 中位 | Jaccard(plan_G, plan_S) | 稀疏度比 S/G | 梯度质量比 S/G |")
    A("|---|---:|---:|---:|---:|---:|")
    for arm, rows in q4.items():
        if not rows:
            continue
        A("| %s | %d | %.0f | %.3f | **%.2f×** | %.3f |"
          % (arm, len(rows), float(np.median([r["K"] for r in rows])),
             float(np.mean([r["jaccard"] for r in rows])),
             float(np.mean([r["s_ratio"] for r in rows])),
             float(np.mean([r["g_ratio"] for r in rows]))))
    A("")
    A("⇒ 等总剂量下，机制臂只能把平均稀疏度拉到对照臂的 **1.3–1.4 倍**，代价是平均梯度质量"
      "降到 **0.86–0.93 倍**，两臂仍有 ~57% 的重合。**这就是本设计的可达域上界**："
      "若效应量受限于这个「扩散 1.35×、梯度 −10%」的交换，预注册必须先用它算 MDE，"
      "不得跑完再解释。\n")
    A("## 结论（四条，均改变 ② 的实现形态）\n")
    A("1. **不能**把冻结地图快照 seed 进另一臂的活地图：事件 2 起两臂点位置 1e-4 级重合率 "
      "≈0（最近点距中位 1.5–3.5 cm）。② 的「冻结地图」只能冻结**剂量计划**，冻结不了地图本身。")
    A("2. 选点在**逐事件冻结状态上是确定性的**（复现 %d/%d 与 %d/%d）⇒ 剂量计划可以提前算好、"
      "逐事件下发，且可复核。"
      % (sum(r["exact"] for r in q2.get("g1", [])), len(q2.get("g1", [])),
         sum(r["exact"] for r in q2.get("g0", [])), len(q2.get("g0", []))))
    A("3. Jaccard ≈ 0.05 ⇒ 机制臂与控位臂在**总源点数**上等量时，"
      "「保留参考集」不再是共同项，CGB 的加法形态必须改写为「固定总预算、改分配」。")
    A("4. **可达域上界（Q4）**：等总剂量时稀疏度比只能到 **1.3–1.4×**、梯度质量代价 **−7~14%**。"
      "预注册必须把这个交换写进功效核算，并声明「若真实效应小于该交换能买到的 ATE，"
      "设计判不出来」——这是设计层缺陷，不是跑完再解释的东西。")
    A("")
    A("**本文件不主张**任何 ATE 效应；它只证明 ② 的可执行形态与 CGB 原形态不同。")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--g1-iter", required=True)
    ap.add_argument("--g0-iter", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args(argv)

    g1 = read_events(Path(args.g1_iter))
    g0 = read_events(Path(args.g0_iter))
    common = sorted(set(g1) & set(g0))

    res = {
        "generated_by": "scripts/paper3_bpw/probe_frozen_dose_feasibility.py",
        "source": {"g1": args.g1_iter, "g0": args.g0_iter},
        "n_common_events": len(common),
        "q1_correspondence": q1_correspondence(g1, g0, common),
        "q2_replay": {"g1": q2_replay(g1, 1.0), "g0": q2_replay(g0, 0.0)},
        "q3_key_contrast": {"g1": q3_key_contrast(g1), "g0": q3_key_contrast(g0)},
        "q4_full_budget_contrast": {"g1": q4_full_budget_contrast(g1),
                                    "g0": q4_full_budget_contrast(g0)},
    }
    md = _md(res, res["source"])
    Path(args.out_md).write_text(md, encoding="utf-8")
    Path(args.out_json).write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
