#!/usr/bin/env python
"""test_fdose_judges.py — FDose 两个判据机的门禁测试（纯 CPU，合成夹具）。

守护「判定类」事实（DISCIPLINE「测量口径」#12 可追溯 + exp32 判据设计教训）：

  K1 出口的机械性：§6 六条出口必须各由一组构造好的读数**唯一**触发。
  K2 单 seed 不得产出效应判决：只给 seed 0 的三臂读数时必须落 SINGLE_SEED。
  K3 MDE 真的在筛：同一个 mean Δ，n=3（MDE 3.70）判不出 vs n=6（MDE 1.57）判得出。
  K4 帧数闸：冒烟与全长混比必须被拒。
  K5 剂量两列并陈：refined 列与 online 列不同时必须都出现在报告里（不单选有利列）。
  K6 机制门 F1 是精确等式：K_i 差 1 就必须判 FAIL。
  K7 机制门 F3 能抓「键没生效」：两臂选择完全相同（Jaccard=1）必须判 FAIL。
  K8 计划越界可见：trace 的 plan_overflow=1 必须让 F2 失败。
  K9 make_dose_plan 的守卫：溢出 trace / 事件序号断裂 / k_plan 与 sel 不一致 都必须抛错。

用法: pytest tests/paper3_bpw/test_fdose_judges.py -v
"""
import csv
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO, "scripts", "paper3_bpw")


def _load(name):
    path = os.path.join(SCRIPTS, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


judge = _load("judge_fdose")
gate = _load("check_fdose_gate")
mkplan = _load("make_dose_plan")


# ─────────────────────────── 夹具 ───────────────────────────
def _write_run(root, ate_cm, gauss, frames, refined=None, status="OK"):
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "tracking_raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["method", "sequence", "status", "ate_rmse_cm"])
        w.writerow(["Combined-Prune", "x", status, "%.4f" % ate_cm])
    with open(root / "efficiency_raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["status", "online_num_gaussians", "refined_num_gaussians", "num_frames"])
        w.writerow([status, gauss, gauss if refined is None else refined, frames])


def _run_judge(tmp_path, ate_k0, ate_g, ate_s, seed_deltas=None, frames=580):
    """单 seed 用 --k0/--g/--s；多 seed（给 seed_deltas）用 --runs 显式 run 清单。

    多 seed 的 Δ 一律由 run 目录**机算**（M7：原来靠手填 JSON，最容易出错的一步）。
    """
    k0 = tmp_path / "k0"
    g = tmp_path / "g"
    s = tmp_path / "s"
    _write_run(k0, ate_k0, 60000, frames)
    _write_run(g, ate_g, 65000, frames)
    _write_run(s, ate_s, 65500, frames)
    out = tmp_path / "j.json"
    argv = ["--k0", str(k0), "--g", str(g), "--s", str(s), "--seed", "0",
            "--out-json", str(out)]
    if seed_deltas is not None:
        # 构造与 seed_deltas 一致的「每 seed 三臂」清单：S - G = delta，其余臂固定。
        spec = {}
        for i, d in enumerate(seed_deltas):
            base = tmp_path / ("s%d" % i)
            _write_run(base / "k0", ate_k0, 60000, frames)
            _write_run(base / "G", ate_g, 65000, frames)
            _write_run(base / "S", ate_g + d, 65500, frames)
            spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                            "S": str(base / "S")}
        runs = tmp_path / "runs.json"
        runs.write_text(json.dumps(spec))
        argv += ["--runs", str(runs)]
    rc = judge.main(argv)
    report = json.loads(out.read_text()) if out.is_file() else {}
    return rc, report


def _write_trace(path, events, kind_of=lambda e, i: "sel", overflow_events=(),
                 sparsity=1.0):
    """events: list of (K, n_extra_pool)；逐事件写 sel 行 + pool_only 行。

    ``overflow_events`` 里的序号会被标成 ``plan_overflow=1``（规格：K=0 且不选点）。
    ``sparsity`` 是 sel 行的 s 值（F3a 比较两臂的**臂内**稀疏度剖面，A1 §2）。
    """
    overflow_events = set(overflow_events)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 0
        for e, (k, n_extra) in enumerate(events):
            for j in range(k):
                gid += 1
                w.writerow([e, 100 * (e + 1), kind_of(e, j), gid, 0, 0, 0,
                            5e-4, 10, sparsity, 5e-4, 0.005, k,
                            1 if e in overflow_events else 0])
            for j in range(n_extra):
                gid += 1
                w.writerow([e, 100 * (e + 1), "pool_only", gid, 0, 0, 0,
                            1.2e-4, 10, sparsity, 1.2e-4, 0.005, k,
                            1 if e in overflow_events else 0])


def _write_plan(path, k):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "protocol": gate and "fdose-plan-v1", "k": k,
        "source": {"trace_sha256": "deadbeef"},
    }))


