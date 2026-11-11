# novelty_component_scheduling_2026-11-10.md — 「regime-aware 组件调度」机制轴立项前 novelty 全扫

> 任务：核查「把跟踪/建图组件栈（K / R / L）的启用集合与强度做成按在线可测 regime 信号的自适应
> 配置调度，目标 ATE 中位数+方差」在 3DGS-SLAM（尤其动态场景）文献中的占用情况。零 GPU，纯文献检索。
> 日期：2026-11-10 ｜ 执行：ZCode subagent（纯文献）+ 主会话复核 ｜ 动机证据（本仓）：
> WP-A 三因子全因子 3-seed 判决（120 run）——A2 部分冗余与 A4 序列依赖同时成立，
> 「没有单一子集在所有 regime 都必要」（`/data/RoGS-SLAM/results/evidence/wpa_factorial_verdict.md`，
> md5 `0ca4eb9564412da85d141386ffd067b4`）。**注意该件不在本仓**，见 §5.7 证据宿主问题。
> **本轮性质：只做 novelty 扫，不写 prereg、不动代码、不跑 GPU（用户 2026-11-10 拍板）。**
> **账本**：P3-D2-049（本件 + 同名一页纸 `onepager_f_axis_2026-11-10.md`，D2 呈报）。
> 修订记录：2026-11-10 G1 = Reject（3 致命/10 重大/9 次要）→ 本版逐条整改（计数、判据本体、
> 引证作用域、BORDERLINE 档、账本号；见文末 §7）。

## 0. 判定标准（四档 + 词面邻居 + 一条模态限定）

**适用范围限定（G1-M3）**：本判据只对 **3DGS-SLAM 或 dense visual SLAM**（含 NeRF-SLAM）
生效；命中表 #3/#4/#8 等特征/边缘 SLAM 只作「近邻词面」登记，不参与 COLLIDES 计数
（6/14 命中非 3DGS 系）。

- **COLLIDES**：任何已发表工作把「跟踪/建图**核心组件栈**（关键帧策略 K、鲁棒估计器 R、
  可靠性/不确定性加权 L 这类**内环组件**）的**启用集合或强度**做成按**在线可测**信号的自适应
  配置，且终点含定位精度（ATE）或面向动态在线 3DGS-SLAM。
- **BORDERLINE（新增档，G1-M1）**：自适应对象是**管线外挂模块**（语义分割模型、外部
  点跟踪器、外部位姿源）的按需启用，信号在线、场景为动态 3DGS-SLAM。**DAGS-SLAM 属此档**
  ——它的「semantic-on-demand」确实是「按在线不确定性启用/停用模块」，直译会撞 COLLIDES
  字面；但被调度的不是内环 K/R/L 组件栈，且终点是算力节省（语义模型调用次数），
  非 ATE 中位+方差。**F 轴必须显式排除「语义掩码组件」，否则此档升级为 COLLIDES。**
- **ADJACENT-1（同对象异信号）**：核心组件自适应已做，但驱动信号是**离线先验/oracle/
  数据集标签/人工设定**，非在线因果可算。
- **ADJACENT-2（同信号异对象）**：在线信号已用于**非组件配置**的目的——加权损失、选 cue、
  调超参、调输入分辨率/帧率、决定关键帧优先级、调整执行级别。
- **ADJACENT-3（词面邻居）**：UP-SLAM「Adaptively Structured」、RTGS「Workload Scheduling
  Unit」、MoE / conditional computation / early-exit / adaptive computation time 类措辞。
  含**跨域**用法（非 SLAM 的 MoE 等）。

**与 E 轴扫的区别（必须并读）**：E 轴扫的对象是「每次建图调用的优化迭代步数」
（`novelty_itr_scheduling_2026-11-08.md` §0，判据二值，结论 ADJACENT 12 条 + COLLIDES 0）；
F 轴对象是**组件配置本身**，词面拥挤度显著更高（conditional computation 是成熟子领域）
⇒ 本次把周边的「自适应计算」全部显式归类，不用二值判定掩盖邻近度。

## 1. 检索式清单（全部实际执行）

