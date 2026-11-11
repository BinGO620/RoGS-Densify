# novelty_itr_scheduling_2026-11-08.md — 「自适应建图迭代调度」机制轴立项前 novelty 全扫

**账本**：P3-D2-045（E 轴立项；本件是该行「先 novelty 全扫再定」路径的直接产物，
判据见其依据列）。2026-11-10 补账本指针（slam-critic G1 F 轴审查 F3：novelty 族纳入账本门）。

> 任务：核查「把每次建图调用内部的优化迭代步数/时长做成事件驱动自适应调度（按地图新鲜度、跟踪残差、
> 关键帧间隔、地图规模等在线信号逐事件调整 mapping itr，目标 ATE 中位数+方差）」在 3DGS-SLAM
> （尤其动态场景）文献中的占用情况。零 GPU，纯文献检索。
> 日期：2026-11-08 ｜ 执行：ZCode subagent（纯文献）｜ 动机证据（本仓）：itr 50/150/300 = ATE
> 10.66/13.59/18.91（调用次数不变），默认 150 次优约 3cm 且在方差洼地（0.32 vs 3.93）。

## 0. 判定标准（任务给定）

- **COLLIDES**：任何已发表工作把「每关键帧/每次建图调用的优化迭代数或时长」做成自适应/调度/事件驱动
  （无论静态或动态 GS-SLAM，无论动机是精度还是算力）。
- **ADJACENT**：致密化阈值/剂量调度、关键帧选择/插入调度、语义模型按需调用（DAGS-SLAM）、外部位姿源、
  固定 itr 的消融分析。

## 1. 检索式清单（全部实际执行）

arXiv（mcp arxiv search_papers，未限分类以避免漏召，后续按题目过滤）：
- A1 `"gaussian splatting" SLAM "adaptive" "optimization iterations"`
- A2 `"gaussian splatting" SLAM "per-keyframe" optimization OR "mapping iterations"`
- A3 `"gaussian splatting" SLAM "computational budget" OR "iteration budget" OR "optimization budget" mapping`
- A4 `"gaussian splatting" "adaptive densification" schedule online SLAM`
- A5 `"gaussian splatting" SLAM "time budget" OR "resource-aware" OR "energy" online mapping allocation`
- A6 `dynamic "gaussian splatting" SLAM "adaptive refinement" OR "iterative refinement" mapping keyframe`
- A7 `"gaussian splatting" SLAM mapping "until convergence" OR "early stopping" OR "converged" keyframe optimization`
- A8 `SLAM "gaussian splatting" "number of iterations" adaptive keyframe mapping dynamic`
- A9 `"gaussian splatting" SLAM "map freshness" OR "stale" OR "on-demand" mapping online`
- A10 `abs:"schedule" AND ...`（语法报错，改由 A3/A5/A9 + 网络检索覆盖 schedule 语义面）

Web（Google/Bing 交叉验证，7 轮）：GS-SLAM adaptive number of iterations per keyframe；CaRtGS 核实；
RK-SLAM；DG-SLAM(NeurIPS 2024)；ADD-SLAM；GS³LAM；tracking-mapping trade-off / anytime / time budget。

本地（全量 grep，29 张深读卡 + mechanisms.md + gap_analysis.md）：
- 关键词 `iter|schedul|adaptive|budget|step`：命中 5 文件（dags_slam 标题 Scheduling、up_slam 标题
  Adaptively Structured、flow4dgs 自适应插入、sc_gs 自适应控制点、tad_gs TAT），全部逐条定性（见 §2）。
- 具体迭代数 `[0-9]+ iterations|itr`：**29 卡零命中**——本地语料无任何一篇报告过逐事件可变的 itr。

全文级核验（arXiv HTML/PDF text 检索）：2410.00486（CaRtGS，8+5 段）、2608.14902（2 段）、
2411.08373（DG-SLAM，5 段）、2505.19420v2（CAD-SLAM 首页级）+ SciOpen 抓取 MGS-SLAM 摘要。

