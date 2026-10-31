#!/usr/bin/env python
"""test_cgb_selection.py — CGB（Coverage-Gap Budget）门禁测试。

对应 `paper3/results/evidence/prereg_cgb_2026-10-30.md` §2/§4。
纯 CPU：最小假对象，不依赖 CUDA。

不变量：
  C1 关闭态一致性：未启用 / 其他 signal ⇒ 返回 None（调用点走原标量路径）
  C2 参考集不动：所有 grad>=τ_base 的点必须仍被选中（CGB 只加不换）
  C3 等剂量：|selected| − |ref_sel| == floor(swap_frac·|ref_sel|)，且 γ=0/γ=1 完全相等
  C4 γ=0 是纯梯度续填：额外点必须是池内 mean_grad 最高的那些
  C5 γ>0 真的换了位置：γ=1 的额外点平均稀疏度显著高于 γ=0（否则机制是空转）
  C6 池约束：额外点必须 grad>=τ_lo，且不在 ref_sel 内
  C7 稀疏度极性：孤立点必须比密集点 s 更大（极性由已知值单测钉住）
  C8 percent_dense 不动：所有点都等于 base 值（否则净增计数会漂）
  C9 trace 默认关；开启时才落文件，且表头正确
  C10 与 BPW 互斥：同一 config 不可能同时激活两个机制

用法: pytest tests/densification/test_cgb_selection.py -v
"""
import os
import tempfile
import types

import torch

from utils import densification_selection as ds


def _fake_gaussians(accum, denom, xyz):
    n = len(accum)
    g = types.SimpleNamespace()
    g.xyz_gradient_accum = torch.tensor(accum, dtype=torch.float32).reshape(n, 1)
    g.denom = torch.tensor(denom, dtype=torch.float32).reshape(n, 1)
    g.get_xyz = torch.tensor(xyz, dtype=torch.float32).reshape(n, 3)

    class _Scaling:
        def max(self, dim):
            assert dim == 1
            return types.SimpleNamespace(values=torch.full((n,), 0.005))

    g.get_scaling = _Scaling()
    return g


def _cfg(**over):
    base = {
        "enabled": True,
        "signal": "coverage_gap",
        "swap_frac": 0.20,
        "gamma": 1.0,
        "tau_low_factor": 0.5,
        "sparsity_k": 6,
    }
    base.update(over)
    return {"SelectiveDensification": base}


def _grid_pool(n=600, seed=0):
    """一个既含密集簇又含孤立点的点云 + 与之匹配的梯度。

    梯度刻意与空间位置**无关**（随机铺在 τ_lo..9τ_base 上），这样"位置效应"
    与"梯度效应"才能分开；也是 C5 能钉住极性而不是靠数据构造的前提。
    低梯度带（τ_lo..τ_base）约占 1/8，必须明显大于 extra_k，否则池被取空、
    γ=0/γ=1 两臂会退化到同一个集合（C5 会变成空断言）。
    """
    gen = torch.Generator().manual_seed(seed)
    n_cluster = n // 2
    cluster = torch.randn((n_cluster, 3), generator=gen) * 0.02
    spread = torch.rand((n - n_cluster, 3), generator=gen) * 4.0 - 2.0
    xyz = torch.cat([cluster, spread], dim=0)
    denom = torch.full((n,), 10.0)
    mean_grad = 1e-4 + torch.rand((n,), generator=gen) * 8e-4
    accum = mean_grad * denom
    return accum, denom, xyz


# --- C1 ---------------------------------------------------------------------
def test_c1_disabled_or_other_signal_returns_none():
    accum, denom, xyz = _grid_pool(60)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    assert ds.compute_coverage_gap_knobs({"SelectiveDensification": {"enabled": False}}, g, 2e-4, 0.01) is None
    assert ds.compute_coverage_gap_knobs(_cfg(signal="persistence_budget"), g, 2e-4, 0.01) is None
    assert ds.compute_coverage_gap_knobs(_cfg(signal="static_prob"), g, 2e-4, 0.01) is None


# --- C2 ---------------------------------------------------------------------
def test_c2_reference_selection_is_never_dropped():
    """CGB 只加不换：参考集里的每一个点都必须仍被选中。"""
    accum, denom, xyz = _grid_pool(400)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    thr, _ = ds.compute_coverage_gap_knobs(_cfg(), g, 2e-4, 0.01)
    selected = thr.squeeze(-1) < 0
    ref_sel = (accum / denom) >= 2e-4
    assert bool(ref_sel.any()), "测试数据没有参考点，断言是空的"
    assert bool(ref_sel[~selected].sum() == 0), "有参考点被 CGB 丢掉了 —— 这就不是 CGB 了"


