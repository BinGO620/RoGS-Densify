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
from pathlib import Path
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


def _write_trace(path, events, kind_of=lambda e, i: "sel", overflow_events=(),
                 sparsity=1.0, pool_sparsity=None, g_sel=None, g_pool=None):
    """events: list of (K, n_extra_pool)；逐事件写 sel 行 + pool_only 行。

    ``overflow_events`` 里的序号会被标成 ``plan_overflow=1``（规格：K=0 且不选点）。
    ``sparsity`` 是 sel 行的 s 值（F3a 跨臂口径比较两臂的**臂内**稀疏度剖面，A1 §2）。

    ``pool_sparsity``（A4 §2.1）：给值时构造**可解析的 γ 效应**。每事件池含两族：
    sel 族（**低** g、s = ``pool_sparsity``）与 pool_only 族（**高** g、s = ``sparsity``）：

      | 行 | mean_grad | sparsity | key(γ=0)=g | key(γ=1)=g·s |
      |---|---|---|---|---|
      | sel | 1.0 | r = pool_sparsity | 1.0 | 1.0·r |
      | pool_only | 1.5 | 1.0 | **1.5** | 1.5 |

    ⇒ γ=0 键选 pool_only 族（1.5 > 1.0）；γ=1 键在 r>1.5 时改选 sel 族（r > 1.5）。
    于是 F3a′ = mean_s(sel 族)/mean_s(pool 族) = r/1.0 = **r**（要求 ``r > 1.5``
    才翻转；``r = 1.05`` 不翻转 ⇒ 比值 1.0，故「比值略动」用例改用**其它构造**）。
    **调用方须给 ``n_extra >= K``**，否则 γ=0 的 top-K 混入 sel 行、比值被拉低。
    """
    overflow_events = set(overflow_events)
    path.parent.mkdir(parents=True, exist_ok=True)
    if pool_sparsity is None:
        s_sel, s_pool, g_sel_d, g_pool_d = sparsity, sparsity, 5e-4, 1.2e-4
    else:
        s_sel, s_pool, g_sel_d, g_pool_d = float(pool_sparsity), float(sparsity), 1.0, 1.5
    if g_sel is not None:
        g_sel_d = float(g_sel)
    if g_pool is not None:
        g_pool_d = float(g_pool)
    g_sel, g_pool = g_sel_d, g_pool_d
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
                            g_sel, 10, s_sel, g_sel, 0.005, k,
                            1 if e in overflow_events else 0])
            for j in range(n_extra):
                gid += 1
                w.writerow([e, 100 * (e + 1), "pool_only", gid, 0, 0, 0,
                            g_pool, 10, s_pool, g_pool, 0.005, k,
                            1 if e in overflow_events else 0])


def _write_gate_json(path, seed, g_dir, s_dir, k0_dir, verdict="PASS",
                     f3a_prime_ok=True, plan_sha=None, f3a_mean=1.31,
                     share=0.96, cross=1.13, baseline=0.87, done_ok=True,
                     plan_path=None):
    """合成 A4 gate 工件（judge 的 gate 校验用；source 指向真实 run 目录）。

    A4/G2(2026-11-03)：judge 现在**在计划文件实体上重算 sha**（不再自比），
    且硬校验 done_ok。因此本夹具默认在 path 同级写一份真实 plan 文件，
    plan_sha 缺省 = 该文件实算 sha；负对照可显式传错值。
    行数上限须覆盖 57 事件 × n_init（gate 合成器写 k×6 列）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    plan_p = Path(plan_path) if plan_path else (path.parent / ("plan_%s.json" % seed))
    if not plan_p.exists():
        plan_p.write_text(json.dumps({"seed": int(seed), "n_events": 57}))
    if plan_sha is None:
        import hashlib
        plan_sha = hashlib.sha256(plan_p.read_bytes()).hexdigest()
    payload = {
        "generated_by": "synthetic-test-gate",
        "source": {"plan": str(plan_p),
                   "g": str(Path(g_dir) / "fdose_selection_trace.csv"),
                   "s": str(Path(s_dir) / "fdose_selection_trace.csv"),
                   "k0": str(Path(k0_dir) / "fdose_selection_trace.csv")},
        "plan": {"sha256": plan_sha},
        "verdict": verdict,
        "done_ok": done_ok,
        "f3a_prime_ok": f3a_prime_ok,
        "f3a_prime": {"reason": "" if f3a_prime_ok else "pool_missing",
                      "f3a_prime_mean": f3a_mean if f3a_prime_ok else None,
                      "f3a_prime_share_above": share if f3a_prime_ok else None,
                      "n_events": 57},
        "f3a_cross_arm": {"ratio_mean": cross},
        "pool_baseline_ratio": {"ratio_median": baseline},
    }
    path.write_text(json.dumps(payload))


def _run_judge(tmp_path, ate_k0, ate_g, ate_s, seed_deltas=None, frames=580):
    """单 seed 用 --k0/--g/--s；多 seed（给 seed_deltas）用 --runs 显式 run 清单。

    多 seed 的 Δ 一律由 run 目录**机算**（M7：原来靠手填 JSON，最容易出错的一步）。
    A4 起：多 seed 清单必须带 `gate_json`（gate 只消费不重算），本夹具合成一份。
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
            gate_p = tmp_path / ("gate_s%d.json" % i)
            _write_gate_json(gate_p, str(i), base / "G", base / "S", base / "k0")
            spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                            "S": str(base / "S"),
                            "gate_json": str(gate_p),
                            "selected_role": "diagnostic_rerun" if i == 0 else "confirmation"}
        runs = tmp_path / "runs.json"
        runs.write_text(json.dumps(spec))
        argv += ["--runs", str(runs)]
    rc = judge.main(argv)
    report = json.loads(out.read_text()) if out.is_file() else {}
    return rc, report


