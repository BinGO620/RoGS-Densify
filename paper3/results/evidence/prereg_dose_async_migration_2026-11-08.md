# 剂量前沿 async 迁移检查预注册（P3-D2-043）—— 2026-11-08

**状态**：判据锁定于本批任何 run 之前（本件随 configs/tests/判读器同 commit 入库，先于派发）。
**触发**：用户 2026-11-08 拍板「冲投稿：现在立项 GPU 增量」；母件判决
（`dose_oversupply_verdict_2026-11-08.md` §三）登记的缺口 = 「地图规模 0.2× 的效率收益
在仪器口径下测得；**async 部署下的对应收益未测**」。本批补的就是这个缺口：
**剂量前沿结论在部署口径的迁移状态**——迁移什么、不迁移什么，如实登记。

---

## §1 口径声明（红线，先于一切判读）

1. 本批全部数字 = **async 部署口径**（`Training.single_thread`/`Dataset.single_thread`/
   `Rasterizer.deterministic_backward` 均不设 ⇒ 默认关，无确定性套件环境）。
   与仪器口径（单线程 + det-raster + 确定性套件）**永不混引**——两口径数字不得进同一张表；
   跨口径只允许「方向是否一致」级别的陈述，且必须显式写明两侧口径。
2. async 绝对 ATE 不与文献/前作表并列（协议不同，纪律 #7/#12）。
3. **比例量（高斯比、PSNR 差）在口径内部成立**：本批 ratio = async/async，
   与仪器口径 ratio 的比较限于「量级带」级（门限见 §4，按仪器读数 + 余量锁定）。

## §2 装置自差准入门（测量口径 #6 核算，引用既有测量）

- 引用 `device_floor_3090_2026-11-05.md`（同机同 config 同 seed 实测）：
  **ATE 自差最高 2.14cm**（dose_tau2x 两样本；off pt 三样本跨 1.75cm）；
  **online 高斯数极差 +96.8%**（宽多模态）；确定性套件全开仍 +65.3%（P3-D2-024）。
- ⇒ 本批**不设任何带宽 < 包络的臂级 ATE 判效门**：所有臂级 ATE 出口按
  「包络三档」机械归类（§4-C3/C4），包络内一律记 **ENVELOPE_UNJUDGEABLE**（不是"过"也不是"不过"）。
- 本批不重测自差（引用上述既有同装置测量即为本门核算）；若判决需要更细噪声参考，另行立项。

## §3 设计（臂集与 run 账；单变量约定沿母件 P3-D2-039：percent_dense 全 0.01，纯 grad 轴）

### 3.1 pt（内部最优迁移，3 臂 × seeds 0/1/2 = 9 run）

| 臂 | 配置（全部为既有 async 基座） | 定义 |
|---|---|---|
| off | `maskstat_off_person_tracking` | Combined-Prune 栈，机制全关（历史 off 基线 async 版） |
| tau4x | `dose_tau4x_person_tracking` | grad 0.0008（0.0002 × 4） |
| zero | `dose_zero_person_tracking` | grad = 1000000000（纯整数字面量，PITFALLS 已登记），densify 全关 |

### 3.2 crowd / mnobox（异质性迁移，2 臂 × seeds 0/1 = 8 run）

| 序列 | off 臂 | tau4x 臂 | 帧数 |
|---|---|---|---|
| crowd | `async_off_crowd`（**新**） | `dose_tau4x_crowd`（既有 async 基座） | 928 |
| moving_nonobstructing_box | `async_off_moving_nonobstructing_box`（**新**） | `dose_tau4x_moving_nonobstructing_box`（既有） | 778 |

- **balloon 不入**：仪器口径 +0.24 亚地板（只记方向），async 迁移无判力，不花算力。
  > **2026-11-08 A1 追注**：balloon 的 n=2 "+0.24 亚地板方向"读数已在第三 seed
  > 补批降级为 UNJUDGED（三 seed 异号）——"无判力"由此更强，排除结论不变。
- **总账 = 17 run**（9 + 4 + 4），全长（`max_frames=0`），async 派发两卡串行链
  （`run_dose_async_migration.sh`），同臂禁并发。
- **派发机器落纸（G3 次要整改，2026-11-08）**：远程 3090
  （`jiangwenheng@172.16.227.24`，双卡），仓路径
  `/home/jiangwenheng/cron/monogs-ours`，Python
  `/home/jiangwenheng/anaconda3/envs/monogs-ours-3090/bin/python`；派发前
  `sync_to_remote.sh` 三方一致 + nvidia-smi 实时占用检查；runner 以
  `MONOGS_REPO`/`MONOGS_PY` 覆盖默认值。批 1（Amendment A1）先行，本批接续同卡链。
