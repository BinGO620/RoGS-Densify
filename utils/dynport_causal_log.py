"""utils/dynport_causal_log.py — DynPort 因果快照记录器（D2-027；修 final-map 仪器偏置）。

**为什么需要**（prereg_dynport_L1 §10 + E2 先例 prereg_E2_online §9 2026-09-29 行）：
既有 judge/`render_compare` 渲染的是**最终地图**；对**瞬态**层结构性有偏——动态基元停在
**末帧位置**，渲染早期帧 = "把人放到他还没走到的位置"（E2n 实测该错位的签名）。DynPort 的动态层
**在共享 GaussianModel 里**（不像 E2 对象层是独立 buffer），且 `load_ply` **不持久 lineage**
⇒ 事后无法从最终 PLY 剥离动态行。故落盘两件：

  1. **每 KF 动态层快照**（`frame_<idx>.npz`）：动态行 raw 参数 + 该帧**估计位姿** c2w。
     体量小（动态层 ~5–30k 基元 × 56 B ≈ 0.3–1.7 MB/KF）。
  2. **收尾静态行掩码**（`dynamic_rows.npy`）：最终 PLY 里哪些行是动态（供评测端做**静态底图**）。

**评测端**（`judge_dynport.py --causal`）：静态底图 = 最终 PLY 去掉动态行；t 时刻地图 = 静态底图
+ 最近 ≤t 的快照动态层；用**快照位姿**渲染 ⇒ 严格因果。

**设计要点**（对齐 causal_render_log.py）：
  1. 纯序列化、零 torch；渲染由评测器做。
  2. **默认关**：`DynPort.causal_log.enabled=false` ⇒ `log_frame` 零文件零状态。
  3. **禁用 GT**：位姿只能来自调用方传入的**估计位姿**（本模块不读 groundtruth）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

DEFAULTS = {"enabled": False, "every_n": 1, "out_dir": ""}


def dynport_causal_cfg(config: dict) -> dict:
    c = dict(DEFAULTS)
    sub = (config.get("DynPort") or {}).get("causal_log")
    if isinstance(sub, dict):
        c.update({k: sub[k] for k in sub if k in c})
    if not isinstance(c["enabled"], bool):
        raise ValueError(f"DynPort.causal_log.enabled 必须是 bool，实为 {c['enabled']!r}")
    if int(c["every_n"]) < 1:
        raise ValueError(f"DynPort.causal_log.every_n 须 ≥1，实为 {c['every_n']!r}")
    return c


def to_np(x):
    if x is None:
        return None
    if hasattr(x, "detach"):
        return x.detach().cpu().numpy()
    return np.asarray(x)


class DynPortCausalWriter:
    """逐 KF 落盘**动态层**快照 + 收尾静态行掩码（默认关 ⇒ 零副作用）。"""

    def __init__(self, config: dict):
        cfg = dynport_causal_cfg(config)
        self.enabled = bool(cfg["enabled"])
        self.every_n = int(cfg["every_n"])
        od = cfg["out_dir"]
        if not od:
            save_dir = str((config.get("Results") or {}).get("save_dir", "results"))
            od = str(Path(save_dir) / "dynport_causal")
        self.out_dir = Path(od) if self.enabled else None
        self.count = 0

    def log_frame(self, frame_idx, c2w, model, active_lineages) -> bool:
        """动态层快照。关闭/非抽帧帧/无动态 ⇒ False（零副作用）。"""
        if not self.enabled:
            return False
        f = int(frame_idx)
        if f % self.every_n != 0:
            return False
        active = list(active_lineages or [])
        if not active:
            return False
        model.ensure_lineage_state()
        import torch
        lin = model.lineage_id
        want = torch.as_tensor(np.asarray(sorted(set(int(x) for x in active)), dtype=np.int64),
                               dtype=torch.int32)
        sel = (lin.unsqueeze(0) == want.unsqueeze(1)).any(dim=0)
        if not bool(sel.any()):
            return False
        c2w = np.asarray(to_np(c2w), dtype=np.float64)
        assert c2w.shape == (4, 4), f"c2w 须 4×4，实为 {c2w.shape}"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        g = lambda x: np.asarray(to_np(x)[sel.cpu().numpy()], dtype=np.float32)
        np.savez(
            self.out_dir / f"frame_{f:06d}.npz",
            frame_idx=np.int64(f), c2w=c2w,
            xyz=g(model._xyz), log_scale=g(model._scaling), rot=g(model._rotation),
            opa=g(model._opacity), f_dc=g(model._features_dc),
        )
        self.count += 1
        return True

    def save_static_mask(self, model) -> bool:
        """收尾：落盘"最终 PLY 里哪些行是动态"（评测端据此做静态底图）。"""
        if not self.enabled:
            return False
        model.ensure_lineage_state()
        base = int(getattr(model, "dyn_lineage_base", 0) or 0)
        lin = np.asarray(to_np(model.lineage_id))
        is_dyn = (lin >= base) if base > 0 else np.zeros(lin.shape[0], dtype=bool)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        np.save(self.out_dir / "dynamic_rows.npy", is_dyn.astype(bool))
        return True


def load_snapshot(path) -> dict:
    with np.load(Path(path), allow_pickle=False) as z:
        return {k: z[k] for k in z.files}
