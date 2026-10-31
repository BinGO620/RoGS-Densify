# 审计：历史致密化实验族（论文 3 Phase 0 前置核验）

**审计时间**：2026-10-27
**审计人**：Claude（论文 3 会话，paper3-densification 分支）
**状态**：✅ 已完成（只读核验；未启动任何 GPU run、未改任何代码）
**对应任务**：HANDOFF next_actions[0]「审计根目录已有致密化实验，区分可复用 baseline 与历史结果」

---

## 0. 审计结论（TL;DR）

1. **两个致密化实验族已完整归档**：`densification_ablation` 与 `selective_densification`
   是 18 族已关闭族中的 2 族，四件套（configs/scripts/tests/results）齐全，位于
   `archive/closed_families/`；工作树顶层 `results/` 无对应活区。归档提交 `2c03fab4c`
   （2026-10-10）为纯 rename（19862 条 R、0 新增），只搬 HEAD 已跟踪文件。
2. **机制代码仍存活于共享代码，默认关闭逐位兼容**：`utils/selective_densification.py`
   （249 行）+ 后端接线 `utils/slam_backend.py:396,829,847` + 模型侧
   `gaussian_splatting/scene/gaussian_model.py:1295+`（per-Gaussian threshold /
   percent_dense 向量路径）；`configs/rgbd/tum/base_config.yaml:240` 门控
   `enabled: false`，默认路径与主线逐位一致（有单测覆盖）。
3. **历史判决为负向/已止损，旧数字不得作为论文 3 新结果**：selective_densification
   30 个正式 run 全部在 moving_obstructing_box（基线 ATE 44cm，非文献标准动态子集）
   上做相对优化，绝对值无竞争力；唯一两次复现的 ATE 改善是**全局激进 clone**（A4/B1，
   grad 0.0002→0.0001 + percent_dense 0.01→0.02，约 -29%），代价是高斯数 2.1×～6.5×
   与 PSNR 下降——这是 Phase 0 必须正面处理的对照，不是可白拿的基线。
4. **可复用资产**（论文 3 可放心引用）：
   - 机制代码默认关闭逐位兼容 + 单测（bit-identical 承诺在实现与测试中）；
   - **深度符号账本更新**（`update_ledger_depth_signed`，|z_gauss−obs|≤0.05m 门）
     是唯一过安慰剂门禁的信号（B2d 41.9cm vs 安慰剂 49.0cm，2/3 seed 配对胜）；
   - 分层信号-剂量-安慰剂实验结构、渲染-跟踪-效率三件套证据格式；
   - 判据纪律：ATE 第一指标、绝对竞争力（≤5cm，目标 2-3cm）、安慰剂区分机制与剂量。

---

## 1. 归档位置与完整性

| 族 | 归档路径 | 四件套 |
|---|---|---|
| densification_ablation | `archive/closed_families/densification_ablation/` | ✅ 全（configs 7 / scripts 1 / tests 1 / results 21 run） |
| selective_densification | `archive/closed_families/selective_densification/` | ✅ 全（configs 15 / scripts 4 / tests 1 / results 27 run 目录） |

- 归档提交 `2c03fab4c`（「重构 Step 3c」）纯 rename，只搬 HEAD 已跟踪文件；
  `.gitignore` 新增 F2 段镜像 archive/ 忽略语义（防再犯误扫）。
- 工作树 `results/` 顶层无这两族活区（现役 8 线 + README.md）；`results/README.md`
  B 节将两族列入「已关闭族归档」；`scripts/health_check.py` 将两族列入
  `ERA_EXEMPT`（v1/早期栈、无 SWBA 属设计状态，非简化臂外推风险）。
- 原始表格数据抽查完整：`A0_default/tables/`、`A4_aggressive_clone_seed0/tables/`、
  `B0_default_seed0/tables/`、`B2d_depth_signed_seed0/tables/` 的
  tracking/efficiency/mapping_raw.csv 均在，归档可复现。

## 2. 历史判决（NOTES.md 单一事实源 + 各 verdict，以下数字不再复跑）

### 2.1 densification_ablation Phase 0（2026-09-02，moving_obstructing_box，7 臂 × 3 seed = 21 run，HEAD 8696ca611）