- **迁移预测（判据先行，预注册预期）**：预计 C1/C2（地图规模/PSNR）迁移成立、
  ATE 轴在包络内不可判（crowd +0.72 / mnobox −0.50 均 < 2.14cm 包络）——
  预期出口 = `MAP_PSNR_TRANSFERRED_ATE_ENVELOPE`。预期失败非判据失败，路由全程机械。

### 3.3 单变量机械守护（契约单测锁定）

- `async_off_crowd` vs `dose_tau4x_crowd`、`async_off_moving_nonobstructing_box` vs
  `dose_tau4x_moving_nonobstructing_box` 解析后 diff 恰为
  {opt_params.densify_grad_threshold, Results.save_dir}（同链派生，inherit 相同）；
- pt 三臂 vs `maskstat_off_person_tracking` diff 恰为
  {opt_params.densify_grad_threshold, Results.save_dir}；
- 七臂共享 Combined-Prune 基线栈，组件旗（SemanticMask/ReliabilitySignal/
  DeferredCommit/RobustTracking 等）全臂一致——**措辞更正（G3 次要整改）**：
  原文"无语义掩码段"失实，基线栈自带语义掩码段且七臂一致，单变量由
  "解析后 diff 恰为两键"的契约单测整体锁定；
- 四臂均无任何仪器开关键、`SelectiveDensification.enabled: false`。

## §4 判据（机械，fail-closed；判读器 `judge_dose_async_migration.py`，INVALID ⇒ rc=2）

### 4.0 前置门（逐 run）

`.done` 锚 `finished_rc0=yes`（缺即拒）＋ 帧数 = 序列全长（pt 580 / crowd 928 /
mnobox 778，`--pair` 显式传参）＋ tracking/efficiency/mapping 读数可解析且有限。
任一不过 ⇒ 该对 `RUN_INVALID`，判读器 rc=2。

### 4.1 C1 地图规模迁移（4 对）

ratio = tau4x(或 zero)/off 的 `online_num_gaussians`，逐 seed 取比值、报 median：

| 对 | 仪器口径读数（参照） | TRANSFERRED | NOT_TRANSFERRED |
|---|---|---|---|
| crowd tau4x/off | 0.1971–0.2553 | median ≤ **0.40** | median ≥ 0.70 |
  > （2026-11-08 追注：参照带为 n=2 vintage；A1 n=3 后 crowd 比值中位 0.239、
  > 新样本 0.2182/0.2634——带内判断不受影响，历史参照值不追改。）
| mnobox tau4x/off | 0.1971–0.2553（同族） | median ≤ **0.40** | median ≥ 0.70 |
| pt tau4x/off | 0.215–0.246（dose_scan） | median ≤ **0.40** | median ≥ 0.70 |
| pt zero/off | 0.146–0.152 | median ≤ **0.30** | median ≥ 0.60 |

门限依据 = 仪器读数上限 × ~1.57（0.40）与 ~2×（0.30），给 async 计数噪声（+96.8%
是同臂绝对量波动，比值口径下按上述余量设防）留出空间；其间 = `UNJUDGEABLE_BAND`。

### 4.2 C2 渲染代价迁移（pt zero/off）

static PSNR 差（zero − off）逐 seed、报 median：median ≤ **−4dB** ⇒ `TRANSFERRED`
（仪器 −6.3~−6.6）；median ≥ −1dB ⇒ `NOT_TRANSFERRED`；其间 = `UNJUDGEABLE_BAND`。

### 4.3 C3 pt ATE 方向迁移（包络三档，n=3）

Δ(zero − off)、Δ(tau4x − off) 逐 seed、报 median，与包络 2.14cm 比较：

- |median| > 2.14 ⇒ `DIRECTION_JUDGED`（报符号；与仪器口径读数同号/反号分别登记）；
- |median| ≤ 2.14 ⇒ `ENVELOPE_UNJUDGEABLE`（预设最可能出口）；
- seeds 异号 ⇒ `SIGN_UNSTABLE`（n=3 下任两 seed 异号即触发，不取中位假装有值）。

### 4.4 C4 crowd / mnobox ATE 方向迁移（n=2，**诊断级报告项**）

同 §4.3 三档，但**包络 2.14cm 系 pt 系 config 实测外推**（device_floor_3090 只测了
pt 系；G3-C4 整改声明）——C4 的 DIRECTION_JUDGED 一律记 **provisional（诊断级）**，
只作报告项并标注 `pt_config_extrapolated_provisional`，**不参与总出口合成**
（合成只消费 §4.3 的 pt 对）。n=2 本就只主张方向（母件纪律），量值不主张、
不与仪器口径数值并列。若判决需要 crowd/mnobox 的自有包络，另行立项实测。

### 4.5 总出口（机械合成）

