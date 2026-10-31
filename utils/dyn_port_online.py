"""utils/dyn_port_online.py — DynPort 在线 adapter + 管理器（把决策核落到真实 GaussianModel）。

设计本体 = results/dynport/evidence/{prereg,impl_design}_dynport_L1.md（账本 D2-027）。
决策核 = `utils/dyn_port_buffer.DynPortBuffer`（只依赖 MapAccess 协议）。

本模块提供 `GaussianModelMap`：实现 MapAccess 协议，把决策核的 world-point 语义桥接到
`GaussianModel` 的像素级插入 API（`insert_candidate_gaussians` + lineage + `prune_points`）。
- 世界点 insert：用**当前帧相机**把 world 点投回像素 + 传感器深度 → 复用仓库既有插入约定；
- move/delete 直接操作模型张量（lineage 过滤 / 就地替换 _xyz）。

跟踪隔离：动态基元带 lineage（`lineage_base` 起），接线层（后端 push_to_frontend）须按
`dynport_enabled` 时过滤这些 lineage ⇒ ATE 隔离"结构性"。本模块只负责登记与落图。
"""
from __future__ import annotations

import numpy as np
import torch

from utils.dyn_port_buffer import DynPortBuffer, dynport_cfg


def _to_np(x):
    if x is None:
        return None
    if hasattr(x, "detach"):
        return x.detach().cpu().numpy()
    return np.asarray(x)