## 2. 命中表

| # | 论文 | 它调度的是什么 | 判定 | 一句依据 |
|---|---|---|---|---|
| 1 | **CaRtGS**（arXiv:2410.00486, 2024-10, IEEE 2025） | 关键帧池内 **reoptimization 频率**：按逐关键帧训练 loss 排序，top-d_k 高 loss 帧权重 2、其余权重 1（Eq.8, d=4），"ensure a more equitable distribution of **iterations across the keyframe pool**"；单次建图调用的迭代步数仍由实时约束固定（splat-wise 反传使同 runtime 下 itr 总量 ×3，常数增益） | **ADJACENT（最逼近车线，必引必区分）** | 它自适应的是「哪些关键帧被更频繁地重优化」（池内采样权重 = 关键帧重优化调度），不是「每次建图调用跑多少步」；信号 = 渲染训练 loss（非地图新鲜度/跟踪残差/关键帧间隔/地图规模）；终点 = PSNR/基元数，不报 ATE；静态场景（Replica/TUM/VEctor）。**但**摘要 "adaptive strategy that enhances optimization iterations" + Fig.2 "keyframe iterations" 词面直撞，审稿人可误读为占位 |
| 2 | **Geometry-Aware Online Mapping**（arXiv:2608.14902, 2026-08, cs.RO） | 把 "strict **per-keyframe optimization budgets**" 当**固定 setting**，在预算内做致密化/初始化改进（transmittance-preserving densification、camera-aware scale init、error-guided densification）；附 100/200/300 itr/keyframe 预算敏感性实验 | **ADJACENT（动机同型、解法异轴）** | §5.3 "both the baseline and our method converge to comparable rendering quality given a large budget (200–300 iterations per keyframe)... our geometry-aware approach maintains stable..."——预算是约束不是被调度对象；终点全渲染指标，无 ATE 主张；静态（Photo-SLAM 骨架）。与我们「itr 50/150/300 敏感性」动机同型，但其贡献在致密化轴 |
| 3 | **UP-SLAM**（arXiv:2505.22335, 2025-05, cs.RO）——本地卡 #27（2026-09-19 全文级） | 标题 "Adaptively Structured" 细读结论见 §3 | **ADJACENT（词面撞车、机制不撞）** | 自适应的是**地图结构**（概率八叉树/增量概率锚点基元增删 + 欠重建检测），全文无逐事件 itr 调度内容 |
| 4 | KFS⁴LAM（arXiv:2610.22505, 2026-10, 内窥） | 运动引导**自适应关键帧选择** + 结构监督建图 | ADJACENT | 选「哪些帧进建图」，非「每次建图跑多少步」；任务明列关键帧选择调度为相邻 |
| 5 | TAD-GS（本地卡，2025） | TAT：致密化阈值按高斯**寿命**自适应 | ADJACENT（已知） | 致密化阈值轴，非迭代步数轴 |
| 6 | DAGS-SLAM（arXiv:2602.21644, 2026-02） | 标题 "Uncertainty-Aware **Scheduling**" = **语义模型按需调用**调度 | ADJACENT（已知） | 词面含 Scheduling，机制是语义模型调用时机，与建图 itr 无关（本地卡核实） |
| 7 | DG-SLAM（arXiv:2411.08373, NeurIPS 2024, 动态） | adaptive Gaussian point addition/pruning（地图内容管理）；动态 GS-SLAM | ADJACENT | 其 Table 5 明示 tracking 20 / mapping 40 itr **固定**（NICE-SLAM 60 / Point-SLAM 150 / SplaTAM 30 / GS-SLAM 81 同表）——恰是「固定 itr 为领域惯例」的证据，可反衬我们的轴 |
| 8 | CAD-SLAM（arXiv:2505.19420 v2；v1 题名 ADD-SLAM "Adaptive Dynamic Dense SLAM"） | 一致性动态检测 + 动静解耦 + 时序高斯在线建模 | ADJACENT | "Adaptive" 指动态感知/建模，非迭代调度（v2 全文核实）；本地 cad_slam 卡同篇 |
| 9 | RTGS（arXiv:2510.06644, 2025-10, cs.AR 边缘） | 算法-硬件协同："adaptive Gaussian pruning" + "dynamic downsampling" + 硬件 Workload Scheduling Unit（按上轮迭代信息的硬件流水调度） | ADJACENT | 算力动机最贴，但调度发生在**硬件 workload 层**与剪枝/降采样，非建图调用 itr 层 |
| 10 | GS³LAM（2024, 期刊, 引 ~53） | 自适应 3D 高斯**扩展**（地图增长策略） | ADJACENT | 地图内容轴；其 "iterations for keyframe mapping" 为固定配置 |
| 11 | RK-SLAM（Applied Sciences 2025, MDPI） | 关键帧位姿微调幅度 × itr 数的**固定 itr 分析** | ADJACENT | itr 是被分析的超参，不是被调度的对象 |
| 12 | MGS-SLAM（CVM 2026, IEEE Xplore, T. Cao） | significance-based：按可见性/不透明度/体积系数**自适应剪枝**高斯 | ADJACENT | SciOpen 摘要核实：剪枝基元选择，非迭代数调整 |
| 13 | Flow4DGS-SLAM（arXiv:2604.22339, CVPR 2026, 动态） | 免超参**自适应动态高斯插入**（回溯差集 M_insert） | ADJACENT（已知） | 插入规则轴（mechanisms.md I3） |
| 14 | 2610.13541 / 2406.15643 / 2610.34344（离线致密化预算类） | error×confidence 固定预算 / 构造式精确预算 / birth-death 结构学习 | ADJACENT | 本仓 gap_note_2026-11-03 已收：致密化预算轴，离线静态侧；非迭代步数调度 |
| 15 | FreeTimeGS（CVPR 2025, 离线动态重建） | 任意时空放置 + 时间预算 | CLEAR/背景 | 非 SLAM、离线、放置预算非优化迭代 |

