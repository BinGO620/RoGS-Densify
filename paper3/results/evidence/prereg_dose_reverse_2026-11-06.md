# 剂量轴反向扫预注册（P3-D2-039）—— 2026-11-06

**状态**：判据锁定于**任何 tau 臂 run 之前**。本文件写定时，tau2x/tau4x 臂零 GPU、零 run 目录。
**母件**：`prereg_dose_a4_instrument_2026-11-06.md`（判据结构与仪器口径）+ `prereg_instrument_mode_2026-11-05.md`。

---

## §0 为什么做这一件（以及它的预期）

`P3-D2-038` 已判：A4（grad 0.5× + percent_dense 2×）在仪器口径下**三 seed 同号更差**
（median Δ = +3.150cm），高斯数 2.5×。剂量轴**向上**这一侧已测完且有害。

**向下这一侧从未测过。** 本件补上，目的是让剂量轴两侧闭合，从而使一句配置结论
可被机械支持：「当前默认 `densify_grad_threshold=0.0002` 是否已越过最优点」。

### §0.1 预期（预先写死，防出结果后自我安慰）

**既有两条弱证据都指向「再降也变差」**：

| 来源 | 读数 | 口径 | 局限 |
|---|---|---|---|
| 历史 A2（`densify_grad_threshold` 0.0004 + **`gaussian_th` 0.7→0.9**） | 49.40 vs A0 43.87 = **+12.6% 更差**，高斯 0.26× | 旧栈 · async · moving_obstructing_box | **两键混杂**（不能归因到 grad）＋非标准序列 |
| 2060 剂量-响应筛查 seed0（`P3-D2-018`，非权威） | τ∈{0.5,1,2,4} → **14.37 / 9.30 / 10.52 / 10.46** | async · person_tracking · n=1 | **本地非权威**，且 3090 复跑判 `DEVICE_FAIL`（`P3-D2-022`） |

⇒ **本件最可能的结果是「反向也变差」，即默认值 ≈ 剂量最优点。**
这不是失败——它把「剂量轴无正面可捞」变成**两侧闭合的机械事实**，而不是单侧推测。
判据必须能承接这个结果（出口 4 `BOTH_SIDES_WORSE` 就是为此设的）。

### §0.2 与 `P3-D2-038` §1.2 的关系（不是「救活 A4」）

A4 prereg 承诺「本族不得在出结果后追加**分解臂**来救活结果」。本件**不是分解臂**：

- 分解臂（乙）＝ 把 A4 的两个键拆开（grad 0.5× + pd 1× / grad 1× + pd 2×），目的是解释 A4 为何失败；
- 本件（甲）＝ **`percent_dense` 回到基线不动**，只把 `densify_grad_threshold` 往**反方向**推
  （0.0002→0.0004→0.0008），回答的是**另一个问题**：「默认值是否已过量」。

本件不试图让 A4 数字变好，也不复算 A4。**若本件出现正面读数，它主张的是「默认剂量过量」，
与 A4「剂量更多有害」是两个独立命题，不构成对 A4 的翻案。**

---

## §1 设计（单变量，两档）

| 臂 | 配置 | 唯一变量 |
|---|---|---|
| `off` | `instrument_maskstat_off`（已存在） | 基线：grad 0.0002 / pd 0.01 |
| `tau2x` | `instrument_dose_tau2x_person_tracking`（本件派生） | `opt_params.densify_grad_threshold: 0.0004` |
| `tau4x` | `instrument_dose_tau4x_person_tracking`（本件派生） | `opt_params.densify_grad_threshold: 0.0008` |

- **`percent_dense` 三臂全部 = 0.01**（基线）。这是本件与 A4 的关键区别：
  A4 把 pd 抬到 0.02，本件不动 pd ⇒ 剂量只经「梯度门槛」这一个通道变化。
- 两臂由 `make_instrument_arm.sh` 从既有的 `dose_tau2x/4x_person_tracking.yaml` 派生
  （那两个基础臂是 `P3-D2-018` 留下的，其唯一变量经实测确认 = `densify_grad_threshold`）。
- 机械守护：契约单测断言两臂与 off 臂的解析后配置差异**恰为** 一个剂量键 + 两条路径键。
- 方向含义：阈值 ↑ ⇒ 通过 clone/split 门槛的点更少 ⇒ **致密化更少**。

### §1.1 序列、长度、优化预算

同 `P3-D2-038`：`person_tracking`、全长 580 帧、仪器口径、`mapping_itr_num=150`。

### §1.2 run 布局（7 run）