| 臂 | 改动 | ATE (cm, 3-seed mean) | vs A0 | 判 |
|---|---|---|---|---|
| A0 默认 | — | 44.44 | — | 对照 |
| A1 延迟 | densify_from 500→3000 | 40.55 | −8.7% | 弱信号 |
| A2 高阈值 | gaussian_th 0.9 / grad 0.0004 | 49.40 | +11.2% | 有害 |
| A3 高频 | update_every 150→50 | 46.60 | +4.9% | 无改善 |
| **A4 激进 clone** | **grad 0.0001 / percent_dense 0.02** | **31.36** | **−29.4%** | **方向成立** |
| A5 保守 split | percent_dense 0.005 | 57.37 | +29.1% | 有害 |
| A6 无致密化 | densify 禁用 | 55.80 | +25.6% | 有害 |

关键发现（判决原文）：**A4 增加高斯密度改善动态场景位姿**（与 TAD-GS「短寿命动态高斯
致密化不足」诊断一致）；**抑制致密化全错**（问题不是太多而是策略不对）；**ATE 与 PSNR
反相关**（A4 ATE 最好但 PSNR 20.12 最低，A5 PSNR 22.24 最高但 ATE 最差）——
PSNR 不能判断跟踪方法，ATE 是第一指标。

### 2.2 selective_densification Phase 1a/1b/1c（2026-09-03，同序列，30 run）

- **1a 残差 static_prob 信号否决**（HEAD bcfb13f45）：B2（动态侧激进）47.60 劣于
  安慰剂 B4 43.83，仅 1/3 seed 胜；锚点 B0/B1 复现成功（43.73/32.88 vs Phase 0
  44.44/31.36）；遮挡混淆归因失效模式实锤（被挡静态背景高残差→误标动态→遮挡边界
  过致密化，B2_seed1 高斯 91.9k 且 ATE 62.2cm）。
- **1b 深度符号信号过安慰剂门禁**（HEAD 594c2f65）：B2d 41.85 vs 安慰剂 B4d 49.04，
  配对 2/3 seed 胜（36.45<39.13 ✓；53.23>45.54 ✗；35.88<62.45 ✓）——信号携带真实
  空间信息；但相对 B0 绝对改善仍弱（mean −4%，配对 1/3），高斯稳定 ~70k（B1 为
  80-275k），**剂量不足为主因**。
- **1c 剂量升级否决**（HEAD 1f175d90）：anchor 0.9→0.95，B2dp 57.28 劣于安慰剂
  B4dp 51.97（1/3 seed 胜）——受治人群过宽 = 回到盲目激进，淹没信号信息量。
- **统计校准**（Codex 无 GPU 分析）：n=3 下任何效应（含 B1 锚点 −10.85cm）配对
  置换 p 均 ≥0.5，所有「通过门禁」表述只读作**方向一致性证据**，非统计显著。

### 2.3 用户复核后总判决（NOTES 行 260 / verdict 末尾）

> **Phase 1 整体记为未达标方向，已止损**（1d 跨序列轮启动后按校准终止，无有效数据）。
> B1=全局激进是唯一两次复现的 ATE 改善，但 32.88cm 的绝对值同样不具竞争力。
> 所有后续工作以标准动态子集 + 绝对 ATE（≤5cm，目标 2-3cm）为第一验收标准。

两条违纪原因（记录在案）：①**战场选择错误**——moving_obstructing_box 基线 44cm、
不在文献标准 Bonn 动态子集（balloon/crowd/person_tracking 家族，published ATE
2-10cm；本仓 v1 在 balloon 3.09cm）；②**机制解释越界**——失效解释只用于指导止损
与改善决策，不作为结论性知识收尾。

## 3. 代码版本与存活状态

| 组件 | 状态 | 证据 |
|---|---|---|
| `utils/selective_densification.py`（249 行） | 存活于共享代码 | 模块头 + 配置门控 |
| 后端接线 `utils/slam_backend.py:146,396,829,847` | 存活 | 调用点仍在 |
| 模型侧 `gaussian_splatting/scene/gaussian_model.py:1295+` | 存活 | `densify_and_split` 支持 per-Gaussian threshold/percent_dense 向量 |
| 配置默认 | **关闭** | `configs/rgbd/tum/base_config.yaml:240` `enabled: false` |
| 默认关闭逐位兼容 | 承诺在实现与测试中 | 模块 docstring + 归档单测 |
| 机制提交链 | 全在 git 历史 | `c77321fa3`→`bcfb13f45`→`34ade3ebf`→`594c2f65d`→`1f175d90b`→`c6a71008c` |

