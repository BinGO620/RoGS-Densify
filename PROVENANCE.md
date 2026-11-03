# PROVENANCE — 本仓库与 monogs-ours 的对应关系

- **源**：`/data/monogs-ours` @ `1b9e3fff7`（分支 `feat/bpw-densification`，2026-11-03
  回灌：FDose n=6 判决收口节点）。上一基线 = `31b0f0367`（2026-10-31）。monogs-ours 本身**不拆分、不修改**，
  作为备份库保留。
- **构建方式**：按 manifest（复制清单）从源复制 → 减法（删论文2 专属机制）→ 验证。
  重建命令：`python /data/monogs-export/copy_by_manifest.py --manifest
  /data/monogs-export/manifests/rogs_densify.yaml --dst <新目录>`，再按本文件修改点表
  重放手术。

## 组织原则

1. 解耦靠减法不靠重写：只删文件与分支，不改名、不重构 `slam_frontend/slam_backend`。
2. 文件布局与 monogs-ours 一致：任何文件可与备份库逐字节 diff。
3. 「本论文的代码」= 下面两张表，显式列出。
4. 主干同源：RoGS-SLAM / RoGS-Map / RoGS-Densify 的共享主干文件来自同一源 commit；
   跨仓 `diff -r utils/` 的差异 = 各论文机制差异。
5. 继承显式化：论文1（MMM 2027）机制模块保留在本仓库，作为实验臂的共同基线平台
   （`combined_prune/method.yaml` 默认开启），本仓库不修改它们。
6. 配置继承链原样保留（`inherit_from`/`method_from`）。
7. 判据件与代码同仓；测试分 mechanism（CPU 单测）/ pipeline（冒烟）两层。

## 表 1：本论文（论文3）的机制文件

| 文件 | 角色 |
|---|---|
| `utils/densification_selection.py` | 致密化选点核：BPW（`persistence_budget`）/ CGB（`coverage_gap`，已判 DESIGN-INVALID）/ FDose（`frozen_dose`）三形态 |
| `utils/selective_densification.py` | 前身/回退路径（`SelectiveDensification` 的 static_prob ledger 形态，Phase 1） |
| `utils/slam_backend.py` 中两处 dispatch | `compute_coverage_gap_knobs`/`compute_frozen_dose_knobs`/`compute_per_gaussian_knobs` 接线（主干修改，见下） |
| `configs/experiments/paper3_bpw/` | 21 个臂配置（bpw off/on/negctl、cgb g0/g1、fdose k0/G/S、p0 sweep） |
| `configs/experiments/combined_prune/method.yaml` | 方法主干（与论文1 共享，`method_from` 目标） |
| `scripts/paper3_bpw/` | runner（run_fdose_l1/run_three_arms/run_p0_sweep/…）+ 判据机（judge_fdose/check_fdose_gate/make_dose_plan/judge_p0a/judge_cgb_l1/check_cgb_gate/derive_seq_floors/summarize_three_arms 等） |
| `tests/densification/`、`tests/paper3_bpw/` | 三形态选点单测 + 判据机门禁（40+65 tests） |
| `results/paper3_bpw/` | 判据小件（逐 run tracking/mapping/efficiency CSV、config.yml、summary/trj_final/stats_final JSON、console.log、.done、FDose selection_trace） |
| `paper3/PREREGISTRATION.md`、`paper3/PROBLEM.md`、`paper3/results/evidence/` | 预注册（判据先锁）、问题定义、审查/判决证据（67 件） |

## 手术执行方式（2026-11-03 起：已脚本化）

表 2 的减法手术**不再靠人工重放**：`/data/monogs-export/manifests/rogs_densify.yaml` 的
`delete:` 段列 9 个 CVM 专属模块，`overlay:` 段列三个主干文件的术后版本
（`/data/monogs-export/overlays/{slam.py,utils/slam_backend.py,utils/slam_frontend.py}`）。
`copy_by_manifest.py` 最后执行 overlay ⇒ 一键重建**包含手术**。

