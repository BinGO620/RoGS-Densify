#!/usr/bin/env python
"""derive_seq_floors.py — 逐序列 ATE 噪声地板与 MDE（机器计算，零手抄）。

**为什么有这个脚本**：`PREREGISTRATION.md` §3.1 曾用单一常数 0.62cm 作全局地板。
该常数是跨批区间 0.18–0.62cm 的上界，而同批逐序列 seed sd 实测从 0.02（crowd3）
到 1.53（person_tracking swbaonly）不等 ⇒ 拿一个常数套所有序列违反
`DISCIPLINE.md`「测量口径」#1。本脚本把逐序列地板的派生变成可复跑工件，
供 §3.2（2026-10-30 修订）直接引用。

三套估计（同一批同码数据，互为参照，按要求报 median + IQR）：

  E1 `seed_sd`      : 每个臂自身逐 seed ATE 的样本 sd（4 臂 × n=3）⇒ df 各为 2
  E2 `paired_sd`    : 每个非 baseline 臂逐 seed 配对差 (arm − baseline) 的 sd ⇒ df=2
  E3 `paired_pooled`: E2 三臂的残差合并（先减各自臂均值）⇒ df=6 的稳定估计

MDE(95%, n=3) = t(0.975, df) × sd / sqrt(n)，df = 2（E1/E2）或 6（E3）。
含义：**在 n=3 seed 的跨 seed 口径下，小于 MDE 的 ΔATE 不可判**（不是"通过"）。

另加 `--paper3-pt`：用论文 3 自己三臂 × 三 seed 的 run 目录，给出
person_tracking 上 on−off / on−negctl 的观测差、配对 sd 与 MDE —— 与 r33 的
逐序列地板互为第二条参照（不同批、不同机制，同一序列）。

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/derive_seq_floors.py \
      --manifest results/paper2_fulltable/evidence/manifest_r33.json \
      --paper3-pt \
      --out-json paper3/results/evidence/seq_floors_2026-10-30.json \
      --out-md   paper3/results/evidence/seq_floors_2026-10-30.md
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# 双侧 95% 的 t 分位数（避免引入 scipy；数值与标准 t 表一致）
T975 = {
    1: 12.706204736174698,
    2: 4.302652729911275,
    3: 3.182446305284263,
    4: 2.7764451051977987,
    5: 2.570581835636305,
    6: 2.4469118511449692,
    8: 2.3060041350333704,
    12: 2.1788128296634177,
}


def t975(df: int) -> float:
    if df in T975:
        return T975[df]
    raise KeyError("no tabulated t(0.975, %d); extend T975" % df)


def mde95(sd: float, n: int, df: int) -> float:
    """最小可检出效应（双侧 95%，给定 sd 与自由度）。"""
    return t975(df) * float(sd) / math.sqrt(int(n))


def iqr(vals):
    v = sorted(vals)
    if len(v) == 1:
        return 0.0
    return v[-1] - v[0]


def _paired_residuals(arms: dict, seq: str, base_key: str = "baseline") -> dict:
    """{arm: [逐 seed 配对差]}，配对键 = seed 编号。"""
    per = {}
    for arm, seqs in arms.items():
        row = seqs.get(seq)
        if not row:
            continue
        per[arm] = {int(p["seed"]): float(p["full_cm"]) for p in row["per_seed"]}
    if base_key not in per:
        return {}
    base = per[base_key]
    out = {}
    for arm, by_seed in per.items():
        if arm == base_key:
            continue
        seeds = sorted(set(base) & set(by_seed))
        if not seeds:
            continue
        out[arm] = [by_seed[s] - base[s] for s in seeds]
    return out


def derive_from_manifest(manifest: dict) -> dict:
    arms = manifest["arms"]
    seqs = sorted(arms[next(iter(arms))].keys())
    rows = {}
    for seq in seqs:
        e1 = {}
        for arm in arms:
            vals = [float(p["full_cm"]) for p in arms[arm][seq]["per_seed"]]
            e1[arm] = {"n": len(vals), "sd": st.stdev(vals) if len(vals) > 1 else 0.0}
        paired = _paired_residuals(arms, seq)
        e2 = {
            arm: {"n": len(d), "sd": st.stdev(d), "mean": st.mean(d)}
            for arm, d in paired.items()
            if len(d) > 1
        }
        resid = []
        for d in paired.values():
            m = st.mean(d)
            resid.extend(x - m for x in d)
        df_pool = len(resid) - len(paired) if paired else 0
        e3 = {
            "df": df_pool,
            "sd": math.sqrt(sum(x * x for x in resid) / df_pool) if df_pool > 0 else None,
        }

        e1_sds = [v["sd"] for v in e1.values()]
        e2_sds = [v["sd"] for v in e2.values()]
        n_seed = min(v["n"] for v in e1.values())

        rows[seq] = {
            "n_seed": n_seed,
            "E1_seed_sd": e1,
            "E1_median_sd": st.median(e1_sds),
            "E1_iqr_sd": iqr(e1_sds),
            "E1_MDE3_median": mde95(st.median(e1_sds), n_seed, 2),
            "E1_MDE3_max": mde95(max(e1_sds), n_seed, 2),
            "E2_paired_sd": e2,
            "E2_median_sd": st.median(e2_sds),
            "E2_iqr_sd": iqr(e2_sds),
            "E2_MDE3_median": mde95(st.median(e2_sds), n_seed, 2),
            "E2_MDE3_max": mde95(max(e2_sds), n_seed, 2),
            "E3_paired_pooled": e3,
            "E3_MDE3": mde95(e3["sd"], n_seed, 6) if e3["sd"] is not None else None,
        }
        # 地板 = 三套估计里最保守（最大）的那个 ⇒ 判"不可判"时不会偏向任何一方
        cands = [rows[seq]["E1_MDE3_max"], rows[seq]["E2_MDE3_max"]]
        if rows[seq]["E3_MDE3"] is not None:
            cands.append(rows[seq]["E3_MDE3"])
        rows[seq]["floor_cm_conservative"] = max(cands)
    return rows


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_ate(run_dir: Path) -> tuple:
    """从 run 目录读 (ate_rmse_cm, status, num_gaussians)。"""
    track = _last_row(run_dir / "tracking_raw.csv") or {}
    eff = _last_row(run_dir / "efficiency_raw.csv") or {}
    ate = _f(track.get("ate_rmse_cm"))
    g = _f(eff.get("num_gaussians"))
    return ate, track.get("status"), (int(g) if g is not None else None)


def _last_row(path: Path):
    if not path.is_file():
        return {}
    rows = list(csv.DictReader(open(path)))
    return rows[-1] if rows else {}


def derive_paper3_pt(root: Path = REPO, arms=("off", "on", "negctl")) -> dict:
    """论文 3 自己三臂 × 三 seed（person_tracking）的观测差与 MDE。"""
    data = {}
    for arm in arms:
        pat = str(root) + (
            "/results/paper3_bpw/bpw_%s_person_tracking/datasets_bonn/*/seed_*/*/"
            % arm
        )
        for d in sorted(glob.glob(pat)):
            p = Path(d)
            seed = p.parent.name.replace("seed_", "")
            ate, status, g = read_ate(p)
            if ate is None:
                continue
            data.setdefault(arm, {})[int(seed)] = {
                "ate_cm": ate,
                "status": status,
                "num_gaussians": g,
                "run": str(p.relative_to(root)),
            }
    out = {"arms": data}
    if "off" not in data:
        return out
    base = data["off"]
    comps = {}
    for arm in arms:
        if arm == "off" or arm not in data:
            continue
        seeds = sorted(set(base) & set(data[arm]))
        diffs = [data[arm][s]["ate_cm"] - base[s]["ate_cm"] for s in seeds]
        entry = {"seeds": seeds, "diffs_cm": diffs, "mean_cm": st.mean(diffs)}
        if len(diffs) > 1:
            sd = st.stdev(diffs)
            entry.update(
                {
                    "sd_cm": sd,
                    "MDE3_df2": mde95(sd, len(diffs), 2),
                    "judge_vs_MDE": (
                        "不可判" if abs(st.mean(diffs)) < mde95(sd, len(diffs), 2) else "超地板"
                    ),
                }
            )
        comps[arm] = entry
    out["comparisons_vs_off"] = comps
    return out


def fmt_table(rows: dict) -> str:
    head = (
        "| 序列 | n | E1 seed sd 中位 (IQR) | E2 配对 sd 中位 (IQR) | "
        "E3 合并配对 sd (df) | MDE₃ E1max | MDE₃ E2max | MDE₃ E3 | **地板(取最保守)** |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
    )
    body = ""
    for seq, r in rows.items():
        e3 = r["E3_paired_pooled"]
        body += (
            "| %s | %d | %.3f (%.3f) | %.3f (%.3f) | %s | %.2f | %.2f | %s | **%.2f** |\n"
            % (
                seq,
                r["n_seed"],
                r["E1_median_sd"],
                r["E1_iqr_sd"],
                r["E2_median_sd"],
                r["E2_iqr_sd"],
                ("%.3f (%d)" % (e3["sd"], e3["df"])) if e3["sd"] is not None else "n/a",
                r["E1_MDE3_max"],
                r["E2_MDE3_max"],
                ("%.2f" % r["E3_MDE3"]) if r["E3_MDE3"] is not None else "n/a",
                r["floor_cm_conservative"],
            )
        )
    return head + body


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--manifest",
        default=str(REPO / "results/paper2_fulltable/evidence/manifest_r33.json"),
    )
    ap.add_argument("--paper3-pt", action="store_true")
    ap.add_argument("--out-json")
    ap.add_argument("--out-md")
    args = ap.parse_args(argv)

    manifest = json.load(open(args.manifest))
    rows = derive_from_manifest(manifest)
    payload = {
        "generated_by": "scripts/paper3_bpw/derive_seq_floors.py",
        "source_manifest": str(Path(args.manifest).relative_to(REPO))
        if str(args.manifest).startswith(str(REPO))
        else args.manifest,
        "source_batch": manifest.get("batch"),
        "convention": "paper3/PREREGISTRATION.md §3.2 (2026-10-30)",
        "mde_formula": "t(0.975, df) * sd / sqrt(n)",
        "per_sequence": rows,
    }
    if args.paper3_pt:
        payload["paper3_person_tracking"] = derive_paper3_pt()

    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n"
        )

    md = ["<!-- 机算产出，勿手改：scripts/paper3_bpw/derive_seq_floors.py -->", ""]
    md.append("源批：%s" % payload["source_batch"])
    md.append("")
    md.append(fmt_table(rows))
    if args.paper3_pt and "comparisons_vs_off" in payload["paper3_person_tracking"]:
        md.append("")
        md.append("## 第二条参照：论文 3 自己三臂（person_tracking）")
        md.append("")
        md.append("| 比较 | 逐 seed Δ(cm) | 均值 | 配对 sd | MDE₃(df=2) | 判读 |")
        md.append("|---|---|---:|---:|---:|---|")
        for arm, c in payload["paper3_person_tracking"]["comparisons_vs_off"].items():
            md.append(
                "| %s − off | %s | %+.4f | %s | %s | %s |"
                % (
                    arm,
                    " / ".join("%+.4f" % d for d in c["diffs_cm"]),
                    c["mean_cm"],
                    ("%.4f" % c["sd_cm"]) if "sd_cm" in c else "n/a",
                    ("%.3f" % c["MDE3_df2"]) if "MDE3_df2" in c else "n/a",
                    c.get("judge_vs_MDE", "n/a"),
                )
            )
    text = "\n".join(md) + "\n"
    if args.out_md:
        Path(args.out_md).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
