# 仪器模式 prereg（P3-D2-030）—— 机制研究的标准测量配置

**状态**：判据与配置锁定于任何仪器模式判效批之前。用户 2026-11-05 拍板选**甲**：
「现阶段可复现性以及机制是否有用才是最重要的」⇒ 仪器模式纳入机制研究标准配置。
**依据**：
- `detraster_L2_2x2_2026-11-05.md` — 2×2 四格，仅「单线程 × det-ON」达 R1_bitwise_identical。
- `detraster_residual_bisect_2026-11-05.md` — async 自由跑为设备无关分叉源
  （同 20 帧两跑 735 vs 700 个不同 iteration）。
- `P3-D2-029` — 判决修订为 R-feasible-under-fixed-schedule。

---

## §0 一句话定义

**仪器模式 = 关掉两个设备无关分叉源（异步调度 + rasterizer backward float atomicAdd）
的测量配置。它的唯一职责是让「同 config 同 seed 两次 run 逐位一致」成立，
从而让臂间差可以被归因到机制本身。**

**它不是部署配置。** 仪器模式的读数与主线 async 读数**不同源**，必须分开登记。

---

## §1 三项锁定开关（缺一即仪器无效）

| 开关 | 位置 | 值 |
|---|---|---|
| `Training.single_thread` | `slam_frontend.py:357`（前端） | `true` |
| `Dataset.single_thread` | `slam_backend.py:317`（后端） | `true` |
| `Rasterizer.deterministic_backward` | `gaussian_renderer/__init__.py:60` | `true` |

**为什么两个 single_thread key 都要设**：前端只读 `Training` 段，后端只读 `Dataset` 段。
只设前者 ⇒ 前端进入「等后端」状态而后端仍在 async 自由跑 ⇒ 仪器无效
（2026-11-05 曾因此产出两个无效 run，已作废）。

**runner 侧三项环境**（由 `run_instrument.sh` export，缺一即 fail-closed 退出）：

```
PYTHONPATH=scripts/paper3_bpw/deterministic_probe   # sitecustomize 注入确定性套件
PYTHONHASHSEED=0                                     # 必须在解释器启动前（sitecustomize 里设无效）
CUBLAS_WORKSPACE_CONFIG=:4096:8
```

---

## §2 仪器有效性判据（每批必验，机械）

**R-valid**：同 config 同 seed 的 **2 个 run**，`compare_three_way.py`（易变列剔除口径）
判 **R1_bitwise_identical**。

- `R1` ⇒ 该臂的仪器状态有效，可用于臂级/逐事件判读。
- `R2` ⇒ **仪器失效，批作废**（不解释机制、不报数字），先查三项开关是否真生效。

判据件集（`compare_three_way.py` 当前口径）：`per_frame_ape.csv`、
`reliability_signal/frames.csv`、`deferred_commit_events.csv`、
`plot/{stats_final,trj_final,trj_full_final}.json`，以及
`tracking_raw.csv` / `efficiency_raw.csv` / `mapping_raw.csv` 的**非易变列**。
易变列 = `run_id` / `source_dir` / `notes` / 一切 wall-clock 与显存峰值列。

**这条判据的地位**：它**不是**机制判据，是**仪器前置条件**。仪器不 valid ⇒ 后续一切判读无意义。

---

## §3 读数登记规则（两套口径，永不混引）

| 口径 | 配置 | 用途 | 登记位置 |
|---|---|---|---|
| **仪器口径**（primary） | `instrument_*` 配置（单线程 + det-ON） | 机制判据（E1/E2）、臂间比较 | 族 prereg 主表，标注 `mode=instrument` |
| **部署口径**（reference） | 原 `*_person_tracking` 配置（async） | 性能/部署可行性参考 | 另表，标注 `mode=async`，**不作机制结论** |

**硬规则**：
1. 任何表格/正文引用仪器口径数字，必须带 `mode=instrument` 标注。
2. 任何臂间差主张只能来自仪器口径。async 口径的臂间差一律记「自差内不可判」
   （`prereg_device_gate_2026-11-05.md` Part A 常驻规则继续有效）。
3. **不得**在同一个比较里混用两套口径（例如「仪器模式的 A 臂」对「async 的 B 臂」）。