# --- C3 ---------------------------------------------------------------------
def test_c3_dose_is_equal_across_gamma_arms():
    """两个 CGB 臂的净增量必须逐事件严格相等（等剂量控位对照的前提）。"""
    accum, denom, xyz = _grid_pool(500)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    thr1, _ = ds.compute_coverage_gap_knobs(_cfg(gamma=1.0, swap_frac=0.10), g, 2e-4, 0.01)
    thr0, _ = ds.compute_coverage_gap_knobs(_cfg(gamma=0.0, swap_frac=0.10), g, 2e-4, 0.01)
    ref_n = int(((accum / denom) >= 2e-4).sum().item())
    n1 = int((thr1.squeeze(-1) < 0).sum().item())
    n0 = int((thr0.squeeze(-1) < 0).sum().item())
    assert n1 == n0, f"剂量不等：gamma=1 -> {n1}, gamma=0 -> {n0}"
    want = ref_n + int(0.10 * ref_n)
    assert n1 == want, f"增量不是 floor(swap_frac*ref_n)={int(0.10*ref_n)}；实得 {n1 - ref_n}"


def test_c3b_swap_frac_zero_is_exact_reference():
    """swap_frac=0 ⇒ 必须逐位复现参考选择（这是装置正确性的必要条件）。"""
    accum, denom, xyz = _grid_pool(300)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    thr, _ = ds.compute_coverage_gap_knobs(_cfg(swap_frac=0.0), g, 2e-4, 0.01)
    selected = thr.squeeze(-1) < 0
    ref_sel = (accum / denom) >= 2e-4
    assert torch.equal(selected, ref_sel)


# --- C4 ---------------------------------------------------------------------
def test_c4_gamma_zero_picks_the_strongest_pool_gradients():
    accum, denom, xyz = _grid_pool(500)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    thr, _ = ds.compute_coverage_gap_knobs(_cfg(gamma=0.0, swap_frac=0.10), g, 2e-4, 0.01)
    mean_grad = (accum / denom)
    ref_sel = mean_grad >= 2e-4
    extra = (thr.squeeze(-1) < 0) & (~ref_sel)
    pool = (mean_grad >= 1e-4) & (~ref_sel)
    k = int(extra.sum().item())
    assert k > 0
    # γ=0 的额外点必须是池内梯度最高的 k 个（不高于被漏掉的池内点）
    assert mean_grad[extra].min() >= mean_grad[pool & (~extra)].max() - 1e-9


# --- C5 ---------------------------------------------------------------------
def test_c5_gamma_one_shifts_placement_towards_sparse_space():
    """这是整个机制的立论点：γ>0 必须真的往稀疏处走，不能是空转。

    先钉住"池没被取空"这一前提：若 extra_k >= |pool|，两臂都会取走整个池，
    γ 就完全不生效，断言会变成空的（首版就是这样假通过的）。
    """
    accum, denom, xyz = _grid_pool(1200)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    s = ds.compute_sparsity(g.get_xyz, k=6)
    mean_grad = accum / denom
    ref_sel = mean_grad >= 2e-4
    pool = (mean_grad >= 1e-4) & (~ref_sel)
    extra_k = int(0.05 * int(ref_sel.sum().item()))
    assert extra_k < int(pool.sum().item()), (
        f"池被取空（extra_k={extra_k} >= |pool|={int(pool.sum().item())}）⇒ γ 无法生效，"
        "本测试会退化成空断言"
    )
    out = {}
    for gamma in (0.0, 1.0):
        thr, _ = ds.compute_coverage_gap_knobs(_cfg(gamma=gamma, swap_frac=0.05), g, 2e-4, 0.01)
        extra = (thr.squeeze(-1) < 0) & (~ref_sel)
        assert int(extra.sum().item()) == extra_k
        out[gamma] = float(s[extra].mean().item())
    assert out[1.0] > out[0.0] * 1.2, (
        f"γ=1 的额外点并不比 γ=0 更稀疏 (s={out[1.0]:.3f} vs {out[0.0]:.3f}) —— 机制空转"
    )


# --- C6 ---------------------------------------------------------------------
def test_c6_extra_points_respect_the_widened_pool():
    accum, denom, xyz = _grid_pool(500)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    thr, _ = ds.compute_coverage_gap_knobs(_cfg(swap_frac=0.30), g, 2e-4, 0.01)
    mean_grad = accum / denom
    selected = thr.squeeze(-1) < 0
    assert float(mean_grad[selected].min().item()) >= 1e-4 - 1e-12, "选中了点外的低梯度点"