| # | 臂 | seed | 用途 |
|---|---|---|---|
| 1 | tau2x | 0 | 主臂 |
| 2 | tau2x | 0 | **R-valid**（同 config 同 seed 第 2 run，须 R1） |
| 3 | tau2x | 1 | 主臂 |
| 4 | tau2x | 2 | 主臂 |
| 5 | tau4x | 0 | 主臂 |
| 6 | tau4x | 1 | 主臂 |
| 7 | tau4x | 2 | 主臂 |

**R-valid 只验 tau2x 一支，不验 tau4x** —— 理由：两臂共用完全相同的代码路径与仪器配置，
唯一差别是一个数值阈值；数值不同的阈值不会引入新的非确定源。此为该判断的**显式登记**，
若 tau4x 出现异常（例如三 seed 极差 ≫ tau2x），必须在判决中标注「tau4x 未做 R-valid」。

**不加 off 桥接 run**：`P3-D2-038` 的桥接 run 已证 off 基线在 `250554d8e` 上逐位可复现，
而本件跑之前 `git diff --stat 250554d8e..HEAD -- utils/ gaussian_splatting/ slam.py
submodules/ configs/rgbd/ configs/experiments/combined_prune/ scripts/paper3_bpw/run_instrument.sh
scripts/paper3_bpw/deterministic_probe/` **为空**（只有文档与本件新增的 config/judge/测试文件）。
⇒ 代码状态与 A4 批**逐字节相同**，等价门结论直接沿用，不重复消耗 GPU。
（此条是可复核断言，不是声称；复核命令写在本行。）

---

## §2 前置门（任一不过 ⇒ 整批作废）

| 门 | 条件 |
|---|---|
| R-valid | tau2x seed0 两 run `compare_three_way.py` 判 `R1_bitwise_identical` |
| 帧数闸 | 每个消费 run 的 `per_frame_ape.csv` **恰 580 行** |
| rc 闸 | 每个消费 run 有 `.done` 且 **`finished_rc0=yes`**（无锚点即拒，fail-closed） |
| 等价门 | 沿用 `P3-D2-038`（代码逐字节相同，见 §1.2） |

---

## §3 判据（机械，按序）

### §3.1 读数

```
ΔATE(seed s, arm a) = ATE_a(s) − ATE_off(s)        [cm]，负 = 改善
gauss_ratio(s, a)   = online_num_gaussians(a,s) / online_num_gaussians(off,s)
```

### §3.2 单臂四条出口（对 tau2x 与 tau4x **各自**判一次）

记 `med`、`same_sign`、`min_r`/`max_r`（该臂三 seed 的 ratio 极值）。

| # | 出口 | 条件 |
|---|---|---|
| 1 | **`POSITIVE_DEFAULT_OVERDOSED`** | `same_sign` 且 `med ≤ −0.5cm` 且 **`0.5 ≤ min_r` 且 `max_r ≤ 1.5`** 且 **PSNR 下降 ≤ 0.5dB** |
| 2 | **`DOSE_CONFOUND`** | `same_sign` 且 `med ≤ −0.5cm` 但（`min_r < 0.5` 或 `max_r > 1.5` 或 PSNR 掉 > 0.5dB） |
| 3 | **`BELOW_CLAIM_FLOOR`** | `same_sign` 且 `\|med\| < 0.5cm` |
| 4 | **`WORSE`** | `same_sign` 且 `med ≥ +0.5cm` |
| 5 | `SEED_UNSTABLE` | 三 seed 异号 |
| — | `INSTRUMENT_INVALID` | §2 任一硬门不过 |

**ratio 带为什么是双侧 [0.5, 1.5]**：A4 prereg 只设了上界 1.5，因为 A4 是「更多」方向。
本件是「更少」方向，混杂形态相反——若高斯数塌到 0.5× 以下仍判「改善」，那也可能是
地图退化成的假象。取对数对称（×2 / ÷2）两侧同带，且`DOSE_CONFOUND` 出口在两侧都叫同一个名字，
便于把 A4 与本件并表。

**PSNR 闸为什么进硬门而非报告项，以及它的口径**：A4 批里 PSNR 是报告项（历史 A4 已证
PSNR 与 ATE 反相关，故不作门槛）。但**本件的正面出口是「主张默认配置有误」**——那必须证明
不是以渲染质量为代价。故仅在「要判正面」这一条进出口上加闸，不影响其他出口。

- **口径（写死）**：`mapping_raw.csv` **末行**的 `psnr`，即 P-A 静态背景区口径
  （同一 run 的 `full` 行在这些仪器 run 上恒为 `nan`，不可用）。列名在 JSON 里记作
  `static_psnr_db`，**不得**简写为「PSNR」而与全图口径混引。
- **`max_psnr_drop_db`** = `max_s (off_static_psnr(s) − arm_static_psnr(s))`，只有 >0.5 才触发闸。
- **纪律声明**：这是**单参照分区指标**，按「测量口径」#1 不得用于**判效主张**；
  本件只把它当**准入闸**（防止「以渲染质量为代价换 ATE」），不用它下任何效果结论。

