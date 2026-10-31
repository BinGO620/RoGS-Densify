#!/usr/bin/env python
"""test_fdose_selection.py — FDose（冻结剂量计划）门禁测试。

对应 `paper3/results/evidence/prereg_fdose_2026-10-31.md` §2/§4.1。
纯 CPU：最小假对象，不依赖 CUDA。

不变量：
  D1 关闭态一致性：未启用 / 其他 signal ⇒ 返回 None（调用点走原标量路径）
  D2 剂量恒等（F1）：|sel| 逐事件严格 == K_i，两臂（γ=0/γ=1）逐事件完全相等
  D3 计划忠实（F2）：K_i 按**事件序号**取，不是按 raw iteration 取
  D4 计划越界可见（F2）：事件数超过计划长度 ⇒ overflow=1 且沿用末位剂量（不得静默扩展）
  D5 修剪真的发生：K_i < |ref_sel| 时选点数就是 K_i（不是「至少参考集那么大」）
  D6 键真的不同（F3）：γ=1 的选中点平均稀疏度显著高于 γ=0
  D7 池约束（F4）：选中点全部 mean_grad >= τ_lo
  D8 percent_dense 不动
  D9 自计划（k0）：dose_plan_path=None ⇒ K_i == |ref_sel|，且选点等于参考集
  D10 坏计划必须抛错，不得静默退化为自计划
  D11 trace 默认关；开启时表头正确、含 sel
  D12 与 BPW/CGB 互斥
"""
import json
import os
import tempfile
import types

import pytest
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
        "signal": "frozen_dose",
        "gamma": 1.0,
        "tau_low_factor": 0.5,
        "sparsity_k": 6,
        "dose_plan_path": None,
    }
    base.update(over)
    return {"SelectiveDensification": base}


def _grid_pool(n=900, seed=0):
    """密集簇 + 散布点；梯度与空间位置刻意无关（位置效应与梯度效应可分开）。"""
    gen = torch.Generator().manual_seed(seed)
    n_cluster = n // 2
    cluster = torch.randn((n_cluster, 3), generator=gen) * 0.02
    spread = torch.rand((n - n_cluster, 3), generator=gen) * 4.0 - 2.0
    xyz = torch.cat([cluster, spread], dim=0)
    denom = torch.full((n,), 10.0)
    mean_grad = 1e-4 + torch.rand((n,), generator=gen) * 8e-4
    accum = mean_grad * denom
    return accum, denom, xyz


def _write_plan(path, k):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"protocol": ds.FDOSE_PLAN_PROTOCOL, "k": list(k)}, fh)


def _n_selected(thr):
    return int((thr.squeeze(-1) < 0).sum().item())


# --- D1 ---------------------------------------------------------------------
def test_d1_disabled_or_other_signal_returns_none():
    accum, denom, xyz = _grid_pool(60)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    assert (
        ds.compute_frozen_dose_knobs(
            {"SelectiveDensification": {"enabled": False}}, g, 2e-4, 0.01
        )
        is None
    )
    for other in ("persistence_budget", "coverage_gap", "static_prob"):
        assert ds.compute_frozen_dose_knobs(_cfg(signal=other), g, 2e-4, 0.01) is None


# --- D2 ---------------------------------------------------------------------
def test_d2_dose_equals_the_plan_and_matches_across_arms():
    """F1：两臂逐事件拿同一个 K_i，且实际选中的点数就是 K_i。"""
    accum, denom, xyz = _grid_pool(900)
    plan = [50, 120, 7]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, plan)
        for gamma in (0.0, 1.0):
            g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
            cfg = _cfg(gamma=gamma, dose_plan_path=path)
            for i, k in enumerate(plan):
                thr, _ = ds.compute_frozen_dose_knobs(cfg, g, 2e-4, 0.01)
                assert _n_selected(thr) == k, (
                    f"事件 {i} gamma={gamma}: 选 {_n_selected(thr)} != K_i {k}"
                )


# --- D3 ---------------------------------------------------------------------
def test_d3_plan_is_keyed_by_event_ordinal_not_iteration():
    """F2：同一事件序号必须拿到同一个 K，与 iteration_count 无关。

    两臂在迭代轴上的 densify 事件列表本来就不同（2026-10-30 实测 63 vs 61 事件），
    用 raw iteration 做键会让同一序号的两臂拿到不同剂量。
    """
    accum, denom, xyz = _grid_pool(900)
    plan = [11, 22]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, plan)
        g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        cfg = _cfg(dose_plan_path=path)
        # 同一实例上换 iteration 值，序号顺序不变 ⇒ 剂量顺序不变
        for it, want in ((1, 11), (1850, 22)):
            thr, _ = ds.compute_frozen_dose_knobs(cfg, g, 2e-4, 0.01, iteration_count=it)
            assert _n_selected(thr) == want, f"iter={it}: {_n_selected(thr)} != {want}"


