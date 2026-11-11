# 剂量轴 A4 仪器口径预注册（P3-D2-038）—— 2026-11-06

**状态**：判据锁定于**任何 A4 臂 run 之前**。本文件写定时，A4 臂零 GPU、零 run 目录。
**母件**：`prereg_instrument_mode_2026-11-05.md`（仪器定义与 R-valid 前置）+
`prereg_dose_response_2026-11-04.md`（剂量轴族）。
**方向来源**：用户 2026-11-06 拍板「丁 · A4 仪器重测」，并拍板「高斯数硬约束 ratio ≤ 1.5」。

---

## §0 为什么做这一件

机制候选池已全清（BPW 重排无效 / MaskStat 负向 / MinObsGate 不可判 / MissStreak A-ABORT），
生长浪费账本判 prune÷densify = 16.7%（管线自带保守清理）。四条证据收敛 ⇒
「在 densify 侧加门控」这条路线在当前管线上没有可捞的收益（`P3-D2-036`）。

**唯一还有历史正信号的干预点 = 剂量轴。**
`audit_legacy_densification_2026-10-27.md` §2.1 记录：A4（`densify_grad_threshold`
0.0002→0.0001 + `percent_dense` 0.01→0.02）在 moving_obstructing_box 上 3-seed 均值
**31.36 vs 44.44cm = −29.4%**，但代价是高斯数 2.1×~6.5×、PSNR 下降。

当时未采信的唯一理由：**「更多」与「更对」不可区分**（`prereg_cgb_2026-10-30.md:33`）。
这一条现在可判——仪器口径下同 config 同 seed 逐位可复现（`P3-D2-030`），
ATE 差值不再含装置噪声，高斯数比也变成精确量。**这是该历史信号第一次可被干净复验。**

> **口径警告（写死）**：历史读数（31.36 / 44.44）是**旧栈 · async · moving_obstructing_box**
> 上的，与本件（**当前栈 · 仪器 · person_tracking**）**永不可并列、不可作差值比较**。
> 本件只复验「A4 这个剂量组合在当前管线 + 当前序列上是否改善 ATE 且高斯数受控」，
> 不承诺复现 −29.4% 这个数。

---

## §1 设计（唯一变量）

### 1.1 臂

| 臂 | 配置 | 定义 |
|---|---|---|
| `off` | `instrument_maskstat_off`（已存在） | 基线：3DGS 默认剂量（grad 0.0002 / percent_dense 0.01） |
| `A4` | `instrument_a4_person_tracking`（本件新建，由 `dose_a4_person_tracking` 派生） | **仅两个键**：`opt_params.densify_grad_threshold: 0.0001`、`opt_params.percent_dense: 0.02` |

**唯一变量** = 上述两个 `opt_params` 键。其余全部逐字段相同（继承链：
`person_tracking.yaml` → `bonn/base_config.yaml` → `tum/base_config.yaml`；
`method_from: combined_prune/method.yaml`；`SelectiveDensification.enabled: false`）。
机械守护：契约单测断言 A4 臂与 off 臂的解析后配置**只在两个键上不同**（§6 清单）。

### 1.2 为什么是这两个键一起动（不做分解）

- 历史 A4 就是这两个键的组合，本件的目的是**复验历史信号**，不是重新设计。
- 分解（grad-only / percent_dense-only）是另一件实验，会**偏离**历史信号的字面形态；
  且算力 ×3。**本件不做分解**，若 A4 出正面读数，分解作为下一阶段的机制归因问题。
  （此条为预注册承诺：本件**不得**在出结果后追加分解臂来「救活」或「解释」A4。）

### 1.3 序列、长度、优化预算

- 序列 = `person_tracking`（唯一有 headroom 的序列；off 基线已就位）。
- 全长 **580 帧**（ATE 是整条轨迹统计量；40 帧读数与全长不可比）。
- 仪器口径 itr = `mapping_itr_num: 150`（`P3-D2-032`：150 是最稳测点，seed 极差 0.32cm；
  换 itr=30 会让 0.5cm 级效应被 3.93cm seed 方差淹没）。

### 1.4 run 布局（5 run，不是 6）

| # | 臂 | seed | 用途 | 卡 |
|---|---|---|---|---|
| 1 | A4 | 0 | 主臂 | GPU0 |
| 2 | A4 | 0 | **R-valid**（同 config 同 seed 第 2 run，须 R1） | GPU0 |
| 3 | A4 | 1 | 主臂 | GPU0 |
| 4 | A4 | 2 | 主臂 | GPU1 |
| 5 | off | 0 | **批次等价性桥接**（见 §2.2） | GPU1 |

**执行偏差（2026-11-06 晚如实登记，slam-critic G3 审查 M2）**：实际派发与本表**不一致**。
`run_dose_a4_batch.sh` 把 **A4 三 seed 全放 GPU0**（s0×2 → s1 → s2），GPU1 只跑 off 桥接；
本表却写「A4 s2 在 GPU1」。实跑日志 `dose_a4_batch_20261106.log` 的 `gpu free` 行只有
三处 `device 0` + 一处 `device 1`。