**COLLIDES 命中数：0**（按任务定义的机制粒度）。ADJACENT 12 条 + CLEAR/背景 2 条 + 本地已知 4 条（TAD-GS/DAGS/Flow4DGS/2610 系）。
最逼近车线排序：CaRtGS > 2608.14902 > UP-SLAM（词面）。

## 3. UP-SLAM 细读结论（任务点名的唯一未清疑似）

来源：本地全文级深读卡 `/home/cb/data/monogs-ours/resources/lit_dyn_mapping/papers/up_slam.md`
（2026-09-19 由摘要级升级为全文级，读 arXiv PDF 全文）。

**结论：「Adaptively Structured」= 地图结构自适应，与建图迭代调度无关。** 具体：
- 自适应对象：**概率八叉树 + 增量概率锚点**（Scaffold-GS 血统）组织的基元生命周期——自适应删除/初始化
  锚点、免手工阈值的欠重建检测。动机逐字："threshold-dependent initialization strategies become
  increasingly unreliable in dynamic environments. Inappropriate threshold settings may lead to excessive
  GPU memory consumption..."——是「阈值敏感性」问题的**结构层**答案，不是「itr 敏感性」的**优化层**答案。
- 其余贡献（免训练多模态残差不确定性、DINOv2 特征蒸馏、正弦时间编码）均在跟踪侧动态过滤与表示层。
- 全卡（52 行全文级笔记）无任何 per-keyframe/per-call 优化迭代数调整的记载；评测终点 ATE RMSE + 渲染。
- **判定：ADJACENT（词面撞车）**。论文中一句话区分即可："UP-SLAM's 'adaptively structured' refers to
  probabilistic octree/anchor-based primitive management, not optimization scheduling."

