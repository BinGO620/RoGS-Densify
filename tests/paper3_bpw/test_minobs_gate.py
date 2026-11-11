"""MinObsGate 单测（prereg_minobs_gate_2026-11-06）。

守护：① 开关默认关 ⇒ (None,None) 走标量路径（逐位不变）；
② obs_gate 分支：denom<N ⇒ 阈值 +inf，其余 = 默认标量；pd_vec 恒为默认。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
import torch

from utils.selective_densification import compute_per_gaussian_knobs

# thr_vec 走 float32，0.0002 会变成 0.00019999...；断言一律用 approx
approx = pytest.approx


def _gaussians(denom):
    d = torch.tensor(denom, dtype=torch.float32).reshape(-1, 1)
    return SimpleNamespace(
        denom=d,
        static_prob=torch.ones_like(d),
        static_obs_count=torch.zeros_like(d),
        get_xyz=torch.zeros((len(denom), 3)),
    )


CFG_ON = {"SelectiveDensification": {
    "enabled": True, "signal": "obs_gate", "min_observations": 8,
    "grad_thr_default": 0.0002,
}}


def test_disabled_returns_none():
    cfg = {"SelectiveDensification": {"enabled": False}}
    g = _gaussians([1.0, 2.0, 3.0])
    assert compute_per_gaussian_knobs(cfg, g, 0) == (None, None)


def test_gate_low_obs_get_inf_high_obs_get_default():
    g = _gaussians([2.0, 8.0, 100.0])   # 2 < 8 → gated；8、100 → pass
    thr, pd = compute_per_gaussian_knobs(CFG_ON, g, 0)
    assert thr.shape == (3, 1)
    assert float(thr[0]) == float("inf")
    assert float(thr[1]) == approx(0.0002, rel=1e-5)
    assert float(thr[2]) == approx(0.0002, rel=1e-5)
    # pd_vec 恒默认（不动 clone/split 边界 —— 同 BPW 的 net-add 纪律）
    assert torch.allclose(pd, torch.full_like(pd, 0.01))


def test_boundary_is_inclusive():
    # denom == N（8）不属于「< N」⇒ 有资格（>= N 即通过）
    g = _gaussians([8.0])
    thr, _ = compute_per_gaussian_knobs(CFG_ON, g, 0)
    assert float(thr[0]) == approx(0.0002, rel=1e-5)


def test_zero_denom_gated():
    g = _gaussians([0.0])
    thr, _ = compute_per_gaussian_knobs(CFG_ON, g, 0)
    assert float(thr[0]) == float("inf")
