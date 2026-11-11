"""Adaptive itr：建图迭代步数的关键帧早期调度（E 轴，P3-D2-045）。

预注册：`paper3/results/evidence/prereg_adaptive_itr_schedule_2026-11-08.md`。

机制（最小形态，预注册写死、零在线信号读取）：按关键帧序数两段式——

    itr(call) = itr_early   若该次建图调用发生于第 kf_threshold 个关键帧之前（含）
    itr(call) = itr_late    否则

默认 `Mapping.adaptive_itr.enabled = False` ⇒ 调用方原样拿回传入的默认值，
主线逐位不变（代码保护例外流程的默认关判据）。

口径（实现注记 `impl_adaptive_itr_2026-11-09.md` §二；不改判据）：
- **序数口径 = 预注册字面**：初始化关键帧（frame 0）算第 1 个关键帧，其后每个
  `keyframe` 建图调用 +1。阈值 8 ⇒ early 覆盖 frame 0–35，正是「40 帧内 itr
  不敏感」的校准窗口（KF 模式 0/5/…/35 共 8 个）。
- **初始化预算不被覆写**：init 关键帧走 `initialize_map`（`init_itr_num`=1050，
  硬编码、B 臂同值），window 满时的 initial BA 走 `50/300`（同样硬编码）。
  二者都不在调度范围内（改它们会破坏 C vs B 的单变量，且超出校准证据覆盖）。
  序数只统计 `keyframe` 分支的建图调用。
- 部署口径（`Dataset.single_thread: false`）不注册本机制：async 的每 KF 调用
  只是自由跑循环里的一次，主优化量来自 `map(iters=1)` 的自由跑；在该口径下
  开调度属**未预注册的新实验**。故 `validate_mode` 在「开启 + 非单线程」时
  fail-closed 报错，而不是静默不生效（DISCIPLINE「组件生效验证」#9）。
"""
from __future__ import annotations

DEFAULTS = {
    "enabled": False,
    "itr_early": 30,     # 预注册值；阈值 8 的来源见 prereg §1（40 帧 = 前 8 KF）
    "itr_late": 50,
    "kf_threshold": 8,
}


def get_config(config) -> dict:
    return (config.get("Mapping", {}) or {}).get("adaptive_itr", {}) or {}


def adaptive_itr_active(config) -> bool:
    """`Mapping.adaptive_itr.enabled` 缺省/false ⇒ False（默认关，主线逐位不变）。"""
    return bool(get_config(config).get("enabled", DEFAULTS["enabled"]))


def _positive_int(block, key):
    value = block.get(key, DEFAULTS[key])
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"Mapping.adaptive_itr.{key} 必须是正整数，实际 {value!r}"
            "（prereg_adaptive_itr_schedule_2026-11-08 §1）"
        )
    return value


def itr_early(config) -> int:
    return _positive_int(get_config(config), "itr_early")


def itr_late(config) -> int:
    return _positive_int(get_config(config), "itr_late")


def kf_threshold(config) -> int:
    """允许 0（= 全部走 itr_late，退化为固定预算的显式写法）。"""
    value = get_config(config).get("kf_threshold", DEFAULTS["kf_threshold"])
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"Mapping.adaptive_itr.kf_threshold 必须是非负整数，实际 {value!r}"
            "（prereg_adaptive_itr_schedule_2026-11-08 §1）"
        )
    return value


def is_early(config, kf_ordinal: int) -> bool:
    """第 kf_ordinal 个关键帧（从 1 起）是否落在早期相位（含阈值帧）。"""
    return int(kf_ordinal) <= kf_threshold(config)


def schedule_iters(config, kf_ordinal: int, default_iters: int) -> int:
    """返回该次建图调用应使用的 itr。

    关闭时**原样返回** `default_iters`（调用方无需分支，逐位不变）；
    开启时按关键帧序数两段式取 `itr_early` / `itr_late`。
    """
    if not adaptive_itr_active(config):
        return default_iters
    return itr_early(config) if is_early(config, kf_ordinal) else itr_late(config)


def validate_mode(config, single_thread: bool) -> None:
    """fail-closed：开启但非单线程口径 ⇒ 报错，不静默不生效。

    部署口径（async）的每 KF 调用不是主优化量载体（主优化来自自由跑
    `map(iters=1)`），在该口径开调度属未预注册的新实验。
    """
    if adaptive_itr_active(config) and not single_thread:
        raise ValueError(
            "Mapping.adaptive_itr 目前只注册在仪器口径（Dataset.single_thread=true）；"
            "部署口径（async）开调度属新实验，须先新 prereg"
            "（prereg_adaptive_itr_schedule_2026-11-08 §1 实现约束）"
        )