**arXiv**（`mcp arxiv search_papers`；宽检索式多次 120s 超时，改用字段限定窄式：
`abs:`/`ti:` + AND 组合，避免相关度排序噪声）：

- B1 `ti:"gaussian splatting" AND abs:"adaptive" AND abs:scheduling`
- B2 `abs:"gaussian splatting" AND abs:SLAM AND abs:"adaptive" AND abs:"module"`
- B3 `abs:SLAM AND abs:"mixture of experts"`
- B4 `abs:SLAM AND abs:"adaptive" AND abs:"execution policy"`（**超时**，由 Web 面覆盖）
- B5 `abs:SLAM AND abs:"robust kernel" AND abs:adaptive`
- B6 `abs:"gaussian splatting" AND abs:SLAM AND abs:"keyframe" AND abs:adaptive AND abs:dynamic`（**超时**，
  拆为 B7 覆盖）
- B7 `abs:SLAM AND abs:keyframe AND abs:"adaptive" AND abs:"selection"`
- B8 `abs:"gaussian splatting" AND abs:SLAM AND abs:"dynamic" AND abs:"robust" AND abs:"uncertainty"`（**超时**，
  由本地 30 卡 + Web 面覆盖）

**Web**（Tavily / Google·Bing 交叉，5 轮）：
- W1 Gaussian splatting SLAM adaptive component scheduling enable disable tracking mapping regime
- W2 SLAM adaptive module selection gating dynamic environment "which components" enable disable online
- W3 "adaptive computation" OR "conditional computation" visual SLAM tracking mapping budget regime difficulty
- W4 OASIS Optimized Adaptive System for Intelligent SLAM dynamic masking strategy processing budget
- W5 Gaussian splatting SLAM disable module at runtime scene dynamic level "adaptive configuration"

**本地**（全量 grep，`resources/lit_dyn_mapping/papers/*.md` = 30 张深读卡 + `mechanisms.md` +
`gap_analysis.md` + `matrix.md`）：
- 关键词族 `regime|switch|policy|adaptive.*component|component.*adaptive|module.*adaptive`：
  **30 卡零命中**。
- 关键词 `adaptive`：仅 5 卡有命中（`flow4dgs_slam` 2 次、`up_slam`/`tad_gs`/`sc_gs`/`ru4d_slam`
  各 1 次），且全部指**表示/插入规则自适应**，无一指运行期组件配置。
- 具体「运行期启停/切换组件」表述：**零命中**（与 E 轴「29 卡零 itr 调度」同型）。

**仓内证据面（F 特有，E 轴没有）**：
- WP-A 五序列 3-seed 全因子：120 run，`wpa_factorial_{prereg,readout,verdict}`（兄弟仓，见 §5.7）；
- `dose_async_migration_verdict_2026-11-08.md`（17 run，部署口径，MIXED）；
- `selfreg_generalization_2026-11-07.md`（四序列 churn 16.7–28.9%）；
- `night_sweep_matrix_2026-11-06.md`（itr 轴，E 轴已止损）。

## 2. 命中表