# --- D4 ---------------------------------------------------------------------
def test_d4_plan_overflow_injects_nothing_and_is_flagged():
    """计划用完之后**注入 0**，不是沿用末位剂量。

    两臂的事件数本来就不同（实测 61/63/64），沿用末位会让事件多的臂多拿到
    那部分剂量 ⇒ 总剂量随事件数分叉，正好把本设计要切断的东西又放回来。
    注入 0 + 打 overflow 标 ⇒ 总剂量 = 计划前缀和，与事件数无关。
    """
    accum, denom, xyz = _grid_pool(900)
    plan = [30, 40]
    logs = []
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, plan)
        g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        cfg = _cfg(dose_plan_path=path)
        for _ in range(2):
            ds.compute_frozen_dose_knobs(cfg, g, 2e-4, 0.01, log_fn=logs.append)
        thr, pd = ds.compute_frozen_dose_knobs(cfg, g, 2e-4, 0.01, log_fn=logs.append)
        assert _n_selected(thr) == 0, "越界事件必须注入 0（否则总剂量随事件数分叉）"
        assert "overflow=1" in logs[-1], f"越界未打标: {logs[-1]}"
        assert "k_plan=0" in logs[-1]
        assert "overflow=0" in logs[0]
        # percent_dense 仍不得被动到（越界不是"关掉 densify"，只是不注入）
        assert bool((pd == 0.01).all())


# --- D5 ---------------------------------------------------------------------
def test_d5_trim_really_trims_below_the_reference_count():
    """K_i 小于本臂 |ref_sel| 时必须真的少选 —— 本设计的剂量是外生的，不是下限。"""
    accum, denom, xyz = _grid_pool(900)
    ref_n = int(((accum / denom) >= 2e-4).sum().item())
    assert ref_n > 20, "测试数据参考点太少，断言是空的"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, [ref_n // 4])
        g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        thr, _ = ds.compute_frozen_dose_knobs(_cfg(dose_plan_path=path), g, 2e-4, 0.01)
        assert _n_selected(thr) == ref_n // 4, "没有修剪：剂量被自身参考集兜底了"


# --- D6 ---------------------------------------------------------------------
def test_d6_gamma_one_is_still_the_sparser_key():
    """F3：换了剂量来源之后，γ 仍然必须真的改变放置（否则机制空转）。"""
    accum, denom, xyz = _grid_pool(1400)
    s = ds.compute_sparsity(xyz.detach().clone(), k=6)
    plan = [120]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, plan)
        means = {}
        for gamma in (0.0, 1.0):
            g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
            thr, _ = ds.compute_frozen_dose_knobs(
                _cfg(gamma=gamma, dose_plan_path=path), g, 2e-4, 0.01
            )
            sel = thr.squeeze(-1) < 0
            means[gamma] = float(s[sel].mean().item())
        assert means[1.0] > means[0.0] * 1.2, (
            f"γ=1 不比 γ=0 更稀疏 (s={means[1.0]:.3f} vs {means[0.0]:.3f}) —— 机制空转"
        )


# --- D7 ---------------------------------------------------------------------
def test_d7_selected_points_respect_the_widened_pool():
    accum, denom, xyz = _grid_pool(900)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, [200])
        g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        thr, _ = ds.compute_frozen_dose_knobs(_cfg(dose_plan_path=path), g, 2e-4, 0.01)
        mean_grad = accum / denom
        sel = thr.squeeze(-1) < 0
        assert float(mean_grad[sel].min().item()) >= 1e-4 - 1e-12, "选中了点外的低梯度点"


# --- D8 ---------------------------------------------------------------------
def test_d8_percent_dense_is_never_moved():
    accum, denom, xyz = _grid_pool(400)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, [50])
        g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        _, pd = ds.compute_frozen_dose_knobs(_cfg(dose_plan_path=path), g, 2e-4, 0.0137)
        assert bool((pd == 0.0137).all()), "percent_dense 被改了 —— clone/split 边界会漂"


