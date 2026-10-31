#!/usr/bin/env python
"""test_bpw_selection.py — Phase 0 BPW 门禁（核心不变量）

对应 `paper3/results/evidence/phase0_mechanism_spec_2026-10-27.md` §3。
纯 CPU：用最小假对象构造选择输入，不依赖 CUDA。

不变量：
  I1 关闭态逐字一致：未启用 / 其他 signal ⇒ 返回 None（调用点走原标量路径）
  I2 预算匹配：选中的源点数 == 参考臂选中的源点数（net-add 相等）
  I3 置换排序不同但预算相同：placebo 与 on 的预算相同、选中集合不同
  I4 池下界：任何被接受的源点都满足 mean-gradient >= tau_low
  I5 退化兜底：持久性计数全为 0 时退回梯度序（不静默乱序）
  I6 证据单调性：同一梯度下，观测次数越多证据分越高
  I7 因果孪生：三臂的 base_rng_key 与臂名无关（2026-10-28 审计新增）

用法: pytest tests/densification/test_bpw_selection.py -v
"""
import csv
import os
import types

import torch

from utils import densification_selection as ds


def _fake_gaussians(accum, denom, scales=None):
    n = len(accum)
    if scales is None:
        scales = [0.005] * n
    g = types.SimpleNamespace()
    g.xyz_gradient_accum = torch.tensor(accum, dtype=torch.float32).reshape(n, 1)
    g.denom = torch.tensor(denom, dtype=torch.float32).reshape(n, 1)
    g.get_xyz = torch.zeros((n, 3))

    class _Scaling:
        def max(self, dim):
            assert dim == 1
            return types.SimpleNamespace(
                values=torch.tensor(scales, dtype=torch.float32).reshape(n)
            )

    g.get_scaling = _Scaling()
    return g


def _cfg(**over):
    base = {
        "enabled": True,
        "signal": "persistence_budget",
        "p0": 8.0,
        "tau_low_factor": 0.5,
    }
    base.update(over)
    return {"SelectiveDensification": base}


def test_i1_disabled_or_other_signal_returns_none():
    g = _fake_gaussians([1e-3, 5e-4], [10.0, 10.0])
    off = {"SelectiveDensification": {"enabled": False}}
    assert ds.compute_budget_matched_knobs(off, g, 2e-4, 0.01) is None
    other = {"SelectiveDensification": {"enabled": True, "signal": "static_prob"}}
    assert ds.compute_budget_matched_knobs(other, g, 2e-4, 0.01) is None


def test_i2_budget_matches_reference_count():
    torch.manual_seed(0)
    n = 300
    denom = torch.rand(n) * 20 + 1
    accum = torch.rand(n) * 5e-4 * denom
    g = _fake_gaussians(accum.tolist(), denom.tolist())

    base_thr = 2e-4
    thr, _ = ds.compute_budget_matched_knobs(_cfg(), g, base_thr, 0.01)
    accepted = thr.squeeze(-1) < 0
    ref_count = int(((accum / denom) >= base_thr).sum().item())
    assert int(accepted.sum().item()) == ref_count


def test_i3_placebo_same_budget_different_set():
    torch.manual_seed(3)
    n = 400
    denom = torch.rand(n) * 5 + 1
    accum = torch.rand(n) * 1e-3 * denom
    g = _fake_gaussians(accum.tolist(), denom.tolist())

    thr_on, _ = ds.compute_budget_matched_knobs(_cfg(), g, 2e-4, 0.01)
    thr_pl, _ = ds.compute_budget_matched_knobs(_cfg(placebo=True), g, 2e-4, 0.01)
    a_on = torch.nonzero(thr_on.squeeze(-1) < 0).flatten()
    a_pl = torch.nonzero(thr_pl.squeeze(-1) < 0).flatten()
    assert a_on.numel() == a_pl.numel()
    assert not torch.equal(a_on, a_pl)


def test_i4_accepted_points_respect_pool_lower_bound():
    torch.manual_seed(5)
    n = 200
    denom = torch.rand(n) * 20 + 1
    accum = torch.rand(n) * 6e-4 * denom
    g = _fake_gaussians(accum.tolist(), denom.tolist())

    thr, _ = ds.compute_budget_matched_knobs(_cfg(), g, 2e-4, 0.01)
    accepted = (thr.squeeze(-1) < 0).cpu().numpy()
    mean_grad = (accum / denom).numpy()
    assert bool((mean_grad[accepted] >= 0.5 * 2e-4).all())