| # | 论文 | 它自适应的是什么 | 判定 | 一句依据 |
|---|---|---|---|---|
| 1 | **OASIS: Optimized Adaptive System for Intelligent SLAM**（ACM TECS 2025, 24(5s), DOI 10.1145/3761808；**非卡来源，摘要级**） | **输入帧区域**按实时视觉重要性动态裁剪（"dynamically reduces input frame areas based on real-time visual importance"），在实时约束下按处理预算换精度 | **ADJACENT-2** | 信号是实时视觉重要性（在线可算）＋处理预算；但对象是**输入像素面积**，不是组件启用/强度；终点 = 精度-能耗权衡，非 ATE 中位+方差；非 3DGS |
| 2 | **VAR-SLAM: Visual Adaptive and Robust SLAM**（arXiv:2510.16205, 2025-10；**非卡来源，摘要级**） | **鲁棒核形状参数**由残差在线估计（adaptive Barron kernels），替代固定阈值核 | **ADJACENT-2** | 在线估计（本仓 R = Huber IRLS 的同族升级）；但对象是**单一核参数**，不是组件栈配置；无组件启停；ORB-SLAM3 特征前端 |
| 3 | **Separated-SLAM**（The Visual Computer 2025, DOI 10.1007/s00371-025-04224-w；**非卡来源，摘要级**） | **跟踪模式切换**（atlas 可得时进入 only-tracking 加速态，实测 only-tracking regime 每帧降 56.9%） | **ADJACENT-2** | 模式切换存在且带在线可观测量；但判据是离线 atlas 存在性（非 regime 估计）；对象是**模式**而非组件集合；非 3DGS |
| 4 | **Adaptive Monocular VI-SLAM for AR**（Sensors 2017, PMC5712971；**非卡来源，摘要级**） | 四级**自适应执行策略**（按 IMU 预积分运动量选执行级别） | **ADJACENT-2** | 正是「按在线运动量选执行分支」，但级别是人工设定的处理链降级（非组件语义启停），终点为手机端耗时；非 3DGS |
| 5 | **UP-SLAM**（arXiv:2505.22335, 2025-05）—— 本地卡 #27（全文级） | **地图结构**：概率八叉树/锚点基元增删（"Adaptively Structured"）+ 免训练多模态残差不确定性 | **ADJACENT-3（词面）** | 自适应对象是**基元生命周期**（地图表示层），非组件配置；E 轴扫已全文核实 |
| 6 | **DAGS-SLAM**（arXiv:2602.21644, 2026-02）—— 本地卡 #13（全文级） | 「Uncertainty-Aware **Scheduling**」= **语义模型按需调用**（semantic-on-demand）；MP 属性同时驱动前端对应点与后端加权 | **BORDERLINE（外挂模块按需启用）** | 直译撞 COLLIDES 字面：在线不确定性信号 + 动态 3DGS + 可选启用。**但对象是外挂语义模型（非内环 K/R/L）**，终点是算力节省。**F 轴必须显式声明不含语义掩码组件**，否则此条升 COLLIDES |
| 7 | **RTGS**（arXiv:2510.06644, 2025-10, cs.AR；**非卡来源**） | 硬件 **Workload Scheduling Unit**（按上轮迭代信息调度 subtile/pixel 工作负载）+ adaptive pruning + dynamic downsampling | **ADJACENT-2** | 信号 = 上轮迭代负载信息（在线）；对象 = **硬件流水线**与输入分辨率；终点 = 实时性；非算法组件语义 |
| 8 | **AdaptSLAM**（arXiv:2301.04620, 2023-01；**非卡来源，摘要级**） | 边缘辅助下按**通信/计算可用性**自适应调整卸载 | **ADJACENT-2** | 在线资源信号驱动；对象是计算卸载位置，非组件启用。**未核全文**：不排除其调度含关键帧/分辨率轴 |
| 9 | **SR-SLAM**（arXiv:2509.01111, 2025-09；**非卡来源，摘要级**） | 场景**可靠性**驱动的特征数量/质量策略 **+ reliability-aware pose refinement that dynamically integrates direct methods** | **ADJACENT-2** | 第三项特征最接近：按在线可靠性**动态启用**直接法分支参与位姿精化——但它是**精化方法的选择**（单一分支），非组件集合配置；且非 3DGS。**必引必区分** |
| 10 | **KFS⁴LAM**（arXiv:2610.22505, 2026-10；**非卡来源，摘要级**） | **自适应关键帧选择** + 结构监督建图（内窥）；关键帧选择由**累积运动**驱动 | **ADJACENT-2** | 对象 = K；信号 = 累积运动量（**在线可算**）⇒ 原稿标 ADJACENT-1 错误，已改。偏离：单一选择规则，非组件集合；非 ATE 终点 |
| 11 | **AIM-SLAM**（arXiv:2603.05097, 2026-03；**非卡来源，摘要级**） | 基础模型驱动的关键帧优先化；**按 information gain 自适应决定关键帧规模** | **ADJACENT-2** | 对象 = K；信号 = information gain（**在线可算**）⇒ 原稿标 ADJACENT-1 错误，已改。偏离：单一选择/规模规则，非组件集合 |
| 12 | **EliGSiR**（arXiv:2609.20348, 2026-09；**非卡来源，摘要级**） | **有界算力**下的持续 RGB-D 建图 | **ADJACENT-2** | 预算约束下的资源分配；对象是建图预算，非组件配置；终点=有界算力 |
| 13 | **本地 30 卡族**（`4dgs_slam`/`4dgs_wu`/`4dtam`/`cad_slam`/`d2gslam`/`d4dgs_slam`/`deformable_gs`/`dgomapping`/`dl_slam`/`dy3dgs_slam`/`dynagslam`/`dynamic3dgaussians`/`dynaslam`/`flow4dgs_slam`/`ggd_slam`/`lvd_gs`/`mope`/`rigs`/`robustsplat`/`rose_slam`/`ru4d_slam`/`sc_gs`/`scout_slam`/`shape_of_motion`/`spacetime_gaussians`/`tad_gs`/`up_slam`/`wildgaussians`/`wildgs_slam`） | 致密化阈值、插入规则、不确定性加权、掩码、生命周期——均为**单一组件内部**的规则改进 | **CLEAR/背景（组件内部机制，非组件配置）** | 30 卡逐卡核对（见 §1 方法），无「按 regime 选组件集合」的记载；`gap_analysis.md` 的结论 1 只覆盖「不确定性门控 vs 动态保留」三元组，**不含**组件配置调度，原稿引它作「系统登记」不成立（已改） |
| 14 | MoE / conditional computation / early-exit 类（**非 SLAM，跨域**） | 按输入动态选子网络/提前退出 | **ADJACENT-3（跨域词面）** | B3 `abs:SLAM AND abs:"mixture of experts"` → 1 条无关 VGGT 探针；该族目前只存在于通用视觉域，尚未进 SLAM。**审稿人必问「为何不直接套 MoE」** |