**依据（2026-11-03 实测）**：升级前先跑了一次纯超集复制，9 个模块全部复活、主干手术
（slam.py 61 行 / backend 190 行 / frontend 43 行）被覆盖——与 2026-11-01 RoGS-Map 事故同根因。
手术后复跑：`deleted=9`、复活模块 0、三处主干残留全 0。

**过程件不入快照仓（2026-11-03）**：FDose 的 `results/paper3_bpw/**/fdose_*_selection_trace.csv`
（23 件 / 906M）**不再入库**。判据链不依赖它：A4 起每 seed 的 F3a′/share/池基线已固化为
gate JSON，判决只消费 gate 工件；judge 的 R6/R7 是报告项，缺 trace 会显式 `missing_trace`。
**可追溯**：monogs-ours 同名路径保留全量（唯一事实源），需重算时从源仓取。
（2026-11-03 验证：untrack 后 judge 在快照仓内仍 rc=0 并逐字复现 INCONCLUSIVE。）

**维护约定**：monogs-ours 的主干三文件若有真实改动，必须按表 2 重放手术生成新 overlay
后再回灌；否则 overlay 会冲掉新改动。

## 表 2：对主干文件的修改（相对 monogs-ours 同名文件）

目的：移除论文2（CVM2027）专属机制的文件与接线。所有删除均为**默认关闭分支**，
主线（论文3 所有臂）行为不变。

### slam.py

| 源行号 | 删除内容 |
|---|---|
| 41–47 | `loop_closure`/`dba_lite` 顶层 import |
| 419–461 | P2b/DBA-oracle/DBA-v0/LoopClosure 结尾三臂（`dba_lite_oracle_enabled`/`dba_lite_enabled`/`loop_closure_enabled` 分支） |
| 470–479 | 保存最终 PLY 后的 DynPort 因果掩码收尾（`dynport_causal_log`） |

### utils/slam_backend.py

| 源行号 | 删除内容 |
|---|---|
| 142 | `dba_lite` import |
| 1595–1601 | P2a DBA 诊断块（`color_refinement` 开头） |
| 1786–1787, 1794–1796 | `save_timing_stats` 里 DynPort 注释与 `dynport_time_s/dynport_frames` 键 |
| 1837–1850 | `push_to_frontend` 的 DynPort 跟踪隔离块（动态行不透明度打 0） |
| 1858–2008 | `_dynport_setup`/`_dynport_step`/`_dynport_fit`/`_dynport_sync_occ` 四个方法 |
| 204–208 | `__init__` 的 `_dynport*` 属性 |
| 2211–2213 | 主循环 `_dynport_step` 调用点 |

### utils/slam_frontend.py

| 源行号 | 删除内容 |
|---|---|
| 52 | `swba` import |
| 413–415 | `__init__` 的 Route B SWBA 初始化 |
| 2928–2962 | `run()` 里 Route B SWBA 健康门与 `on_new_keyframe` 调用块 |

## 删除的模块（9 个，论文2/CVM2027 专属）

`utils/{swba, loop_closure, place_recognition, mast3r_verify, dba_lite,
dyn_port_buffer, dyn_port_online, dyn_port_offline, dynport_causal_log}.py`

（它们在 RoGS-Map 仓库中保留。）

## 保留决策（如实记录）

1. **默认关闭的平台开关集**保留未删：`transient_map`/`object_transient`/`mope_layer`/
   `obsdebt`/`occupancy_memory`/`depth_reanchor`/`flow_mask*`/`mask_quality`/
   `mask_stability`/`causal_render_log`/`mapping_probe`/`oracle_pose`/`gtmc_mask`/
   `bootstrap_vo`/`full_frame_pose`/`coarse_pose`/`visibility_window`/
   `reliable_tracking`/`tri_reliability`/`alpha_lifecycle` 等。理由：它们是
   `base_config.yaml` 开关面的组成部分、顶层 import 织入主干，属冻结平台的一部分；
   全部默认关闭，对论文3 所有臂零行为影响。删除它们收益小、手术风险大。
2. **`configs/rgbd/`** 只保留论文3 用到的序列（bonn: base/person_tracking/balloon；
   tum: base_config）；其余序列配置未带。
