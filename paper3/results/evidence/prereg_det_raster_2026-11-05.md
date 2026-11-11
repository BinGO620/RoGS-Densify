# 确定性栅格化机制族 L1 预注册（det-raster；P3-D2-027）—— 2026-11-05

**状态**：判据锁定于任何代码改动之前。账本：`P3-D2-027`（D1 自裁立项——用户
2026-11-05 指令「多拿主意，记住原则，往结果方向努力」；R8 新机制族 L1 执行类）。
**目标对齐（成文）**：终点 = 毕业论文研究内容三的正面机制贡献（Bonn 9 序列
ATE ≤5cm）；当前唯一阻塞 = 装置非确定性使臂级效应 <2cm 不可测（P3-D2-022~026
五件证据链）。本族 = **修测量仪器本身**：把管线变成逐位可复现，臂级判据才有
资格复活。仪器修复不进贡献栏（评测协议条款）；它的产出 = 让此后的机制效应
**可测**。

## §0 立项依据（三件）

1. P3-D2-024：torch 官方确定性套件全开仍 9/9 件分叉（零 raise ⇒ 分叉源在
   custom CUDA 栅格化 backward 一类，torch 管不到）；
2. P3-D2-026：clone/split/prune 决策关停仍分叉 ⇒ 不是决策放大器独扛；
3. **KF 模式证据（2026-11-05 零 GPU 补查）**：D1 两 run KF 序列分叉
   （120 vs 121 个 KF，首分叉第 42 个 KF，145 帧不同）——分叉级联进前端
   结构决策改变 run 骨架；全管线 B/C KF 反而一致（116/116）⇒ 粗地图下
   KF 阈值面更贴悬崖。**只有把数值源钉死，前端结构才稳定。**

## §1 L1 设计（可行性探针，杀得起）

- **改动面**：`diff-gaussian-rasterization` backward 的梯度累加
  （atomicAdd → per-tile 缓冲 + 按 gaussian id 分段归约，确定性顺序）。
  **feature 分支**开发（机制修复例外流程②）；主干零改动。
- **开关**：`Rasterizer.deterministic_backward: false`（默认关）——默认关时
  **单测级数学路径全等**（CPU/参考实现断言；run 级逐位在本装置不可达，
  按 `prereg_device_robust_estimand` E1① 收窄口径）；单测覆盖开关两态。
- **外围核（2026-11-05 已过，成本闸 PASS）**：现役源 = `submodules/
  compressed-3dgs-niedermayr/submodules/diff-gaussian-rasterization/`（仓内唯一
  实体副本）；`forward.cu` **0 处 atomicAdd**（前向本就确定，与全部证据一致）；
  `backward.cu` 5 处 atomicAdd 全在 per-pixel 循环内（pixel 内前向序确定，
  非确定性 = 跨像素对同一 gaussian 的归约顺序）+ `backward_indexed.cu` 变体
  一份（后续核其消费方）。改写面 = 单 kernel 累加路径（per-pixel 局部缓冲 +
  按 gaussian id 分段归约），**未超出 L1 预算** ⇒ 不触发 R-over-budget。
- **外部方案扫描（已做，2026-11-05）**：DISTWAR（atomic 优化，非确定性）、
  gsplat（未确认确定性开关）、arXiv 2505.18764（硬件栅格化）——**无现成
  确定性 backward 可换**，自研是唯一路径（来源见判决脚注）。

## §2 L1 成功判据（机械，跑前锁定）

1. **R-feasible**：det-ON + 开关 ON，`person_tracking` 40 帧 × 2 run 同 seed
   ⇒ **逐位一致**（`compare_three_way.py` 10 件 + **KF 模式一致**）且
   rc=0×2 ⇒ 进 L2（全长 2 run 同判据）；
2. **R-infeasible**：开关 ON 仍分叉 ⇒ 止损（一次有据修正机会，第二次失败即
   记「已排除」——与 divsrc R-crash 同款）；
3. **R-over-budget**：实现面超出「单 kernel 累加路径重写」（需动 forward 或
   多 kernel 联动）⇒ 止损，不追加预算。
- L2 通过后：3090 全长 ×2 → 地板重测（确定性态）→ 甲路径（按机标定窄门）
  新 prereg——**都不在本 prereg 范围**。

## §3 算力与时间盒

- 开发在 feature 分支（本地 2060 快筛许可）；40 帧探针每次 ~6min（2060）/ ~3min
  （3090）；3090 正式探针按「算力归属」派发。
- **硬顶：2026-11-12**。到点未达 R-feasible ⇒ 止损收口（负面结果照记，
  仪器维持乙常驻 + 框架 v2 路线）。
- 单测进 `tests/`，全量 pytest 不许红。

## §4 不主张什么

- 本族不产生 ATE 效应主张（它是仪器）；确定性本身不作贡献主张（评测卫生）；
- 修复若成，臂级判据复活**仍须**新 prereg（甲路径按机标定 + 地板重测），
  本 prereg 不预支任何判效结论。