def _run_gate(tmp_path, plan_k, g_events, s_events):
    plan = tmp_path / "plan.json"
    _write_plan(plan, plan_k)
    gt = tmp_path / "g.csv"
    st = tmp_path / "s.csv"
    _write_trace(gt, g_events)
    _write_trace(st, s_events)
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "gate.md")])
    return rc, json.loads(out.read_text())


# ─────────────────────────── K1：六条出口 ───────────────────────────
def test_k1_rule2_placement_positive(tmp_path):
    rc, rep = _run_judge(tmp_path, 11.0, 11.5, 9.0, seed_deltas=[-4.0, -5.0, -4.5])
    assert rc == 0
    assert rep["rule_applied"] == 2 and rep["verdict"].startswith("PLACEMENT_POSITIVE")


def test_k1_rule3_placement_negative(tmp_path):
    rc, rep = _run_judge(tmp_path, 11.0, 11.0, 15.0, seed_deltas=[+4.5, +5.5, +4.0])
    assert rep["rule_applied"] == 3 and rep["verdict"].startswith("PLACEMENT_NEGATIVE")


def test_k1_rule4_extend_when_consistent_but_below_mde(tmp_path):
    # mean = -0.6, |mean| < MDE(n=3)=3.70, 三 seed 同向 ⇒ EXTEND
    rc, rep = _run_judge(tmp_path, 11.0, 11.2, 10.6, seed_deltas=[-0.6, -0.7, -0.5])
    assert rep["rule_applied"] == 4 and rep["verdict"].startswith("EXTEND")


def test_k1_rule5_inconclusive_when_signs_disagree(tmp_path):
    rc, rep = _run_judge(tmp_path, 11.0, 11.0, 11.0, seed_deltas=[-0.5, +0.6, -0.1])
    assert rep["rule_applied"] == 5 and rep["verdict"].startswith("INCONCLUSIVE")


def test_k1_rule5_when_consistent_but_n_already_6(tmp_path):
    deltas = [-0.3] * 6
    rc, rep = _run_judge(tmp_path, 11.0, 11.0, 10.7, seed_deltas=deltas)
    # n=6 的 MDE=1.57 > |mean|=0.3 ⇒ 不能再延长（上限），落规则 5
    assert rep["rule_applied"] == 5


# ─────────────────────────── K2：单 seed 不出效应判决 ───────────────────────────
def test_k2_single_seed_never_emits_an_effect_verdict(tmp_path):
    rc, rep = _run_judge(tmp_path, 11.0, 11.5, 13.0)   # |Δ|=1.5cm，看着"很大"
    assert rc == 0
    assert rep["rule_applied"] is None
    assert rep["verdict"].startswith("SINGLE_SEED")


# ─────────────────────────── K3：MDE 真的在筛 ───────────────────────────
def test_k3_mde_gates_the_same_delta_by_n(tmp_path):
    """同一个 mean Δ = −2.0：n=3（MDE 3.70）判不出，n=6（MDE 1.57）判得出。"""
    rc, rep3 = _run_judge(tmp_path / "a", 11.0, 11.0, 9.0,
                          seed_deltas=[-2.0, -2.0, -2.0])
    assert rep3["rule_applied"] == 4, "n=3 时 |−2.0| < 3.70 应当只允许延长"
    assert abs(rep3["mde"]["mde_cm"] - 3.70) < 0.02
    rc, rep6 = _run_judge(tmp_path / "b", 11.0, 11.0, 9.0, seed_deltas=[-2.0] * 6)
    assert rep6["rule_applied"] == 2, "n=6 时 |−2.0| > 1.57 应当判可判"
    assert abs(rep6["mde"]["mde_cm"] - 1.57) < 0.02


