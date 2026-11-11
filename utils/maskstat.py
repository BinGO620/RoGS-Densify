"""MaskStat — 动态占比加权的致密化统计（论文 3 机制，账本 P3-D2-016）。

问题：MonoGS 原版 ADC 的致密化统计（``xyz_gradient_accum / denom``）把全部像素的
屏幕空间梯度计入 —— 动态物体（人）剪影处的巨大光度残差直接污染统计，剪影上的
高斯被持续 clone/split（幽灵致密化）。

机制（prereg_maskstat_2026-11-04 §0 + Amendment A1）：每个视角对统计的贡献按该
视角静态像素占比 ``w = 1 - dynamic_ratio`` 加权：

    xyz_gradient_accum[update_filter] += w * grad_norm
    denom[update_filter]              += w

``w = 1`` 视角 ⇒ 与基线逐位一致；全动态视角 ``w = 0`` ⇒ 零贡献。**无阈值参数**。

口径（Amendment A1，2026-11-04 冒烟发现后收口）：
- **机制掩码自持**：本模块直接调 ``compute_semantic_dynamic_mask``（内部无 enabled
  门），参数读 ``Mapping.maskstat_*`` 自持块，**不设也不读** ``SemanticMask.enabled``
  —— 该标志另有 ≥5 处既有消费者（前端插入门控等，smoke 实测 frame 0 "person px
  zeroed"），把它当惰性开关会破坏单变量（off 臂混入他族机制行为）。
- off 臂 config **不含任何语义掩码段** ⇒ 与标准基线逐位一致。
- 判决（ATE/剂量）不消费掩码 ⇒ 不触碰 DISCIPLINE「测量口径」#3 仪器单源约束。
- loss / 优化器 / 剂量通路零改动。
- fail-closed：maskstat 开而掩码计算路径不可用（无图像 / 模型加载失败）⇒
  RuntimeError，不静默按 w=1 退化（DISCIPLINE「组件生效验证」#9）。
  例外语义：掩码占比超 ``max_mask_ratio`` 被安全阀压成 None ⇒ 机制含义就是
  "该视角几乎无静态证据"，取 w=0 并在 trace 记 ratio=None（非退化路径）。
"""

from __future__ import annotations

import os

import torch

from utils.semantic_mask import compute_semantic_dynamic_mask


def maskstat_active(config) -> bool:
    """`Mapping.maskstat_dens_stats` 缺省/false ⇒ False（默认关，主线逐位不变）。"""
    return bool(config.get("Mapping", {}).get("maskstat_dens_stats", False))


def _maskstat_model_cfg(config) -> dict:
    """把 MaskStat 自持参数块折成 compute_semantic_dynamic_mask 需要的形状。

    只读 ``Mapping.maskstat_*``；**永不**读 ``SemanticMask``（Amendment A1）。
    """
    mp = config.get("Mapping", {})
    return {
        "SemanticMask": {
            "model": mp.get("maskstat_model", "maskrcnn"),
            "dynamic_classes": mp.get("maskstat_dynamic_classes", [1]),
            "dilate_px": mp.get("maskstat_dilate_px", 5),
            "max_mask_ratio": mp.get("maskstat_max_mask_ratio", 0.95),
            "conf_threshold": mp.get("maskstat_conf_threshold", 0.5),
            "mask_threshold": mp.get("maskstat_mask_threshold", 0.5),
        }
    }


def static_ratio_from_mask(mask) -> float | None:
    """(1,H,W) bool 动态掩码 → 静态像素占比 w ∈ [0,1]；mask 为 None ⇒ None。"""
    if mask is None:
        return None
    return float(1.0 - mask.to(torch.float32).mean().item())


def compute_stats_weight(config, viewpoint) -> tuple[float, float | None]:
    """该视角的统计权重 w 与动态占比（trace 用）；maskstat 关 ⇒ (1.0, None)。

    掩码按 viewpoint 缓存在自持属性 ``maskstat_mask``（与 semantic_mask 的
    ``dynamic_mask`` 缓存互不干扰）。fail-closed 见模块 docstring（Amendment A1）。
    """
    if not maskstat_active(config):
        return 1.0, None
    mask = getattr(viewpoint, "maskstat_mask", None)
    if mask is None:
        img = getattr(viewpoint, "original_image", None)
        if img is None:
            raise RuntimeError(
                "maskstat: 机制开但 viewpoint.original_image 不可得；"
                "禁止静默按 w=1 退化（prereg §2 G3）"
            )
        mask = compute_semantic_dynamic_mask(_maskstat_model_cfg(config), img)
        if mask is None:
            # 安全阀语义：动态占比 > max_mask_ratio ⇒ 该视角几乎无静态证据 ⇒ w=0。
            viewpoint.maskstat_mask = None
            viewpoint.maskstat_ratio = None
            return 0.0, None
        viewpoint.maskstat_mask = mask
    ratio = float(1.0 - mask.to(torch.float32).mean().item())  # w = 静态占比
    viewpoint.maskstat_ratio = ratio
    return ratio, 1.0 - ratio  # (w, 动态占比)


class MaskStatTracer:
    """机制激活证据（prereg §2 G4）：逐 mapping call 一行，run 级 CSV。

    ``<run-scoped save_dir>/maskstat_trace.csv``；默认关时从不实例化。
    """

    HEADER = (
        "phase,iteration,n_entries,mean_w,share_w_lt_1,share_w_eq_0,"
        "mean_mask_ratio\n"
    )

    def __init__(self, config):
        save_dir = config.get("Results", {}).get("save_dir")
        if not save_dir:
            raise RuntimeError("maskstat: Results.save_dir 缺失，trace 无法落盘")
        os.makedirs(save_dir, exist_ok=True)
        self.path = os.path.join(save_dir, "maskstat_trace.csv")
        if not os.path.isfile(self.path):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(self.HEADER)
        self._n_rows = 0

    def log_call(self, phase, iteration, weights, mask_ratios):
        """weights: 各 entry 的 w；mask_ratios: 各 entry 动态占比（None ⇒ 安全阀态）。"""
        n = len(weights)
        if n == 0:
            return
        ws = [float(w) for w in weights]
        rs = [float(r) for r in mask_ratios if r is not None]
        row = (
            f"{phase},{int(iteration)},{n},"
            f"{sum(ws) / n:.6f},"
            f"{sum(1 for w in ws if w < 1.0) / n:.6f},"
            f"{sum(1 for w in ws if w <= 0.0) / n:.6f},"
            f"{(sum(rs) / len(rs)) if rs else float('nan'):.6f}\n"
        )
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(row)
        self._n_rows += 1

    @property
    def n_rows(self) -> int:
        return self._n_rows