def _write_trace_no_pool(path, events, sparsity=1.0):
    """A4 §2.5 负对照夹具：**只写 sel 行**（模拟 trace_pool:false 的旧 trace）⇒ F3a′ pool_missing。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 0
        for e, (k, _n_extra) in enumerate(events):
            for j in range(k):
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            5e-4, 10, sparsity, 5e-4, 0.005, k, 0])


def _write_plan(path, k, n_init=1):
    """写最小计划 JSON。默认带 `n_init: 1`（A4 契约：判据机默认从计划读站点切分）；
    n_init=None ⇒ 不带该字段（模拟 A4 之前的旧版计划，须配 --n-init 才能跑）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    plan = {"protocol": gate and "fdose-plan-v1", "k": k,
            "source": {"trace_sha256": "deadbeef"}}
    if n_init is not None:
        plan["n_init"] = n_init
    path.write_text(json.dumps(plan))


def _run_gate(tmp_path, plan_k, g_events, s_events, s_pool_sparsity=1.6):
    """跑机制门。默认给 S 臂**池内 s 梯度**（A4 §2.1：sel 行 s=1.3、pool_only 行 s=1.0）
    ⇒ F3a′ 同池反事实键对比 = 1.3 ⇒ 硬门成立；期望 FAIL 的用例不受影响（别的子门判死）。
    """
    plan = tmp_path / "plan.json"
    _write_plan(plan, plan_k)
    gt = tmp_path / "g.csv"
    st = tmp_path / "s.csv"
    _write_trace(gt, g_events)
    _write_trace(st, [(k, max(k, 1)) for k, _ in s_events],
                pool_sparsity=s_pool_sparsity)
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


def test_a6_absolute_frame_gate(tmp_path):
    """A6 帧数绝对闸：旧的相对闸只查三臂一致 —— 三臂同为 40 帧的冒烟也能过。
    默认 --expect-frames 580 ⇒ 三臂一致的冒烟也必须被拒；显式传 40 才放行
    （冒烟判定必须显式声明，不许静默混进全长口径）。"""
    runs = tmp_path / "smoke"
    _write_run(runs / "k0", 1.2, 60000, 40)
    _write_run(runs / "g", 1.2, 65000, 40)
    _write_run(runs / "s", 1.3, 65500, 40)
    argv = ["--k0", str(runs / "k0"), "--g", str(runs / "g"), "--s", str(runs / "s"),
            "--seed", "0", "--out-json", str(tmp_path / "j.json")]
    assert judge.main(argv) == 2, "三臂一致但 ≠ 580 ⇒ 绝对闸必须拒"
    assert judge.main(argv + ["--expect-frames", "40"]) == 0
    rep = json.loads((tmp_path / "j.json").read_text())
    assert rep["arms"]["G"]["num_frames"] == 40


def test_a6_runs_schema_validation(tmp_path):
    """A6 --runs schema：缺 G/S 键 ⇒ 清晰 rc=2（原来是走到取 Δ 时的未捕获 KeyError）；
    seed 集合不含 --seed / 坏键 / 非 JSON 对象 ⇒ rc=2。"""
    runs = tmp_path / "anchor"
    _write_run(runs / "k0", 11.0, 60000, 580)
    _write_run(runs / "g", 11.0, 65000, 580)
    _write_run(runs / "s", 10.9, 65500, 580)
    argv = ["--k0", str(runs / "k0"), "--g", str(runs / "g"), "--s", str(runs / "s"),
            "--seed", "0"]
    rp = tmp_path / "runs.json"

    # 缺 G 键
    base = tmp_path / "s0"
    _write_run(base / "k0", 11.0, 60000, 580)
    _write_run(base / "s", 10.9, 65500, 580)
    rp.write_text(json.dumps({"0": {"k0": str(base / "k0"), "S": str(base / "s")}}))
    assert judge.main(argv + ["--runs", str(rp)]) == 2

    # seed 集合 {1} 不含 --seed 0
    rp.write_text(json.dumps({"1": {"k0": str(runs / "k0"), "G": str(runs / "g"),
                                    "S": str(runs / "s")}}))
    assert judge.main(argv + ["--runs", str(rp)]) == 2

    # 坏键（非数字）/ 非对象
    rp.write_text(json.dumps({"zero": {"k0": "", "G": "", "S": ""}}))
    assert judge.main(argv + ["--runs", str(rp)]) == 2
    rp.write_text(json.dumps([["0"]]))
    assert judge.main(argv + ["--runs", str(rp)]) == 2


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
    """两臂稀疏度剖面相同且 S 池内无 s 梯度（γ 没生效）⇒ 机制门必须失败。
    A4 起：跨臂比降报告项，判死的是 F3a′（同池反事实 = 1.0）。"""
    plan = [5, 5]
    ev = [(5, 3), (5, 3)]
    rc, rep = _run_gate(tmp_path, plan, ev, ev, s_pool_sparsity=1.0)
    assert rc == 1
    assert rep["f3a_cross_arm"]["ratio_mean"] == pytest.approx(1.0)
    assert rep["f3a_prime"]["f3a_prime_mean"] == pytest.approx(1.0)
    assert rep["f3a_prime"]["ok"] is False
    # 两臂同事件序数与 sel 数，但池行数不同 ⇒ 索引空间有差异，Jaccard 只作报告项
    # （A1 起；此处约 0.714）——它低不能替代 F3a′，高也不能救 F3a′。
    assert 0.0 <= rep["f3b_index_jaccard"]["mean"] <= 1.0
    assert rep["verdict"] == "FAIL"


def test_k7a_f3a_passes_when_s_arm_is_sparser(tmp_path):
    """A4 语义：S 臂**池内**有 s 梯度（sel 行 1.3 / pool_only 行 1.0）⇒ F3a′ = 1.3 过门；
    跨臂比同时报 1.3（报告项，不判）。"""
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    g_ev = [(5, 2), (5, 2)]
    s_ev = [(5, 2), (5, 2)]
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, g_ev, sparsity=1.0)
    _write_trace(st, [(5, 5), (5, 5)], sparsity=1.0, pool_sparsity=1.6)
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3a_prime"]["f3a_prime_mean"] == pytest.approx(1.6)
    assert rep["f3a_prime"]["f3a_prime_share_above"] == pytest.approx(1.0)
    assert rep["f3a_cross_arm"]["ratio_mean"] == pytest.approx(1.6)
    assert rc == 0 and rep["verdict"] == "PASS"


