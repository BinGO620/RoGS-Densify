# MaskStat 预注册（动态占比加权的致密化统计）—— 2026-11-04

**状态**：判据锁定于任何机制代码/正式 run 之前（账本 `P3-D2-016`；用户 2026-11-04 授权夜间自动演进）。
**原则**：沿用 `PREREGISTRATION.md` §3.2（逐序列地板 + 预注册 MDE 核算）与 `DISCIPLINE.md` 全部条款。

## 0. 研究问题与机制形态

**问题**：MonoGS 原版 ADC 的致密化统计（`xyz_gradient_accum / denom`）把**全部像素**的屏幕空间
梯度计入分母与分子——动态物体（人）剪影处的巨大光度残差直接污染统计 ⇒ 人物剪影上的高斯被
持续 clone/split（幽灵致密化），地图被动态残差无条件放大（`PROBLEM.md` H1→H2）。

**机制（MaskStat）**：每个视角对统计的贡献按该视角**静态像素占比** w 加权：

```
xyz_gradient_accum[update_filter] += w * grad_norm   （原式 += grad_norm）
denom[update_filter]              += w               （原式 += 1）
w = 1 - dynamic_pixel_ratio(viewpoint)               （运行期语义掩码，逐 KF 缓存）
```

- **无阈值参数**（不逐序列调参；w=1 视角 ⇒ 与基线逐位一致；全动态视角 w=0 ⇒ 不贡献）。
- **单变量保证**：loss、优化器、剂量通路、trace 开关全部不动；两臂唯一行为差别 = 统计加权。
  两臂 config **都**开 `SemanticMask.enabled`（掩码在 off 臂算但**不被消费**），唯一差别
  = `Mapping.maskstat_dens_stats: true/false` —— 掩码计算本身无行为副作用（no_grad、无 RNG）。
- **机制输入口径**：运行期 MaskRCNN person 掩码（`dynamic_classes: [1]`，dilate 5px，逐 KF
  缓存于 viewpoint）。这是**机制输入**而非评测仪器；本族判决（ATE/剂量）不消费任何掩码，
  不触碰 `DISCIPLINE.md`「测量口径」#3 的仪器单源约束（canonical `dynamic_mask/` 仍归评测链）。
  ⛔ **本条掩码供给方式已被 Amendment A1 取代（2026-11-04，判读数据前）**：
  掩码改由 MaskStat 自持参数块（`Mapping.maskstat_*`）直供，off 臂不含任何语义掩码段
  —— 原文「两臂都开 `SemanticMask.enabled`」实测会混入他族机制行为（该标志另有 ≥5 处
  消费者），见 `prereg_maskstat_amendment_a1_2026-11-04.md`。
- **默认关**：`Mapping.maskstat_dens_stats` 缺省/false ⇒ 代码路径与主线逐位一致（回归测点）。

**为何是这条轴（与已关闭族的关系）**：FDose n=6 已判「等剂量下换放置键」无 ≥MDE 效应 ⇒ 放置轴
关闭；本仓 12 个关闭族全部在「换信号源 / 换权重形状 / 换放置 / 换对照」层，**统计输入纯度**
（谁有资格给 ADC 喂梯度）从未被干预。文献同向：StopThePop 2402.00525（排序污染统计）、
CountingContributions 2610.27108（view-count 分母污染）、TAD-GS/RobustSplat（动态瞬态致密化元凶）。

## 1. 装置与臂

- 序列：`person_tracking`（唯一 headroom 序列，地板 3.83cm；r33 基线 10–13cm）。
- 臂：`maskstat_off`（基线，带掩码计算但不消费）/ `maskstat_on`（机制开）。
  同 HEAD、同 `rng_sequence`、因果孪生（初始点云与随机 KF 序一致）。
- 种子：**L1 = seeds 0/1**（seed 两级纪律：迭代 2 seeds；晋级 3 seeds 才谈确认）。
- 算力：先探远程 3090；可达 ⇒ 正式批走远程（权威）；不可达 ⇒ 本地 2060 串行（**非权威**，
  产物标 provisional，不进论文表）。
- 冒烟：40 帧（`--max-frames 40`）先过装置门再放全长。

## 2. 机制门（确定性读数，先于 ATE；`tests/densification/test_maskstat_stats.py`）

- **G1 关闭态逐位一致**：`maskstat_dens_stats` 缺省/false ⇒ `add_densification_stats` 数学路径
  与原式逐位一致（单测：weight=None 与原公式全等；w=1.0 与 weight=None 全等）。
- **G2 加权语义**：w=0.25 ⇒ accum 精确 ×0.25、denom 精确 +0.25×n；w=0 ⇒ 零贡献。
- **G3 fail-closed**：maskstat 开但掩码不可得（`SemanticMask.enabled=false` 或掩码为 None）
  ⇒ RuntimeError，**不得**静默按 w=1 退化（M3 类静默组件坑）。
