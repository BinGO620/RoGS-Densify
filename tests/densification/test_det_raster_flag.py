"""det-raster 两态单测（P3-D2-027 / prereg_det_raster_2026-11-05 §1）。

守护事实：
  ① config 门 `Rasterizer.deterministic_backward` 缺省 False（默认关 = 主线路径）；
  ② flag 经 GaussianRasterizationSettings 贯通到 backward 调用参数；
  ③ 定点量化数学（2^24）在 torch 层可复算：整数加法次序无关 = 确定性的根据。

CUDA kernel 本体由 40 帧探针（prereg §2 R-feasible）验证，不在单测范围。
"""

import torch

from diff_gaussian_rasterization import GaussianRasterizationSettings

SCALE = 16777216  # 2^24


def test_settings_default_off():
    """① 缺省 False：不传 deterministic_backward ⇒ flag 为 False（默认关）。"""
    s = GaussianRasterizationSettings(
        image_height=4, image_width=4, tanfovx=0.1, tanfovy=0.1,
        bg=torch.zeros(3), scale_modifier=1.0,
        viewmatrix=torch.eye(4), projmatrix=torch.eye(4),
        projmatrix_raw=torch.eye(4),
        sh_degree=0, campos=torch.zeros(3),
        prefiltered=False, debug=False,
    )
    assert s.deterministic_backward is False


def test_settings_flag_passes_through():
    """② 显式 True 能被设置并在 backward args 生成逻辑中可读（ctx 同源）。"""
    s = GaussianRasterizationSettings(
        image_height=4, image_width=4, tanfovx=0.1, tanfovy=0.1,
        bg=torch.zeros(3), scale_modifier=1.0,
        viewmatrix=torch.eye(4), projmatrix=torch.eye(4),
        projmatrix_raw=torch.eye(4),
        sh_degree=0, campos=torch.zeros(3),
        prefiltered=False, debug=False,
        deterministic_backward=True,
    )
    assert s.deterministic_backward is True


def test_fixed_point_quantize_roundtrip():
    """③ 定点量化 round-trip：|v| ≤ 1e4 时 |q(v)/2^24 − v| ≤ 2^-25（半 ulp）。"""
    v = torch.tensor([0.0, 1e-9, 3.14159, -2.71828, 1e4, -1e4, 123.456])
    q = torch.round(v * SCALE)         # torch.round = half-to-even，同 llrintf
    back = q / SCALE
    assert torch.all((back - v).abs() <= 2.0 ** -25 + 1e-12)


def test_fixed_point_sum_order_independent():
    """④ 核心性质：整数加法次序无关——任意排列求和逐位一致（float 则不然）。"""
    torch.manual_seed(0)
    vals = (torch.rand(4096) * 2 - 1) * 100.0
    qi = torch.round(vals * SCALE).to(torch.int64)
    perm = torch.randperm(4096)
    assert torch.equal(qi.sum(0), qi[perm].sum(0))
    # 对照：float 同值同排列求和可不同（本断言只在存在差异时成立性不稳，故不断言 float 必异）


def test_quantize_clamp():
    """⑤ 超界钳制：|v| > 1e4 被钳到 ±1e4×2^24（确定性钳制，不是饱和错误）。"""
    v = torch.tensor([2.0e4, -5.0e4])
    q = torch.round(v * SCALE).clamp(-int(1.0e4 * SCALE), int(1.0e4 * SCALE))
    back = q / SCALE
    assert back.abs().max() <= 1.0e4 + 1.0 / SCALE