## 4. 最终判定：**ADJACENT-ONLY（可立项，但须差异化声明）**

依据三段论：
1. **机制粒度上无撞车**：没有任何已发表工作把「每次建图调用内部的优化迭代步数/时长」做成按在线系统信号
   （地图新鲜度/跟踪残差/关键帧间隔/地图规模）逐事件调度的机制。本地 29 卡零记载；arXiv 10 组检索式 +
   7 轮网络交叉验证零命中；CaRtGS 全文核实为池内采样权重而非调用预算。
2. **但空间不是真空**：(a) CaRtGS 已占「优化迭代在关键帧池上的自适应分配」的**词面与思想近邻**
   （"adaptive optimization ... distribution of iterations"）；(b) 2608.14902 已把 per-keyframe
   iteration budget 当作核心 setting 并做过 100/200/300 预算敏感性（与我们动机证据同型）；(c) DG-SLAM
   Table 5 等表明固定 itr 是全领域惯例。⇒ CLEAR（完全无人染指）不成立。
3. **novelty 主张必须收窄为**：**调用级（event-level）建图迭代预算调度**——
   - 调度对象：每次建图调用的 itr 数/时长（CaRtGS 是池内关键帧重优化权重；2608.14902 是预算内致密化）；
   - 驱动信号：SLAM 自身系统状态（地图新鲜度、跟踪残差、关键帧间隔、地图规模），非渲染 loss、非硬件负载；
   - 优化终点：**ATE 中位数 + 方差**（全部近邻的终点都是 PSNR/渲染或算力，无一以定位精度/稳定性为目标）；
   - 场景：动态 GS-SLAM（CaRtGS/2608.14902 均静态）。
   
差异化写作清单（论文 3 必做）：① 必引 CaRtGS 并逐点对照上表 4 维差异；② 引 2608.14902 承认
per-keyframe budget 敏感性已知、声明我们的响应是调度而非致密化改进；③ 一句话排掉 UP-SLAM 词面；
④ 可借 DG-SLAM Table 5 做「全领域固定 itr」的惯例证据引入问题。

## 5. 局限（检索面盲区自报）

1. **非 arXiv 渠道覆盖不全**：IEEE Xplore / MDPI / Springer 期刊只经 web 搜索覆盖了被引较多者
   （RK-SLAM、GS³LAM、MGS-SLAM、CaRtGS-IEEE 版）；低引期刊/会议可能漏网。
2. **中文文献未检索**（任务约定 arXiv 英文即可）；中文学位论文/学报若有同机制则本次不可见。
3. **语义变体只部分覆盖**：learning rate schedule、convergence-gated mapping、optimization allocation
   等变体措辞未穷尽；A9 "map freshness" 检索式实际召回了通用 GS-SLAM 集（arXiv 相关度排序噪声大），
   不能保证穷尽式召回。
4. **2022 NeRF-SLAM 时代仅间接核查**：经 DG-SLAM Table 5（NICE-SLAM 60/ESLAM 60/Co-SLAM 30 固定）
   间接确认固定 itr 惯例，未逐篇全查 2022 NeRF-SLAM 论文正文。
5. **CaRtGS 版本差异**：判定基于 arXiv v4 全文（Eq.8/Sec III-C.2 逐字）；搜索引擎摘要称其"按实际处理
   时间而非固定迭代数优化"——v4 全文未检出该表述（疑为模型改写失真），v1–v3 未逐版比对；IEEE 定稿版
   未读。若最终成稿引用 CaRtGS，建议再核 IEEE 版机制描述是否一致。
6. **本仓 29 卡语料本身的收文偏置**（动态 GS-SLAM 为主，静态加速/边缘部署类仅 RTGS 一类新查）。
7. 零 GPU 约束满足：本次无任何本地复现，全部结论为文献级证据。
