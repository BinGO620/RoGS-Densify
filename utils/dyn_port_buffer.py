"""utils/dyn_port_buffer.py — DynPort：在线动态 GS 管理（DynaGSLAM 式移植）。

设计本体 = results/dynport/evidence/{prereg,impl_design}_dynport_L1.md（账本 D2-027）。
默认关闭（config `DynPort.enabled=false`）：关闭时不构造任何状态，行为与主线逐位一致。

═══ 架构（2026-10-05 实装期修正，impl_design v1 §2.1 之外的新事实）═══
在线环路里 **地图是共享的 `GaussianModel`**：后端 mapping 渲染 `self.gaussians`，
前端 tracking 也渲染 `self.gaussians`（经 `push_to_frontend`→`sync_backend` 同步）。
⇒ 动态基元**必须插进 `self.gaussians` 才能被渲染**（离线探针的"独立 packed 视图"在线无对应钩子）。
本模块因此设计为 **map-access 抽象**：

  - 纯决策核 `DynPortBuffer` 只依赖一个 `MapAccess` 协议（见下），**不 import 探针/不持有 run**；
  - 单元测试用 `FakeMap`（CPU）实现协议；
  - 在线由后端 adapter（`GaussianModelMap`，后续 step）实现协议，把决策落到真实模型。

**跟踪隔离（prereg §1 / gap #14）**：动态基元插进共享模型后会被同步到前端 ⇒ **必须**在
`push_to_frontend` 里按 lineage 过滤以保 ATE 隔离（"结构性"而非"声称"）。本模块只负责
**登记 lineage**（`active_lineages()`），过滤在接线层做；**若接线层不做过滤 ⇒ 删去"ATE 隔离"主张**
（E2 先例 `prereg_E2_online.md` §2-D 同款纪律）。

═══ 与离线探针 `dyn_probe.DynPortBuffer` 的区别（"探针≠在线"）═══
探针用 GT 深度 / trj_est 离线位姿 / canonical 掩码 + packed 渲染视图；本类只接收**运行期数据**
（世界点云 = 运行期掩码 ∧ 传感器深度反投影、在线位姿；`dbar` = 传感器深度均值），经 MapAccess 落图。
"""
from __future__ import annotations

from typing import Protocol

import numpy as np

UNTRACKED = -1


# ── config 开关三件套（仿 utils/semantic_mask.py:75-85）────────────────────────

def get_dynport_config(config) -> dict:
    return (config or {}).get("DynPort", {}) or {}


def dynport_enabled(config) -> bool:
    return bool(get_dynport_config(config).get("enabled", False))


def dynport_cfg(config) -> dict:
    """填默认值的 config 快照（超参先锁见 prereg §1；键名统一 unproj_stride）。"""
    c = dict(get_dynport_config(config))
    return {
        "enabled": bool(c.get("enabled", False)),
        "lam_d": float(c.get("lam_d", 0.05)),
        "cap": int(c.get("cap", 50000)),
        "lmax": int(c.get("lmax", 45)),
        "unproj_stride": int(c.get("unproj_stride", 3)),
        "fit_iters": int(c.get("fit_iters", 300)),
        "lineage_base": int(c.get("lineage_base", 900000)),
        "control_shift_m": float(c.get("control_shift_m", 0.0)),
    }


# ── map-access 协议（决策核只依赖它；在线 adapter / 测试 FakeMap 各实现一份）────

class MapAccess(Protocol):
    """DynPort 决策核所需的最小地图接口。索引 `idx` 是**全局基元下标**（稳定，直至下次删改）。"""

    def dyn_indices(self, lineage_ids) -> np.ndarray:
        """返回属于给定 lineage 集合的全局基元下标 (M,) int64。"""
        ...

    def lineage_of(self, idx: np.ndarray) -> np.ndarray:
        """按下标返回其 lineage 标签 (M,) int32/64（速度预测分组用）。"""
        ...

    def world_points(self, idx: np.ndarray) -> np.ndarray:
        """按全局下标取世界坐标 (M,3) float32（host numpy）。"""
        ...

    def move(self, idx: np.ndarray, new_xyz: np.ndarray) -> None:
        """把全局下标 idx 的基元世界坐标**替换**为 new_xyz (M,3)（Case1 显式搬移）。"""
        ...

    def insert(self, world: np.ndarray, colors: np.ndarray, lineage_id: int) -> np.ndarray:
        """插入新基元，返回其全局下标 (K,)（Case2）。"""
        ...

    def delete(self, idx: np.ndarray) -> None:
        """按下标删除基元（Cond1/Cond2/cap）。"""
        ...


# ── 决策核 ───────────────────────────────────────────────────────────────────

