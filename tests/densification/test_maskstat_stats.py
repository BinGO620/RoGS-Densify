#!/usr/bin/env python
"""test_maskstat_stats.py — MaskStat（动态占比加权致密化统计）门禁测试。

对应 `paper3/results/evidence/prereg_maskstat_2026-11-04.md` §2（机制门 G1–G5）
与账本 `P3-D2-016`。纯 CPU：unbound 方法 + 最小假对象，不依赖 CUDA。

不变量（与测试断言一一对应）：
  G1 关闭态逐位一致：weight=None ⇒ 与原公式（accum += grad_norm; denom += 1）全等
  G2a w=1.0 与 weight=None 数学全等
  G2b w=0.25 ⇒ accum 精确 ×0.25、denom 精确 +0.25·n
  G2c w=0.0 ⇒ 零贡献（统计不动）
  G3 fail-closed：maskstat 开而掩码不可得 ⇒ RuntimeError（不静默按 w=1 退化）
  G4 trace 落盘：表头 + 逐 call 行，字段齐全
  C1 配置门：Mapping.maskstat_dens_stats 缺省/false ⇒ 不激活
  C2 static_ratio_from_mask：全静态 1.0 / 全动态 0.0 / 混合按占比 / None ⇒ None
"""
import os
import types

import pytest
import torch

from gaussian_splatting.scene.gaussian_model import GaussianModel
from utils.maskstat import (
    MaskStatTracer,
    compute_stats_weight,
    maskstat_active,
    static_ratio_from_mask,
)


def _fake_gaussians(n):
    g = types.SimpleNamespace()
    g.xyz_gradient_accum = torch.zeros((n, 1), dtype=torch.float32)
    g.denom = torch.zeros((n, 1), dtype=torch.float32)
    return g


def _fake_viewspace(n, seed=0):
    torch.manual_seed(seed)
    t = torch.randn(n, 2, dtype=torch.float32) * 3.0
    wrapper = types.SimpleNamespace()
    wrapper.grad = t.clone()
    return wrapper


def _update_filter(n, seed=1):
    torch.manual_seed(seed)
    return torch.rand(n) > 0.4


def _apply(g, vp, filt, weight=None):
    GaussianModel.add_densification_stats(g, vp, filt, weight=weight)


def _reference(vp, filt):
    """原公式（2026-11-04 之前的实现，逐字）：accum += norm(grad[:,:2]); denom += 1。"""
    return torch.norm(vp.grad[filt, :2], dim=-1, keepdim=True)


def test_g1_weight_none_bit_identical():
    n = 32
    vp, filt = _fake_viewspace(n), _update_filter(n)
    g = _fake_gaussians(n)
    _apply(g, vp, filt, weight=None)
    ref_accum = torch.zeros((n, 1), dtype=torch.float32)
    ref_accum[filt] = _reference(vp, filt)
    ref_denom = filt.to(torch.float32).reshape(n, 1)
    assert torch.equal(g.xyz_gradient_accum, ref_accum)
    assert torch.equal(g.denom, ref_denom)


def test_g2a_weight_one_equals_none():
    n = 32
    vp, filt = _fake_viewspace(n), _update_filter(n)
    g0, g1 = _fake_gaussians(n), _fake_gaussians(n)
    _apply(g0, vp, filt, weight=None)
    _apply(g1, vp, filt, weight=1.0)
    assert torch.allclose(g0.xyz_gradient_accum, g1.xyz_gradient_accum)
    assert torch.allclose(g0.denom, g1.denom)


def test_g2b_weight_fraction_scales():
    n = 32
    vp, filt = _fake_viewspace(n), _update_filter(n)
    g_full, g_w = _fake_gaussians(n), _fake_gaussians(n)
    _apply(g_full, vp, filt, weight=None)
    _apply(g_w, vp, filt, weight=0.25)
    assert torch.allclose(g_w.xyz_gradient_accum, 0.25 * g_full.xyz_gradient_accum)
    assert torch.allclose(g_w.denom, 0.25 * g_full.denom)


