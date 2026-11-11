# 分叉源 config 二分诊断预注册（divsrc-bisect；P3-D2-026）—— 2026-11-05

**状态**：判据锁定于任何诊断 run 之前。账本：`P3-D2-026`（D1 自裁立项，R8 执行类；
框架依据 = `P3-D2-025` 获批的继续研究方向 + `DISCIPLINE.md`「测量口径」6）。
**性质**：装置测量诊断（非判效、非机制）。产出只进「测量性结论」边界叙事与
未来甲复活 prereg 的前置证据，**不作贡献主张**（`prereg_device_robust_estimand`
§4）。

## §0 问题与既有证据

P3-D2-024 探针（确定性套件全开）证明同 config 同 seed 分叉不可修复，但留下一个
未定量的问题：**分叉的放大机制是什么？** 零 GPU 结构分析（归一化 console diff，
B vs C；总行数口径 = `grep -c` 原始日志）已定性：

- 主节拍一致：Eval 各 **25** 条（25/25，逐值不同）；Deferred promotion health
  各 **115** 条（其中 83/83 条逐值不同，32 条逐位同）；
- 值普遍分叉：Pruned 数、scale_min、ATE 全部不同；
- **结构差共 2 处**：B 多 1 个 prune 事件（113 vs 112）；C 多 1 个
  opacity-reset 事件（2 vs 1）——重跑间存在少量事件轨迹差（归因未定：真调度差
  或仪器丢行，本诊断不裁决）。

⇒ 分叉 = **数值级为主 + 阈值翻转放大**（蝴蝶效应形态），主节拍非调度级
结构分叉。上游数值分叉源最优先候选 = custom CUDA 栅格化 backward 的
atomicAdd（`P3-D2-024` 判决；**候选推断，未定位算子**）；放大器 = 各类
阈值决策路径（clone/split/prune 翻转改变地图规模，反馈进后续一切）。

## §1 二分设计（单变量：clone/split/prune 决策路径 ON → OFF；确定性套件全开不变）

- **D1 臂（clone/split/prune 关停；**注意不是"全决策关停"——见下"仍活跃"清单**）**：
  `maskstat_off_person_tracking` 配置 + 以下覆盖（config 是唯一定义；零代码改动，
  `update_recursive` 深合并四键全被消费——G1 已核）：
  ```yaml
  opt_params:
    densify_grad_threshold: 1.0e9   # clone/split 永不触发（update_filter 恒空；init 段同一键）
    densify_from_iter: 1000000000   # 只移除 init 段 reset 的 OR 分支（init 真正 densify 门
                                    # = init_gaussian_update=100 取模，未覆盖、由上一键关停 clone/split）
  Training:
    gaussian_update_every: 1000000000  # 主环 densify_and_prune 永不触发：主环 iteration_count
                                       # 从 init 段消耗 init_itr_num 后起步（>50），1e9 周期内
                                       # 不可能再 == offset(50)
    init_gaussian_th: -1.0             # init 段 prune-by-opacity 永不删（opacity ≥ 0 > -1）
  Results:
    save_dir: results/paper3_bpw/divsrc_nodens_person_tracking
  ```
  **仍活跃的决策/调度路径（如实列出）**：deferred promotion 阈值
  （explained_opacity/unmapped）、**DeferredCommit prune 臂**（reject/expire/
  capacity——`Pruned N lineage(s)` 签名唯一发射点 `slam_backend.py:2344`；
  2026-11-05 G2 带日期补列，初稿漏单列）、`reset_opacity_nonvisible`（主环
  调度）、语义插入门（逐 KF scheduled）——D1 臂结论只针对被关停的
  clone/split/prune 三类。两臂均关 map 压缩（harmless-deletion；method.yaml
  口径，G1 更正：原稿"保持不变"失实）。
  **带日期更正（2026-11-05，G2）**：§4 冒烟预算 "~3min" 实测 372s（40 帧、
  决策关停态插入量更大）。
  其余管线（逐 KF 插入、init/reset 调度、优化循环、跟踪、eval）不变。
- **D0 臂（决策开，基线）**：复用 P3-D2-024 样本 B/C（同确定性、同 config
  maskstat_off、同 seed），**不重跑**。
- 序列/seed/机：`person_tracking`、seed 0、3090 GPU0 单卡串行、确定性套件
  全开（sitecustomize 注入，同探针仪器 `scripts/paper3_bpw/deterministic_probe/`）。
- 冒烟：40 帧 × 1 run 先行（防 config 边界崩：空 update_filter、prune 跳过路径；
  runner 内 MAX_FRAMES **显式赋值** 40——PITFALLS 2026-11-05 P40）。

## §2 比对判据（跑前锁定）

对 D1 两 run 做逐位比对（复用 `compare_three_way.py`，比对集同 B3 口径）：

- **R-div-src（D1 两 run 逐位一致）** ⇒ clone/split/prune 三类决策的阈值翻转
  是分叉放大到 O(+65%) 的**必要环节**（关停后管线可复现）；上游数值分叉源仍在
  （栅格化 backward 候选不变），其影响被该决策反馈放大。
  含义：① 未来甲复活路径 = 确定性栅格化（代码改动级）；② 丙框架 E2 的目标量
  = 决策事件本身。**注意**：仍活跃的其余决策路径（promotion/reset/插入门）
  未被本臂隔离，不排除它们参与放大——结论只写"clone/split/prune 是必要环节"。
- **R-div-loop（D1 两 run 仍分叉）** ⇒ clone/split/prune 决策**不是必要环节**：
  分叉在其余管线（优化循环本体（栅格化 backward → 梯度 → 优化器 → 地图/位姿）
  或仍活跃的 promotion/reset/插入门）内自行发散 ⇒ 放大器假设收窄，数值源更靠
  核心；「仅针对 clone/split/prune 的决策稳健化」不足以恢复臂级判效力。
- **R-crash（冒烟或全长 rc≠0）** ⇒ 记录 raise 即停，config 边界按
  fail-closed 处置（一次有据修正后第二次失败即收口）。
- 附带报告项：D1 的 ATE/高斯数（只描述决策关停态的地图行为，不与任何臂比较）、
  墙钟（不比较，无配对参照）。

## §3 出口与不主张

- 两读法并陈：无论 R-div-src / R-div-loop，**上游数值源的身份（atomicAdd）
  仍是候选推断而非证明**——本诊断只切分"放大器 vs 本体"，不定位算子。
- 不改任何既有判决；不重开任何已关闭族；不产生贡献主张；结果进
  「测量性结论」叙事（装置敏感度证据链第 4 件）与未来甲复活 prereg 前置。
- 3090 单机结论，不外推。

## §4 算力与时间盒

- 冒烟 40 帧（~3min）→ 全长 2 run（~50min，单卡串行）；
- 硬顶：派发后 **4 小时**；到点按已完成 run 收口。
