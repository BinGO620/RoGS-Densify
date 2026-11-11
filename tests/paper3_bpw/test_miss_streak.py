"""MissStreak 单测（prereg_miss_streak_2026-11-06）。

守护：① 默认关 ⇒ 原样返回掩码（逐位不变）；② 开时 miss_streak>M 并入掩码；
③ 长度不匹配时防御性原样返回；④ 信号语义（命中清零、未命中累加）。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch

from utils.miss_streak import extend_prune_mask, max_miss_streak, miss_streak_active


def test_default_off_passthrough():
    cfg = {"MissStreak": {"enabled": False}}
    g = SimpleNamespace(miss_streak=torch.zeros((3, 1)))
    m = torch.tensor([False, False, False])
    assert extend_prune_mask(cfg, g, m) is m
    assert miss_streak_active(cfg) is False
    assert miss_streak_active({}) is False


def test_on_extends_mask():
    cfg = {"MissStreak": {"enabled": True, "max_miss_streak": 30}}
    assert max_miss_streak(cfg) == 30
    g = SimpleNamespace(miss_streak=torch.tensor([[0.0], [30.0], [31.0], [100.0]]))
    m = torch.tensor([False, False, False, False])
    out = extend_prune_mask(cfg, g, m)
    # 严格大于 30 才裁：30 不裁、31/100 裁
    assert out.tolist() == [False, False, True, True]


def test_missing_field_passthrough():
    cfg = {"MissStreak": {"enabled": True}}
    g = SimpleNamespace()          # 无 miss_streak 字段
    m = torch.tensor([False, False])
    assert extend_prune_mask(cfg, g, m) is m


def test_length_mismatch_passthrough():
    cfg = {"MissStreak": {"enabled": True}}
    g = SimpleNamespace(miss_streak=torch.ones((5, 1)))
    m = torch.tensor([False, False])
    assert extend_prune_mask(cfg, g, m) is m


def test_streak_semantics_hit_resets_miss_accumulates():
    """信号语义：命中清零、未命中累加（用真实方法，需 cuda 则跳过）。"""
    import pytest
    torch = __import__("torch")
    if not torch.cuda.is_available():
        pytest.skip("需要 CUDA（update_miss_streak 在 cuda 上分配）")
    from gaussian_splatting.scene.gaussian_model import GaussianModel
    g = GaussianModel.__new__(GaussianModel)
    g._xyz = torch.zeros((4, 3), device="cuda")
    g.update_miss_streak(torch.tensor([True, False, True, False], device="cuda"))
    # 全部先 +1，然后命中的两个清零
    assert g.miss_streak.squeeze(-1).tolist() == [0.0, 1.0, 0.0, 1.0]
    g.update_miss_streak(torch.tensor([False, False, False, True], device="cuda"))
    assert g.miss_streak.squeeze(-1).tolist() == [1.0, 2.0, 1.0, 0.0]