# ─────────────────────────── K4：帧数闸 ───────────────────────────
def test_k4_frame_count_mismatch_is_rejected(tmp_path):
    k0 = tmp_path / "k0"; g = tmp_path / "g"; s = tmp_path / "s"
    _write_run(k0, 11.0, 60000, 580)
    _write_run(g, 11.0, 65000, 580)
    _write_run(s, 11.0, 65500, 40)          # 冒烟 vs 全长
    rc = judge.main(["--k0", str(k0), "--g", str(g), "--s", str(s), "--seed", "0"])
    assert rc == 2, "跨帧数比较必须被拒"


# ─────────────────────────── K5：剂量两列并陈 ───────────────────────────
def test_k5_both_gaussian_columns_are_reported(tmp_path):
    k0 = tmp_path / "k0"; g = tmp_path / "g"; s = tmp_path / "s"
    _write_run(k0, 11.0, 60000, 580)
    _write_run(g, 11.0, 65000, 580, refined=69000)   # 模拟末端 KF 竞态
    _write_run(s, 11.0, 65500, 580)
    out = tmp_path / "j.json"
    judge.main(["--k0", str(k0), "--g", str(g), "--s", str(s), "--seed", "0",
                "--out-json", str(out)])
    rep = json.loads(out.read_text())
    assert rep["arms"]["G"]["num_gaussians"] == 65000
    assert rep["arms"]["G"]["refined_gaussians"] == 69000, "refined 列被丢了 —— 单列引用会骗人"


# ─────────────────────────── K6：F1 精确等式 ───────────────────────────
def test_k6_gate_fails_when_one_event_is_off_by_one(tmp_path):
    plan = [5, 5]
    g_ev = [(5, 3), (5, 3)]
    s_ev = [(5, 3), (4, 3)]      # 第 2 个事件少选 1 个
    rc, rep = _run_gate(tmp_path, plan, g_ev, s_ev)
    assert rc == 1 and rep["verdict"] == "FAIL"
    assert rep["arms"]["S"]["events_with_wrong_k"][0]["event"] == 1


# ─────────────────────────── K7：F3a 抓「键没生效」 ───────────────────────────
# Amendment A1（2026-10-31）：原 F3 用跨臂 gauss_idx Jaccard，但两臂各自在线长地图
# ⇒ 索引空间从事件 1 起不可比（冒烟实测位置重合率 0.000），该门恒为真。现改为
# F3a = 臂内稀疏度剖面（S/G 比），并把索引 Jaccard 降为报告项 F3b。
def test_k7_gate_fails_when_columns_are_identical(tmp_path):
    """两臂稀疏度剖面相同（γ 没生效）⇒ 机制门必须失败，且 F3b 也报 1.0。"""
    plan = [5, 5]
    ev = [(5, 3), (5, 3)]
    rc, rep = _run_gate(tmp_path, plan, ev, ev)
    assert rc == 1
    assert rep["f3a_sparsity"]["ratio_mean"] == pytest.approx(1.0)
    assert rep["f3b_index_jaccard"]["mean"] == pytest.approx(1.0)
    assert rep["verdict"] == "FAIL"


def test_k7a_f3a_passes_when_s_arm_is_sparser(tmp_path):
    """S 臂自身选中的点更疏（比值 1.3）⇒ F3a 过；F3b 再低也不影响判定。"""
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    g_ev = [(5, 2), (5, 2)]
    s_ev = [(5, 2), (5, 2)]
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, g_ev, sparsity=1.0)
    _write_trace(st, s_ev, sparsity=1.3)
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3a_sparsity"]["ratio_mean"] == pytest.approx(1.3)
    assert rep["f3a_sparsity"]["share_above"] == pytest.approx(1.0)
    assert rc == 0 and rep["verdict"] == "PASS"


def test_k7a2_f3a_fails_when_sparsity_barely_moves(tmp_path):
    """比值 1.05（低于 1.15 门）⇒ F3a 失败，即使索引 Jaccard 很低。"""
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 2), (5, 2)], sparsity=1.0)
    _write_trace(st, [(5, 2), (5, 2)], sparsity=1.05)
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3a_sparsity"]["ratio_mean"] == pytest.approx(1.05)
    assert rep["verdict"] == "FAIL"


