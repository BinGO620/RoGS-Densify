# E 轴实现注记：Adaptive itr 调度器（`Mapping.adaptive_itr`）—— 2026-11-09

**账本**：P3-D2-045（立项）+ P3-D2-044（授权链）。
**预注册**：`prereg_adaptive_itr_schedule_2026-11-08.md`（判据锁定于本件与实现之前）。
**本件职责**：只登记**实现层面的口径决定与预注册字面之间需要对齐的地方**，不改判据、
不改出口。判据本体在 prereg，本件不复制。

---

## 一、实现形态

- 新模块 `utils/adaptive_itr.py`：`adaptive_itr_active()` / `itr_early()` / `itr_late()` /
  `kf_threshold()` / `is_early()` / `schedule_iters()` / `validate_mode()`。
- 接线点 = `utils/slam_backend.py` 的 `keyframe` 分支（**唯一** per-KF 建图 itr 消费点，
  即 `iter_per_kf` 的赋值处）：`schedule_iters(config, ordinal, iter_per_kf)`。
- 默认关：`Mapping.adaptive_itr.enabled` 缺省 False ⇒ `schedule_iters` **原样返回**
  调用方传入的 itr（不是返回某个默认值）；三个参数在关闭路径上**零消费**。
- 单测 `tests/paper3_bpw/test_adaptive_itr.py`（17 条）：默认关透传 / 关闭时坏参数不抛 /
  两段式边界（含阈值帧）/ 默认值 = prereg 值 / 四种非法参数 fail-closed /
  async 口径开启 fail-closed / C 臂 vs A 臂单变量契约 / 后端接线文本断言。
- C 臂配置 `configs/experiments/paper3_bpw/adaptive_itr_person_tracking.yaml`：
  `inherit_from` A 臂（`instrument_person_tracking`），**只加** `Mapping.adaptive_itr`
  块 + save_dir；仪器三开关原样继承（单变量契约测试守护）。

## 二、与 prereg 字面需要对齐的三处（**均不改判据、不改出口**）

### 2.1 关键帧序数口径：初始化关键帧计为第 1 个，但不被调度

prereg §1 的校准句写的是「40 帧 = pt 序列**前 8 个关键帧**（KF 每 10 帧一枚，
40 帧 run 的 KF 模式 0/5/…/35）」。实测该模式是 **0/5/…/35 共 8 个**（间隔 5 帧，
不是 10 帧）——**8 个关键帧 × 5 帧 = 40 帧，与校准窗口自洽**。

- **实现取字面口径**：序数从初始化关键帧（frame 0）起算为 #1，其后每个
  `keyframe` 分支建图调用 +1。故 early 相位 = 序数 1–8 = **frame 0–35**，
  恰好落在「itr 不敏感（极差 0.015cm）」的 40 帧校准窗口内；KF40（#9）起走 `itr_late`。
- **初始化关键帧自身的建图预算不被覆写**：它走 `init_itr_num`（1050，硬编码，
  B 臂同值），不是 `Training.mapping_itr_num`。若把调度套到该调用上，C vs B 的
  差异就不再是「itr 调度」而是「初始化预算 1050→30」，既破坏单变量，
  也超出校准证据的覆盖范围（校准扫的是 per-KF itr，不是 init 预算）。
  该调用只参与序数计数。

### 2.2 M3 预注册预期值（−5%）按实测 KF 密度应为 −2%（门只设方向，不受影响）

prereg §3 M3 的括注：「预期 ≈ −5%（8/58 KF 早期 × (50−30)/50）」。其中 **58 KF**
是「580 帧 ÷ 每 10 帧一枚」的推算，实测 **115 KF**（每 5 帧一枚，console
`Candidate insert KF 5…575` 计数 115）。按实测密度重算：

| 量 | B（fixed-50） | C（调度 30→50） |
|---|---|---|
| per-KF 主建图迭代 | 115 × 50 = 5750 | 7 × 30 + 108 × 50 = 5610 |
| 初始化 BA | 1050 | 1050（不调度） |
| prune 调用（iters=1） | 115 | 115 |
| **合计 `mapping_iterations`** | **6915** | **6775** |

⇒ 预期节省 **−140 迭代 = −2.02%**（B 臂 6915 与本仓 `itr_full_580_verdict` 的
itr=50 全长实测值逐数相符，可作交叉核对锚）。

M3 的字面判据是「`mapping_iterations(C) < mapping_iterations(B)`」——**只设方向**，
预注册预期值仅作报告项；故本对齐不改变任何出口的机械路由。L1 判读器须把
「预期值 −5%（prereg）vs 实测 −2.0%（本仓密度）」作为报告项并列，不得改写 prereg。

### 2.3 async 口径 fail-closed（不静默不生效）

部署口径（`Dataset.single_thread: false`）下每 KF 调用只是自由跑循环里的一次，
主优化量来自 `map(iters=1)` 的自由跑；在该口径开调度属**未预注册的新实验**。
`validate_mode()` 在「开启 + 非单线程」时抛 ValueError（fail-closed），
不在 async 下静默跑成「关了但看起来开着」。L1 三臂全部在仪器口径（单线程）。

## 三、机制生效证据（DISCIPLINE 9：组件必须真生效）

- **逐调用日志**：`[adaptive_itr] KF#<序数> (frame <帧>) itr=<步数>`（每次 keyframe
  分支调用一行，115 行/全长 run；行宽 ~46 字符 < rich 折行阈值）。
- **落盘计数**：`backend_timing.json` 新增 `adaptive_itr_early_calls` /
  `adaptive_itr_late_calls`（默认关恒 0；全长预期 7 / 108）。
- **既有列交叉核对**：`efficiency_raw.csv` 的 `mapping_iterations` 与
  `backend_timing.json` 的 `mapping_iterations`（C 预期 6775，B 6915）。
- 判读器 M1 的门：逐行核对「序数 ≤ 8 ⇒ itr = itr_early；序数 ≥ 9 ⇒ itr = itr_late」，
  且 early/late 计数与 `backend_timing.json` 一致；任一不符 ⇒ `MECH_INVALID`（rc=2）。

## 四、本件不主张

- 不主张 ATE 改善（H-B 只是方向假设，`L1_ATE_GAIN` 才升格）；
- 不主张预注册预期值本身正确——2.2 只是把「按本仓实测密度应有的节省」算清楚；
- 不主张 async 迁移（未测，且实现层已 fail-closed）。
