#!/usr/bin/env python
"""test_derive_seq_floors.py — 逐序列地板/MDE 派生器的极性门禁。

判据单一事实源 = `paper3/PREREGISTRATION.md` §3.2（2026-10-30 修订）。

本测试用**合成 manifest** 钉住三件事（不依赖盘上真实批，避免"跑完才知道判据机对不对"）：

  T1 公式对照：sd 已知、n=3 时 MDE = t(0.975,df)·sd/√3 —— 用标准 t 表值手算对拍。
  T2 阴性对照（must-not-be-constant）：把某臂的 seed 分散度放大 ⇒ 该序列地板必须变大。
     若一条恒定输出能同时过 T1 与 T2，说明派生器不是恒真。
  T3 配对键是 seed 而不是顺序：把某臂的 per_seed 记录**倒序**写进 manifest，
     配对差与地板必须逐位不变。
  T4 零离散度退化：三 seed 完全相同 ⇒ 地板 = 0（不是 NaN，也不得抛错）。
  T5 保守取法：地板 = 三套估计的最大值，且 E3（合并配对，df=6）不弱于任一臂的 E2。
"""
import importlib.util
import math
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "derive_seq_floors", REPO / "scripts" / "paper3_bpw" / "derive_seq_floors.py"
)
dsf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dsf)


def _manifest(vals_by_arm):
    """空 manifest：每个臂给出同一序列的 three-seed ATE 列表。"""
    arms = {}
    for arm, vals in vals_by_arm.items():
        arms[arm] = {
            "seqA": {
                "per_seed": [
                    {"seed": i, "full_cm": float(v), "kf_cm": float(v)}
                    for i, v in enumerate(vals)
                ],
                "mean_full_cm": sum(vals) / len(vals),
                "sd_full_cm": 0.0,
                "mean_kf_cm": sum(vals) / len(vals),
            }
        }
    return {"arms": arms}


BASE = {
    "baseline": [10.0, 10.2, 9.9],
    "armX": [10.1, 10.3, 10.0],
}


def test_t1_mde_matches_textbook_formula():
    """MDE = t(0.975,df)·sd/√n；sd=√2 时 MDE = 4.3027·√2/√3 = 3.513。"""
    got = dsf.mde95(math.sqrt(2.0), 3, 2)
    assert got == pytest.approx(4.302652729911275 * math.sqrt(2.0) / math.sqrt(3))
    assert got == pytest.approx(3.513, abs=1e-3)
    # df=6 的 t 也须与标准表一致
    assert dsf.mde95(1.0, 3, 6) == pytest.approx(
        2.4469118511449692 / math.sqrt(3)
    )


def test_t2_negative_control_floor_moves_with_dispersion():
    """把 armX 的 seed 分散度从 ±0.15 放大到 ±1.5 ⇒ 地板必须显著变大。"""
    tight = dsf.derive_from_manifest(_manifest(BASE))
    loose_vals = dict(BASE)
    loose_vals["armX"] = [9.0, 10.3, 11.6]
    loose = dsf.derive_from_manifest(_manifest(loose_vals))
    assert tight["seqA"]["floor_cm_conservative"] < 0.5
    assert loose["seqA"]["floor_cm_conservative"] > 2.0
    assert loose["seqA"]["floor_cm_conservative"] > 4 * tight["seqA"]["floor_cm_conservative"]


def test_t3_pairing_is_keyed_by_seed_not_row_order():
    """per_seed 记录倒序写 ⇒ 配对差与地板逐位不变（配对键 = seed 号）。"""
    ord_vals = dict(BASE)
    ord_vals["armX"] = [10.1, 10.3, 10.0]
    rev = _manifest(ord_vals)
    rev["arms"]["armX"]["seqA"]["per_seed"] = list(
        reversed(rev["arms"]["armX"]["seqA"]["per_seed"])
    )
    a = dsf.derive_from_manifest(_manifest(ord_vals))["seqA"]
    b = dsf.derive_from_manifest(rev)["seqA"]
    assert a["E2_paired_sd"]["armX"]["mean"] == pytest.approx(
        b["E2_paired_sd"]["armX"]["mean"]
    )
    assert a["E2_paired_sd"]["armX"]["sd"] == pytest.approx(
        b["E2_paired_sd"]["armX"]["sd"]
    )
    assert a["floor_cm_conservative"] == pytest.approx(b["floor_cm_conservative"])


def test_t4_degenerate_zero_dispersion_gives_zero_floor():
    """三 seed 完全相同 ⇒ 地板 = 0，且不得抛 ZeroDivisionError。"""
    flat = {"baseline": [5.0, 5.0, 5.0], "armX": [5.0, 5.0, 5.0]}
    r = dsf.derive_from_manifest(_manifest(flat))["seqA"]
    assert r["floor_cm_conservative"] == pytest.approx(0.0)
    assert r["E3_MDE3"] == pytest.approx(0.0)


def test_t5_floor_is_conservative_max_and_e3_not_weaker_than_single_arm():
    """地板 = max(E1max, E2max, E3)；且 E3(df=6) ≤ 任一臂 E2 的 df=2 上界。"""
    r = dsf.derive_from_manifest(_manifest(BASE))["seqA"]
    cands = [r["E1_MDE3_max"], r["E2_MDE3_max"], r["E3_MDE3"]]
    assert r["floor_cm_conservative"] == pytest.approx(max(cands))
    assert r["E3_MDE3"] <= r["E2_MDE3_max"] + 1e-12