def test_k7a3_index_jaccard_cannot_pass_the_gate_any_more(tmp_path):
    """A1 的核心：索引 Jaccard 再低（0.0）也**不能**让 γ 空转的臂过关。"""
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 2), (5, 2)], sparsity=1.0)
    # S 臂选到完全不同的索引，但稀疏度剖面与 G 相同 ⇒ 键没生效
    with open(st, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 9000
        for e in range(2):
            for j in range(5):
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            5e-4, 10, 1.0, 5e-4, 0.005, 5, 0])
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3b_index_jaccard"]["mean"] == pytest.approx(0.0)
    assert rep["verdict"] == "FAIL", "索引 Jaccard 低不能替代 F3a"


def test_k7b_gate_passes_when_arms_differ(tmp_path):
    plan = [5, 5]
    g_ev = [(5, 3), (5, 3)]
    s_ev = [(5, 3), (5, 3)]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, g_ev)
    # 让 S 臂选到不同的 gauss_idx：先写 pool_only 再写 sel，偏移索引
    with open(st, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 1000
        for e, (k, n_extra) in enumerate(s_ev):
            for j in range(k):
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            5e-4, 10, 1.3, 5e-4, 0.005, k, 0])
            for j in range(n_extra):
                gid += 1
                w.writerow([e, 100 * (e + 1), "pool_only", gid, 0, 0, 0,
                            1.2e-4, 10, 1.3, 1.2e-4, 0.005, k, 0])
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3b_index_jaccard"]["mean"] == pytest.approx(0.0)
    assert rep["f3a_sparsity"]["ratio_mean"] == pytest.approx(1.3)
    assert rc == 0 and rep["verdict"] == "PASS"


# ─────────────────────────── K8：计划越界可见 ───────────────────────────
def test_k8_injecting_past_the_plan_fails(tmp_path):
    """计划用完之后仍注入 ⇒ 总剂量随事件数分叉 ⇒ 必须 FAIL。

    越界事件本身是规格要求的（注入 0、flag=1）；FAIL 的是"越界还继续选点"。
    """
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 1), (5, 1)])
    with open(st, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 2000
        for e in range(3):                      # 3 个事件 > 计划长度 2
            for j in range(5):
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            5e-4, 10, 1.0, 5e-4, 0.005, 5, 1 if e == 2 else 0])
    out = tmp_path / "gate.json"
    gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
               "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["verdict"] == "FAIL", "越界仍注入 5 个点必须判失败"
    # 失败点必须落在「剂量恒等」上：S 臂第 3 个事件 sel=5 而规格要求 0
    wrong = rep["arms"]["S"]["events_with_wrong_k"]
    assert any(w["event"] == 2 and w["n_sel"] == 5 and w["plan_k"] == 0 for w in wrong), wrong


def test_k8b_correct_overflow_zero_injection_passes(tmp_path):
    """越界注入 0 且 flag=1 是**合规**行为 —— 两臂事件数不同是常态。"""
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    # 长臂：第 3 个事件越界 ⇒ 注入 0 且 flag=1（池里仍有候选，所以给 pool_only）
    _write_trace(gt, [(5, 1), (5, 1), (0, 1)], overflow_events=(2,))
    # 短臂只有 2 个事件（另一份 trace 需自己写两臂不同）
    with open(st, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 3000
        for e, k in ((0, 5), (1, 5)):
            for j in range(k):
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            5e-4, 10, 1.3, 5e-4, 0.005, k, 0])
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["arms"]["G"]["n_overflow_events"] == 1
    assert rep["f2_overflow_flag_violations"] == 0
    assert rep["f2_plan_faithful"] is True
    assert rep["f5_activity"]["sum_sel_G"] == 10 == rep["f5_activity"]["sum_plan"]
    assert rc == 0 and rep["verdict"] == "PASS", rep["arms"]