**计数（逐行重算，G1-F1 整改）**：
COLLIDES **0** ｜ BORDERLINE **1**（#6 DAGS-SLAM）｜ ADJACENT-1 **0** ｜ ADJACENT-2 **10**
（#1/#2/#3/#4/#7/#8/#9/#10/#11/#12）｜ ADJACENT-3 **2**（#5/#14）｜ CLEAR/背景 **1 族**（#13）。
**表体合计 14 行**（0+1+0+10+2+1 = 14 ✔）。前一版写「ADJACENT-2 × 6」是错的（G1-F1）。

**最逼近排序（统一一处，G1-F1 整改）**：**DAGS-SLAM（BORDERLINE，唯一进字面档）>
SR-SLAM（动态启用直接法分支）> VAR-SLAM（在线估核参数）> KFS⁴LAM/AIM-SLAM（在线信号调 K）> OASIS（预算换精度）> UP-SLAM（纯词面）。**

## 3. 四维差异化（F 轴版；禁止照抄 E 轴）

| 维度 | F 轴主张 | 最近邻居及其偏离 |
|---|---|---|
| **对象** | 跟踪/建图**组件栈的启用集合与强度**（`DynamicKeyframe` / `RobustTracking` / `ReliabilitySignal` 的 enable + 参数），即运行期**组件配置本身** | OASIS 调输入面积；VAR-SLAM 调单核参数；RTGS 调硬件流水线；AdaptSLAM 调卸载位置；SR-SLAM 调特征策略。**无一调「组件集合」** |
| **信号** | **在线因果可算的 regime 估计**：场景动态程度 / 残差统计 / churn / 观测饱和-稀疏——只用当前帧与历史帧，不读未来帧、不读数据集标签 | OASIS = 实时视觉重要性（接近但对象不同）；Separated-SLAM = 离线 atlas 存在性；KFS⁴LAM/AIM-SLAM = 任务先验/基础模型信息量 |
| **终点** | **ATE 中位数 + 方差 + 地图统计**，且不牺牲跟踪；预算匹配（全开 vs 调度，等算力） | OASIS = 精度-能耗；RTGS/AdaptSLAM/EliGSiR = 实时性/有界算力；KFS⁴LAM = 重建完整性 |
| **场景** | 动态在线 RGB-D SLAM（Bonn 动态类，仪器口径，3 seed） | OASIS/AdaptSLAM/Separated-SLAM 为特征/边缘 SLAM；KFS⁴LAM 内窥；本仓 30 卡中无一做组件配置调度 |