⇒ **两臂不同卡**：A4 三 seed 在卡0，off 基线三 seed 来自卡1（`maskstat_instrument_verdict:10,36`），
仓内无卡0↔卡1 逐位等价证据。**这违反本 prereg 与父件的「同批同卡」要求**。
判决仍按机械出口落 `CLOSED_NEGATIVE_OR_UNSTABLE`（Δ=+3.15cm 远大于任何已知跨机差线索），
但**「跨卡无关」这一条不成立**，判决引用时必须带此限定（详见判决 §1.1）。
后续：补卡0↔卡1 等价探针；新批一律同卡。

off 臂 seed 1/2 **不重跑**，条件见 §2.2 的机械分支。

---

## §2 两道前置门（任一不过 ⇒ 整批作废，不报数字）

### 2.1 R-valid（仪器前置）

同 config 同 seed 2 run ⇒ `compare_three_way.py`（易变列剔除口径）判 `R1_bitwise_identical`。
A4 臂 seed0 的两 run 即此门（run #1 与 #2；由 `run_instrument.sh <arm> 0 0 2` 一次派出）。
R2 ⇒ **整批作废**，先查 `single_thread`（两个 key）/ `deterministic_backward` /
`PYTHONHASHSEED` / `CUBLAS_WORKSPACE_CONFIG` 是否真生效，不出判决、不解释机制。

### 2.2 批次等价性门（本次新增，理由见 §0 与下方说明）

**事实**：off 基线三 seed 的 run 锚点记录 HEAD = `c2978f891` / `c599d965a` / `58164bb15`，
而 A4 臂将在当前 HEAD 上跑。两者之间核心代码有 **+249 行**差异
（`utils/e2_trace.py` 新增、`utils/miss_streak.py` 新增、
`utils/selective_densification.py` +15、`utils/slam_backend.py` +29、
`gaussian_splatting/scene/gaussian_model.py` +35、`slam.py` +4），
**全部为默认关的机制门**（`E2.trace_events` / `MissStreak.enabled` / `signal=="obs_gate"`），
submodule pin 三方相同（`b35ed864`）。

**门（机械）**：`off` 臂 seed0 在当前 HEAD 跑 **1 run**（run #5），与既有基线
`instrument_maskstat_off/.../seed_0/2026-11-05-22-12-05` 做 `compare_three_way.py` 比对：

- **R1_bitwise_identical** ⇒ 代码等价成立 ⇒ **off 臂三 seed 基线合法可复用**，批次等价门 PASS。
- **R2_divergent** ⇒ 代码不等价 ⇒ **机械分支**：off 臂 seeds 1/2 **必须重跑**（+2 run），
  不得用旧基线。重跑后全部门按新基线重判。

**诚实标注**：该等价门是 **1 seed 的抽样证明**，不是全 seed 证明。
若某个非目标 seed 恰好走到旧 HEAD 未覆盖的分支，本门检出不了。
登记为已知边界；若判决落在出口边界附近（\|median Δ\| 与 0.5cm 相差 < 0.3cm），
则该不确定性必须写进判决正文，不得只写成「已过等价门」。

---

## §3 判据（机械，按序执行，四条出口互斥）

### 3.1 读数定义

```
ΔATE(seed s)   = ATE_A4(s) − ATE_off(s)                 [cm]
gauss_ratio(s) = online_num_gaussians(A4,s) / online_num_gaussians(off,s)
```

- `ATE` 取 `tracking_raw.csv` 的 `ate_rmse_cm`（全长单 run 末行值）。
- 高斯数取 `efficiency_raw.csv` 的 `online_num_gaussians`（**在线地图**末态规模）；
  `refined_num_gaussians`（细化后）作为报告项并陈。

**口径更正（2026-11-06 晚，slam-critic G3 审查 M4）**：本条原写「与已关闭族的口径一致」，
**引证错宿主** —— 最近的同类族（MaskStat 仪器回补）的判读器 `judge_maskstat.py:150`
用的是 **`refined_gaussians`**，不是 online。两列本批都报（online 2.63/2.52/2.55、
refined 2.48/2.37/2.41，**同量级、结论不变**），但不得声称「与已关闭族一致」。
选 online 作主判据的理由独立成立：它量的是**在线地图**规模，而 ATE 也是在线产物；
refined 是离线细化后的规模，与在线跟踪无直接因果。

### 3.2 硬门（先于出口，不过即作废）

| 门 | 条件 |
|---|---|
| 帧数闸 | 每个消费 run 的 `per_frame_ape.csv` **恰 580 行** |
| rc 闸 | 每个消费 run 的 `instrument_*.done` **`finished_rc0=yes`**（无则拒，不得默认通过） |
| R-valid 闸 | §2.1 PASS |
| 等价门 | §2.2 PASS（或已按机械分支重跑） |

### 3.3 四条出口（机械路由，不看机制解释）

记 `med = median(ΔATE)`，`same_sign = 三个 ΔATE 同号`，`max_ratio = max_s gauss_ratio(s)`。

