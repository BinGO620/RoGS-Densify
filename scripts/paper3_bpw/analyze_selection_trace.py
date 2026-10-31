#!/usr/bin/env python
"""analyze_selection_trace.py — 选点回放诊断分析器（零 GPU，纯 CPU）。

输入：`bpw_on_person_tracking_trace` 的 `bpw_selection_trace.csv`（每事件
accepted/ref_passed/pool_only 三类源点的世界坐标 + 梯度 + denom + evidence）。

回答的问题（Phase 0 复盘的缺口）：
  Q1 选择器到底把点选在哪 —— 相对"该时刻相机看到的场景"？
     用该事件的**当时**视角把世界点投影回图像平面，量：
       - 是否落在 dynamic_mask（人形掩码）内（人身上/人体边缘）
       - 是否落在"已建图且被渲染解释"的区域（用深度一致性近似：与渲染深度
         的偏差、与最新观测深度的偏差）
  Q2 accepted 与 ref_passed 的差异：被跳过的参考点（ref_passed）和被选中的
     pool_only 点，各自的空间分布特征（是否更靠近动态区/更远/更薄）。
  Q3 denom（持久性）在 accepted/pool_only 上的分布：机制是否真的偏好
     "观测多"的点，还是被 p0=8 的收缩压平。

口径（保守）：
  - 每事件用"最近一个 keyframe"的相机位姿把世界点投影（需要跑出每个事件的
    iteration ↔ keyframe 映射；用 run 内 console 的 iter 与 KF uid 近似对齐）。
  - 深度一致性 = |渲染深度 − 观测深度| / 观测深度，阈值 5% 与 10% 两档报。
  - 掩码落在 = 投影像素在 dynamic_mask 内。掩码时间戳由 depth_stem 对应。

输出：markdown 报告 + JSON（零手抄）。不落任何判决；本文件是诊断，不是判定。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics as st
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_trace(path: Path):
    if not path.is_file():
        return []
    out = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            out.append(
                {
                    "iter": int(r["iter"]),
                    "kind": r["kind"],
                    "idx": int(r["gauss_idx"]),
                    "x": _f(r["x"]),
                    "y": _f(r["y"]),
                    "z": _f(r["z"]),
                    "mean_grad": _f(r["mean_grad"]),
                    "denom": _f(r["denom"]),
                    "evidence": _f(r["evidence"]),
                    "ref_in_pool": int(r["ref_grad_in_pool"]),
                }
            )
    return out


def depth_stem_index(dataset_path: Path):
    """depth-stem -> (mask path, depth path, rgb path)。"""
    depth_dir = dataset_path / "depth"
    mask_dir = dataset_path / "dynamic_mask"
    out = {}
    if not depth_dir.is_dir():
        return out
    for d in sorted(depth_dir.glob("*.png")):
        stem = d.stem
        mask = mask_dir / f"{stem}.png"
        out[stem] = {
            "depth": d,
            "mask": mask if mask.is_file() else None,
        }
    return out


def load_mask(path):
    return np.asarray(Image.open(path).convert("L")) > 127


def load_depth(path, scale=5000.0):
    arr = np.asarray(Image.open(path))
    return arr.astype(np.float64) / scale  # meters


def project_points(xyz, K, R, T):
    """世界点 (N,3) -> 像素 (u,v,valid)。R/T 为 cam R/T（getWorld2View2 约定）。"""
    xyz = np.asarray(xyz, dtype=np.float64)
    R = np.asarray(R, dtype=np.float64)
    T = np.asarray(T, dtype=np.float64)
    # getWorld2View2: W2C = [[R, T],[0,1]]，其中 T 是 c2w 平移的取反。
    # cam_points = R @ xyz + T
    cam = xyz @ R.T + T  # (N,3)
    z = cam[:, 2]
    valid = z > 0.05
    u = K[0, 0] * cam[:, 0] / np.where(z > 1e-9, z, 1.0) + K[0, 2]
    v = K[1, 1] * cam[:, 1] / np.where(z > 1e-9, z, 1.0) + K[1, 2]
    return u, v, z, valid


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default=str(
        REPO / "results" / "paper3_bpw" / "bpw_on_person_tracking_trace" /
        "bpw_selection_trace.csv"))
    ap.add_argument("--dataset", default=str(
        REPO / "datasets" / "bonn" / "rgbd_bonn_person_tracking"))
    ap.add_argument("--console", default=str(
        REPO / "results" / "paper3_bpw" / "bpw_on_person_tracking_trace" /
        "console.log"))
    ap.add_argument("--out-json")
    ap.add_argument("--out-md")
    args = ap.parse_args(argv)

    trace = read_trace(Path(args.trace))
    if not trace:
        print("trace 为空或不存在:", args.trace)
        return 1

    # 事件 ↔ KF 位姿对齐：用 console.log 的 Candidate insert KF n 行近似
    # 事件迭代（iter）→ KF uid；KF uid → 位姿在 tracking_raw.csv 的
    # trajectory（per_frame_ape.csv 无位姿）。这里用 per_frame_ape 的
    # frame_id + datasets 的 groundtruth 不足以得到估计位姿 —— 精确投影
    # 需要 run 的估计轨迹（plot/trj_final.json）。
    # 保守简化：本版先不投影到像素（缺可靠位姿映射），改做**世界坐标
    # 空间**的分布统计 + denom/evidence 分析；投影版留待后续（需把估计
    # 轨迹从 plot JSON 读入并按 KF 对齐）。
    kinds = {}
    for row in trace:
        kinds.setdefault(row["kind"], []).append(row)
    n_total = len(trace)

    def stats(rows, key):
        vals = [r[key] for r in rows if r[key] is not None]
        if not vals:
            return {}
        return {
            "n": len(vals),
            "mean": st.mean(vals),
            "median": st.median(vals),
            "p10": sorted(vals)[max(0, len(vals) // 10 - 1)],
            "p90": sorted(vals)[min(len(vals) - 1, 9 * len(vals) // 10)],
            "min": min(vals),
            "max": max(vals),
        }

    report = {"n_total": n_total, "n_by_kind": {k: len(v) for k, v in kinds.items()}}
    for kind, rows in kinds.items():
        report[kind] = {
            "denom": stats(rows, "denom"),
            "mean_grad": stats(rows, "mean_grad"),
            "evidence": stats(rows, "evidence"),
        }

    # 世界坐标空间特征：每个事件内，accepted 点之间的平均最近邻距离、
    # 相对该事件 ref_sel 的空间重叠（accepted 中有多少 % 同时 ∈ ref_sel）。
    per_event = {}
    for row in trace:
        per_event.setdefault(row["iter"], []).append(row)
    overlap = []
    for it, rows in per_event.items():
        acc = [r for r in rows if r["kind"] == "accepted"]
        ref = [r for r in rows if r["kind"] == "ref_passed"]
        if acc and (acc or ref):
            acc_ids = {r["idx"] for r in acc}
            ref_ids = {r["idx"] for r in ref}
            both = acc_ids & ref_ids
            overlap.append(len(both) / max(1, len(acc_ids)))
    report["accepted_overlap_with_ref_passed"] = (
        stats([{"accepted_overlap": o} for o in overlap], "accepted_overlap")
        if overlap
        else {}
    )
    # denom 分组：被选中的点 vs 被跳过的参考点 —— 机制是否偏好"观测多"
    acc_d = [r["denom"] for r in kinds.get("accepted", []) if r["denom"] is not None]
    ref_d = [r["denom"] for r in kinds.get("ref_passed", []) if r["denom"] is not None]
    pool_d = [r["denom"] for r in kinds.get("pool_only", []) if r["denom"] is not None]
    report["denom_by_kind"] = {
        "accepted": stats([{"d": d} for d in acc_d], "d"),
        "ref_passed": stats([{"d": d} for d in ref_d], "d"),
        "pool_only": stats([{"d": d} for d in pool_d], "d"),
    }

    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(report, indent=1, ensure_ascii=False) + "\n"
        )
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
