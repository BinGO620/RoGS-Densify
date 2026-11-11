#!/usr/bin/env python
"""test_dose_response_render.py — 剂量-响应报告生成器的门禁测试（纯 CPU，合成夹具）。

守护 P3-D2-019（G2 审查）四条呈现/门类条件的对应事实：

  M1 platform 列必须真判：三个两两差**全部** < 地板才 YES；
     旧实现只判「2× 臂存在」⇒ 任意 gap 都 YES，恒真。
  M2 D1 必须带下界：三臂（或多臂）剂量几乎同值（降幅 < 3%）必须 DEVICE_FAIL，
     不允许「单调不增」平凡为真而 PASS。
  M3 帧数闸机械化：任一 run 非 580 帧必须抛 RuntimeError，不许与全长混比；
     glob 命中多个 run 目录也必须拒绝（禁隐式取末位）。
  M7 KEY_REGISTRY 登记：本族 prereg 的声明键必须能在 producer 里找到。

用法: pytest tests/paper3_bpw/test_prereg_dose_response_render.py -v
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "scripts" / "paper3_bpw"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rnd = _load("render_dose_response")


# ─────────────────────────── 夹具 ───────────────────────────
def _rows(ates, online, frames=580):
    return [
        {"tau_scale": s, "tau": s * 0.0002, "ate_cm": a,
         "status": "OK", "num_frames": f,
         "online_num_gaussians": g, "refined_num_gaussians": g}
        for s, a, g, f in zip([0.5, 1.0, 2.0, 4.0], ates, online,
                             frames if isinstance(frames, list) else [frames] * 4)
    ]


def _wide():
    """四臂：剂量跨度大（90%↓），ATE 在低剂量侧平台（2× vs 4× 差 0.05cm）。
    这是真实批的形态（seed0）。"""
    return _rows([14.3685, 9.3029, 10.5178, 10.4638],
                 [173654, 74977, 28501, 15944])


# ─────────────────────────── M1：platform 真判 ---------------

def test_m1_platform_ok_true_when_all_gaps_below_floor():
    a = rnd._seed_analysis(_wide())
    pl = a["platform"]
    assert pl is not None
    assert pl["platform_ok"] is True
    assert pl["gap_2x_4x_cm"] < rnd.FLOOR_CM


def test_m1_platform_ok_false_when_one_gap_exceeds_floor():
    """M1 负对照：2× 臂存在但 2×−1× 超过地板 ⇒ 必须 NO。
    旧实现只要 2.0 在臂集合里就写 YES（恒真），这条会红。"""
    rows = _rows([14.0, 6.0, 12.0, 12.0],
                 [173654, 74999, 28501, 15944])
    a = rnd._seed_analysis(rows)
    assert a["platform"]["gap_2x_1x_cm"] > rnd.FLOOR_CM
    assert a["platform"]["platform_ok"] is False


def test_m1_platform_ok_false_on_diagonal_trend():
    """三臂严格单调升且跨度超过地板 ⇒ 不能记平台。"""
    rows = _rows([10.0, 10.2, 12.0, 20.0],
                 [100000, 80000, 50000, 20000])
    a = rnd._seed_analysis(rows)
    assert a["platform"]["gap_2x_4x_cm"] > rnd.FLOOR_CM
    assert a["platform"]["platform_ok"] is False


# ─────────────────────────── M2：D1 下界 ---------------------

def test_m2_d1_changed_true_for_real_dose_spread():
    a = rnd._seed_analysis(_wide())
    assert a["d1_dose_monotone"] is True
    assert a["d1_total_drop_pct"] > 3.0
    assert a["d1_dose_changed"] is True


def test_m2_d1_changed_false_when_all_arms_same_dose():
    """M2 负对照：四臂终态高斯完全相同 ⇒ 单调不增平凡为真，但剂量没变，
    必须 DEVICE_FAIL。旧实现只判 monotone，会 PASS。"""
    rows = _rows([10.0, 10.1, 10.2, 10.3], [50000, 50000, 50000, 50000])
    a = rnd._seed_analysis(rows)
    assert a["d1_dose_monotone"] is True
    assert a["d1_total_drop_pct"] == 0.0
    assert a["d1_dose_changed"] is False


def test_m2_d1_changed_false_when_drop_below_floor_pct():
    """1% 的剂量抖动在 ±3% 装置带内 ⇒ 不算「真的变了」。"""
    rows = _rows([10.0, 10.0, 10.0, 10.0], [50000, 50000, 50000, 49500])
    a = rnd._seed_analysis(rows)
    assert a["d1_dose_changed"] is False


# ─────────────────────────── M3：帧数闸 ---------------------

def test_m3_assert_frames_accepts_full_length():
    assert rnd._assert_frames(580) == 580


def test_m3_assert_frames_rejects_smoke():
    """M3 负对照：40 帧冒烟不得冒充全长。"""
    with pytest.raises(RuntimeError, match="num_frames"):
        rnd._assert_frames(40)


def test_m3_assert_frames_rejects_none():
    with pytest.raises(RuntimeError):
        rnd._assert_frames(None)


# ─────────────────────────── M7：KEY_REGISTRY 登记 -----------

def test_m7_registry_has_dose_response_prereg():
    spec = importlib.util.spec_from_file_location(
        "prereg_criterion_keys", REPO / "scripts" / "02_analysis" / "prereg_criterion_keys.py")
    keys_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(keys_mod)
    key = "paper3/results/evidence/prereg_dose_response_2026-11-04.md"
    assert key in keys_mod.KEY_REGISTRY, "剂量-响应 prereg 未登记进键门（M7）"
    declared = keys_mod.KEY_REGISTRY[key]
    need = {"platform_ok", "d1_dose_changed", "d1_total_drop_pct", "num_frames"}
    got = {k for _c, (ks, _p) in declared.items() for k in ks}
    assert need <= got, f"登记键缺 {need - got}"


def test_m7_missing_key_turns_red():
    """M7 负对照：声明的键在 producer 里不存在 ⇒ 必须报缺。"""
    spec = importlib.util.spec_from_file_location(
        "prereg_criterion_keys", REPO / "scripts" / "02_analysis" / "prereg_criterion_keys.py")
    keys_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(keys_mod)
    declared = {"Cx": (["key_a", "key_b"], ["prod.py"])}
    assert keys_mod.missing_keys(declared, {"prod.py": 'res["key_a"]'}) == {"Cx": ["key_b"]}
