"""det-raster 合成冒烟（P3-D2-027 L1 前置自检，非判据件）。

目的：在真实数据探针之前，用固定合成场景验证两件事：
  (a) det-ON 同 seed ×2 ⇒ 渲染 + 全部梯度逐位一致（确定性成立）；
  (b) det-ON vs det-OFF ⇒ 语义等价（差异仅在 ~2^-24 量级的定点舍入）。

判据地位：本脚本不产生 L1 判决；L1 判据是 40 帧真实序列探针（prereg §2）。
"""
import hashlib
import sys

import torch
from diff_gaussian_rasterization import (
    GaussianRasterizationSettings,
    GaussianRasterizer,
)


def build(P=512, H=64, W=64, seed=0):
    g = torch.Generator(device="cuda").manual_seed(seed)
    torch.manual_seed(seed)
    means3D = (torch.rand(P, 3, generator=g, device="cuda") - 0.5) * 2.0
    means3D[:, 2] = means3D[:, 2].abs() + 2.0
    opacities = torch.rand(P, 1, generator=g, device="cuda") * 0.5 + 0.5
    scales = torch.rand(P, 3, generator=g, device="cuda") * 0.05 + 0.01
    rotations = torch.randn(P, 4, generator=g, device="cuda")
    rotations = rotations / rotations.norm(dim=1, keepdim=True)
    colors = torch.rand(P, 3, generator=g, device="cuda")
    view = torch.eye(4, device="cuda")
    proj = torch.eye(4, device="cuda")
    bg = torch.zeros(3, device="cuda")
    return means3D, opacities, scales, rotations, colors, view, proj, bg, H, W


def run(det, seed=0, P=512):
    means3D, opacities, scales, rotations, colors, view, proj, bg, H, W = build(P=P, seed=seed)
    means3D = means3D.clone().requires_grad_(True)
    opacities = opacities.clone().requires_grad_(True)
    scales = scales.clone().requires_grad_(True)
    rotations = rotations.clone().requires_grad_(True)
    colors = colors.clone().requires_grad_(True)
    means2D = torch.zeros_like(means3D, requires_grad=True)
    st = GaussianRasterizationSettings(
        image_height=H, image_width=W, tanfovx=0.5, tanfovy=0.5, bg=bg,
        scale_modifier=1.0, viewmatrix=view, projmatrix=proj, projmatrix_raw=proj,
        sh_degree=0, campos=torch.zeros(3, device="cuda"),
        prefiltered=False, debug=False, deterministic_backward=det,
    )
    r = GaussianRasterizer(raster_settings=st)
    img, radii, depth, opacity, n_touched = r(
        means3D=means3D, means2D=means2D, opacities=opacities,
        colors_precomp=colors, scales=scales, rotations=rotations,
        theta=torch.zeros(3, device="cuda"), rho=torch.zeros(3, device="cuda"),
    )
    loss = (img ** 2).sum() + depth.sum() + opacity.sum() + n_touched.float().sum()
    loss.backward()
    grads = {
        "means3D": means3D.grad, "opacities": opacities.grad, "scales": scales.grad,
        "rotations": rotations.grad, "colors": colors.grad, "means2D": means2D.grad,
    }
    return img, loss, grads


def h(t):
    return hashlib.md5(t.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


torch.cuda.init()
img_a, loss_a, g_a = run(det=True, seed=0)
img_b, loss_b, g_b = run(det=True, seed=0)
img_off, loss_off, g_off = run(det=False, seed=0)

print("== (a) det-ON ×2 逐位一致 ==")
ok_a = True
for name, ta, tb in [("img", img_a, img_b), ("loss", loss_a, loss_b)] + [(k, g_a[k], g_b[k]) for k in g_a]:
    same = h(ta) == h(tb)
    ok_a &= same
    print(f"  {name:10s} {'IDENTICAL' if same else 'DIFFER'}  {h(ta)[:12]} / {h(tb)[:12]}")
print("  => (a)", "PASS" if ok_a else "FAIL")

print("== (b) det-ON vs det-OFF 语义等价 ==")
rel_loss = abs(loss_a.item() - loss_off.item()) / max(abs(loss_off.item()), 1e-12)
max_rel_g = 0.0
for k in g_a:
    a, o = g_a[k].double(), g_off[k].double()
    denom = o.abs().clamp_min(1e-8)
    max_rel_g = max(max_rel_g, ((a - o).abs() / denom).max().item())
print(f"  loss det-ON={loss_a.item():.9f} det-OFF={loss_off.item():.9f} rel={rel_loss:.3e}")
print(f"  max per-elem rel grad diff = {max_rel_g:.3e}")
print("  => (b)", "PASS" if (rel_loss < 1e-5 and max_rel_g < 1e-3) else "FAIL")

sys.exit(0 if (ok_a and rel_loss < 1e-5 and max_rel_g < 1e-3) else 1)
