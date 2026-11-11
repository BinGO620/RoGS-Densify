"""Adaptive itr 单测（E 轴，P3-D2-045 / prereg_adaptive_itr_schedule_2026-11-08）。

守护三件事：
  ① **默认关逐位一致**：`schedule_iters` 关闭时原样返回调用方传入的 itr，
     且三参数即使写坏也不读（未启用 ⇒ 零行为、零异常）；
  ② **开启时两段式**：前 `kf_threshold` 个关键帧调用用 `itr_early`（含阈值帧），
     其后用 `itr_late`；`kf_threshold=0` 是「全 late」的合法写法；
  ③ **fail-closed**：非法参数 / 部署口径（非单线程）开启 ⇒ 报错，不静默退化
     （DISCIPLINE「组件生效验证」#9）。
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.adaptive_itr import (
    adaptive_itr_active,
    is_early,
    itr_early,
    itr_late,
    kf_threshold,
    schedule_iters,
    validate_mode,
)

ROOT = Path(__file__).resolve().parents[2]
CFG_DIR = ROOT / "configs/experiments/paper3_bpw"

ON = {
    "Mapping": {
        "adaptive_itr": {
            "enabled": True,
            "itr_early": 30,
            "itr_late": 50,
            "kf_threshold": 8,
        }
    }
}
OFF = {"Mapping": {"lifecycle_mode": "prune"}}


# ─────────────────── ① 默认关 ───────────────────
def test_default_off_passthrough():
    assert adaptive_itr_active(OFF) is False
    assert adaptive_itr_active({}) is False
    assert adaptive_itr_active({"Mapping": {"adaptive_itr": {"enabled": False}}}) is False
    # 关闭时原样返回（不是「返回 None」也不是「返回默认 50」）
    for ordinal in (1, 8, 9, 115):
        assert schedule_iters(OFF, ordinal, 150) == 150
        assert schedule_iters(OFF, ordinal, 1) == 1


def test_off_never_reads_params():
    """关闭 + 参数写坏 ⇒ 不抛异常（未启用路径零消费）。"""
    cfg = {"Mapping": {"adaptive_itr": {"enabled": False, "itr_early": "bad"}}}
    assert schedule_iters(cfg, 1, 150) == 150


# ─────────────────── ② 两段式 ───────────────────
def test_on_boundary_is_inclusive():
    assert itr_early(ON) == 30 and itr_late(ON) == 50 and kf_threshold(ON) == 8
    assert is_early(ON, 1) is True
    assert is_early(ON, 8) is True      # 「第 8 个关键帧之前（含）」= 第 8 个仍是早期
    assert is_early(ON, 9) is False
    assert schedule_iters(ON, 8, 150) == 30
    assert schedule_iters(ON, 9, 150) == 50


def test_on_ignores_default_iters():
    """开启时调用方传入的默认值（= Training.mapping_itr_num）被完全覆盖。"""
    assert schedule_iters(ON, 1, 150) == 30
    assert schedule_iters(ON, 115, 150) == 50


def test_zero_threshold_means_all_late():
    cfg = {"Mapping": {"adaptive_itr": {"enabled": True, "itr_early": 30,
                                        "itr_late": 50, "kf_threshold": 0}}}
    assert kf_threshold(cfg) == 0
    assert schedule_iters(cfg, 1, 150) == 50


def test_defaults_match_prereg():
    """未写参数时取预注册值（prereg §1：30 / 50 / 8）。"""
    cfg = {"Mapping": {"adaptive_itr": {"enabled": True}}}
    assert (itr_early(cfg), itr_late(cfg), kf_threshold(cfg)) == (30, 50, 8)


# ─────────────────── ③ fail-closed ───────────────────
@pytest.mark.parametrize("block", [
    {"itr_early": 0},
    {"itr_early": -5},
    {"itr_early": True},          # bool 不是合法正整数（int 子类陷阱）
    {"itr_early": 2.5},
    {"itr_late": 0},
    {"kf_threshold": -1},
    {"kf_threshold": "8"},
])
def test_invalid_params_raise(block):
    cfg = {"Mapping": {"adaptive_itr": {"enabled": True, **block}}}
    with pytest.raises(ValueError):
        itr_early(cfg) if "itr_early" in block else (
            itr_late(cfg) if "itr_late" in block else kf_threshold(cfg))


def test_validate_mode_fails_closed_on_async():
    with pytest.raises(ValueError, match="single_thread"):
        validate_mode(ON, single_thread=False)
    validate_mode(ON, single_thread=True)      # 仪器口径合法
    validate_mode(OFF, single_thread=False)    # 关闭时不干预


# ─────────────────── ④ 配置契约 ───────────────────
def _resolved(name):
    from utils.config_utils import load_config

    return load_config(str(CFG_DIR / f"{name}.yaml"))


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat(v, key))
        else:
            out[key] = v
    return out


ALLOWED_DIFF = {
    "Results.save_dir",
    "inherit_from",
    "Mapping.adaptive_itr.enabled",
    "Mapping.adaptive_itr.itr_early",
    "Mapping.adaptive_itr.itr_late",
    "Mapping.adaptive_itr.kf_threshold",
}


def test_arm_config_single_variable_vs_default():
    """C 臂 vs A 臂（默认 itr=150）：差异恰为 adaptive_itr 块 + 路径键。"""
    a = _flat(_resolved("instrument_person_tracking"))
    c = _flat(_resolved("adaptive_itr_person_tracking"))
    diff = {k for k in set(a) | set(c) if a.get(k) != c.get(k)}
    assert diff == ALLOWED_DIFF, f"C 臂非单变量！额外差异: {sorted(diff - ALLOWED_DIFF)}"
    assert c["Mapping.adaptive_itr.enabled"] is True
    assert c["Mapping.adaptive_itr.itr_early"] == 30
    assert c["Mapping.adaptive_itr.itr_late"] == 50
    assert c["Mapping.adaptive_itr.kf_threshold"] == 8
    # 仪器口径必须原样继承（调度的单变量前提）
    assert c["Training.single_thread"] is True
    assert c["Dataset.single_thread"] is True
    assert c["Rasterizer.deterministic_backward"] is True
    # 不得顺手开别的机制（混入即失去单变量）
    assert c["SelectiveDensification.enabled"] is False
    assert c.get("Mapping.maskstat_dens_stats", False) is False
    assert c.get("MissStreak.enabled", False) is False


def test_arm_config_file_is_thin():
    """派生文件只写 inherit_from + Mapping.adaptive_itr + Results.save_dir。"""
    raw = yaml.safe_load((CFG_DIR / "adaptive_itr_person_tracking.yaml").read_text())
    assert set(raw) <= {"inherit_from", "Mapping", "Results"}, set(raw)
    assert raw["inherit_from"].endswith("instrument_person_tracking.yaml")


def test_backend_wiring_text():
    """后端 keyframe 分支必须真调用调度器并逐调用落盘（防被删/被静默短路）。

    纯文本级断言（与 test_instrument_mode_contract 的 runner 断言同款）：
    行为面由 L1 的 M1 机制门（console 逐行核对）兜底。
    """
    txt = (ROOT / "utils/slam_backend.py").read_text()
    assert "adaptive_itr_on" in txt
    assert "schedule_iters(" in txt
    # 稳定子串（rich 会吞 `[...]`；见 PITFALLS「rich markup 吞标记」）
    assert "adaptive_itr KF#" in txt
    assert '"adaptive_itr_early_calls"' in txt
    assert '"adaptive_itr_late_calls"' in txt