**推论**：F 轴的差异化不是「自适应」本身（这个词在 SLAM 已被广泛占用），而是
**「按在线 regime 在组件集合空间做离散选择」**这一对象轴的空位。这一点必须在论文中
用一句话锚定，不能只声称「adaptive」。

## 4. 与 E 轴 / 内容三的属地边界（必写，写不清不立项）

- **内容三（已止损为配置结论）**：属地 = **地图生长与跟踪耦合的调度轴**（E 轴 =
  建图调用级 itr 预算）。E 轴 `L2_SIGN_UNSTABLE` 后，其身份是配置结论（fixed-50 优于默认），
  不再作为机制主张；调度器代码默认关保留。
- **内容一（RoGS-SLAM，MMM2027 已录用）**：属地 = **观测可靠性处理**（语义掩码 + Huber IRLS +
  可靠性信号 + lineage 生命周期）。F 轴是其**扩展**：把内容一里**静态常开**的加固组件
  升级为 regime-aware 配置调度。
- **重叠风险与处置**：
  1. **K（`DynamicKeyframe`）与内容三「跟踪耦合调度」同属跟踪侧调度** ⇒ F 轴文档必须把
     K 的角色限定为「组件配置中的一个开关」（gap_cap 固定时只调 enable/强度），
     不主张「关键帧调度策略」这一更宽的轴；后者仍属内容三。
  2. **L（`ReliabilitySignal`）与内容一的「可靠性信号」字面重叠** ⇒ 内容一的 L 是**固定 cue 配置**
     （`cue: "both"`）；F 轴只决定**何时启用 L**，不重新设计 cue 本身。信号设计与配置调度权属分开。
  3. **R（`RobustTracking`）与 VAR-SLAM 的在线核参数重叠** ⇒ F 轴若只呈现「按 regime 切
     huber 开关」，与 VAR-SLAM 的「在线估核形参」在动机上同族；差异化必须落在**组件级离散选择**
     （多组件联合）而非单参数连续估计。
- **三条线可分的判据（本轮立场 + 可执行硬门草案）**：内容一 = 组件**内部**设计；
  内容三 = 地图生长**调度**；F = 组件**集合**的运行期配置。三者对象不同、粒度不同，
  但 F 与内容三在 K 上相邻。**可执行硬门（草案，进 prereg 前须再磨）**：
  ① **K-off 门**：F 轴效应必须在 `DynamicKeyframe.enabled=false` 时仍成立（否则 = 内容三复活）；
  ② **L-internal 门**：F 轴不得修改 `ReliabilitySignal` 的 cue 定义/参数，只许开关（否则 = 内容一修改）；
  ③ **R-single-param 门**：F 轴的 R 决策必须是**离散选择**（如 huber on/off 或 delta 档位二选一），
  不得做连续核形参估计（否则 = VAR-SLAM 同族）；
  ④ **语义掩码排除门**：F 轴不含 `SemanticMask` 的按需启用（否则 = DAGS-SLAM BORDERLINE 升 COLLIDES）。
  **上述四门同时成立才算「三条线可分」；任一不成立 ⇒ 不得立项。**

## 5. 局限（检索面盲区自报）

1. **非 arXiv 渠道覆盖不全**：IEEE Xplore / ACM DL / Springer / MDPI 只经 Web 搜索覆盖到被引
   较多或标题显眼者（OASIS、Separated-SLAM、Adaptive VI-SLAM、VAR-SLAM、RK-SLAM）；
   低引期刊/会议可能漏网。
2. **中文文献未检索**（沿 E 轴约定）；中文学位论文/学报若有同机制则本次不可见。
   中文关键词面（如「自适应组件/模块调度」「按场景难度切换」）未扫。
3. **语义变体未穷尽**：`conditional computation` / `early exit` / `dynamic network` /
   `compute allocation` / `policy gating` 等同族措辞在 SLAM 内的组合未逐一扫；本次只确认
   「SLAM + Mixture-of-Experts」零命中（B3）。