默认致密化参数（tum base_config，A0/B0 行为 = 共享代码现状）：
`gaussian_update_every: 150`、`gaussian_th: 0.7`、`densify_from_iter: 500`、
`densify_until_iter: 15000`、`densify_grad_threshold: 0.0002`、
`percent_dense: 0.01`、`densification_interval: 100`、`opacity_reset_interval: 3000`。

## 4. 对论文 3 / Phase 0 的直接含义

1. **on 机制不能是「复制 A4 全局激进」**——旧判决已表明全局激进以 PSNR 下降和高斯
   失控为代价，绝对值无竞争力；把 A4 当作新贡献或新基线都会撞「旧结果冒充新结果」红线。
   A4/B1 的定位只能是**参照锚点**（说明「动态场景需要更多/更密高斯」的方向信号）。
2. **Phase 0 战场必须换**：旧阶段在 moving_obstructing_box 上优化相对指标被判无效
   战场。论文 3 选标准动态子集（balloon/crowd/person_tracking 家族，本仓 v1 自证
   balloon 3.09cm 可达），判据锚定绝对 ATE（≤5cm，目标 2-3cm）。
3. **可借的最小机制形态**（仅作候选，最终由下一轮收窄决定）：TAD-GS 式时间感知
   （VAD/TAT）+ 本仓已过安慰剂门禁的深度符号账本信号。历史表明「信号正确而剂量保守」
   只换来 41.9cm 的平庸绝对值——机制必须同时解决剂量/预算问题，否则无转化价值。
4. **文献空位核对**（gap_analysis #15 + NOTES 行 295-297）：「延迟/寿命感知致密化 ×
   在线 SLAM 插入的耦合」在线侧仍为空（TAD-GS 离线全序列、RobustSplat 离线延迟致密化、
   SplatMAP 离线稠密点云驱动）；论文 3 的定位面与 Gap G3 一致，但**新机制 + 新判据**
   才构成主张，旧实验只作背景。
5. **Phase 0 设计必须预注册**：`paper3/PREREGISTRATION.md` §3 明确标注「不是已锁定
   判据」，正式锁定前必须回答指标定义、分母、帧集、噪声地板、失败处理、多指标冲突优先级。
6. **复用纪律**：旧三件套证据格式（tracking_raw/mapping_raw/efficiency_raw + 渲染对照）
   直接复用为论文 3 证据模板；旧数字只作对照与历史记录，不作新结果。

## 5. 证据链

- 归档结构：`archive/closed_families/{densification_ablation,selective_densification}/`
  （四件套齐全；results/evidence/ 含 manifest.json + verdict.md）
- 判决原文：两族 `results/evidence/verdict.md`（densification_ablation 3.3KB；
  selective_densification 9.9KB，含 1a/1b/1c 补充与统计校准、用户复核降格记录）
- manifest：`manifest.json`（git_head 8696ca611 / bcfb13f45；arms/seeds/result 摘要）
- NOTES.md 单一事实源：行 36-39（实验台账）、254-266（两族结论）、290-297（致密化文献）
- 归档提交：`2c03fab4c`；机制提交：`c77321fa3`→`c6a71008c`（Phase 1d）
- `results/README.md` B 节（已关闭族导航）；`scripts/health_check.py:776`
  （ERA_EXEMPT 含两族）
- 配置默认：`configs/rgbd/tum/base_config.yaml:240-260,316-372`
- 机制代码：`utils/selective_densification.py`；接线 `utils/slam_backend.py:146,396,829,847`
- 文献卡：`resources/lit_dyn_mapping/papers/tad_gs.md`（VAD/TAT/TOW）、
  `robustsplat.md`（延迟致密化）、`gap_analysis.md` #15（在线耦合空位）
- 原始表格抽查：`A0_default/tables/`、`A4_aggressive_clone_seed0/tables/`（online_num
  _gaussians 155800，ATE 30.40）、`B0_default_seed0/tables/`、`B2d_depth_signed_seed0/tables/`
