"""MissStreak：连续未命中的 prune 侧机制（prereg_miss_streak_2026-11-06）。

背景（E2 实测教训）：`denom`（事件窗口内命中计数）在稳态饱和在上限（=100），
无论门槛取 8 还是 100，干预强度都 <1% ⇒ 不可用作门控信号。

`miss_streak` = 连续未命中渲染次数：动态物体离开后遗留的基元、被遮挡的背景
才会累积，是真正有区分度的「最近是否被支持」信号。

机制：`miss_streak > M` 的高斯额外进入 prune 掩码（即便 opacity 尚可）。
门 = `MissStreak.enabled`（默认 False ⇒ 零开销、逐位不变）。
"""
DEFAULTS = {
    "enabled": False,
    "max_miss_streak": 30,   # 先验锁定 M=30（≈5 个 densify 事件窗口）
}


def get_config(config):
    return config.get("MissStreak", {}) or {}


def miss_streak_active(config):
    return bool(get_config(config).get("enabled", DEFAULTS["enabled"]))


def max_miss_streak(config):
    return int(get_config(config).get("max_miss_streak", DEFAULTS["max_miss_streak"]))


def extend_prune_mask(config, gaussians, prune_mask):
    """把 miss_streak > M 的高斯并入 prune 掩码。关闭时原样返回（逐位不变）。"""
    if not miss_streak_active(config):
        return prune_mask
    ms = getattr(gaussians, "miss_streak", None)
    if ms is None:
        return prune_mask
    ms = ms.squeeze(-1)
    if ms.shape[0] != prune_mask.shape[0]:
        return prune_mask  # 防御：数量不匹配（中间发生了结构变化）
    stale = ms > float(max_miss_streak(config))
    return prune_mask | stale