4. **宽检索式不稳定 + 超时→覆盖映射缺失（G1-N2 整改）**：arXiv 宽式 3 次 120s 超时
   （B4/B6/B8）。**逐条说明覆盖**：B4（execution policy）由 W2/W3 网络面覆盖；
   B6（keyframe adaptive dynamic）拆为 B7 `abs:SLAM AND abs:keyframe AND abs:"adaptive"
   AND abs:"selection"` 执行并召回 KFS⁴LAM/AIM-SLAM；B8（dynamic robust uncertainty）
   由本地 30 卡 + W1/W5 覆盖。⇒ 无检索式完全失覆盖，但**窄式召回可能不如全式**，如实登记。
5. **本地 30 卡的收文偏置**：动态 GS-SLAM 为主（30 卡中 face-dynamic/anti-dynamic/瞬态/4D 四族），
   边缘/加速/特征 SLAM 仅少数；「30 卡零命中」不等于全领域零命中。
6. **版本与读深（G1-N1/N2 整改）**：OASIS 只读 ACM DL 摘要级（TECS 2025 正式版未读全文，
   卷期 `24(5s)` 未用 DOI 元数据二次核）；VAR-SLAM/AdaptSLAM/SR-SLAM/KFS⁴LAM/AIM-SLAM/
   EliGSiR 只读 arXiv 摘要（**均非本地卡来源**，表中已逐条标注）；Separated-SLAM 只读
   Springer 摘要。其中 **SR-SLAM 与 KFS⁴LAM/AIM-SLAM 的判定（ADJACENT-2）依赖摘要**，
   成稿前须补全文核实；若全文显示其存在组件集合级调度，本判定须上修。
7. **WP-A 上游证据宿主问题（F 轴特有）**：`wpa_factorial_verdict.md` 实体在兄弟仓
   `/data/RoGS-SLAM/results/evidence/`（md5 `0ca4eb9564412da85d141386ffd067b4`，120 run，
   已 commit 跟踪），**不在本仓**；`rootcause_rescope_2026-11-08.md:90` 的指针在本仓悬空。
   按账本/判决落盘纪律，F 轴 prereg 引用它之前必须先裁定证据宿主（复制进本仓 evidence？
   或登记「兄弟仓 + hash」引用？）。**本轮只登记问题，不裁定**（属 D2）。
   **作用域限定（G1-M6）**：该判决的 5 序列为 mv_no_box / mv_no_box2 / pt1 / pt2 / balloon
   （见其 readout），**不外推到 walking/crowd 或其他序列**；且其 `readout.json` 的
   `caliber`/`head`/`exp_id` 三键经 G1 核查为 None ⇒ **口径不可机读核**，引用时须注明
   「按判决书文字口径，非机读校验」。
8. **术语消歧（必写进 prereg）**：`A2/A4` 在 WP-A 是**分支名**（A2 部分冗余 / A4 序列依赖），
   在本仓剂量轴是**剂量臂**（`densify_grad_threshold` + `percent_dense`）。F 轴文档一律写
   `wpa_factorial` 前缀，禁止裸写 A2/A4。
9. **未回写导航（G1-M10）**：本次新增的 5 个近邻（DAGS-SLAM 已在本仓卡 #13；OASIS、
   VAR-SLAM、Separated-SLAM、Adaptive VI-SLAM、SR-SLAM、KFS⁴LAM、AIM-SLAM、EliGSiR
   为非卡来源）**尚未回写** `resources/lit_dyn_mapping/{matrix.md,INDEX.md}`。
   本轮不写（属下一轮文献维护），但成稿引用前必须回写，否则「非卡来源」无法审计。

## 6. 结论与建议

**最终判定：ADJACENT-ONLY + 1 BORDERLINE（机制粒度无撞车，但空间不真空）**，依据三段论：

1. **无 COLLIDES**：本仓 30 卡零命中、arXiv 5 组有效窄式（B1/B2/B3/B5/B7）零命中、
   Web 5 轮零命中——没有已发表工作把「跟踪/建图**内环组件栈**的启用与强度」做成按在线 regime
   信号的调度，且以 ATE 中位+方差为终点。**唯一 BORDERLINE = DAGS-SLAM**
   （外挂语义模型按需启用，字面撞、对象不同；须靠 §4④ 排除门守住）。