class GaussianModelMap:
    """MapAccess 协议在真实 `GaussianModel` 上的实现（**在线用**）。"""

    def __init__(self, model, lineage_base: int, min_scale=None, max_scale=None):
        self.model = model
        self.lineage_base = int(lineage_base)
        self.min_scale = min_scale
        self.max_scale = max_scale
        # 步内原始下标追踪：delete 会重排模型数组，前端 occ_aware_visibility 掩码须按
        # **步初下标**同步（否则 is_keyframe 的 logical_or 尺寸脱钩崩溃，2026-10-06 冒烟实测）。
        self._orig = None            # 步初 -> 当前 的原始下标（np.int64，与模型基元数平行）
        self._orig_count = 0

    # -- 步同步（供 manager 调用）--
    def begin_step(self):
        n = int(self.model.get_xyz.shape[0])
        self._orig_count = n
        self._orig = np.arange(n, dtype=np.int64)     # 与"步初数组"平行，随增删同步

    def end_step(self):
        """返回 `(orig_map, old_count)`：
        - `orig_map`（长度 = 当前模型基元数）：orig_map[i] = 当前第 i 个基元在**步初**的下标，-1 = 本步新增；
        - `old_count` = 步初模型基元数（occ 掩码若为该长度即可按 orig_map 安全重排）。
        后端用它把 `occ_aware_visibility` 掩码重排到新长度（长度必须恒等于基元数，
        否则前端 is_keyframe 的 logical_or 尺寸脱钩崩溃；2026-10-06 冒烟实测）。"""
        m = self._orig
        if m is None:
            return np.empty(0, dtype=np.int64), int(self.model.get_xyz.shape[0])
        return m.copy(), int(self._orig_count)

    # -- 协议 --
    def dyn_indices(self, lineage_ids):
        self.model.ensure_lineage_state()
        want = torch.as_tensor(np.asarray(sorted(set(int(x) for x in lineage_ids)),
                                          dtype=np.int64), dtype=torch.int32)
        if want.numel() == 0:
            return np.empty((0,), dtype=np.int64)
        lin = self.model.lineage_id
        mask = (lin.unsqueeze(0) == want.unsqueeze(1)).any(dim=0)
        return mask.nonzero(as_tuple=False).squeeze(1).cpu().numpy().astype(np.int64)

    def world_points(self, idx):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.size == 0:
            return np.empty((0, 3), dtype=np.float32)
        t = self.model.get_xyz.detach()[torch.as_tensor(idx, dtype=torch.long,
                                                        device=self.model.get_xyz.device)]
        return t.cpu().numpy().astype(np.float32)

    def lineage_of(self, idx):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.size == 0:
            return np.empty((0,), dtype=np.int32)
        self.model.ensure_lineage_state()
        lin = self.model.lineage_id[torch.as_tensor(idx, dtype=torch.long)]
        return lin.cpu().numpy().astype(np.int32)

    def move(self, idx, new_xyz):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.size == 0:
            return
        with torch.no_grad():
            dev = self.model.get_xyz.device
            self.model._xyz.data[torch.as_tensor(idx, dtype=torch.long, device=dev)] = \
                torch.as_tensor(np.asarray(new_xyz, dtype=np.float32), device=dev)

    def insert(self, world, colors, lineage_id):
        world = np.asarray(world, dtype=np.float32).reshape(-1, 3)
        cols = np.asarray(colors, dtype=np.float32).reshape(-1, 3)
        if world.shape[0] == 0:
            return np.empty((0,), dtype=np.int64)
        px, py, d = self._project(world)
        ok = np.isfinite(d) & (d > 1e-3) & np.isfinite(px) & np.isfinite(py)
        if not bool(ok.any()):
            return np.empty((0,), dtype=np.int64)
        prev = int(self.model.get_xyz.shape[0])
        n = self.model.insert_candidate_gaussians(
            self._last_cam, px[ok], py[ok], d[ok], cols[ok],
            kf_id=int(lineage_id),
            lineage_ids=np.full(int(ok.sum()), int(lineage_id), dtype=np.int32),
            min_gaussian_scale=self.min_scale, max_gaussian_scale=self.max_scale,
        )
        n = int(n)
        # 步内下标追踪：新增条目用 -1 占位（保持 _orig 与模型数组等长）
        if self._orig is not None:
            self._orig = np.concatenate([self._orig, np.full(n, -1, dtype=np.int64)])
        return np.arange(prev, prev + n, dtype=np.int64)

    def delete(self, idx):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.size == 0:
            return
        self.model.ensure_lineage_state()
        n = int(self.model.get_xyz.shape[0])
        mask = torch.zeros(n, dtype=torch.bool)
        gi = torch.as_tensor(idx, dtype=torch.long)
        mask[gi] = True
        if self._orig is not None and self._orig.size == n:
            self._orig = np.delete(self._orig, idx)
        self.model.prune_points(mask.to(self.model.get_xyz.device))

    # -- world→pixel 桥接（插入必须走仓库像素级 API）--
    def set_camera(self, cam):
        """记录当前帧相机（insert 用）。cam = {fx,fy,cx,cy,R,T}（R,T = world2cam）。

        插入走 `insert_candidate_gaussians` ⇒ 需要 **camera 对象**（`.R/.T` 为 torch tensor；
        `getWorld2View2` 会 `translate.to(R.device)`，numpy 会崩——与 `transient_cam_from_msg` 同契约）。
        这里就地构造 SimpleNamespace（避免为一次桥接 import 整个后端模块）。
        """
        import types
        dev = self.model.get_xyz.device if hasattr(self.model, "get_xyz") else "cuda"
        c = types.SimpleNamespace()
        c.fx, c.fy, c.cx, c.cy = float(cam["fx"]), float(cam["fy"]), float(cam["cx"]), float(cam["cy"])
        c.R = torch.as_tensor(np.asarray(cam["R"]), dtype=torch.float32, device=dev)
        c.T = torch.as_tensor(np.asarray(cam["T"]), dtype=torch.float32, device=dev)
        self._last_cam = c

    def _project(self, world):
        cam = self._last_cam
        R = np.asarray(_to_np(cam.R), dtype=np.float64)
        T = np.asarray(_to_np(cam.T), dtype=np.float64)
        pc = (R @ np.asarray(world, dtype=np.float64).T).T + T.reshape(1, 3)   # world→cam
        z = pc[:, 2]
        zz = np.where(np.abs(z) < 1e-6, 1e-6, z)
        px = cam.fx * pc[:, 0] / zz + cam.cx
        py = cam.fy * pc[:, 1] / zz + cam.cy
        return px.astype(np.float32), py.astype(np.float32), z.astype(np.float32)