- **G4 trace 落盘**：on 臂逐 mapping call 写 `maskstat_trace.csv`
  （`iteration,n_entries,mean_w,share_w_lt_1,share_w_eq_0,mean_mask_ratio`），机制激活证据。
- **G5 RNG 无扰动**：掩码计算不消耗全局 RNG（no_grad + 无随机算子）；冒烟期 off 臂与
  `bpw_off` 同 seed 冒烟对照 F1 式核一遍（如装置允许）。

## 3. ATE 与剂量判读（L1，n=2）

- 主判据：`ΔATE(on − off)` 逐 seed 配对（全帧 `ate_rmse_cm`，tracking_raw.csv 第 8 列）。
- **功效核算（§3.2(b) 强制）**：sd = 1.491（来源 A：bpw on−off 逐 seed 配对差，3 seeds）
  ⇒ **MDE(2) = 13.4cm** —— n=2 **不可能判显著**。因此 L1 的 ATE 是**方向参考**，不是门：
  - 只允许写「方向一致 / 方向不一致」，不允许写「改善/退化」；
  - 晋级 3 seeds（明晨）的条件 = 机制门 G1–G5 全过 **且** 2 seeds 方向一致且非劣
    （Δ 均值 < +地板 3.83cm 的一半即 +1.9cm）。
- 剂量三口径并陈（源点/gross/净存活以终态高斯数代理）：`on` 终态高斯数 **≤ off × 1.10**
  （G6 非爆炸门；机制预期是**减**剂量——动态区少长）；剂量下降本身**不是**收益证据
  （P3-D2-004 教训：信号正确而剂量保守 ≠ 好），只作机制作用量的量化。
  ⛔ **1.10 门带宽已被装置自差证据废止为判效带宽（2026-11-05，P3-D2-023 乙案）**：
  3090 同 config 同 seed 自差 −30.3%~+96.8%，1.10 门 << 装置噪声。G6 作为机械出口的
  历史角色不变；此后臂级判读按 `prereg_device_gate_2026-11-05.md` Part A2 执行。
- 渲染指标不作判据（§3.1 反相关教训）；`G−k0` 类报告项本族不适用（无第三臂）。

## 4. 出口规则（看数据前锁定，按序机械应用）

1. **装置失效**：G1–G5 任一不过 ⇒ 冻结读数、修装置、按原判据重跑。不得解释机制。
2. **机制死**：G4 显示 on 臂 w 分布与 off 臂不可区分（share_w_lt_1 < 5% 或 mean_w > 0.98）
   ⇒ 机制无作用量，本族止损记「已排除方向」（与 BPW/CGB/FDose 并列）。
3. **方向可判**：机制门全过 + 2 seeds 方向一致 + mean Δ < −地板一半（−1.9cm）⇒ 晋级
   3 seeds 确认（明晨 G2 审查后派发）。
4. **落在延长区**：方向一致但 |mean| < 1.9cm ⇒ 扩 seed 2（n=3）重判一次；仍不显著 ⇒ 规则 5。
5. **不可判**：方向不一致或 n=3 仍 |Δ| < MDE(3)=3.70cm ⇒ 记「不可判」，写进 NOTES
   「已排除方向」同一条（与 BPW/CGB/FDose 并列），不作任何效应主张。
6. **报告项**：终态高斯数比、w 分布直方（每 seed）、掩码占比逐 KF 分布；不参与 PASS/FAIL。

## 5. 时间盒与夜间硬顶（DISCIPLINE「时间盒与硬门」）

- **硬顶 2026-11-05 06:30**：到点按当时已完成的最高出口规则收尾，**不加 run**、不「再给一点时间」。
- 阶梯：冒烟(40 帧×2臂) → 装置门 → seed0 双臂全长 → 判读 → seed1 双臂全长 → 判读 →
  （余量 >2h 才许）+1 不同类型序列 1 seed 预筛。
- 失败处置：全长 run rc≠0 ⇒ 该 run 记 FAIL 不补跑凑数；机制性失效（可复现）⇒ **一次**有据
  诊断 + 修正迭代（时间盒内），第二次失败即止损。

## 6. 本预注册不主张什么

- n=2 的任何 ATE 数字不构成效果结论（MDE 13.4cm）；
- 剂量下降不是收益；「不退化」不是贡献；
- 本族无论结果如何，**判决工件都标 provisional（本地 2060）**，进论文表须远程 3090 复跑；
- 机制若过门，正面叙事权归「把可靠性统计接入致密化判据」整条线，与本族单一实现解绑。
