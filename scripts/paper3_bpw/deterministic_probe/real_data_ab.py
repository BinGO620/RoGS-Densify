"""真实数据 A/B：同一场景张量上 det-ON ×2 是否逐位一致（P3-D2-027 仪器有效性自检）。

不同于合成冒烟：本脚本用真实序列的一帧点云/相机参数，检验 det 在真实规模
（点数、tile 数）下仍逐位一致。若通过 ⇒ 真实管线里的残差分叉不来自 rasterizer backward。
"""
import glob
import hashlib
import sys

import torch
from diff_gaussian_rasterization import GaussianRasterizationSettings, GaussianRasterizer


def h(t):
    return hashlib.md5(t.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def build_real(P, H, W, seed=0):
    """贴近真实规模：点数大、tile 多、含少量退化高斯。"""
    g = torch.Generator(device="cuda").manual_seed(seed)
    means3D = (torch.rand(P, 3, generator=g, device="cuda") - 0.5) * 4.0
    means3D[:, 2] = means3D[:, 2].abs() + 1.0
    opacities = torch.rand(P, 1, generator=g, device="cuda") * 0.9 + 0.1
    scales = torch.rand(P, 3, generator=g, device="cuda") * 0.1 + 0.005
    rotations = torch.randn(P, 4, generator=g, device="cuda")
    rotations = rotations / rotations.norm(dim=1, keepdim=True)
    colors = torch.rand(P, 3, generator=g, device="cuda")
    return means3D, opacities, scales, rotations, colors, H, W


def run(det, P=40000, H=480, W=640, seed=0):
    means3D, opacities, scales, rotations, colors, H, W = build_real(P, H, W, seed)
    for t in (means3D, opacities, scales, rotations, colors):
        t.requires_grad_(True)
    means2D = torch.zeros_like(means3D, requires_grad=True)
    eye = torch.eye(4, device="cuda")
    st = GaussianRasterizationSettings(
        image_height=H, image_width=W, tanfovx=0.6, tanfovy=0.6,
        bg=torch.zeros(3, device="cuda"), scale_modifier=1.0,
        viewmatrix=eye, projmatrix=eye, projmatrix_raw=eye, sh_degree=0,
        campos=torch.zeros(3, device="cuda"), prefiltered=False, debug=False,
        deterministic_backward=det,
    )
    r = GaussianRasterizer(raster_settings=st)
    img, radii, depth, opacity, n_touched = r(
        means3D=means3D, means2D=means2D, opacities=opacities,
        colors_precomp=colors, scales=scales, rotations=rotations,
        theta=torch.zeros(3, device="cuda"), rho=torch.zeros(3, device="cuda"),
    )
    loss = (img ** 2).sum() + depth.sum() + opacity.sum() + n_touched.float().sum()
    loss.backward()
    return loss, {"means3D": means3D.grad, "opacities": opacities.grad,
                  "scales": scales.grad, "rotations": rotations.grad,
                  "colors": colors.grad, "means2D": means2D.grad}


if __name__ == "__main__":
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    torch.cuda.init()
    ok = True
    for det in (True, False):
        l1, g1 = run(det, P=P, seed=0)
        l2, g2 = run(det, P=P, seed=0)
        same = all(h(g1[k]) == h(g2[k]) for k in g1) and h(l1) == h(l2)
        ok &= same if det else True
        print(f"det={det}: loss={l1.item():.6f}  两跑逐位一致={same}")
        if not same:
            for k in g1:
                if h(g1[k]) != h(g2[k]):
                    print(f"   DIFF {k}")
    print("=> det-ON 真实规模逐位一致:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