# --- D9 ---------------------------------------------------------------------
def test_d9_self_plan_reproduces_the_reference_selection():
    """k0 臂（δ=γ=0，自计划）：K_i = |ref_sel| ⇒ 选中集与参考规则**逐位相同**。

    等价性的机理：pool = {g >= τ_lo} ⊇ ref_sel = {g >= τ_base}，在 pool 内按 g 取
    |ref_sel| 个最大的点，恰好回到 ref_sel（τ_base 的定义就是这个分位）。
    ⇒ k0 不需要另跑一条 off 臂来当剂量参考。
    注意 k0 **必须** γ=0：γ>0 会换键，等价性不成立（这正是 D6 检的事）。
    """
    accum, denom, xyz = _grid_pool(900)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    thr, _ = ds.compute_frozen_dose_knobs(
        _cfg(gamma=0.0, dose_plan_path=None), g, 2e-4, 0.01
    )
    ref_sel = (accum / denom) >= 2e-4
    selected = thr.squeeze(-1) < 0
    assert torch.equal(selected, ref_sel), "自计划臂与基础规则不等价 —— k0 不能当剂量参考"
    assert ds.fdose_active(_cfg(gamma=0.0, dose_plan_path=None))


# --- D10 --------------------------------------------------------------------
def test_d10_broken_plan_raises_instead_of_degrading_to_self_plan():
    """计划读不出来必须报错。静默退化为自计划 = 处理臂变成参考臂却仍报干净 run。"""
    accum, denom, xyz = _grid_pool(200)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    with tempfile.TemporaryDirectory() as d:
        bad_protocol = os.path.join(d, "bad_protocol.json")
        with open(bad_protocol, "w", encoding="utf-8") as fh:
            json.dump({"protocol": "something-else", "k": [10]}, fh)
        with pytest.raises(ValueError):
            ds.compute_frozen_dose_knobs(_cfg(dose_plan_path=bad_protocol), g, 2e-4, 0.01)

        empty = os.path.join(d, "empty.json")
        with open(empty, "w", encoding="utf-8") as fh:
            json.dump({"protocol": ds.FDOSE_PLAN_PROTOCOL, "k": []}, fh)
        with pytest.raises(ValueError):
            ds.compute_frozen_dose_knobs(_cfg(dose_plan_path=empty), g, 2e-4, 0.01)


# --- D11 --------------------------------------------------------------------
def test_d11_trace_is_off_by_default_and_correct_when_on():
    accum, denom, xyz = _grid_pool(300)
    with tempfile.TemporaryDirectory() as d:
        plan_path = os.path.join(d, "plan.json")
        _write_plan(plan_path, [40])
        cfg = _cfg(dose_plan_path=plan_path)
        cfg["Results"] = {"save_dir": d}
        g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        ds.compute_frozen_dose_knobs(cfg, g, 2e-4, 0.01)
        assert not os.path.exists(
            os.path.join(d, "fdose_selection_trace.csv")
        ), "trace 默认必须是关的"

        cfg_on = _cfg(dose_plan_path=plan_path, trace_selection=True)
        cfg_on["Results"] = {"save_dir": d}
        g2 = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        ds.compute_frozen_dose_knobs(cfg_on, g2, 2e-4, 0.01)
        path = os.path.join(d, "fdose_selection_trace.csv")
        assert os.path.isfile(path)
        with open(path) as fh:
            lines = fh.read().splitlines()
        assert lines[0] == (
            "event,iter,kind,gauss_idx,x,y,z,mean_grad,denom,sparsity,key,"
            "max_scale,k_plan,plan_overflow"
        )
        rows = [ln.split(",") for ln in lines[1:]]
        kinds = {r[2] for r in rows}
        assert kinds <= {"sel", "pool_only"}, f"未知 kind: {kinds}"
        assert "sel" in kinds
        assert sum(1 for r in rows if r[2] == "sel") == 40, "trace 的 sel 行数必须等于 K_i"
        assert all(r[12] == "40" for r in rows), "trace 必须逐行记录 k_plan"
        # 默认不写未选中的池内点：580 帧单臂会到 50 MB（CGB 实测触发 GitHub 告警）。
        # 门 F1–F5 只需要 selected 的身份 + 逐事件 K，池规模由 `[fdose] pool=` 日志给。
        assert kinds == {"sel"}, f"默认必须只写 sel，实得 {kinds}"

        # 越界哨兵行：越界事件注入 0，默认（只写 sel）时一行都不写 ⇒ gate 看不到
        # 「发生过越界」。哨兵行 kind=overflow_zero 只承载 flag。
        cfg_ov = _cfg(dose_plan_path=plan_path, trace_selection=True)
        cfg_ov["Results"] = {"save_dir": os.path.join(d, "ov")}
        g_ov = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        for _ in range(2):                     # 计划只有 1 个事件
            ds.compute_frozen_dose_knobs(cfg_ov, g_ov, 2e-4, 0.01)
        with open(os.path.join(d, "ov", "fdose_selection_trace.csv")) as fh:
            ov_rows = [ln.split(",") for ln in fh.read().splitlines()[1:]]
        sents = [r for r in ov_rows if r[2] == "overflow_zero"]
        assert len(sents) == 1 and sents[0][13] == "1", "越界必须留一条哨兵行且 flag=1"

        cfg_pool = _cfg(dose_plan_path=plan_path, trace_selection=True, trace_pool=True)
        cfg_pool["Results"] = {"save_dir": os.path.join(d, "pool")}
        g3 = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        ds.compute_frozen_dose_knobs(cfg_pool, g3, 2e-4, 0.01)
        with open(os.path.join(d, "pool", "fdose_selection_trace.csv")) as fh:
            kinds2 = {ln.split(",")[2] for ln in fh.read().splitlines()[1:]}
        assert "pool_only" in kinds2, "trace_pool: true 时必须把未选中的池内点也写出来"