| # | 出口名 | 条件 | 含义 |
|---|---|---|---|
| 1 | **`POSITIVE_ATE_DOSE_OK`** | `same_sign` 且 `med ≤ −0.5cm` 且 `max_ratio ≤ 1.5` | **ATE 改善且剂量受控** ⇒ 论文 3 第一个正面读数候选（仍是候选，进 L2 扩展前不算机制贡献） |
| 2 | **`DOSE_CONFOUND`** | `same_sign` 且 `med ≤ −0.5cm` 且 `max_ratio > 1.5` | ATE 改善但高斯数膨胀 ⇒ **混杂坐实**，「更多 vs 更对」不可区分（诚实负结果） |
| 3 | **`BELOW_CLAIM_FLOOR`** | `same_sign` 且 `\|med\| < 0.5cm` | 方向一致但效应小于本设计可主张下限 |
| 4 | **`CLOSED_NEGATIVE_OR_UNSTABLE`** | `med ≥ +0.5cm` 且 `same_sign`；**或** 三 seed 异号 | 方向为负（A4 更差）或跨 seed 不稳定 ⇒ 关闭 |
| — | `INSTRUMENT_INVALID` | §3.2 任一硬门不过 | 整批作废，不报数字 |

**0.5cm 门槛**沿用 `prereg_maskstat_instrument_2026-11-05.md` §3.2（仪器口径下
Δ 是精确值，剩余不确定性只来自 seed 抽样；0.5cm ≈ person_tracking ATE 的 4%）。

**1.5 高斯数比门槛**（用户 2026-11-06 拍板）：历史 A4 的 2.1×~6.5× 是「增益可能只是
更多基元」的直接证据。1.5 的取法——`percent_dense` 上调本身会让更多点走 split
（每个被 split 的点净增 1 个基元），故允许温和增长；1.5× 之外的增长已足以让
「更密 vs 更对」不可区分。**此门不因结果而调**（不得事后放宽）。

### 3.4 报告项（不参与 PASS/FAIL）

- `refined_num_gaussians` 比（并陈）。
- 渲染代价：`mapping_raw.csv` 末行的 `psnr` / `depth_l1_cm`（历史 A4 的 PSNR 代价须如实并列；
  按纪律「ATE 是第一指标」，PSNR 不作门槛，但也**不得**只报 ATE 不说渲染代价）。
- `mapping_iterations` / `online_time_s`（剂量上升是否显著改变算力；仅描述）。

---

## §4 本件不主张什么

- **不与历史 A4 的 −29.4% 比较**（栈不同、序列不同、口径不同，三条都不满足并列条件）。
- **不与 async 部署口径的读数并列**（仪器口径绝对值 ~13.6cm 与部署口径不可比）。
- 只跑 `person_tracking` 一序列 ⇒ 不主张跨序列泛化；L2 扩展需另立判据。
- 剂量轴是**配置/超参**问题，**不是机制贡献**。若出口 1 成立，论文中的身份是
  「主线的剂量设定依据」，不是「我们提出了新机制」。贡献纪律（`P3-D2-025`）继续有效。
- 「不退化」不是贡献；评测协议不是贡献。

---

## §5 时间盒与执行阶梯

| 阶段 | 内容 | 预计 |
|---|---|---|
| P0 | 写 prereg（本件）+ A4 臂配置 + 契约单测 | ~20min |
| P1 | 远程同步代码（`sync_to_remote.sh`，**禁 `git stash -u`**）→ HEAD 三方一致 | ~5min |
| P2 | 派发 5 run（GPU0: A4 s0×2 → s1；GPU1: A4 s2 + off 桥接） | ~2.5h |
| P3 | R-valid 闸 + 等价门判读 | ~10min |
| P4 | 机判 + 判决落盘 + 账本 `P3-D2-038` | ~30min |

**硬顶**：2026-11-07 06:00。到点按已完成最高阶段收尾，**不加 run**。
失败处置：单 run rc≠0 ⇒ 记 FAIL，补跑**最多一次**（同 config 同 seed）；二次失败即止损。

---

## §6 机械清单（判据机必须产出的键）

判读器 = `scripts/paper3_bpw/judge_dose_a4_instrument.py`，须产出并写入 JSON：

`verdict`、`median_delta_ate_cm`、`per_seed[s].delta_ate_cm`、`per_seed[s].gauss_ratio`、
`per_seed[s].off`/`on`（含 `ate_cm` / `gaussians` / `frames` / `run`）、
`max_gauss_ratio`、`same_sign`、`claim_floor_cm`、`gauss_ratio_cap`、
`n_frames_expected`、`reasons`。

负对照（单测，至少三条）：
① 全零 Δ ⇒ `BELOW_CLAIM_FLOOR`；
② Δ 异号 ⇒ `CLOSED_NEGATIVE_OR_UNSTABLE`；
③ ATE 改善但 ratio > 1.5 ⇒ `DOSE_CONFOUND`（**这条是本件的核心防守**）；
④ 缺 `finished_rc0=yes` ⇒ `INSTRUMENT_INVALID`。