def test_k8c_sentinel_row_makes_overflow_auditable_with_sel_only_trace(tmp_path):
    """默认 trace 只写 sel ⇒ 越界事件（注入 0）本来一行都没有。

    没有哨兵行的话，gate 看不到「发生过越界」，就无法核对 flag。哨兵行
    `kind=overflow_zero` 只承载 flag，不进选择集合。
    """
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 0), (5, 0)])
    # S 臂：2 个正常事件 + 1 个越界哨兵行（sel 为空）
    with open(st, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 4000
        for e, k in ((0, 5), (1, 5)):
            for j in range(k):
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            5e-4, 10, 1.3, 5e-4, 0.005, k, 0])
        w.writerow([2, 300, "overflow_zero", -1, 0, 0, 0,
                    0, 0.0, 0.0, 0, 0.0, 0, 1])
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["arms"]["S"]["n_overflow_events"] == 1
    assert rep["arms"]["S"]["n_sentinel_rows"] == 1
    assert rep["arms"]["S"]["events_with_wrong_k"] == []
    assert rep["f2_overflow_flag_violations"] == 0
    assert rep["f5_activity"]["sum_sel_S"] == 10
    assert rc == 0 and rep["verdict"] == "PASS"


# ─────────────────────────── K9：make_dose_plan 的守卫 ───────────────────────────
def test_k9_make_plan_rejects_overflow_trace(tmp_path):
    p = tmp_path / "t.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        w.writerow([0, 1, "sel", 1, 0, 0, 0, 5e-4, 10, 1.0, 5e-4, 0.005, 1, 1])
    with pytest.raises(ValueError):
        mkplan.read_plan(p)


def test_k9_make_plan_rejects_broken_event_ordinals(tmp_path):
    p = tmp_path / "t.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        w.writerow([0, 1, "sel", 1, 0, 0, 0, 5e-4, 10, 1.0, 5e-4, 0.005, 1, 0])
        w.writerow([2, 3, "sel", 2, 0, 0, 0, 5e-4, 10, 1.0, 5e-4, 0.005, 1, 0])
    with pytest.raises(ValueError):
        mkplan.read_plan(p)


def test_k9_make_plan_rejects_trace_where_sel_neq_k(tmp_path):
    p = tmp_path / "t.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        w.writerow([0, 1, "sel", 1, 0, 0, 0, 5e-4, 10, 1.0, 5e-4, 0.005, 2, 0])
    with pytest.raises(ValueError):
        mkplan.read_plan(p)


def test_k9_make_plan_truncation_sets_n_plan(tmp_path):
    """--n-plan 截断：总剂量从此只由前缀和决定，越界注入 0（prereg §2 末段）。"""
    p = tmp_path / "t.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        for e, k in enumerate([3, 4, 5]):
            for j in range(k):
                w.writerow([e, 100 * (e + 1), "sel", j, 0, 0, 0,
                            5e-4, 10, 1.0, 5e-4, 0.005, k, 0])
    out = tmp_path / "plan.json"
    mkplan.main(["--trace", str(p), "--out", str(out), "--n-plan", "2"])
    plan = json.loads(out.read_text())
    assert plan["k"] == [3, 4] and plan["sum_k"] == 7 and plan["n_plan"] == 2
    assert plan["overflow_dose"] == 0
    assert plan["source"]["n_events_in_trace"] == 3, "原始事件数必须留痕"
    with pytest.raises(ValueError):
        mkplan.main(["--trace", str(p), "--out", str(out), "--n-plan", "9"])


def test_k9_make_plan_writes_protocol_and_sha(tmp_path):
    p = tmp_path / "t.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        for e, k in enumerate([3, 4]):
            for j in range(k):
                w.writerow([e, 100 * (e + 1), "sel", j, 0, 0, 0,
                            5e-4, 10, 1.0, 5e-4, 0.005, k, 0])
    out = tmp_path / "plan.json"
    mkplan.main(["--trace", str(p), "--out", str(out)])
    plan = json.loads(out.read_text())
    assert plan["protocol"] == "fdose-plan-v1"
    assert plan["k"] == [3, 4] and plan["sum_k"] == 7
    assert len(plan["source"]["trace_sha256"]) == 64


# ─────────────────────── K10：A2 的 gross 口径与站点界（slam-critic M8/致命项复核） ───
def _load_mod():
    return gate