# --- D12 --------------------------------------------------------------------
def test_d12_fdose_is_exclusive_with_bpw_and_cgb():
    assert ds.fdose_active(_cfg())
    assert not ds.bpw_active(_cfg()) and not ds.cgb_active(_cfg())
    for other in ("persistence_budget", "coverage_gap"):
        cfg = _cfg(signal=other)
        assert not ds.fdose_active(cfg)
    assert not ds.fdose_active(
        {"SelectiveDensification": {"enabled": False, "signal": "frozen_dose"}}
    )


# --- D13 --------------------------------------------------------------------
def test_d13_ties_are_broken_deterministically_by_index():
    """平局必须按 gauss_idx 确定性打破（prereg §7 曾声称有测试、实际没有）。

    构造：池内 40 个点全用**同一个** mean_grad（完全平局）+ 4 个参考点。
    K 取 10 ⇒ 平局里必须有确定的 10 个，且两次调用结果逐位相同。
    """
    n_ref, n_tie, k = 4, 40, 10
    n = n_ref + n_tie
    denom = torch.full((n,), 10.0)
    accum = torch.cat([torch.full((n_ref,), 9e-4), torch.full((n_tie,), 5e-4)]) * denom
    xyz = torch.zeros(n, 3)
    g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, [k])
        runs = []
        for _ in range(2):
            g2 = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
            thr, _ = ds.compute_frozen_dose_knobs(
                _cfg(gamma=0.0, dose_plan_path=path), g2, 8e-4, 0.01
            )
            runs.append((thr.squeeze(-1) < 0).clone())
        assert torch.equal(runs[0], runs[1]), "平局打破了两次不同 —— 选择不确定"
        sel = runs[0]
        assert int(sel.sum().item()) == k, f"选 {int(sel.sum())} != K {k}"
        # 平局组里被选中的必须是索引最小的那些（stable argsort 的确定性落点）
        tied = sel[n_ref:]
        chosen = torch.nonzero(tied).flatten().tolist()
        expected = list(range(k - n_ref))
        assert chosen == expected, f"平局未按索引升序取: {chosen} vs {expected}"


# --- D14 --------------------------------------------------------------------
def test_d14_first_event_after_reset_must_be_ordinal_zero():
    """M5：地图重建后第一个 densify 事件的 ordinal 必须是 0，否则**报错**而不是静默错剂量。

    `BackEnd.reset()` 删 `_fdose_event_idx` 并置 `_fdose_ordinal_must_be_zero`；
    本测试钉两件事：① 合法路径（reset 后首事件）不误报；② 若计数器没被清（模拟旧
    行为：reset 删了属性但别处又塞回旧值）⇒ 必须抛 RuntimeError，不得静默继续。
    """
    accum, denom, xyz = _grid_pool(n=200)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        _write_plan(path, [5] * 4)
        cfg = _cfg(gamma=0.0, dose_plan_path=path)

        # ① reset 之后的首事件：带标志、无计数器 ⇒ 正常走，且 ordinal 从 0 消费
        g = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        g._fdose_ordinal_must_be_zero = True
        thr, _ = ds.compute_frozen_dose_knobs(cfg, g, 8e-4, 0.01)
        assert int((thr.squeeze(-1) < 0).sum().item()) == 5, "首事件没按计划 K=5 注入"
        assert not getattr(g, "_fdose_ordinal_must_be_zero", False), "标志用过就应清掉"

        # ② 计数器未清（旧 serial 状态泄漏到新地图）⇒ 必须抛错
        g2 = _fake_gaussians(accum.tolist(), denom.tolist(), xyz.tolist())
        g2._fdose_ordinal_must_be_zero = True
        g2._fdose_event_idx = 7          # 模拟重建后仍带着旧序号
        with pytest.raises(RuntimeError):
            ds.compute_frozen_dose_knobs(cfg, g2, 8e-4, 0.01)