def test_i5_all_zero_persistence_falls_back_to_gradient_order():
    """持久性全零（尚未观测）时不得静默乱序：退回梯度序。"""
    n = 60
    accum = torch.linspace(0, 5e-4 * 10, n)
    g = _fake_gaussians(accum.tolist(), [0.0] * n)

    thr, _ = ds.compute_budget_matched_knobs(_cfg(), g, 2e-4, 0.01)
    accepted = (thr.squeeze(-1) < 0).cpu().numpy()
    reference = (accum / 1.0 >= 2e-4).numpy()
    assert bool((reference <= accepted).all())


def test_i6_evidence_increases_with_observation_count():
    grads = torch.tensor([1e-4, 1e-4, 1e-4])
    persistence = torch.tensor([0.0, 8.0, 100.0])
    ev = ds.compute_evidence(grads, persistence, p0=8.0)
    assert ev[0] < ev[1] < ev[2]


# --- I7: causal-twin key alignment -------------------------------------------
# Audit 2026-10-28: the three BPW arms are named bpw_{off,on,negctl}_balloon.
# ``slam.py`` overwrites ``Dataset.sequence`` with the config basename, so a key
# derived from ``Dataset.sequence`` would differ per ARM and give each arm its own
# initial point cloud and random-KF order -- destroying the pairing the whole
# three-arm design rests on. ``Dataset.rng_sequence` pins an arm-independent tag.

def test_i7_rng_key_matches_across_arms():
    """三臂只差行为、不差随机流：base_rng_key 必须与臂名无关。"""
    from utils.causal_twin import base_rng_key
    from utils.config_utils import load_config

    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    keys = []
    for arm in ("off", "on", "negctl"):
        path = os.path.join(
            repo, "configs/experiments/paper3_bpw", f"bpw_{arm}_balloon.yaml"
        )
        cfg = load_config(path)
        # 复现 slam.py:735-736 的运行期覆写（臂名进入 Dataset.sequence）
        cfg["Dataset"]["sequence"] = f"bpw_{arm}_balloon"
        cfg["seed"] = 0
        keys.append(base_rng_key(cfg))

    assert keys[0] == keys[1] == keys[2], (
        "三臂的 RNG base key 不同 ⇒ 初始点云/随机 KF 顺序不同，"
        f"配对前提不成立: {keys}"
    )
    assert keys[0][0] == "balloon", f"rng_sequence 未生效: {keys[0]}"


def test_i7b_negative_control_guard_is_load_bearing():
    """去掉 rng_sequence 后三臂 key 必须重新分叉，否则该回归测试是空的。"""
    from utils.causal_twin import base_rng_key
    from utils.config_utils import load_config

    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    keys = []
    for arm in ("off", "on", "negctl"):
        path = os.path.join(
            repo, "configs/experiments/paper3_bpw", f"bpw_{arm}_balloon.yaml"
        )
        cfg = load_config(path)
        cfg.pop("rng_sequence", None)  # simulate the pre-fix config
        cfg["Dataset"].pop("rng_sequence", None)
        cfg["Dataset"]["sequence"] = f"bpw_{arm}_balloon"
        cfg["seed"] = 0
        keys.append(base_rng_key(cfg))

    assert len(set(keys)) == 3, (
        "负对照失效：即使去掉 rng_sequence，三臂 key 仍然相同 ⇒ "
        f"上一条测试无法检出该缺陷。keys={keys}"
    )

# --- I8/I9: budget_scale (efficiency lever) ----------------------------------
# Phase 0 measured no ATE gain from the persistence ranking at matched budget.
# The remaining honest question is whether the ranking buys the same ATE with
# FEWER new Gaussians. ``budget_scale`` is that lever; default 1.0 must stay
# bit-identical to the reference arm or Phase 0 results would silently drift.

def test_i8_budget_scale_default_is_identity():
    """Default budget_scale=1.0 must match the reference arm exactly."""
    torch.manual_seed(11)
    n = 250
    denom = torch.rand(n) * 20 + 1
    accum = torch.rand(n) * 6e-4 * denom
    g = _fake_gaussians(accum.tolist(), denom.tolist())

    a = ds.compute_budget_matched_knobs(_cfg(budget_scale=1.0), g, 2e-4, 0.01)
    b = ds.compute_budget_matched_knobs(_cfg(), g, 2e-4, 0.01)
    assert torch.equal(a[0], b[0])


def test_i9_budget_scale_shrinks_quota_monotonically():
    """Smaller budget_scale accepts a monotonically non-increasing count."""
    torch.manual_seed(13)
    n = 400
    denom = torch.rand(n) * 20 + 1
    accum = torch.rand(n) * 6e-4 * denom
    g = _fake_gaussians(accum.tolist(), denom.tolist())

    counts = []
    for bs in (1.0, 0.5, 0.25):
        thr, _ = ds.compute_budget_matched_knobs(_cfg(budget_scale=bs), g, 2e-4, 0.01)
        counts.append(int((thr.squeeze(-1) < 0).sum().item()))

    assert counts == sorted(counts, reverse=True), counts
    assert counts[-1] < counts[0], counts