def test_k7a2_f3a_fails_when_sparsity_barely_moves(tmp_path):
    """A4 语义：S 池内键对比只有 1.05（低于 1.15 门）⇒ F3a′ 失败，即使索引 Jaccard 很低。

    构造：sel 族 s=1.05、g=1.0；pool 族 s=1.0、g=1.0·1.05+ε？——不行，键必须严格翻转。
    改用**两族 g 差很小**的构造：sel 族 g=1.00、s=1.05；pool 族 g=1.03、s=1.00
    ⇒ γ=0 键选 pool(1.03>1.00)、γ=1 键选 sel(1.05 > 1.03) ⇒ 比值 = 1.05/1.00 = 1.05。
    """
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 5), (5, 5)], sparsity=1.0)
    _write_trace(st, [(5, 5), (5, 5)], sparsity=1.0, pool_sparsity=1.05,
                 g_sel=1.00, g_pool=1.03)
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3a_prime"]["f3a_prime_mean"] == pytest.approx(1.05)
    assert rep["f3a_prime"]["ok"] is False
    assert rep["verdict"] == "FAIL"


def test_k7a3_index_jaccard_cannot_pass_the_gate_any_more(tmp_path):
    """A1/A4 的核心：索引 Jaccard 再低（0.0）也**不能**让 γ 空转的臂过关。"""
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 2), (5, 2)], sparsity=1.0)
    # S 臂选到完全不同的索引，但**池内 s 无差异**（sel 与 pool_only 同为 1.0）⇒ 键没生效
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
            for j in range(2):
                gid += 1
                w.writerow([e, 100 * (e + 1), "pool_only", gid, 0, 0, 0,
                            1.2e-4, 10, 1.0, 1.2e-4, 0.005, 5, 0])
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3b_index_jaccard"]["mean"] == pytest.approx(0.0)
    assert rep["f3a_prime"]["ok"] is False
    assert rep["verdict"] == "FAIL", "索引 Jaccard 低不能替代 F3a′"


def test_k7b_gate_passes_when_arms_differ(tmp_path):
    plan = [5, 5]
    g_ev = [(5, 3), (5, 3)]
    s_ev = [(5, 3), (5, 3)]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, g_ev)
    # 让 S 臂选到不同的 gauss_idx，且**池内有 s 梯度**（sel 1.3 / pool_only 1.0）
    with open(st, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 1000
        for e, (k, n_extra) in enumerate(s_ev):
            for j in range(k):                  # sel 族：低 g / 高 s（γ=1 选中）
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            1.0, 10, 1.6, 1.0, 0.005, k, 0])
            for j in range(n_extra):            # pool 族：高 g / 低 s（γ=0 选中）
                gid += 1
                w.writerow([e, 100 * (e + 1), "pool_only", gid, 0, 0, 0,
                            1.5, 10, 1.0, 1.5, 0.005, k, 0])
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3b_index_jaccard"]["mean"] == pytest.approx(0.0)
    assert rep["f3a_cross_arm"]["ratio_mean"] == pytest.approx(1.6)
    assert rc == 0 and rep["verdict"] == "PASS"


# ─────────────────────── A4：F3a′ 同池反事实键对比（三态） ───────────────────────
def test_a4_f3a_prime_pool_missing_fails(tmp_path):
    """A4 §2.1/§2.5 负对照：trace 无 pool_only 行（未开 trace_pool）⇒ F3a′ FAIL
    （reason=pool_missing）——「正式批判读的 trace 必须带池行」折进硬门，不是可忘的旗标。"""
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace_no_pool(gt, [(5, 0), (5, 0)])
    _write_trace_no_pool(st, [(5, 0), (5, 0)], sparsity=1.3)
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3a_prime"]["reason"] == "pool_missing"
    assert rep["f3a_prime"]["ok"] is False
    assert rep["f3a_prime_ok"] is False
    assert rep["verdict"] == "FAIL" and rc == 1
    assert "pool_missing" in (tmp_path / "g.md").read_text()


def test_a4_f3a_prime_passes_with_pool_gradient(tmp_path):
    """A4 正向：S 臂池内有 s 梯度 ⇒ F3a′ = sel(1.3)/pool(1.0) = 1.3 ≥ 1.15 且 100% > 1.10 ⇒ 过门；
    同时输出跨臂报告项与池基线报告项。"""
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 2), (5, 2)], sparsity=1.0)
    _write_trace(st, [(5, 5), (5, 5)], sparsity=1.0, pool_sparsity=1.6)
    out = tmp_path / "gate.json"
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    fp = rep["f3a_prime"]
    assert fp["reason"] == "" and fp["ok"] is True
    assert fp["f3a_prime_mean"] == pytest.approx(1.6)
    assert fp["f3a_prime_share_above"] == pytest.approx(1.0)
    assert fp["n_events"] == 2 and fp["n_pool_only_rows"] == 10
    # 报告项必须存在（A4 §2.2/§2.4）
    assert rep["f3a_cross_arm"]["ratio_mean"] == pytest.approx(1.6)
    assert rep["pool_baseline_ratio"]["n_events"] == 2
    assert rep["verdict"] == "PASS" and rc == 0