def test_g2c_weight_zero_no_contribution():
    n = 32
    vp, filt = _fake_viewspace(n), _update_filter(n)
    g = _fake_gaussians(n)
    _apply(g, vp, filt, weight=0.0)
    assert torch.equal(g.xyz_gradient_accum, torch.zeros((n, 1)))
    assert torch.equal(g.denom, torch.zeros((n, 1)))


def test_g3_fail_closed_when_no_image():
    # maskstat 开而图像不可得 ⇒ RuntimeError（Amendment A1：不静默按 w=1 退化）
    cfg = {"Mapping": {"maskstat_dens_stats": True}}
    vp = types.SimpleNamespace(original_image=None)
    with pytest.raises(RuntimeError, match="maskstat"):
        compute_stats_weight(cfg, vp)


def test_g3_weight_from_cached_mask():
    # 自持缓存属性 maskstat_mask（与 semantic_mask 的 dynamic_mask 互不干扰，A1）
    mask = torch.zeros(1, 8, 8, dtype=torch.bool)
    mask[0, :2, :] = True  # 16/64 动态 ⇒ w = 0.75
    cfg = {"Mapping": {"maskstat_dens_stats": True}}
    vp = types.SimpleNamespace(original_image=None, maskstat_mask=mask)
    w, dyn_ratio = compute_stats_weight(cfg, vp)
    assert w == pytest.approx(0.75)
    assert dyn_ratio == pytest.approx(0.25)


def test_g3_inactive_returns_unit_weight():
    cfg = {"Mapping": {"maskstat_dens_stats": False}}
    vp = types.SimpleNamespace(original_image=None)
    w, dyn_ratio = compute_stats_weight(cfg, vp)
    assert w == 1.0 and dyn_ratio is None


def test_c1_config_gate_default_off():
    assert maskstat_active({}) is False
    assert maskstat_active({"Mapping": {}}) is False
    assert maskstat_active({"Mapping": {"maskstat_dens_stats": False}}) is False
    assert maskstat_active({"Mapping": {"maskstat_dens_stats": True}}) is True


def test_c2_static_ratio_math():
    assert static_ratio_from_mask(None) is None
    assert static_ratio_from_mask(torch.zeros(1, 4, 4, dtype=torch.bool)) == pytest.approx(1.0)
    assert static_ratio_from_mask(torch.ones(1, 4, 4, dtype=torch.bool)) == pytest.approx(0.0)
    m = torch.zeros(1, 4, 4, dtype=torch.bool)
    m[0, 0, 0] = True  # 1/16 动态
    assert static_ratio_from_mask(m) == pytest.approx(15.0 / 16.0)


def test_g4_trace_writes_rows(tmp_path):
    cfg = {"Results": {"save_dir": str(tmp_path)}}
    tr = MaskStatTracer(cfg)
    tr.log_call("map", 7, [1.0, 0.5, 0.0], [0.0, 0.5, 1.0])
    tr.log_call("init", 3, [0.9], [0.1])
    assert tr.n_rows == 2
    lines = open(tr.path, encoding="utf-8").read().strip().splitlines()
    assert lines[0].startswith("phase,iteration,n_entries,mean_w")
    assert lines[1].startswith("map,7,3,")
    assert "0.500000" in lines[1]  # mean_w = (1+0.5+0)/3
    assert lines[2].startswith("init,3,1,")
    # 追加语义：同 run 重实例化不重建表头
    tr2 = MaskStatTracer(cfg)
    tr2.log_call("map", 8, [1.0], [0.0])
    assert len(open(tr2.path, encoding="utf-8").read().strip().splitlines()) == 4


def test_g4_tracer_requires_save_dir():
    with pytest.raises(RuntimeError, match="save_dir"):
        MaskStatTracer({"Results": {}})