class DynPortBuffer:
    """在线动态基元管理（纯决策 + lineage 记账）。无 per-primitive 可学标量 ⇒ 不撞 α 共线墙。"""

    def __init__(self, cfg: dict, map_access: MapAccess):
        self.cfg = cfg
        self.map = map_access
        self.lam_d = float(cfg["lam_d"])
        self.cap = int(cfg["cap"])
        self.lmax = int(cfg["lmax"])
        self.lineage_base = int(cfg["lineage_base"])
        self._next_lid = 0
        # lid -> {"birth": frame_idx, "n": 现存数}；first_seen 由 lid 的 birth 帧统一管理
        self.issued: dict[int, dict] = {}
        # 计数器（J5 生效证据）
        self.case1_hits = 0
        self.case2_new = 0
        self.cond1_deleted = 0
        self.cond2_deleted = 0
        self.evicted_total = 0
        self.cap_hits = 0
        self.log: list[dict] = []
        self._last_obs = None
        self._last_thr = None

    # -- lineage 记账 --
    def _issue(self, frame_idx: int) -> int:
        lid = self.lineage_base + self._next_lid
        self._next_lid += 1
        # `cent`/`last`/`vel` = 常速度外推（DynaGSLAM v⁻ 的替代：无光流时用帧间质心差分）。
        self.issued[lid] = {"birth": int(frame_idx), "cent": None,
                            "last": int(frame_idx), "vel": np.zeros(3, np.float32)}
        return lid

    def active_lineages(self) -> list[int]:
        return sorted(self.issued)

    def _predict(self, cur_idx, j):
        """按各 lineage 的常速度把缓冲基元外推到当前帧（消除帧间位移，替代光流 warp）。"""
        if cur_idx.shape[0] == 0:
            return self.map.world_points(cur_idx), cur_idx
        buf_xyz = self.map.world_points(cur_idx)
        lid_of = np.asarray(self.map.lineage_of(cur_idx))
        pred = buf_xyz.copy()
        for lid in np.unique(lid_of):
            rec = self.issued.get(int(lid))
            if rec is None or rec["cent"] is None:
                continue
            dt = float(j - rec["last"])
            if dt <= 0:
                continue
            sel = (lid_of == lid)
            pred[sel] = buf_xyz[sel] + rec["vel"].reshape(1, 3) * dt
        return pred, cur_idx

    def _update_vel(self, cur_idx, matched_pts_by_lid, j):
        """用本帧匹配到的当前观测更新各 lineage 质心与速度。"""
        for lid, new_cent in matched_pts_by_lid.items():
            rec = self.issued.get(int(lid))
            if rec is None:
                continue
            dt = float(j - rec["last"])
            if rec["cent"] is not None and dt > 0:
                rec["vel"] = ((new_cent - rec["cent"]) / dt).astype(np.float32)
            rec["cent"] = new_cent.astype(np.float32)
            rec["last"] = int(j)

    def _refresh_tracks(self, j, thr):
        """把本帧**观测点云**按最近的要基元分组，更新各 lineage 质心/速度。

        lineage 的"当前观测质心" = 在该 lineage 预测位置 thr 邻域内的观测点均值。
        """
        active = self.active_lineages()
        if not active:
            return
        cur_idx = self.map.dyn_indices(active)
        if cur_idx.shape[0] == 0:
            return
        obs = self._last_obs
        if obs is None or obs.shape[0] == 0:
            return
        from scipy.spatial import cKDTree
        pred, _ = self._predict(cur_idx, j)
        lid_of = np.asarray(self.map.lineage_of(cur_idx))
        dd, ii = cKDTree(pred).query(obs, k=1)
        matched = {}
        for k in np.nonzero(dd <= thr)[0]:
            lid = int(lid_of[ii[k]])
            matched.setdefault(lid, []).append(obs[k])
        cents = {lid: np.mean(np.asarray(v), axis=0) for lid, v in matched.items()}
        self._update_vel(cur_idx, cents, j)

    @property
    def n(self) -> int:
        if not self.issued:
            return 0
        return int(self.map.dyn_indices(self.active_lineages()).shape[0])

    # -- 主入口：一帧 --
    def step(self, frame_idx, pts_world, colors, dbar):
        """pts_world/colors = 运行期掩码反投影所得（世界系，(N,3)）；dbar = 传感器深度均值。

        返回本帧 log dict（含 5 个计数器）。因果：只用当前帧数据。
        """
        j = int(frame_idx)
        pts = np.asarray(pts_world, dtype=np.float32).reshape(-1, 3)
        cols = np.asarray(colors, dtype=np.float32).reshape(-1, 3)
        rec = {"frame": j, "inserted": 0, "case1_hits": self.case1_hits,
               "n_buf": self.n, "cond1_deleted": self.cond1_deleted,
               "cond2_deleted": self.cond2_deleted, "cap_hits": self.cap_hits}
        if pts.shape[0] == 0:
            self._housekeeping(j, pts)
            rec.update({"n_buf": self.n, "cond1_deleted": self.cond1_deleted,
                        "cond2_deleted": self.cond2_deleted, "cap_hits": self.cap_hits})
            self.log.append(rec)
            return rec

        thr = max(self.lam_d * float(dbar if dbar else 1.0), 1e-3)
        n_new = 0
        self._last_obs = pts                      # 供 _refresh_tracks 用（本帧观测点云）
        active = self.active_lineages()
        if active:
            cur_idx = self.map.dyn_indices(active)
            if cur_idx.shape[0] > 0:
                from scipy.spatial import cKDTree
                # 常速度外推后再匹配（替代 DynaGSLAM 的光流 warp：消除帧间位移，
                # 使 Case1 在真实运动速度下仍命中）。无 vel 的 lineage 位置不变。
                pred, _ = self._predict(cur_idx, j)
                dist, hit_idx = cKDTree(pred).query(pts, k=1)
                hit = dist <= thr
                if hit.any():
                    self.map.move(cur_idx[hit_idx[hit]], pts[hit])   # Case1 显式搬移
                    self.case1_hits += int(hit.sum())
                if (~hit).any():
                    n_new = int((~hit).sum())
                    self.map.insert(pts[~hit], cols[~hit], self._issue(j))
            else:
                n_new = int(pts.shape[0])
                self.map.insert(pts, cols, self._issue(j))
        else:
            n_new = int(pts.shape[0])
            self.map.insert(pts, cols, self._issue(j))
        self.case2_new += n_new

        # 更新各 lineage 的质心与速度（用本帧观测，按 lineage 分组）
        self._refresh_tracks(j, thr)
        self._housekeeping(j, pts, thr=thr)
        rec.update({"inserted": n_new, "case1_hits": self.case1_hits, "n_buf": self.n,
                    "cond1_deleted": self.cond1_deleted,
                    "cond2_deleted": self.cond2_deleted, "cap_hits": self.cap_hits})
        self.log.append(rec)
        return rec

    def _housekeeping(self, j, pts, thr=None):
        """Cond1（可观测）/ Cond2（寿命）/ cap 驱逐。pts 为本帧观测点云（可能为空）。"""
        active = self.active_lineages()
        if not active:
            return
        # 无观测帧（pts 空）沿用上一次的 thr（由调用方缓存），避免回退到固定 1.0 造成 ~40× 口径漂移
        # （G3-重大#7：Cond1 空观测回退阈值须与主路径同源 lam_d·d̄）。
        if thr is None:
            thr = self._last_thr if self._last_thr is not None else max(self.lam_d * 1.0, 1e-3)
        cur_idx = self.map.dyn_indices(active)
        if cur_idx.shape[0] == 0:
            return
        self._last_thr = thr
        # Cond1：把缓冲基元**外推到当前帧**后，观测点云中无近邻者删（与 Case1 同一外推口径，
        # 否则真实运动速度下会把"移动中"的基元误判为不可观测 ⇒ churn）。
        pred, _ = self._predict(cur_idx, j)
        if pts is not None and pts.shape[0] > 0:
            from scipy.spatial import cKDTree
            dd, _ = cKDTree(pts).query(pred, k=1)
            dead = dd > thr
            if dead.any():
                self.map.delete(cur_idx[dead])
                self.cond1_deleted += int(dead.sum())
                cur_idx = cur_idx[~dead]
        # Cond2：寿命（按 lineage birth 帧）
        if cur_idx.shape[0] > 0:
            # 粒度 = 整个 lineage（DynaGSLAM 的"瞬态批次"语义）；只删仍有 GS 的 lineage。
            old_lids = [lid for lid in active if (j - self.issued[lid]["birth"]) > self.lmax]
            if old_lids:
                old_idx = self.map.dyn_indices(old_lids)
                if old_idx.shape[0] > 0:
                    self.map.delete(old_idx)
                    self.cond2_deleted += int(old_idx.shape[0])
                for lid in old_lids:
                    self.issued.pop(lid, None)
        # cap：超额 FIFO 驱逐（按 lineage 旧者先出）
        if self.n > self.cap:
            self._evict_to_cap()

    def _evict_to_cap(self):
        active = self.active_lineages()          # 已按 lid 升序 = 加入顺序（FIFO）
        n_remove = self.n - self.cap
        removed = 0
        for lid in active:
            if removed >= n_remove:
                break
            idx = self.map.dyn_indices([lid])
            self.map.delete(idx)
            removed += int(idx.shape[0])
            self.issued.pop(lid, None)
            self.evicted_total += int(idx.shape[0])
        self.cap_hits += 1

    def vitality(self):
        return {"case1_hits": int(self.case1_hits), "case2_new": int(self.case2_new),
                "cond1_deleted": int(self.cond1_deleted),
                "cond2_deleted": int(self.cond2_deleted),
                "evicted_total": int(self.evicted_total), "cap_hits": int(self.cap_hits),
                "buf_final": self.n}


COUNTER_FIELDS = ("frame", "inserted", "case1_hits", "n_buf",
                  "cond1_deleted", "cond2_deleted", "cap_hits")


def write_counters_csv(buf: DynPortBuffer, path: str) -> None:
    """落盘 J5 生效证据（无落盘 = 静默组件，违纪）。"""
    import csv
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(COUNTER_FIELDS))
        w.writeheader()
        for rec in buf.log:
            w.writerow({k: rec.get(k, 0) for k in COUNTER_FIELDS})