def test_i10_invalid_budget_scale_is_rejected():
    """budget_scale <= 0 must raise, never silently disable densification."""
    import pytest

    g = _fake_gaussians([1e-3, 5e-4], [10.0, 10.0])
    with pytest.raises(ValueError):
        ds.compute_budget_matched_knobs(_cfg(budget_scale=0.0), g, 2e-4, 0.01)



def test_i11_trace_selection_writes_csv_when_enabled(tmp_path):
    """诊断 trace（默认关）：enabled 时在 save_dir 写 bpw_selection_trace.csv。

    守护两件事：① trace_selection=False 时**不产生文件**（默认关，与主线逐位一致）；
    ② True 时写出 accepted/ref_passed/pool_only 三类行，且 accepted 行数与
    预算（ref 选中数）一致、ref_grad_in_pool 列在 accepted 行为 1（accepted ⊆ pool）。
    """
    torch.manual_seed(17)
    n = 120
    denom = torch.rand(n) * 20 + 1
    accum = torch.rand(n) * 6e-4 * denom
    g = _fake_gaussians(accum.tolist(), denom.tolist())

    off_cfg = {
        "SelectiveDensification": {
            "enabled": True, "signal": "persistence_budget",
            "p0": 8.0, "tau_low_factor": 0.5,
        },
        "Results": {"save_dir": str(tmp_path / "off")},
    }
    ds.compute_budget_matched_knobs(off_cfg, g, 2e-4, 0.01)
    assert not (tmp_path / "off" / "bpw_selection_trace.csv").exists(), \
        "trace_selection 默认关 ⇒ 不得产生文件"

    on_cfg = {
        "SelectiveDensification": {
            "enabled": True, "signal": "persistence_budget",
            "p0": 8.0, "tau_low_factor": 0.5, "trace_selection": True,
        },
        "Results": {"save_dir": str(tmp_path / "on")},
    }
    ds.compute_budget_matched_knobs(on_cfg, g, 2e-4, 0.01)
    path = tmp_path / "on" / "bpw_selection_trace.csv"
    assert path.exists()

    rows = list(csv.DictReader(open(path)))
    kinds = [r["kind"] for r in rows]
    n_acc = kinds.count("accepted")
    ref_count = int(((accum / denom) >= 2e-4).sum().item())
    assert n_acc == ref_count, f"accepted 行应等于 ref 选中数 ({ref_count}), 实得 {n_acc}"
    for r in rows:
        assert float(r["mean_grad"]) >= 1e-4 - 1e-9, "accepted 不得低于 tau_lo（⊆ pool）"
        if r["kind"] == "accepted":
            # 重新排序的机制点：accepted ⊆ pool，但可 ∈ 或 ∉ ref_sel ——
            # 若 accepted 全部 ∈ ref_sel，BPW 就是 no-op。列只记录事实。
            assert r["ref_grad_in_pool"] in ("0", "1")
        elif r["kind"] == "ref_passed":
            assert r["ref_grad_in_pool"] == "1", "ref_passed 必须来自 ref_sel ∧ pool"
        else:
            assert r["kind"] == "pool_only"
            assert r["ref_grad_in_pool"] == "0", "pool_only 不得在 ref_sel"
    assert set(kinds) <= {"accepted", "ref_passed", "pool_only"}


def test_i12_trace_respects_placebo_same_schema(tmp_path):
    """placebo 臂打开 trace 时行结构与 on 一致（accepted 数仍 = budget）。"""
    torch.manual_seed(19)
    n = 150
    denom = torch.rand(n) * 20 + 1
    accum = torch.rand(n) * 6e-4 * denom
    g = _fake_gaussians(accum.tolist(), denom.tolist())
    cfg = {
        "SelectiveDensification": {
            "enabled": True, "signal": "persistence_budget",
            "p0": 8.0, "tau_low_factor": 0.5, "placebo": True,
            "placebo_seed": 7, "trace_selection": True,
        },
        "Results": {"save_dir": str(tmp_path / "pl")},
    }
    ds.compute_budget_matched_knobs(cfg, g, 2e-4, 0.01)
    path = tmp_path / "pl" / "bpw_selection_trace.csv"
    assert path.exists()
    rows = list(csv.DictReader(open(path)))
    kinds = [r["kind"] for r in rows]
    ref_count = int(((accum / denom) >= 2e-4).sum().item())
    assert kinds.count("accepted") == ref_count
    assert set(kinds) <= {"accepted", "ref_passed", "pool_only"}