2. **但空间不真空**：(a) OASIS 已占「实时重要性信号 + 预算换精度」的思想近邻（对象是输入面积）；
   (b) VAR-SLAM 已占「在线自适应鲁棒核」= R 轴近邻；(c) SR-SLAM 已占「按可靠性动态启用
   直接法精化分支」= 分支级动态启用；(d) KFS⁴LAM/AIM-SLAM 已占 K 轴在线自适应；
   (e) conditional computation / MoE 是成熟通用子领域，审稿人必问「为何不直接套 MoE」。
3. **可立项的唯一收窄形态**：**「按在线可测 regime 在离散组件集合空间做配置选择」**，四维
   差异化见 §3，且必须同时过 §4 的四道可执行硬门（K-off / L-internal / R-single-param /
   语义掩码排除）。

**建议（呈报用户，D2）**：

- **建议：本轮不立项**。理由三条（按权重，G1-M5 整改：时间算术已按实录更正）：
  1. **时间**：距中期 2026-12-14 仅 34 天。E 轴实录 = prereg（11-08 16:13 mtime）→ L1（11-09 19:17–21:32）
     → L2（11-10 02:04–04:01）→ 判读/判决（11-10 04:10–18:54），即**判据链两天、GPU ≈2.7h**；
     但那是**已有实现 + 判据链已过 G3** 的条件。F 轴需先做实现（prereg 之外）+ 四道硬门验证批
     + 3 seed 确认，按同一节奏保守估**仍需 2–3 周**（实现 ~3–5 天 + L1/L2 ≈2 天 + 审查/整改 ≈3–5 天），
     且 E 轴 L2 刚证明「L1 方向级优势会在 3 seed 翻转」（s1 Δ=+0.5136，仅超地板 0.0136cm = 2.72%，
     按 D23 记自差内不可判）——不能把 L1 当机制成立。
     **结论：中期前无法交付可信的 F 轴结果。**
  2. **重叠未清**：F 轴调 K 与内容三「跟踪耦合调度」相邻、调 L 与内容一「可靠性信号」字面重叠、
     调 R 与 VAR-SLAM 同族、语义模型启用与 DAGS 同型。§4 的四道硬门目前是**草案**，
     尚未在 prereg 中锁定，也尚未验证可执行（如 K-off 门在现有代码里是否真可分离待查）。
  3. **novelty 拥挤度高于 E 轴**：E 轴是「30 卡零命中 + 词面近邻 ADJACENT-12、COLLIDES 0」；
     F 轴已有 **1 BORDERLINE + 9 ADJACENT-2**（含 4 篇与本仓组件轴直接相邻），
     写作与审稿成本更高，而 34 天窗口里写作时间还要留给中期与 ch1。
- **替代动作（推荐给中期报告「下一步计划」）**：把 F 轴写成**中期后（2027-01 起）的候选方向**，
  前置条件 = ① 锁定并验证 §4 四道硬门；② 裁定 WP-A 证据宿主（§5.7）；③ 补 SR-SLAM /
  KFS⁴LAM / AIM-SLAM 全文核实（§5.6）；④ 回写 `matrix.md`/`INDEX.md`（§5.9）。
  中期报告只报「已完成 + 已止损 + 候选方向评估完成」，**不承诺 F 轴机制贡献**。
- **若用户仍决定立项**：须走 prereg 判据先行 + 代码保护例外流程全套，且第一条判据必须是
  **K-off 门**（`DynamicKeyframe.enabled=false` 时效应仍成立），否则与内容三不可区分。

**本件不主张**：不主张 F 轴机制有效、不主张其 novelty 已清（§5 盲区）、不主张中期可交付
F 轴结果。本件只做占用核查与风险登记。

## 7. 修订记录（G1 整改对照）

G1 = **Reject**（3 致命 / 10 重大 / 9 次要，报告 `/tmp/slam_critic_g1_f_axis_2026-11-10.md`）→ 本版逐条处置：