3. **判据件取舍**：`results/paper3_bpw` 中 CGB（已判 DESIGN-INVALID）与 BPW 的
   `*_selection_trace.csv`（约 165 MB 逐事件过程 dump）未带入；其判决/摘要仍在
   `paper3/results/evidence/`。FDose 现役线的 selection_trace 全部保留。
4. monogs-ours 的开发管理件（DISCIPLINE/DECISIONS/NOTES/LOG/PITFALLS、.zcode/.claude、
   health_check、其余实验族的 configs/scripts/tests/results、papers/、biyelunwen/）
   一律不带。

## 数字验证矩阵（论文3 无已发表表，验证 = 门禁 + 等价性）

| 项 | 方式 | 状态 |
|---|---|---|
| 机制选点逻辑 | tests/densification 40 个 CPU 单测（BPW/CGB/FDose 三形态） | 全绿 |
| 判据机 | tests/paper3_bpw 65 个门禁（judge/check/plan 契约） | 全绿 |
| FDose 40 帧冒烟 | 三臂全通，判据与 `fdose_gate_smoke_2026-10-31.json` 同源（预注册证据随仓） | 通过 |
| 裁剪等价性 | 冒烟 A/B vs monogs-ours@31b0f0367 纯净源（见下） | 通过 |
| 580 帧全量 | 未跑（D2-011 待用户答复 + G4 核销，见 PREREGISTRATION） | — |
| 配置同源 | 27 个 yaml 与 monogs-ours@31b0f0367 逐字节一致（parity check 2026-11-01） | ✓ |

## 验证记录

| 项 | 结果 |
|---|---|
| AST import 闭包 | 95 文件检查，无缺失（`closure_check.py`） |
| `py_compile` slam.py / slam_frontend.py / slam_backend.py | 通过 |
| `pytest tests/densification tests/paper3_bpw tests/test_config_valid.py` | **105 passed**（monogs-ours 基线 96 + config 校验） |
| submodule pin | `diff-gaussian-rasterization@43e21bff`、`simple-knn@44f764299`（与 monogs-ours 历史及 upstream MonoGS 一致） |
| 2060 冒烟 A/B（40 帧，bpw_off，seed 0） | 裁剪仓 vs monogs-ours@31b0f0367 纯净参照：ATE RMSE 1.1688 vs 1.1718 cm（Δ=0.003cm ≈ 0.26%，CUDA 非确定性量级，低于同配置跨批噪声 0.18–0.62cm）；stats_final/per_frame_ape/tracking_raw 全字段一致（仅时间戳与噪声级小数差）。**减法未改变管线行为** |
| **2026-11-03 回灌 @ `1b9e3fff7`** | parity 全部同源（25/25 configs）· pytest **121 passed** · 40 帧冒烟 bpw_off ~/. 裁剪仓 **1.1818 cm** vs 纯净源参照 1.1718 cm（Δ=0.010 cm ≈ 0.85%，低于跨批噪声带 0.18–0.62 cm）⇒ 等价性通过 · closure_check 报 `gui`/`utils` 两项为**工具误报**（纯净源同报，包名解析问题）· submodule pin 保持 `43e21bff`/`44f76429` · 新带入 FDose n=6 判决工件与 seeds 3/4/5 run 产物 |

## 归档原则（2026-11-04 登记；用户指令，适用于每一个仓库）

- **工作区永远只留最新**：过时的版本/草稿/历史快照一律移入本仓 `archive/`（就近归档，
  命名 `{语义}_{YYYY-MM-DD}`），不散落工作区顶层。
- **归档 ≠ 删除**：归档件是证据键，账本指针不追改；每处归档配 `README.md` 并在仓内
  索引登记。
- **本仓独立性**：实验一律回 monogs-ours 做，本仓只收"已判据确认"的成果快照
  （四步同步见 monogs-ours `/data/master-thesis/WORKFLOW.md`）；本仓自持门禁与
  PROVENANCE，不依赖 monogs-ours 工作区即可复验。
- **里程碑触发同步**：只在判决落地/投稿等里程碑做 manifest 重灌 + gate 全跑 +
  PROVENANCE 登记；平时不同步（避免快照漂移）。