def test_a4_f3a_prime_insufficient_events_fails(tmp_path):
    """A4 反退化守卫：有效事件 < max(3, ⌈N_plan/2⌉) ⇒ FAIL（reason=insufficient_events）。"""
    plan = [5, 5, 5, 5, 5, 5]          # N_plan=6 ⇒ need = 3
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 1), (5, 1)], sparsity=1.0)                  # 只 2 个事件
    _write_trace(st, [(5, 1), (5, 1)], sparsity=1.0, pool_sparsity=1.6)
    out = tmp_path / "gate.json"
    gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
               "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f3a_prime"]["reason"] == "insufficient_events"
    assert rep["f3a_prime"]["ok"] is False
    assert rep["verdict"] == "FAIL"


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
            for j in range(k):                      # sel 族：低 g / 高 s（γ=1 选中）
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            1.0, 10, 1.6, 1.0, 0.005, k, 0])
            for j in range(k):                      # pool 族：高 g / 低 s（γ=0 选中）
                gid += 1
                w.writerow([e, 100 * (e + 1), "pool_only", gid, 0, 0, 0,
                            1.5, 10, 1.0, 1.5, 0.005, k, 0])
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
                            1.0, 10, 1.6, 1.0, 0.005, k, 0])
            for j in range(k):
                gid += 1
                w.writerow([e, 100 * (e + 1), "pool_only", gid, 0, 0, 0,
                            1.5, 10, 1.0, 1.5, 0.005, k, 0])
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
    mkplan.main(["--trace", str(p), "--out", str(out), "--n-plan", "2", "--n-init", "1"])
    plan = json.loads(out.read_text())
    assert plan["k"] == [3, 4] and plan["sum_k"] == 7 and plan["n_plan"] == 2
    assert plan["overflow_dose"] == 0
    assert plan["n_init"] == 1, "A4 契约：站点切分必须冻进计划"
    assert plan["source"]["n_events_in_trace"] == 3, "原始事件数必须留痕"
    with pytest.raises(ValueError):
        mkplan.main(["--trace", str(p), "--out", str(out), "--n-plan", "9",
                     "--n-init", "1"])
    # A4：缺 --n-init 必须报错（不许静默默认）
    with pytest.raises(ValueError):
        mkplan.main(["--trace", str(p), "--out", str(out)])


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
    mkplan.main(["--trace", str(p), "--out", str(out), "--n-init", "2"])
    plan = json.loads(out.read_text())
    assert plan["protocol"] == "fdose-plan-v1"
    assert plan["k"] == [3, 4] and plan["sum_k"] == 7
    assert plan["n_init"] == 2
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
    """M8 的 F1_init/F1_map：某一整段失效不得被另一段的正常计数掩盖，且必须驱动 verdict。

    场景 A（整段错）：plan 4 事件 [5,5,5,5]、n_init=2；G 臂 init 段两个事件都少注入、
    map 段合规 ⇒ F1_init 红 / F1_map 绿。
    场景 B（整段缺失）：G 臂的 init 段事件**整段不在 trace 里** —— 合并计数
    `_check_arm` 只看出现过的行，对缺失不可见（events_with_wrong_k 为空）；分站点
    视图按**计划事件**逐个核对，把缺失记成该段的错。
    """
    plan = [5, 5, 5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan, n_init=2)
    st = tmp_path / "s.csv"
    _write_trace(st, [(5, 5)] * 4, sparsity=1.0, pool_sparsity=1.6)

    # 场景 A：init 段整段错（4 vs 5），map 段正常
    gt = tmp_path / "g.csv"
    _write_trace(gt, [(4, 0), (4, 0), (5, 0), (5, 0)])
    out = tmp_path / "gate.json"
    gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
               "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    fs = rep["f1_by_site"]
    assert fs["G"]["F1_init"]["ok"] is False and fs["G"]["F1_init"]["n_events"] == 2
    assert [e["event"] for e in fs["G"]["F1_init"]["events_with_wrong_k"]] == [0, 1]
    assert fs["G"]["F1_map"]["ok"] is True
    assert fs["S"]["ok"] is True and fs["G"]["ok"] is False
    assert rep["f1_site_ok"] is False and rep["verdict"] == "FAIL"

    # 场景 B：init 段整段缺失 —— 合并计数盲区，分站点必须接住
    gt2 = tmp_path / "g_miss.csv"
    with open(gt2, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        gid = 0
        for e in (2, 3):
            for _ in range(5):
                gid += 1
                w.writerow([e, 100 * (e + 1), "sel", gid, 0, 0, 0,
                            5e-4, 10, 1.0, 5e-4, 0.005, 5, 0])
    out2 = tmp_path / "gate_miss.json"
    gate.main(["--plan", str(plan_p), "--g", str(gt2), "--s", str(st),
               "--out-json", str(out2), "--out-md", str(tmp_path / "g2.md")])
    rep2 = json.loads(out2.read_text())
    fs2 = rep2["f1_by_site"]
    assert rep2["arms"]["G"]["events_with_wrong_k"] == [], "合并计数对缺失事件不可见"
    assert fs2["G"]["F1_init"]["ok"] is False
    miss = fs2["G"]["F1_init"]["events_with_wrong_k"]
    assert [e["event"] for e in miss] == [0, 1] and all(e.get("missing") for e in miss)
    assert fs2["G"]["F1_map"]["ok"] is True
    assert rep2["f1_site_ok"] is False and rep2["verdict"] == "FAIL"


def test_k10d_require_done_turns_missing_anchor_into_fail(tmp_path):
    """M6：加 `--require-done` 时缺 .done 锚点 ⇒ FAIL；写了 finished_rc0=yes ⇒ 恢复 PASS。

    没有这条，「runner 用 `|| true` 继续下一段」的失败臂可以带着半截 trace 通过装置门。
    """
    plan = [5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "G" / "tr.csv"; st = tmp_path / "S" / "tr.csv"
    _write_trace(gt, [(5, 0), (5, 0)])
    _write_trace(st, [(5, 5), (5, 5)], sparsity=1.0, pool_sparsity=1.6)
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


def test_k10e_f5_k0_report_is_report_only(tmp_path):
    """Amendment A3：F5② 降为报告项 —— k0 跑满全事件（Σsel_k0 > ΣK_plan 是常态），
    不得因 k0 恒不等而把正确运行判死；报告字段须给出三个子读数。

    反例极性：k0 的 trace 若含 plan_overflow=1（无计划却有越界标记 = 臂配置错误）
    或 Σsel_k0 < ΣK_plan（计划与 k0 trace 不配套 = 工件错误），报告必须显红 ——
    但仍然只报不判。"""
    plan = [5, 5]                       # ΣK_plan = 10
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 0), (5, 0)])
    _write_trace(st, [(5, 5), (5, 5)], sparsity=1.0, pool_sparsity=1.6)
    out = tmp_path / "gate.json"

    # 常态：k0 跑 3 个事件（无计划 ⇒ 无越界标记），Σsel_k0 = 14 > 10
    k0t = tmp_path / "k0.csv"
    _write_trace(k0t, [(5, 0), (5, 0), (4, 0)])
    rc = gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
                    "--k0", str(k0t),
                    "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    k0r = rep["f5_k0_report"]
    assert k0r["sum_sel_k0"] == 14 and k0r["sum_plan"] == 10
    assert k0r["ge_plan_ok"] is True and k0r["no_overflow_flag_ok"] is True
    assert k0r["overflow_flag_wrong_inert"] == 1     # 事件 2 的 G/S 语义判错，保留不判
    assert rep["verdict"] == "PASS" and rc == 0, "k0 Σsel 不等不得影响 verdict"

    # 反例 1：k0 带越界标记 ⇒ no_overflow_flag_ok 翻红，仍不判死
    k0bad = tmp_path / "k0_flag.csv"
    _write_trace(k0bad, [(5, 0), (5, 0)], overflow_events=(1,))
    gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
               "--k0", str(k0bad),
               "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f5_k0_report"]["no_overflow_flag_ok"] is False
    assert rep["verdict"] == "PASS"

    # 反例 2：Σsel_k0 < ΣK_plan ⇒ ge_plan_ok 翻红（计划与 k0 不配套），仍不判死
    k0short = tmp_path / "k0_short.csv"
    _write_trace(k0short, [(2, 0), (2, 0)])
    gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
               "--k0", str(k0short),
               "--out-json", str(out), "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f5_k0_report"]["ge_plan_ok"] is False
    assert rep["verdict"] == "PASS"

    # 不给 --k0 ⇒ 报告字段为 None，其余照常
    gate.main(["--plan", str(plan_p), "--g", str(gt), "--s", str(st),
               "--out-json", str(out),
               "--out-md", str(tmp_path / "g.md")])
    rep = json.loads(out.read_text())
    assert rep["f5_k0_report"] is None and rep["verdict"] == "PASS"