### §3.3 汇合出口（两臂一起看，机械路由）

| 出口 | 条件 | 含义 |
|---|---|---|
| **`BOTH_SIDES_WORSE`** | 两臂都是 `WORSE`（或一臂 `WORSE` + 另一臂 `BELOW_CLAIM_FLOOR`） | **剂量轴两侧闭合**：默认值 ≈ 最优点，剂量轴无可捞收益 ⇒ 登记为已排除方向 |
| `DOWN_SIDE_HAS_EFFECT` | 任一侧 `POSITIVE_DEFAULT_OVERDOSED` | 默认剂量过量 ⇒ 配置结论（不进贡献栏） |
| `MONOTONE_WORSE_DOWN` | 两臂均 `WORSE` 且 `med(tau4x) > med(tau2x)` | 加注：剂量越低越差 ⇒ 剂量-ATE 在本区间单调 |
| `INCONCLUSIVE` | 其余组合 | 如实记，不解释 |

---

## §4 报告项（不参与 PASS/FAIL）

- `refined_num_gaussians` 比（并陈）。
- PSNR / `depth_l1_cm`（三臂并陈，不只报进出口那一档）。
- `mapping_iterations` / `online_time_s`（算力是否随剂量变化）。
- **与 A4 并表的剂量-ATE 四点图**：0.5×(A4，pd 2×) / 1×(off) / 2×(tau2x) / 4×(tau4x)。
  **注**：A4 那一点多了 pd 2× 这个变化，画图时必须标注，不得当作纯 grad 轴的点。

---

## §5 本件不主张什么

- **`percent_dense` 下侧（0.01→0.005）本件不测** —— 这是**已知缺口，显式登记**：
  历史 A5（`percent_dense` 0.005 单键）在旧栈上 57.37 vs 43.87 = **+30.7% 更差**，
  但那是旧栈 / async / 非标准序列，不可当作本栈证据。本件因 10-run 纪律上限（渐进阶梯
  「禁止首跳 ≥10 run 的批」）只开 2 臂 7 run；若两臂都判 `WORSE` 而剂量轴仍需彻底闭合，
  `pd 0.005` 作为**下一轮独立立项**（3 run）。
- 不与历史 A2（49.40 vs 43.87）作差值比较（旧栈 / async / 非标准序列 / 两键混杂，四条全不满足）。
- 不与 2060 async 剂量-响应（14.37/9.30/10.52/10.46）作并列（跨机 + 跨口径 + n=1）。
- 只跑 `person_tracking` ⇒ 不主张跨序列泛化。
- 剂量是**配置**问题，不是机制贡献；即便出正面读数也不进贡献栏（`P3-D2-025`）。
- 本件**不**解释 A4 为何失败，也不为 A4 翻案。

---

## §6 时间盒与执行阶梯

| 阶段 | 内容 | 预计 |
|---|---|---|
| P0 | prereg + 两臂配置 + 判读器 + 契约单测 | 20min |
| P1 | 同步代码 → 派发 7 run（双卡） | ~5min |
| P2 | R-valid 闸判读 | 5min |
| P3 | 机判 + 判决落盘 + 账本 `P3-D2-039` | 30min |

**硬顶**：2026-11-07 08:00。到点按已完成最高阶段收尾，**不加 run**。
失败处置：单 run rc≠0 ⇒ 补跑最多一次（同 config 同 seed）；二次失败即止损。

---

## §7 机械清单（判读器须产出）

`scripts/paper3_bpw/judge_dose_scan.py`，JSON 键：
`per_arm[arm].verdict`、`per_arm[arm].median_delta_ate_cm`、`per_arm[arm].same_sign`、
`per_arm[arm].min_gauss_ratio`、`per_arm[arm].max_gauss_ratio`、
`per_arm[arm].max_psnr_drop_db`、`per_seed[arm][s].{delta_ate_cm,gauss_ratio,psnr}`、
`joint_verdict`、`claim_floor_cm`、`gauss_ratio_band`、`n_frames_expected`、`reasons`。

负对照（单测至少五条）：
① 全零 Δ ⇒ `BELOW_CLAIM_FLOOR`；② Δ 异号 ⇒ `SEED_UNSTABLE`；
③ ATE 改善但 ratio > 1.5 ⇒ `DOSE_CONFOUND`；④ ATE 改善但 ratio < 0.5 ⇒ `DOSE_CONFOUND`；
⑤ ATE 改善但 PSNR 掉 1dB ⇒ `DOSE_CONFOUND`；
⑥ 两臂均 `WORSE` ⇒ `joint_verdict = BOTH_SIDES_WORSE`。
