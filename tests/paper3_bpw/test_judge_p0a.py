#!/usr/bin/env python
"""test_judge_p0a.py — P0-A′ 判据机的门禁（阳性 + 阴性对照）

判据单一事实源 = `paper3/PREREGISTRATION.md` §3.1（逐事件口径）。
本测试守护三件事，用**合成 run 目录**钉住极性（不依赖盘上真实 run，避免
"跑完才知道判据机对不对"）：

  T1 阳性对照：三臂首事件 k 相同 + 全事件序列相同 ⇒ 判据机报「首事件相等」且
     「budget 不等事件数 = 0」。
  T2 阴性对照（首事件不等）：把 negctl 首事件 budget 改大 1 ⇒ 判据机必须报
     不相等。若这条能过而 T1 也过，说明判据机不是恒真/恒假。
  T3 阴性对照（后续事件不等）：只改 negctl 的第 2 个事件 ⇒ 首事件仍报相等、
     但「budget 不等事件数」必须 > 0 —— 这是把「首事件」与「逐事件」分开报的
     关键：两个读数不得互相冒充。

另加 T4：console.log 解析必须认得 rich 吃掉 `[bpw]` 前缀后的行形
（`MonoGS:  iter=1 pool=... budget=...`），并忽略 `:map` 诊断行。

用法：/data/conda_envs/monogs-ours/bin/python -m pytest tests/paper3_bpw -v
"""
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "judge_p0a", REPO / "scripts" / "paper3_bpw" / "judge_p0a.py"
)
jp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jp)


EFFICIENCY_HEADER = "status,num_frames,num_gaussians\n"
TRACKING_HEADER = "status,ate_rmse_cm\n"


def _make_run(root: Path, budgets, pools=None, gauss=20000, ate=1.0, frames=439):
    """构造一个最小 run 目录：console.log + tracking_raw.csv + efficiency_raw.csv。"""
    root.mkdir(parents=True, exist_ok=True)
    pools = pools if pools is not None else [b * 2 for b in budgets]
    lines = []
    for i, (budget, pool) in enumerate(zip(budgets, pools)):
        it = 1 + 100 * i
        lines.append(
            f"MonoGS:  iter={it} pool={pool} budget={budget} "
            f"accepted={min(budget, pool)} mean_p=99.50 fallback=0\n"
        )
        # selector 的另一条诊断行，必须以 [seldens] 之外的形式存在、不得被解析成事件
        lines.append(f"MonoGS: :map iter={it} n=20000 mean_static_prob=0.700\n")
    (root / "console.log").write_text("".join(lines))
    (root / "efficiency_raw.csv").write_text(
        EFFICIENCY_HEADER + f"OK,{frames},{gauss}\n"
    )
    (root / "tracking_raw.csv").write_text(TRACKING_HEADER + f"OK,{ate}\n")
    return root


def _judge(tmp_path, on_budgets, nc_budgets, off_budgets=(100, 200)):
    off = _make_run(tmp_path / "off", list(off_budgets), gauss=19000, ate=1.10)
    on = _make_run(tmp_path / "on", list(on_budgets), gauss=20000, ate=1.00)
    nc = _make_run(tmp_path / "negctl", list(nc_budgets), gauss=20100, ate=1.05)
    arms = {}
    for arm, run in (("off", off), ("on", on), ("negctl", nc)):
        arms[arm] = jp.summarize_arm(arm, run)
    cmp = jp.compare(arms["on"], arms["negctl"])
    first = arms["on"]["events"][0]["budget"] == arms["negctl"]["events"][0]["budget"]
    return arms, first, cmp


def test_t1_positive_control_identical_series(tmp_path):
    _, first, cmp = _judge(tmp_path, [2187, 1972, 1140], [2187, 1972, 1140])
    assert first is True, "首事件 k 相同时判据机应报相等"
    assert cmp["n_budget_mismatch"] == 0, "同序列不应报事件不等"
    assert cmp["shared_iters"] == 3


def test_t2_negative_control_first_event_differs(tmp_path):
    _, first, cmp = _judge(tmp_path, [2187, 1972, 1140], [2188, 1972, 1140])
    assert first is False, "首事件差 1 必须被判为不相等（判据机不得恒真）"
    assert cmp["n_budget_mismatch"] == 1


def test_t3_negative_control_later_event_differs(tmp_path):
    _, first, cmp = _judge(tmp_path, [2187, 1972, 1140], [2187, 1975, 1140])
    assert first is True, "首事件仍相等时不得被后续分叉污染"
    assert cmp["n_budget_mismatch"] == 1, "后续分叉必须单独计入逐事件读数"
    assert cmp["mismatch_rows"][0]["iter"] == 101


def test_t4_parser_ignores_diagnostic_lines_and_reads_rich_prefixed_rows(tmp_path):
    run = _make_run(tmp_path / "parse", [2187, 1972])
    events = jp.parse_events(run / "console.log")
    assert [e["iter"] for e in events] == [1, 101], "只应解析 densify 事件行"
    assert events[0]["budget"] == 2187 and events[0]["pool"] == 4374


def test_t5_selector_self_consistency_reads_accepted(tmp_path):
    arms, _, _ = _judge(tmp_path, [2187, 1972, 1140], [2187, 1972, 1140])
    for arm in ("on", "negctl"):
        for e in arms[arm]["events"]:
            assert e["accepted"] == min(e["budget"], e["pool"])


def test_t6_reference_values_are_reported_not_judged(tmp_path):
    """最终高斯数 / ATE 属报告项：判据机给出数值，但不得据此改变 P0-A′ 布尔。"""
    arms, first, _ = _judge(tmp_path, [2187], [2187])
    assert arms["on"]["num_gaussians"] == 20000
    assert arms["negctl"]["num_gaussians"] == 20100
    assert arms["on"]["ate_cm"] == pytest.approx(1.0)
    assert first is True