| # | 项 | 处置 |
|---|---|---|
| F1 | 计数自相矛盾（ADJACENT-2 × 6 vs 表体 7；合计 13≠14；两套 top-3） | §2 逐行重算：COLLIDES 0 / BORDERLINE 1 / ADJ-1 0 / ADJ-2 10 / ADJ-3 2 / CLEAR 1 族 = 14 行；top-3 统一一处 |
| F2 | 「逐卡核实」不实（gap_analysis 零命中；D⁴GS 全仓 0 命中；CountingContributions 属另一语料） | §2 第 13 行改为**逐卡名单全列**（30 卡实名）+ 明说 gap_analysis 的结论 1 只覆盖「不确定性门控 vs 动态保留」三元组、**不含**组件配置调度；删除 D⁴GS/CountingContributions 引用 |
| F3 | 账本门 glob 只覆盖 `*_verdict_*.md`；`novelty_*.md` 全族不受管（68/139） | 本轮**不扩 glob**：改由独立 commit 处理（见 §8 说明）；本件头部已挂 P3-D2-049 |
| M1/M2 | DAGS 应为 BORDERLINE；SR-SLAM 漏述「动态启用直接法精化」 | 新增 BORDERLINE 档；#6 DAGS 改档并加「F 轴须排除语义掩码」；#9 SR-SLAM 补第三项特征并升为必引 |
| M3 | ADJACENT-1 三分之二错标（KFS⁴LAM/AIM-SLAM 信号是在线的） | #10/#11 均改 ADJACENT-2，并注明原判错误 |
| M4 | COLLIDES 定义缺模态限定 | §0 首段加适用范围：只对 3DGS/dense visual SLAM 生效；6/14 非 3DGS 只作词面登记 |
| M5 | 一页纸「E 轴二值判据 + 零近邻」反号 | 一页纸同步改为「COLLIDES 0、词面近邻 12 条」；时间算术改按实录（2–3 周） |
| M6 | WP-A 缺作用域与口径不可机读声明 | §5.7 补 5 序列名单 + 「不外推 walking/crowd」+ `caliber/head/exp_id=None` 如实登记 |
| M7 | 摘要行与表体两处 top-3 不一致 | 已合并为一处（§2 末） |
| M8 | L2 引述缺 D23 边际性（0.0136cm = 2.72%） | §6.1 已补 |
| M9 | 前置条件漏 SR-SLAM | §6 替代动作改为四条（含三篇全文核实） |
| M10 | 新近邻未回写 INDEX/matrix | §5.9 如实登记为「本轮不写、成稿前必须回写」 |
| N1–N9 | 非卡来源未标 / KFS 读深 / Web 零命中歧义 / 错字 / 未用列 / 2h vs 3.3h / 账本号顺序 / OASIS 卷期 / 中文关键词面 | 表内逐条标「非卡来源/摘要级」；§5.4 逐条映射超时→覆盖；删「车线」错字；§5.2 补中文关键词面；§5.6 补读深与卷期 |

## 8. 遗留（需用户或后续轮次处理）

1. **WPA 证据宿主**：属 D2，本件不裁定（§5.7）。
2. **账本门 glob 类级修复**：`novelty_*.md`、`*_readout_*.md` 之外的诊断/审计/日志类
   （`LOG.md`、`audit_*`、`cgb_*`、`phase0_*`、`fdose_*` 等 68 份）**不应一律挂账本号**——
   它们是读数/日志，不是呈报件。正确修法 = 按**文书类别白名单**（verdict / onepager /
   prereg / amendment / novelty / impl_design / readout / manifest）逐类登记，
   而非扩大通配符。**本轮不改**（超 F 轴 novelty 范围）；已在此登记为已知缺口，
   并建议下一轮「项目文件审计」按类处理。
3. **四道硬门的可执行性验证**：K-off / L-internal / R-single-param / 语义掩码排除
   需在 F 轴 prereg 前做代码级核查（现有 `Mapping.adaptive_itr` 与
   `DynamicKeyframe`/`RobustTracking`/`ReliabilitySignal` 的开关是否真能独立分离）。
4. **文献回写**：§5.9。