### 已知差异（必须随读数一起交代）
同一机制配置在两套口径下的绝对数不同（示例：det-raster 臂 40 帧，
仪器 ATE 1.1682cm / 19771 高斯，async ATE 1.1771cm / 25976 高斯）。
⇒ 仪器口径的**绝对值不可与文献/前作直接比**；只有**仪器口径内部的臂间差**有判力。

---

## §4 对框架 v2 的修正（E1① 放宽、E3 边界更新）

`prereg_device_robust_estimand_2026-11-05.md` §1 E1① 原写「run 级逐位一致在本装置不可达」。
**该句自本件起作废**，改为：

> E1① 两态单测：config 开关默认关 = 单测级数学路径全等。
> **且**仪器模式下 2 run 逐位一致（R-valid，本件 §2）。

E3 的边界交代更新为：**仪器口径下臂级终态可判**（逐位可复现 ⇒ 臂间差即机制差）；
async 口径下仍「自差内不可判」。两者并列陈述，不互相替代。

---

## §5 成本与执行约束

- **时间成本**：仪器模式单线程 ⇒ 每 run 约 160s/40 帧（async 约 165s），
  但**不能并行占满多卡**（单线程设计上就是一卡一线）。
  臂级批若 n=3 × 2 臂 = 6 run/序列，全长 580 帧约 6 × 40min ≈ 4h（单卡串行）。
- **调度**：仪器批**一律本地 2060 或 3090 空闲卡**，且**同批同卡**（跨卡整批换，
  不混批）。理由：det-raster 已使 backward 跨装置一致，但整批同卡可消除残余
  装置级变量，成本为零。
- **每批必带 R-valid 检查**（§2）；R-valid 不过 ⇒ 整批作废重跑，不得挑样本。

---

## §6 与既有族的关系

- **不追溯**：已关闭族（BPW / CGB / FDose / MaskStat / 剂量-响应）判决维持原样。
- **向前适用**：此后所有新族 prereg 必须 ① 引用本件；② 指定仪器配置名；
  ③ 在 §2 的 R-valid 前置写进族 prereg 的执行节。
- **可选的回补**（需用户点头才做）：把 MaskStat 与剂量-响应在仪器模式下重跑
  一遍，看原「不可判」是否转为可判。这会改写已关闭族的读数解读，
  属新判据适用，须另开账本条。

---

## §7 出口规则（机械）

1. R-valid 不过 ⇒ 仪器失效，整批作废（不解释、不报数）。
2. R-valid 过 + 族判据（E1/E2）过 ⇒ 允许写机制主张，**且必须同时写明
   「仪器口径」**。
3. R-valid 过但族判据落在地板内 ⇒ 「仪器口径下不可判」（此时才是有意义的不可判——
   区别于 async 下「因装置噪声太大而不可判」）。
4. 任何出口都不产生「评测协议 = 贡献」的主张（框架 v2 §4 继续有效）。

---

## §8 首次端到端验证（2026-11-05 17:37–17:58，本 prereg 锁定后）

用 `scripts/paper3_bpw/run_instrument.sh instrument_person_tracking 0 40 2` 实跑：

```
selfcheck: hashseed + det-algorithms + both single_thread keys + det_backward ✔
gpu free: 5859 MiB
run1 done rc=0 elapsed=625s
run2 done rc=0 elapsed=636s
VERDICT: R1_bitwise_identical
=== INSTRUMENT OK: 逐位一致 ⇒ 该臂可用于臂级判读 ===
```

两 run 关键量：

| | run1 | run2 |
|---|---|---|
| ATE | 1.1682 cm | 1.1682 cm |
| KF-ATE | 1.277 cm | 1.277 cm |
| num_gaussians | 19771 | 19771 |
| mapping_iterations | 2107 | 2107 |

⇒ **仪器 + runner + prereg 三件自洽可用**（§2 的 R-valid 判据在真实管线上跑通）。

### 执行约束补记（本轮踩到）
- **显存预检必须做**：本轮首次启动撞上 36 小时前的孤儿 spawn 子进程
  （占 704 MiB，父进程已死归 systemd），单线程模式峰值 ~4.8 GiB ⇒ OOM。
  已在 runner 加 fail-closed 预检（`memory.free < 5200 MiB` 即拒启动，`exit 4`）。
- 每次 40 帧 run 约 625–636s（含 color refinement）；全长 580 帧约 40min/run 量级。