def test_k10_gross_primitives_uses_per_site_bounds():
    """init 站点界 = 0.01·6·30 = 1.80 m，map 站点 = 0.01·6·1 = 0.06 m。

    审查方原报漏了 cameras_extent=6.0（用 0.30 / 0.01），把 init 站点的点大量误判成
    split ⇒ gross 比虚高 7 倍。本测试钉住正确界的**极性**：同一个 max_scale 序列，
    在 init 站点（宽界）几乎不 split，在 map 站点（窄界）split 明显更多。
    """
    ev = {0: {"sel": [{"max_scale": 0.5}] * 10},        # init 站点，界 1.80 ⇒ 0 split
          11: {"sel": [{"max_scale": 0.5}] * 10}}       # map 站点，界 0.06 ⇒ 全 split
    out = gate.gross_primitives(ev, n_init=11)
    assert out["bounds_m"] == [pytest.approx(1.80), pytest.approx(0.06)]
    assert out["split"] == 10, out          # 只有 map 站点的那 10 个
    assert out["gross"] == 10 * 1 + 10 * 2, out  # init 10 clone + map 10 split


def test_k10b_per_site_dose_split_matches_n_init():
    ev = {i: {"sel": [{}] * (i + 1)} for i in range(20)}
    out = gate.per_site_dose(ev, n_init=11)
    assert out["dose_init"] == sum(i + 1 for i in range(11))
    assert out["dose_map"] == sum(i + 1 for i in range(11, 20))
    assert 0 < out["share_init"] < 1


def test_k10c_f1_by_site_separates_init_and_map_failures(tmp_path):
    """M8 的 F1_init/F1_map：某一整段失效不得被另一段的正常计数掩盖。

    构造：plan 4 事件 [5,5,5,5]、n_init=2；G 臂的 init 段合规、map 段事件 2 少注入 1。
    合并计数只报「1 个事件错」，但分站点必须指出错在 map 段、init 段干净。
    """
    plan = [5, 5, 5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 0), (5, 0), (4, 0), (5, 0)])
    _write_trace(st, [(5, 0)] * 4, sparsity=1.3)
    out = tmp_path / "gate.json"
    gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
               "--n-init", "2",
               "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    fs = rep["f1_by_site"]
    assert fs["G"]["init"]["ok"] is True and fs["G"]["init"]["n_events"] == 2
    assert fs["G"]["map"]["ok"] is False
    assert [e["event"] for e in fs["G"]["map"]["events_with_wrong_k"]] == [2]
    assert fs["S"]["ok"] is True and fs["G"]["ok"] is False
    assert rep["verdict"] == "FAIL"


def test_k10d_require_done_turns_missing_anchor_into_fail(tmp_path):
    """M6：加 `--require-done` 时缺 .done 锚点 ⇒ FAIL；写了 finished_rc0=yes ⇒ 恢复 PASS。

    没有这条，「runner 用 `|| true` 继续下一段」的失败臂可以带着半截 trace 通过装置门。
    """
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "G" / "tr.csv"; st = tmp_path / "S" / "tr.csv"
    _write_trace(gt, [(5, 0), (5, 0)])
    _write_trace(st, [(5, 0), (5, 0)], sparsity=1.3)
    out = tmp_path / "gate.json"
    argv = ["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
            "--out-json", str(out), "--out-md", str(tmp_path / "g.md"),
            "--require-done"]

    rc = gate.main(argv)
    rep = json.loads(out.read_text())
    assert rep["done_ok"] is False and rep["verdict"] == "FAIL" and rc != 0
    assert rep["done"]["G"]["found"] is False

    for arm, d in (("G", gt.parent), ("S", st.parent)):
        (d / f"fdose_{arm}_seed0.done").write_text(
            "arm=%s\nseed=0\nrc=0\nmax_frames=580\nfinished_rc0=yes\n" % arm)
    rc = gate.main(argv)
    rep = json.loads(out.read_text())
    assert rep["done_ok"] is True and rep["verdict"] == "PASS" and rc == 0
    assert rep["done"]["S"]["finished_rc0"] is True

    # 负对照：锚点在但 rc 非 0 ⇒ 仍判废（"有文件"不等于"跑完了"）
    (gt.parent / "fdose_G_seed0.done").write_text(
        "arm=G\nseed=0\nrc=1\nmax_frames=580\nfinished_rc0=no\n")
    gate.main(argv)
    rep = json.loads(out.read_text())
    assert rep["done_ok"] is False and rep["verdict"] == "FAIL"


