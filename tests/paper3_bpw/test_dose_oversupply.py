"""剂量过供给验证批契约测试（prereg_dose_oversupply_2026-11-07）。

守护：① 四条新臂（dose_zero + 3× tau4x）与各自 off 臂的解析后配置 diff
恰为 {densify_grad_threshold, save_dir, inherit_from}（单变量，纯 grad 轴）；
② dose_zero 的阈值是**纯整数** 1000000000（PyYAML 科学计数 str 坑的回归锚）；
③ percent_dense 三臂全 0.01 不动；④ 仪器开关齐全、机制全关。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "configs/experiments/paper3_bpw"

ALLOWED = {"opt_params.densify_grad_threshold", "Results.save_dir", "inherit_from"}


def _resolved(name):
    sys.path.insert(0, str(ROOT))
    from utils.config_utils import load_config

    return load_config(str(CFG / f"{name}.yaml"))


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat(v, key))
        else:
            out[key] = v
    return out


def test_dose_zero_grad_threshold_is_plain_int():
    """PyYAML 科学计数坑回归：`1.0e9` 会被解析成 str ⇒ Tensor>=str 崩溃
    （PITFALLS 已登记，2026-11-05 divsrc 二分首冒烟 rc=1 同款）。本臂必须纯 int。"""
    c = _resolved("instrument_dose_zero_person_tracking")
    v = c["opt_params"]["densify_grad_threshold"]
    assert isinstance(v, int) and v == 1000000000, (type(v), v)


@pytest.mark.parametrize("base,arm", [
    ("instrument_maskstat_off", "instrument_dose_zero_person_tracking"),
    ("instr_off_crowd", "instrument_dose_tau4x_crowd"),
    ("instr_off_balloon", "instrument_dose_tau4x_balloon"),
    ("instr_off_moving_nonobstructing_box", "instrument_dose_tau4x_moving_nonobstructing_box"),
])
def test_arm_is_single_variable(base, arm):
    """新臂 vs off 臂：解析后 diff 恰为一个剂量键 + 两条路径键。"""
    off = _flat(_resolved(base))
    arm_cfg = _flat(_resolved(arm))
    diff = {k for k in set(off) | set(arm_cfg) if off.get(k) != arm_cfg.get(k)}
    assert diff == ALLOWED, f"{arm} 非单变量！额外差异: {sorted(diff - ALLOWED)}"


@pytest.mark.parametrize("arm,grad", [
    ("instrument_dose_zero_person_tracking", 1000000000),
    ("instrument_dose_tau4x_crowd", 0.0008),
    ("instrument_dose_tau4x_balloon", 0.0008),
    ("instrument_dose_tau4x_moving_nonobstructing_box", 0.0008),
])
def test_arm_values_and_gates(arm, grad):
    """剂量值、percent_dense 不动、仪器开关、机制全关。"""
    c = _resolved(arm)
    assert c["opt_params"]["densify_grad_threshold"] == grad
    assert c["opt_params"]["percent_dense"] == pytest.approx(0.01), \
        "percent_dense 被动过——纯 grad 轴约定破坏（P3-D2-039）"
    assert c["Training"]["single_thread"] is True
    assert c["Dataset"]["single_thread"] is True
    assert c["Rasterizer"]["deterministic_backward"] is True
    assert c["SelectiveDensification"]["enabled"] is False
    assert (c.get("Mapping") or {}).get("maskstat_dens_stats", False) is False
    assert (c.get("MissStreak") or {}).get("enabled", False) is False
    assert (c.get("E2") or {}).get("trace_events", False) is False
