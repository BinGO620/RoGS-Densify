"""judge_dose_oversupply 的 H1 路由单测（prereg_dose_oversupply_2026-11-07 §4）。

五条出口各一条正例 + 每序列异号「未判」的构造（不取中位假装有值）。
fixture 直接构造 judge_sequence 的输出形状（不跑 subprocess，测纯路由）。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "jdo", ROOT / "scripts/paper3_bpw/judge_dose_oversupply.py")
jdo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jdo)


def _seq(delta_a, delta_b, judged=True, gain=None):
    """构造一个序列的**摊平**形状（与 main() 的实际存储一致；
    2026-11-08 接线 bug 回归：原单测用嵌套形状，没抓到 route_h1 读法不一致）。"""
    return {"status": "ok",
            "deltas": [delta_a, delta_b],
            "same_sign": (delta_a > 0) == (delta_b > 0) if judged else False,
            "judged": judged,
            "gain_cm": gain if judged else None,
            "reasons": []}


def _per_seq(crowd, mnobox, balloon):
    return {"crowd": crowd, "mnobox": mnobox, "balloon": balloon}


def test_prediction_confirmed():
    """三序列均可判、严格同序 crowd>mnobox>balloon、crowd>0.5 ⇒ PREDICTION_CONFIRMED。"""
    per = _per_seq(_seq(-1.5, -1.2, gain=1.35),   # crowd gain 1.35
                   _seq(-0.9, -0.8, gain=0.85),   # mnobox 0.85
                   _seq(-0.6, -0.55, gain=0.575))  # balloon 0.575
    v, reasons = jdo.route_h1(per)
    assert v == "PREDICTION_CONFIRMED", reasons


def test_gain_no_predictor():
    """三序列均 >0.5 但排序错乱 ⇒ GAIN_NO_PREDICTOR（标定研究退守）。"""
    per = _per_seq(_seq(-0.6, -0.5, gain=0.55),    # crowd 最小
                   _seq(-1.0, -0.9, gain=0.95),    # mnobox 最大（错序）
                   _seq(-0.8, -0.7, gain=0.75))
    v, _ = jdo.route_h1(per)
    assert v == "GAIN_NO_PREDICTOR"


def test_sequence_dependent_unjudged():
    """crowd 可判为正、balloon 异号未判 ⇒ SEQUENCE_DEPENDENT（不取中位假装有值）。"""
    per = _per_seq(_seq(-1.5, -1.2, gain=1.35),
                   _seq(-0.8, -0.7, gain=0.75),
                   _seq(-0.3, +0.2, judged=False))
    v, reasons = jdo.route_h1(per)
    assert v == "SEQUENCE_DEPENDENT"
    assert "未判" in reasons[0]


def test_sequence_dependent_mixed_positive():
    """crowd/mnobox 正、balloon 无增益 ⇒ SEQUENCE_DEPENDENT。"""
    per = _per_seq(_seq(-1.5, -1.2, gain=1.35),
                   _seq(-0.9, -0.8, gain=0.85),
                   _seq(-0.2, -0.1, gain=0.15))
    v, _ = jdo.route_h1(per)
    assert v == "SEQUENCE_DEPENDENT"


def test_no_generalization():
    """三序列均可判但增益都 <0.5cm ⇒ NO_GENERALIZATION（prereg §4 前提：三序列均可判）。

    附带守卫：异号未判序列走 SEQUENCE_DEPENDENT，不得混入本出口
    （另一条测试 test_sequence_dependent_unjudged 已覆盖该分支）。
    """
    per = _per_seq(_seq(-0.2, -0.1, gain=0.15),
                   _seq(+0.1, -0.2, judged=False),
                   _seq(+0.4, +0.2, gain=-0.3))
    v, _ = jdo.route_h1(per)
    assert v == "SEQUENCE_DEPENDENT"   # 有未判序列 ⇒ 不满足「三序列均可判」前提
    per2 = _per_seq(_seq(-0.2, -0.1, gain=0.15),
                    _seq(-0.1, -0.05, gain=0.075),
                    _seq(+0.4, +0.2, gain=-0.3))
    v2, _ = jdo.route_h1(per2)
    assert v2 == "NO_GENERALIZATION"


def test_invalid_blocks_everything():
    """任一序列 INVALID ⇒ INSTRUMENT_INVALID（硬门优先，不判效应）。"""
    per = _per_seq({"status": "invalid", "reasons": ["缺 run"]},
                   _seq(-0.9, -0.8, gain=0.85),
                   _seq(-0.6, -0.55, gain=0.575))
    v, _ = jdo.route_h1(per)
    assert v == "INSTRUMENT_INVALID"


def test_unjudged_not_smuggled_as_median():
    """异号序列的 gain 必须是 None（judged=False），路由不得偷用中位数。"""
    per = _per_seq(_seq(-1.5, +1.2, judged=False),  # 异号
                   _seq(-0.8, -0.7, gain=0.75),
                   _seq(-0.6, -0.55, gain=0.575))
    v, reasons = jdo.route_h1(per)
    assert per["crowd"]["gain_cm"] is None
    assert v == "SEQUENCE_DEPENDENT" and "未判" in reasons[0]