# ─────────────────────── A4：n_init 单一事实源 = 计划 JSON ───────────────────────
def test_a4_n_init_contract_plan_is_single_source(tmp_path):
    """A4 契约：n_init 的默认来源是计划 JSON，不许静默默认 11（M8 教训）。

    ① 计划带 n_init、不给 --n-init ⇒ 从计划读（source=plan）；
    ② 旧版计划（无 n_init 字段）+ --n-init ⇒ 用 CLI（source=cli），兼容旧计划；
    ③ 旧版计划 + 不给 --n-init ⇒ 报错（禁止静默默认）；
    ④ 计划 n_init 与 --n-init 同给但不一致 ⇒ 报错（不许静默覆盖契约）；
    ⑤ n_init 越出计划长度 ⇒ 报错。
    """
    plan = [5, 5]
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 0), (5, 0)])
    _write_trace(st, [(5, 5), (5, 5)], sparsity=1.0, pool_sparsity=1.6)
    out = tmp_path / "gate.json"

    def run(plan_path, extra=()):
        argv = (["--plan", str(plan_path), "--g", str(gt), "--s", str(st),
                 "--out-json", str(out), "--out-md", str(tmp_path / "g.md")]
                + list(extra))
        gate.main(argv)
        return json.loads(out.read_text())

    p_ni2 = tmp_path / "plan_ni2.json"; _write_plan(p_ni2, plan, n_init=2)
    p_old = tmp_path / "plan_old.json"; _write_plan(p_old, plan, n_init=None)

    rep = run(p_ni2)
    assert rep["n_init"] == 2 and rep["n_init_source"] == "plan"
    assert rep["plan"]["n_init"] == 2 and rep["verdict"] == "PASS"

    rep = run(p_old, ["--n-init", "2"])
    assert rep["n_init"] == 2 and rep["n_init_source"] == "cli"

    with pytest.raises(SystemExit):
        run(p_old)                              # ③ 无源可用 ⇒ 拒跑
    with pytest.raises(SystemExit):
        run(p_ni2, ["--n-init", "1"])           # ④ 与计划矛盾 ⇒ 拒跑
    p_ni3 = tmp_path / "plan_ni3.json"; _write_plan(p_ni3, plan, n_init=3)
    with pytest.raises(SystemExit):
        run(p_ni3)                              # ⑤ 越出计划长度 ⇒ 拒跑