# ─────────────────────── K11：F2 的 covered 子句真的挡人（M3 次要） ───
def test_k11_short_arm_fails_f2(tmp_path):
    """短触发的臂（事件数 < N_plan）必须 FAIL —— 原 `covered >= min(len(plan_k),1)`
    形同虚设，只要 1 个事件就过。"""
    plan = [5, 5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 0)] * 3, sparsity=1.0)
    _write_trace(st, [(5, 0)] * 2, sparsity=1.3)     # 只跑了 2 个事件
    out = tmp_path / "gate.json"
    gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
               "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f2_plan_faithful"] is False, "短触发必须判 F2 失败"
    assert rep["verdict"] == "FAIL"


def test_k11b_full_coverage_still_passes(tmp_path):
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 0)] * 2, sparsity=1.0)
    _write_trace(st, [(5, 0)] * 2, sparsity=1.3)
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f2_plan_faithful"] is True
    assert rc == 0 and rep["verdict"] == "PASS"


# ─────────────────────── K12：M7 的跨 seed 清单护栏 ───────────────────────
def test_k12_runs_list_rejects_inconsistent_frame_counts(tmp_path):
    """--runs 里某 seed 的某臂帧数不同 ⇒ 必须拒绝（跨帧数比较无效）。"""
    spec = {}
    for i in (0, 1):
        base = tmp_path / ("x%d" % i)
        _write_run(base / "k0", 11.0, 60000, 580)
        _write_run(base / "G", 11.0, 65000, 580)
        _write_run(base / "S", 11.0, 65500, 580 if i == 0 else 40)
        spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                        "S": str(base / "S")}
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps(spec))
    rc = judge.main(["--k0", str(tmp_path / "x0/k0"), "--g", str(tmp_path / "x0/G"),
                     "--s", str(tmp_path / "x0/S"), "--seed", "0",
                     "--runs", str(runs), "--out-json", str(tmp_path / "j.json")])
    assert rc == 2


def test_k12b_runs_list_computes_deltas_from_runs_not_hand_filled(tmp_path):
    """Δ 必须由 run 目录机算：给 [k0=11, G=11, S=9] ⇒ Δ = −2.0（不是手填值）。"""
    spec = {}
    for i in range(3):
        base = tmp_path / ("y%d" % i)
        _write_run(base / "k0", 11.0, 60000, 580)
        _write_run(base / "G", 11.0, 65000, 580)
        _write_run(base / "S", 9.0, 65500, 580)
        spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                        "S": str(base / "S")}
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps(spec))
    out = tmp_path / "j.json"
    judge.main(["--k0", str(tmp_path / "y0/k0"), "--g", str(tmp_path / "y0/G"),
                "--s", str(tmp_path / "y0/S"), "--seed", "0",
                "--runs", str(runs), "--out-json", str(out)])
    rep = json.loads(out.read_text())
    assert rep["seed_deltas_cm"] == [pytest.approx(-2.0)] * 3
    assert rep["mde"]["n_seed"] == 3


# ─────────────────────── K13：M7 的「静默取末行」护栏 ───────────────────────
def test_k13_ambiguous_tables_raise_instead_of_taking_last_row(tmp_path):
    """同 seed 重跑把两行追加进同一张表 ⇒ read_arm 必须报错，不能静默取末行。"""
    run = tmp_path / "2026-01-01-00-00-00"
    run.mkdir(parents=True)
    with open(run / "tracking_raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", "status", "ate_rmse_cm"])
        w.writerow(["2026-01-01-00-00-00", "OK", "11.0"])
        w.writerow(["2026-01-02-00-00-00", "OK", "12.0"])     # 另一次重跑
    with pytest.raises(ValueError, match="run_id"):
        judge.read_arm(run)


def test_k13b_duplicate_rows_same_run_id_raise(tmp_path):
    run = tmp_path / "2026-01-01-00-00-00"
    run.mkdir(parents=True)
    with open(run / "tracking_raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", "status", "ate_rmse_cm"])
        w.writerow(["2026-01-01-00-00-00", "OK", "11.0"])
        w.writerow(["2026-01-01-00-00-00", "OK", "11.0"])
    with pytest.raises(ValueError, match="重复追加"):
        judge.read_arm(run)


def test_k13c_single_row_is_fine(tmp_path):
    run = tmp_path / "2026-01-01-00-00-00"
    run.mkdir(parents=True)
    with open(run / "tracking_raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", "status", "ate_rmse_cm"])
        w.writerow(["2026-01-01-00-00-00", "OK", "11.0"])
    assert judge.read_arm(run)["ate_cm"] == pytest.approx(11.0)