# --- C7 ---------------------------------------------------------------------
def test_c7_sparsity_polarity_is_pinned_by_known_values():
    """极性单测：最孤立的点必须 s 最大（不是靠命名，是靠数值）。

    构造：6 个点挤在 1mm 内 + 1 个孤立点在 (5,5,5)。k=3 ⇒ 密簇内每点的第 4 近邻
    仍在密簇里（~1mm），孤立点的第 4 近邻是密簇（~8.6m）⇒ 两者相差三个数量级。
    n 必须 > k+1，否则 k 近邻退化为"全体"，极性问题查不出来（本测试就该报错而不是
    悄悄通过 —— 见 C7 首版的假通过）。
    """
    cluster = [[0.0, 0.0, 0.0], [0.001, 0.0, 0.0], [0.0, 0.001, 0.0],
               [0.0, 0.0, 0.001], [0.0007, 0.0007, 0.0], [0.0, 0.0007, 0.0007]]
    xyz = torch.tensor(cluster + [[5.0, 5.0, 5.0]])
    s = ds.compute_sparsity(xyz, k=3)
    assert s[6] == s.max(), f"孤立点不是最稀疏: {s.tolist()}"
    assert s[:6].max() < s[6] / 10.0, f"密集簇没有明显更密: {s.tolist()}"
    assert abs(float(torch.median(s).item()) - 1.0) < 1e-5, "归一化口径不是中位=1"


def test_c7b_sparsity_is_scale_free():
    """同一形状放大 10 倍，s 必须不变（比值口径，不依赖标定常数）。"""
    xyz = torch.tensor(
        [[0.0, 0.0, 0.0], [0.001, 0.0, 0.0], [0.0, 0.001, 0.0], [5.0, 5.0, 5.0]]
    )
    a = ds.compute_sparsity(xyz, k=3)
    b = ds.compute_sparsity(xyz * 10.0, k=3)
    assert torch.allclose(a, b, atol=1e-5), f"稀疏度不是尺度无关: {a.tolist()} vs {b.tolist()}"


# --- C8 ---------------------------------------------------------------------
def test_c8_percent_dense_is_never_moved():
    accum, denom, xyz = _grid_pool(400)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    _, pd = ds.compute_coverage_gap_knobs(_cfg(), g, 2e-4, 0.0137)
    assert bool((pd == 0.0137).all()), "percent_dense 被改了 —— 净增计数会漂"


# --- C9 ---------------------------------------------------------------------
def test_c9_trace_is_off_by_default_and_correct_when_on():
    accum, denom, xyz = _grid_pool(200)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg()
        cfg["Results"] = {"save_dir": d}
        ds.compute_coverage_gap_knobs(cfg, g, 2e-4, 0.01)
        assert not os.path.exists(os.path.join(d, "cgb_selection_trace.csv")), "trace 默认必须是关的"

        cfg_off = _cfg(trace_selection=True)
        cfg_off["Results"] = {"save_dir": d}
        ds.compute_coverage_gap_knobs(cfg_off, g, 2e-4, 0.01)
        path = os.path.join(d, "cgb_selection_trace.csv")
        assert os.path.isfile(path)
        with open(path) as fh:
            lines = fh.read().splitlines()
        assert lines[0] == "iter,kind,gauss_idx,x,y,z,mean_grad,denom,sparsity,key,max_scale"
        kinds = {ln.split(",")[1] for ln in lines[1:]}
        assert kinds <= {"ref", "extra", "pool_only"}, f"未知 kind: {kinds}"
        assert "ref" in kinds and "extra" in kinds


# --- C10 --------------------------------------------------------------------
def test_c10_bpw_and_cgb_are_mutually_exclusive():
    assert ds.cgb_active(_cfg()) and not ds.bpw_active(_cfg())
    bpw = _cfg(signal="persistence_budget")
    assert ds.bpw_active(bpw) and not ds.cgb_active(bpw)
    assert not ds.cgb_active({"SelectiveDensification": {"enabled": False, "signal": "coverage_gap"}})


# --- C11: 因果孪生（与 BPW 同一契约） ---------------------------------------
def test_c11_rng_key_matches_across_cgb_arms():
    """CGB 两臂只差 gamma，不得差随机流（初始点云/随机 KF 顺序必须一致）。"""
    from utils.causal_twin import base_rng_key
    from utils.config_utils import load_config

    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    keys = []
    for arm in ("g0", "g1"):
        path = os.path.join(
            repo, "configs/experiments/paper3_bpw", f"cgb_{arm}_person_tracking.yaml"
        )
        if not os.path.isfile(path):
            import pytest

            pytest.skip(f"配置尚未创建: {path}")
        cfg = load_config(path)
        cfg["Dataset"]["sequence"] = f"cgb_{arm}_person_tracking"
        cfg["seed"] = 0
        keys.append(base_rng_key(cfg))
    assert keys[0] == keys[1], f"CGB 两臂 RNG key 不同 ⇒ 配对前提不成立: {keys}"
    assert keys[0][0] == "person_tracking", f"rng_sequence 未生效: {keys[0]}"