# ─────────────────────── A5：R6/R7 的机械产出（prereg §4.2「必须报」） ───────
def _write_trace_in_run(run_dir, events):
    """往 run 目录写 fdose_selection_trace.csv。events: {event: (iter, n_sel, n_pool)}；
    gauss_idx = 1000*event + 序号（两臂同构 ⇒ 池 Jaccard 可对拍）。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "fdose_selection_trace.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event", "iter", "kind", "gauss_idx", "x", "y", "z",
                    "mean_grad", "denom", "sparsity", "key", "max_scale",
                    "k_plan", "plan_overflow"])
        for e in sorted(events):
            it, n_sel, n_pool = events[e]
            idx = 1000 * e
            for _ in range(n_sel):
                idx += 1
                w.writerow([e, it, "sel", idx, 0, 0, 0,
                            5e-4, 10, 1.0, 5e-4, 0.005, n_sel, 0])
            for _ in range(n_pool):
                idx += 1
                w.writerow([e, it, "pool_only", idx, 0, 0, 0,
                            1.2e-4, 10, 1.0, 1.2e-4, 0.005, n_sel, 0])


def test_a4j_a4_provenance_and_per_seed_gate_metrics_in_judge(tmp_path):
    """G2 重大#2/#3：最终 judge 必须带 A4 provenance、每 seed gate 指标（F3a′/跨臂/C/A）
    与每 seed 原始 ATE；MD 与 JSON 都要有。"""
    spec = {}
    deltas = [-2.0, -2.5, -1.5]
    for i, d in enumerate(deltas):
        base = tmp_path / ("p%d" % i)
        _write_run(base / "k0", 11.0, 60000, 580)
        _write_run(base / "G", 11.0, 65000, 580)
        _write_run(base / "S", 11.0 + d, 65500, 580)
        gp = tmp_path / ("pgate%d.json" % i)
        _write_gate_json(gp, str(i), base / "G", base / "S", base / "k0")
        spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                        "S": str(base / "S"), "gate_json": str(gp),
                        "selected_role": "confirmation"}
    runs = tmp_path / "runs.json"; runs.write_text(json.dumps(spec))
    out = tmp_path / "j.json"; md = tmp_path / "j.md"
    judge.main(["--k0", spec["0"]["k0"], "--g", spec["0"]["G"], "--s", spec["0"]["S"],
                "--seed", "0", "--runs", str(runs), "--out-json", str(out),
                "--out-md", str(md)])
    rep = json.loads(out.read_text())
    prov = rep["a4_provenance"]
    assert prov["amendment"] == "P3-D2-014"
    assert prov["post_data_instrument_correction"] is True
    assert prov["thresholds"] == {"mean_min": 1.15, "event_ratio_min": 1.10,
                                  "event_share_min": 0.60}
    assert prov["thresholds_changed"] is False
    assert prov["ATE_not_used_to_choose_threshold"] is True
    for s in ("0", "1", "2"):
        gd = rep["per_seed_gate"][s]
        assert gd["gate_verdict"] == "PASS"
        assert gd["f3a_prime_mean"] == pytest.approx(1.31)
        assert gd["pool_baseline_median"] == pytest.approx(0.87)
        assert gd["f3a_cross_arm_mean"] == pytest.approx(1.13)
        # 每 seed 原始 ATE 必须自带（G2 次要#3）
        for a in ("k0", "G", "S"):
            assert rep["per_seed_arms"][s][a]["ate_cm"] is not None
            assert "run_dir" in rep["per_seed_arms"][s][a]
    text = md.read_text()
    assert "每 seed 装置门与 A4 读数" in text
    assert "每 seed 原始读数" in text
    assert "P3-D2-014" in text


def test_a4k_first_run_vs_diagnostic_rerun_is_explicit(tmp_path):
    """G2 致命项：seed0 若用诊断重跑，必须并陈首跑 vs 重跑的 ATE/Δ/方向翻转/选用理由；
    缺 first_run 元数据时也要在报告里明确「未提供」而不是假装只有一个 run。"""
    spec = {}
    for i in range(3):
        base = tmp_path / ("q%d" % i)
        _write_run(base / "k0", 11.0, 60000, 580)
        _write_run(base / "G", 11.0, 65000, 580)
        # seed0 重跑：S=12 ⇒ +1.0；seed1/2：S=11.4/11.8 ⇒ +0.4/+0.8
        _write_run(base / "S", 12.0 if i == 0 else 11.0 + 0.4 * i, 65500, 580)
        gp = tmp_path / ("qgate%d.json" % i)
        _write_gate_json(gp, str(i), base / "G", base / "S", base / "k0")
        spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                        "S": str(base / "S"), "gate_json": str(gp),
                        "selected_role": "diagnostic_rerun" if i == 0 else "confirmation"}
    # seed0 首跑：S 比 G 低 1.0（−1.0），与重跑 +1.0 相反 ⇒ 方向翻转
    first = tmp_path / "first"
    _write_run(first / "k0", 11.0, 60000, 580)
    _write_run(first / "G", 11.0, 65000, 580)
    _write_run(first / "S", 10.0, 65500, 580)
    spec["0"]["first_run"] = {"k0": str(first / "k0"), "G": str(first / "G"),
                              "S": str(first / "S")}
    spec["0"]["selection_reason"] = "trace_pool 仪器通道"
    runs = tmp_path / "runs.json"; runs.write_text(json.dumps(spec))
    out = tmp_path / "j.json"; md = tmp_path / "j.md"
    judge.main(["--k0", spec["0"]["k0"], "--g", spec["0"]["G"], "--s", spec["0"]["S"],
                "--seed", "0", "--runs", str(runs), "--out-json", str(out),
                "--out-md", str(md)])
    rep = json.loads(out.read_text())
    fv = rep["first_run_vs_diagnostic_rerun"]
    assert fv["selected_role"] == "diagnostic_rerun"
    assert fv["first_run_deltas_cm"]["S_minus_G"] == pytest.approx(-1.0)
    assert fv["rerun_deltas_cm"]["S_minus_G"] == pytest.approx(1.0)
    assert fv["direction_flip_cm"]["flipped"] is True
    assert fv["selection_reason"] == "trace_pool 仪器通道"
    text = md.read_text()
    assert "首跑 vs 诊断重跑" in text
    assert "方向翻转" in text


def test_a4l_md_per_seed_r6r7_not_only_anchor(tmp_path):
    """G2 次要：多 seed MD 必须逐 seed 展示 R6/R7 状态，不能只给 anchor。"""
    spec = {}
    for i in range(3):
        base = tmp_path / ("z%d" % i)
        _write_run(base / "k0", 11.0, 60000, 580)
        _write_run(base / "G", 11.0, 65000, 580)
        _write_run(base / "S", 10.5, 65500, 580)
        _write_trace_in_run(base / "G", {0: (100, 6, 4), 1: (200, 5, 3)})
        _write_trace_in_run(base / "S", {0: (250, 7, 5), 1: (350, 5, 3)})
        gp = tmp_path / ("zgate%d.json" % i)
        _write_gate_json(gp, str(i), base / "G", base / "S", base / "k0")
        spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                        "S": str(base / "S"), "gate_json": str(gp)}
    runs = tmp_path / "runs.json"; runs.write_text(json.dumps(spec))
    md = tmp_path / "j.md"
    judge.main(["--k0", spec["0"]["k0"], "--g", spec["0"]["G"], "--s", spec["0"]["S"],
                "--seed", "0", "--runs", str(runs), "--out-json", str(tmp_path / "j.json"),
                "--out-md", str(md)])
    text = md.read_text()
    sec = text.split("## 每 seed R6/R7")[1] if "## 每 seed R6/R7" in text else ""
    assert sec, "MD 缺逐 seed R6/R7 小节"
    # 三个 seed 都要出现在该小节（逐 seed 而非仅 anchor）
    for s in ("0", "1", "2"):
        assert ("| %s |" % s) in sec


def test_a5_r6_r7_report_items(tmp_path):
    """A5：R6/R7 必须由判据机产出，缺 trace 必须显式 missing（M3 类：不许静默消失）。

    R6：事件 0 池 G=10 / S=12 ⇒ 相对差 +0.2；事件 1 池相等 ⇒ 0；中位 0.1。
    R7：S 的 iter 整体慢 150（> 事件间隔中位 100）⇒ 触发「剂量按数量相等，
    不按地图时刻相等」，且该句必须进 caveats。
    """
    base = tmp_path / "runs"
    _write_run(base / "k0", 11.0, 60000, 580)
    _write_run(base / "G", 11.0, 65000, 580)
    _write_run(base / "S", 10.8, 65500, 580)
    _write_trace_in_run(base / "G", {0: (100, 6, 4), 1: (200, 5, 3)})
    _write_trace_in_run(base / "S", {0: (250, 7, 5), 1: (350, 5, 3)})
    rc = judge.main(["--k0", str(base / "k0"), "--g", str(base / "G"),
                     "--s", str(base / "S"), "--seed", "0",
                     "--out-json", str(tmp_path / "j.json"),
                     "--out-md", str(tmp_path / "j.md")])
    assert rc == 0
    rep = json.loads((tmp_path / "j.json").read_text())
    assert rep["R6R7_status"] == "ok"
    r6, r7 = rep["R6_pool_drift"], rep["R7_ordinal_time_shift"]
    assert r6["n_common_events"] == 2
    assert r6["pool_rel_diff_median"] == pytest.approx(0.1)
    assert 0.0 < r6["pool_jaccard_mean"] <= 1.0
    assert r7["iter_diff_median"] == 150 and r7["n_events_diff"] == 0
    assert r7["abs_iter_diff_p90"] == 150
    assert r7["warn_dose_by_count_not_time"] is True
    md = (tmp_path / "j.md").read_text()
    assert "R6/R7 残余混杂量化" in md
    assert "剂量按数量相等" in md and any("R7 触发" in c for c in rep["caveats"])

    # 缺 trace ⇒ 显式 missing_trace（报告项缺源不许静默）
    base2 = tmp_path / "runs2"
    _write_run(base2 / "k0", 11.0, 60000, 580)
    _write_run(base2 / "G", 11.0, 65000, 580)
    _write_run(base2 / "S", 10.8, 65500, 580)
    _write_trace_in_run(base2 / "G", {0: (100, 6, 4)})   # 只有 G 有，S 缺
    judge.main(["--k0", str(base2 / "k0"), "--g", str(base2 / "G"),
                "--s", str(base2 / "S"), "--seed", "0",
                "--out-json", str(tmp_path / "j2.json"),
                "--out-md", str(tmp_path / "j2.md")])
    rep2 = json.loads((tmp_path / "j2.json").read_text())
    assert rep2["R6R7_status"] == "missing_trace"
    assert "S" in rep2["R6R7_missing_detail"]
    assert "不可算" in (tmp_path / "j2.md").read_text()


# ─────────────────────── K11：F2 的 covered 子句真的挡人（M3 次要） ───
def test_k11_short_arm_fails_f2(tmp_path):
    """短触发的臂（事件数 < N_plan）必须 FAIL —— 原 `covered >= min(len(plan_k),1)`
    形同虚设，只要 1 个事件就过。"""
    plan = [5, 5, 5]
    plan_p = tmp_path / "plan.json"; _write_plan(plan_p, plan)
    gt = tmp_path / "g.csv"; st = tmp_path / "s.csv"
    _write_trace(gt, [(5, 0)] * 3, sparsity=1.0)
    _write_trace(st, [(5, 5)] * 2, sparsity=1.0, pool_sparsity=1.6)   # 只跑了 2 个事件
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
    _write_trace(st, [(5, 5)] * 2, sparsity=1.0, pool_sparsity=1.6)
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
    """Δ 必须由 run 目录机算：给 [k0=11, G=11, S=9] ⇒ Δ = −2.0（不是手填值）。
    A4 起多 seed 清单必须带 gate（每 seed 一份），本夹具合成 gate。"""
    spec = {}
    for i in range(3):
        base = tmp_path / ("y%d" % i)
        _write_run(base / "k0", 11.0, 60000, 580)
        _write_run(base / "G", 11.0, 65000, 580)
        _write_run(base / "S", 9.0, 65500, 580)
        gate_p = tmp_path / ("ygate%d.json" % i)
        _write_gate_json(gate_p, str(i), base / "G", base / "S", base / "k0")
        spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                        "S": str(base / "S"), "gate_json": str(gate_p)}
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps(spec))
    out = tmp_path / "j.json"
    judge.main(["--k0", str(tmp_path / "y0/k0"), "--g", str(tmp_path / "y0/G"),
                "--s", str(tmp_path / "y0/S"), "--seed", "0",
                "--runs", str(runs), "--out-json", str(out)])
    rep = json.loads(out.read_text())
    assert rep["seed_deltas_cm"] == [pytest.approx(-2.0)] * 3
    assert rep["mde"]["n_seed"] == 3


def test_a4g_gate_artifact_is_required_and_verified(tmp_path):
    """G2 重大#2/#3 的机械护栏：多 seed 判决必须绑定 gate 工件，且 gate 必须与
    manifest 选定 run 一致、verdict=PASS；任一不符 ⇒ rc=2，不得从 raw trace 自救。"""
    def _mk(tag):
        spec = {}
        for i in range(3):
            base = tmp_path / ("%s%d" % (tag, i))
            _write_run(base / "k0", 11.0, 60000, 580)
            _write_run(base / "G", 11.0, 65000, 580)
            _write_run(base / "S", 9.0 + i, 65500, 580)
            spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"),
                            "S": str(base / "S")}
        return spec

    # ① 缺 gate_json ⇒ rc=2
    spec = _mk("n")
    runs = tmp_path / "runs_no_gate.json"; runs.write_text(json.dumps(spec))
    rc = judge.main(["--k0", spec["0"]["k0"], "--g", spec["0"]["G"],
                     "--s", spec["0"]["S"], "--seed", "0",
                     "--runs", str(runs), "--out-json", str(tmp_path / "j1.json")])
    assert rc == 2

    # ② gate 存在但 verdict=FAIL ⇒ rc=2
    spec = _mk("f")
    for i in range(3):
        p = tmp_path / ("fgate%d.json" % i)
        _write_gate_json(p, str(i), spec[str(i)]["G"], spec[str(i)]["S"],
                         spec[str(i)]["k0"], verdict="FAIL")
        spec[str(i)]["gate_json"] = str(p)
    runs = tmp_path / "runs_fail_gate.json"; runs.write_text(json.dumps(spec))
    rc = judge.main(["--k0", spec["0"]["k0"], "--g", spec["0"]["G"],
                     "--s", spec["0"]["S"], "--seed", "0",
                     "--runs", str(runs), "--out-json", str(tmp_path / "j2.json")])
    assert rc == 2

    # ③ gate 的 source 指向别的 run ⇒ rc=2（不许拿旧 gate 配新 run）
    spec = _mk("m")
    other = tmp_path / "other_g"
    _write_run(other / "k0", 11.0, 60000, 580)
    _write_run(other / "G", 11.0, 65000, 580)
    _write_run(other / "S", 11.0, 65500, 580)
    for i in range(3):
        p = tmp_path / ("mgate%d.json" % i)
        _write_gate_json(p, str(i), other / "G", other / "S", other / "k0")
        spec[str(i)]["gate_json"] = str(p)
    runs = tmp_path / "runs_mismatch.json"; runs.write_text(json.dumps(spec))
    rc = judge.main(["--k0", spec["0"]["k0"], "--g", spec["0"]["G"],
                     "--s", spec["0"]["S"], "--seed", "0",
                     "--runs", str(runs), "--out-json", str(tmp_path / "j3.json")])
    assert rc == 2


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


# ---------------------------------------------------------------------------
# G2 2026-11-03（6-seed 判决复核）三条负对照：gate 校验分支必须"设防"
# ---------------------------------------------------------------------------
def _multi_seed_fixture(tmp_path, n=2, **gate_kw):
    """合成 n-seed manifest + 合成 gate 工件；返回 (argv, spec)。"""
    spec, out = {}, tmp_path / "j.json"
    argv = ["--k0", "", "--g", "", "--s", "", "--seed", "0", "--out-json", str(out)]
    for i in range(n):
        base = tmp_path / ("s%d" % i)
        for arm in ("k0", "G", "S"):
            _write_run(base / arm, 11.0 + 0.01 * i, 60000, 580)
        gate_p = tmp_path / ("gate_s%d.json" % i)
        _write_gate_json(gate_p, str(i), base / "G", base / "S", base / "k0", **gate_kw)
        spec[str(i)] = {"k0": str(base / "k0"), "G": str(base / "G"), "S": str(base / "S"),
                        "gate_json": str(gate_p), "selected_role": "confirmation"}
    if n == 1:
        spec["0"]
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps(spec))
    anchors = spec["0"]
    argv[1] = anchors["k0"]; argv[3] = anchors["G"]; argv[5] = anchors["S"]
    return argv + ["--runs", str(runs)], spec


def test_g2_plan_sha_tamper_is_rejected(tmp_path):
    """G2 2026-11-03 重大#1 负对照：gate 的 plan sha 被篡改 ⇒ 必须 rc=2。

    旧实现从 gate 自己读 sha 再与 gate 自己比（恒真），该测试在旧码上会 FAIL；
    现在 judge 在计划文件实体上重算，篡改值必然不等。
    """
    argv, _ = _multi_seed_fixture(tmp_path, n=2, plan_sha="0" * 64)
    assert judge.main(argv) == 2, "篡改 plan sha 必须被拒（校验不得自比）"


def test_g2_missing_plan_file_is_rejected(tmp_path):
    """计划文件缺失 ⇒ fail-closed（旧实现返回 None 后跳过校验 = fail-open）。"""
    argv, spec = _multi_seed_fixture(tmp_path, n=2)
    g = json.loads(Path(spec["0"]["gate_json"]).read_text())
    Path(g["source"]["plan"]).unlink()
    assert judge.main(argv) == 2, "计划文件不存在时不得放行"


def test_g2_done_ok_false_is_rejected(tmp_path):
    """G2 2026-11-03 次要#9：gate 的 done_ok=False（无 .done 锚点）⇒ 判决必须拒。"""
    argv, _ = _multi_seed_fixture(tmp_path, n=2, done_ok=False)
    assert judge.main(argv) == 2, "done_ok=False 的 run 不得出正式判决"


def test_g2_swapped_gate_plan_is_rejected(tmp_path):
    """换用别的 seed 的 gate（其 plan 文件与本身份不符）⇒ 必须被拒。"""
    argv, spec = _multi_seed_fixture(tmp_path, n=2)
    # 把 seed1 的 gate 覆盖成 seed0 的 gate → source 与 manifest run 不一致
    Path(spec["1"]["gate_json"]).write_text(Path(spec["0"]["gate_json"]).read_text())
    assert judge.main(argv) == 2, "gate source 与 manifest 选定 run 不一致必须被拒"