| 出口 | 条件 |
|---|---|
| `RUN_INVALID` | 任一对前置门不过 |
| `MAP_PSNR_TRANSFERRED_ATE_ENVELOPE` | C1 四对全 TRANSFERRED 且 C2 TRANSFERRED，C3（pt 对）∈ {ENVELOPE_UNJUDGEABLE, SIGN_UNSTABLE, DIRECTION_JUDGED 同号}（**预期出口**）；C4 不参与合成 |
| `FULL_TRANSFER` | MAP_PSNR_… 条件 + 至少一个 **C3（pt 对）** DIRECTION_JUDGED 且与仪器口径**同号** |
| `CONTRADICTED` | 任一 C1/C2 NOT_TRANSFERRED，或任一 **C3（pt 对）** DIRECTION_JUDGED 与仪器口径**反号**（C4 反号不触发，仅报告） |
| `MIXED` | 其余（含 UNJUDGEABLE_BAND 组合） |

路由优先级（互斥）：`RUN_INVALID` → `CONTRADICTED` → `FULL_TRANSFER` →
`MAP_PSNR_TRANSFERRED_ATE_ENVELOPE` → `MIXED`（FULL 严格强于 MAP_PSNR_…，
故 MAP_PSNR_… 实义 = "C1/C2 迁移且**无任何 pt 对**判出方向"）。

**判读命令落纸（G3-C3 整改，2026-11-08；roots 为 save_dir/datasets_bonn/<同名>，
run 目录在 `seed_<n>/` 下；`<HEAD>` = 派发时 `git rev-parse --short HEAD` 实值）**：

```
python scripts/paper3_bpw/judge_dose_async_migration.py \
  --pair pt_zero:results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/maskstat_off_person_tracking:results/paper3_bpw/dose_zero_person_tracking/datasets_bonn/dose_zero_person_tracking:580:zero:0,1,2 \
  --pair pt_tau4x:results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/maskstat_off_person_tracking:results/paper3_bpw/dose_tau4x_person_tracking/datasets_bonn/dose_tau4x_person_tracking:580:tau4x:0,1,2 \
  --pair crowd:results/paper3_bpw/async_off_crowd/datasets_bonn/async_off_crowd:results/paper3_bpw/dose_tau4x_crowd/datasets_bonn/dose_tau4x_crowd:928:tau4x:0,1 \
  --pair mnobox:results/paper3_bpw/async_off_moving_nonobstructing_box/datasets_bonn/async_off_moving_nonobstructing_box:results/paper3_bpw/dose_tau4x_moving_nonobstructing_box/datasets_bonn/dose_tau4x_moving_nonobstructing_box:778:tau4x:0,1 \
  --envelope-cm 2.14 --require-head <HEAD> \
  --out paper3/results/evidence/dose_async_migration_judge_2026-11-08.json
```

判读器 collect() 校验 `.done` 的 `caliber==async_deploy` 且 `head==<HEAD>`
（G3-C1/C3：历史 rc0 run——含 2060 provisional 与仪器口径 run——一律拒收，
防止损/失败场景静默顶替与跨设备污染；同名之差的仪器根
`instrument_dose_tau4x_*` 因其 `.done` 无 async caliber 而被机械拒绝）。

## §5 时间盒与止损

**硬顶 2026-11-09 14:00**。单 run rc≠0 补跑最多一次；二次失败止损该臂 ⇒ 该对记
`RUN_INVALID`。**语义对齐（G3-C2 整改，2026-11-08）**：判读器 fail-closed 语义 =
任一对 RUN_INVALID ⇒ **总出口 RUN_INVALID、rc=2**（不出任何判读级结论）；
其余对的对级读数仍写入 judge JSON 供诊断，但不得单独引用作结论——两处
（本节与 §4.5/判读器 route()）讲同一个故事，不存在"部分判读"路径。

## §6 本件不主张什么

- 不主张 async 口径的效应量值（包络内一切读数不可判；超包络只主张方向）；
- 不主张两口径数值可比（§1 红线）；
- 不撤销母件判决（仪器口径）——两口径读数**并存登记**，若方向冲突如实登记 `CONTRADICTED`；
- 若 C1/C2 不迁移 = 重要负读数，如实登记进判决与 NOTES（负结果不包装）；
- 评测协议不是贡献。

## §7 等价性与工件

- 本批新增 = 本 prereg + 2 个 async off 配置 + runner + 判读器 + 契约/路由单测
  （scripts/tests 层）；核心路径零改动沿母件 §3.4 结论，派发前以
  `git diff 250554d8e..HEAD --stat -- utils/ gaussian_splatting/ slam.py submodules/`
  复核为空（2026-11-08 已核，Amendment A1 同款）。
- pt off/tau4x/zero 配置为既有 async 基座（2026-10-30/11-04 立项时入库），
  本批首次以 3090 全长权威身份跑——其历史 2060 provisional 读数
  （dose_response screen）不并入本批判读（非权威，DISCIPLINE 算力条）。
- 判据工件：批日志（逐 run rc/elapsed/HEAD 锚）、judge JSON（per_seed 逐 run 锚）。