class DynPortManager:
    """在线管理器：持有决策核 + adapter；后端每 KF 调 `step(frame_idx, viewpoint, mask)`。

    只接收**运行期数据**（viewpoint 的传感器深度 / 在线位姿 / 运行期掩码）——不 import 探针。
    """

    def __init__(self, model, config, device=None):
        self.cfg = dynport_cfg(config)
        self.map = GaussianModelMap(model, self.cfg["lineage_base"],
                                    min_scale=float((config.get("DynPort") or {}).get("min_scale_m", 0.001)),
                                    max_scale=float((config.get("DynPort") or {}).get("max_scale_m", 0.02)))
        self.core = DynPortBuffer(self.cfg, self.map)

    def step(self, frame_idx, viewpoint, mask_np, stride=None):
        """一帧：掩码∧传感器深度 反投影为世界点 → 决策核 step。返回 log dict。"""
        depth = _to_np(getattr(viewpoint, "depth", None))
        rgb = _to_np(getattr(viewpoint, "original_image", None))
        if depth is None:
            return None
        depth = depth[0] if depth.ndim == 3 else depth
        m = np.asarray(mask_np, dtype=bool)
        m = m[0] if m.ndim == 3 else m
        R = _to_np(viewpoint.R)
        T = _to_np(viewpoint.T)
        c2w = self._c2w(R, T)
        cam = {"fx": float(viewpoint.fx), "fy": float(viewpoint.fy),
               "cx": float(viewpoint.cx), "cy": float(viewpoint.cy), "R": R, "T": T}
        self.map.set_camera(cam)
        st = int(stride if stride is not None else self.cfg["unproj_stride"])
        pts, cols, dbar = self._unproject(m, depth, rgb, c2w, cam, st)
        # C− 阴性对照：插入点沿相机系 x 横移 control_shift_m（仪器判别力锚；默认 0 = 不改）
        shift = float(self.cfg.get("control_shift_m", 0.0))
        if shift != 0.0 and pts.shape[0] > 0:
            pts = self._shift_cam_x(pts, c2w, shift)
        self.map.begin_step()                     # 记录步初下标（供 occ_aware_visibility 同步）
        rec = self.core.step(int(frame_idx), pts, cols, dbar)
        rec = dict(rec or {})
        rec["_occ_sync"] = self.map.end_step()    # (keep_mask_over_step_start, n_added)
        return rec

    @staticmethod
    def _shift_cam_x(pts_w, c2w, shift_m):
        """世界点沿相机 x 轴平移 shift_m（等价于像素平面 Δpx = fx·shift/z 的 3D 版）。"""
        w2c = np.linalg.inv(c2w)
        pc = (w2c[:3, :3] @ np.asarray(pts_w, dtype=np.float64).T).T + w2c[:3, 3]
        pc[:, 0] += float(shift_m)
        out = (c2w[:3, :3] @ pc.T).T + c2w[:3, 3]
        return out.astype(np.float32)

    @staticmethod
    def _c2w(R, T):
        m = np.eye(4)
        m[:3, :3] = np.asarray(R, dtype=np.float64)
        m[:3, 3] = np.asarray(T, dtype=np.float64)
        return np.linalg.inv(m)

    def _unproject(self, mask, depth, rgb, c2w, cam, stride):
        H, W = depth.shape
        ys, xs = np.nonzero(mask)
        if ys.size == 0:
            return np.empty((0, 3), np.float32), np.empty((0, 3), np.float32), None
        ys, xs = ys[::stride], xs[::stride]
        d = depth[ys, xs].astype(np.float64)
        ok = np.isfinite(d) & (d > 0.2) & (d < 8.0)
        ys, xs, d = ys[ok], xs[ok], d[ok]
        if ys.size == 0:
            return np.empty((0, 3), np.float32), np.empty((0, 3), np.float32), None
        xc = (xs - cam["cx"]) / cam["fx"] * d
        yc = (ys - cam["cy"]) / cam["fy"] * d
        pts_c = np.stack([xc, yc, d, np.ones_like(d)], axis=0)          # 4×N
        pts_w = (c2w @ pts_c)[:3].T.astype(np.float32)
        if rgb is not None:
            cols = rgb[:, ys, xs].T.astype(np.float32) if rgb.ndim == 3 else np.tile(rgb, (ys.size, 1))
        else:
            cols = np.ones((ys.size, 3), np.float32) * 0.5
        return pts_w, cols, float(np.mean(d))
