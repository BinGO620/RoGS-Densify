"""utils/dyn_port_offline.py — DynPort-Offline：离线动态修复算子的 MapAccess 适配器（default-off）。

设计本体 = resources/notes/dynport_offline_design_2026-10-06.md；
判据本体 = results/dynport_offline/evidence/prereg_dynport_offline_L1.md（账本 D1-033 立项）。

与在线版（`utils/dyn_port_online.py`）的关系：
- **决策核同型**：都复用 `utils.dyn_port_buffer.DynPortBuffer`（Case1 KNN 复用 / Case2 新建 /
  Cond1 可观测删 / Cond2 寿命删）。本模块只把 MapAccess 协议实现在**算子自持的张量字典**上
  （离线无共享 GaussianModel 的动态行；底图 PLA 载入后 lineage 全 UNTRACKED）。
- **渲染**：动态层与静态底图经 `PackedPC`（探针的只读组合视图）合并渲染 ⇒ 核心代码零改动。
- **冻结静态**：拟合只对动态层参数组跑 Adam（静态底图张量不在优化器里 ⇒ 逐位不动）。

default-off 语义（J9）：`enabled=False` 时本模块不产生任何修复（驱动层直接复制底图 PLY）。
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import torch

from utils.dyn_port_buffer import DynPortBuffer, dynport_cfg

# 动态层参数键（与 dyn_probe.make_dynamic / dyn_tensors 逐键一致）
DYN_KEYS = ("xyz", "log_scale", "rot", "opa", "dc")


class OfflineDynMap:
    """MapAccess 协议在**算子自持张量字典**上的实现（离线用）。

    - 动态层 = self.d：{key: nn.Parameter, "rest": Tensor, "K": int}（raw 参数空间，可微）；
    - lineage 记账与在线同（`lineage_base` 起连续分配）；
    - 插入走注入的 `new_gaussian_fn(points, colors)`（默认 = 仓库 `_gaussians_from_points`
      约定；单测可注入 CPU 桩，避免 GPU 依赖）。
    """

    def __init__(self, new_gaussian_fn: Callable[[np.ndarray, np.ndarray], dict],
                 lineage_base: int):
        self._new_fn = new_gaussian_fn
        self.lineage_base = int(lineage_base)
        self.d: Optional[dict] = None
        self._lin = np.empty((0,), dtype=np.int32)   # 逐基元 lineage（与 d 平行）

    # -- MapAccess 协议 --
    @property
    def n(self) -> int:
        return 0 if self.d is None else int(self.d["xyz"].shape[0])

    def dyn_indices(self, lineage_ids):
        want = set(int(x) for x in lineage_ids)
        if not want or self._lin.size == 0:
            return np.empty((0,), dtype=np.int64)
        return np.nonzero(np.isin(self._lin, np.fromiter(want, dtype=np.int32, count=len(want))))[0] \
            .astype(np.int64)

    def lineage_of(self, idx):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.size == 0:
            return np.empty((0,), dtype=np.int32)
        return self._lin[idx].astype(np.int32)

    def world_points(self, idx):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.size == 0 or self.d is None:
            return np.empty((0, 3), dtype=np.float32)
        return self.d["xyz"].detach().cpu().numpy()[idx].astype(np.float32)

    def move(self, idx, new_xyz):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.size == 0 or self.d is None:
            return
        with torch.no_grad():
            t = torch.as_tensor(np.asarray(new_xyz, dtype=np.float32),
                                device=self.d["xyz"].device)
            self.d["xyz"].data[idx] = t

    def insert(self, world, colors, lineage_id):
        world = np.asarray(world, dtype=np.float32).reshape(-1, 3)
        cols = np.asarray(colors, dtype=np.float32).reshape(-1, 3)
        if world.shape[0] == 0:
            return np.empty((0,), dtype=np.int64)
        newd = self._new_fn(world, cols)
        n_new = int(newd["xyz"].shape[0])
        if n_new == 0:
            return np.empty((0,), dtype=np.int64)
        prev = self.n
        if self.d is None:
            self.d = newd
        else:
            for k in DYN_KEYS:
                self.d[k] = torch.nn.Parameter(torch.cat([self.d[k].detach(),
                                                          newd[k].detach()], 0))
            self.d["rest"] = torch.cat([self.d["rest"], newd["rest"]], 0)
            self.d["K"] = self.d["K"]     # 必须保留（缺 K ⇒ 渲染/拼接 KeyError，探针远程事故先例）
        self._lin = np.concatenate([self._lin,
                                    np.full(n_new, int(lineage_id), dtype=np.int32)])
        return np.arange(prev, prev + n_new, dtype=np.int64)

    def delete(self, idx):
        idx = np.asarray(idx, dtype=np.int64)
        if idx.size == 0 or self.d is None:
            return
        keep = np.ones(self.n, dtype=bool)
        keep[idx] = False
        kt = torch.as_tensor(keep, device=self.d["xyz"].device)
        for k in DYN_KEYS:
            self.d[k] = torch.nn.Parameter(self.d[k].detach()[kt].clone())
        self.d["rest"] = self.d["rest"][kt]
        self.d["K"] = self.d["K"]
        self._lin = self._lin[keep]


def build_offline_map(model, lineage_base: int,
                      min_scale=None, max_scale=None) -> OfflineDynMap:
    """默认 `new_gaussian_fn` = 仓库自身插入约定（`_gaussians_from_points`）。

    与在线 `GaussianModelMap.insert` 同约定（KNN 尺度 + RGB2SH + 反 sigmoid(0.5) 不透明度）。
    """
    point_size = float(model.config["Dataset"]["point_size"])

    def _new_gaussian_fn(points, colors):
        import torch.nn as nn
        dev = model.get_xyz.device if hasattr(model, "get_xyz") else "cuda"
        pts = torch.as_tensor(np.asarray(points, dtype=np.float32), device=dev)
        cols = torch.as_tensor(np.asarray(colors, dtype=np.float32), device=dev)
        xyz, feats, log_scales, rots, opa = model._gaussians_from_points(
            pts, cols, point_size, min_gaussian_scale=min_scale, max_gaussian_scale=max_scale)
        K = feats.shape[2]
        dc = feats[:, :, 0:1].transpose(1, 2).contiguous()
        rest = feats[:, :, 1:].transpose(1, 2).contiguous()
        return {"xyz": nn.Parameter(xyz.detach().clone()),
                "log_scale": nn.Parameter(log_scales.detach().clone()),
                "rot": nn.Parameter(rots.detach().clone()),
                "opa": nn.Parameter(opa.detach().clone()),
                "dc": nn.Parameter(dc.detach().clone()),
                "rest": rest.detach(), "K": int(K)}

    return OfflineDynMap(_new_gaussian_fn, lineage_base)


def make_core(cfg: dict, offline_map: OfflineDynMap) -> DynPortBuffer:
    """决策核（与在线同型）绑定到离线 MapAccess。"""
    return DynPortBuffer(cfg, offline_map)


def repair_enabled(config: dict) -> bool:
    """离线算子开关（default-off ⇒ 驱动层不产生修复，输出 = 输入底图逐位一致，J9）。"""
    return bool(dynport_cfg(config).get("enabled", False))
