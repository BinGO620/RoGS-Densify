# E 轴预注册：建图迭代步数的早期调度（KF-warmup itr schedule）—— 2026-11-08

**状态**：判据锁定于任何实现与 run 之前（本件先于代码入库）。
**上游**：novelty 全扫 `novelty_itr_scheduling_2026-11-08.md`（**ADJACENT-ONLY 可立项**：
COLLIDES=0/ADJACENT=12；最近邻 CaRtGS=逐帧重优化频率调度〔静态、渲染 loss 信号、PSNR 终点〕、
Geometry-Aware=预算固定仅敏感性、UP-SLAM=结构自适应）+ 根因分析 `rootcause_rescope_2026-11-08.md`
+ 用户拍板链：P3-D2-044（占位解除）→「先 novelty 全扫再定」（本件即"再定"的落字）。

## §0 价值命题与四维差异化（对 ADJACENT-ONLY 的收窄声明）

| 维度 | 本机制 | 最近邻（CaRtGS / Geometry-Aware / UP-SLAM） |
|---|---|---|
| 对象 | **单次建图调用内的优化步数**（itr） | 逐帧重优化**频率**/权重（CaRtGS）；预算为**固定 setting**（G-Aware）；地图**结构**增删（UP-SLAM） |
| 信号 | 关键帧序数（早期/晚期相位，零额外算力） | 渲染 loss 排序（CaRtGS）；无（固定预算敏感性）；不确定性预测（UP-SLAM） |
| 终点 | **ATE 中位数+方差 parity + 建图算力节省** | PSNR/基元数（CaRtGS）；几何质量（G-Aware）；重建完整性（UP-SLAM） |
| 场景 | 动态在线 RGB-D SLAM（Bonn 动态类，仪器口径） | 静态场景（CaRtGS/G-Aware/UP-SLAM） |

**动机证据（全部本仓已判）**：itr 50/150/300 = ATE 10.66/13.59/18.91（调用次数全同，
`itr_full_580_verdict`）；**40 帧内 itr 不敏感**（50/100/150/300 极差 0.015cm，part1@40帧）；
默认 150 距 25~50 平坦区劣约 3cm（P3-D2-032 收口）；150 在方差洼地（0.32 vs itr=30 的 3.93）。

## §1 机制（最小形态，L1）

**调度规则（预注册写死，零在线信号读取）**：按关键帧序数两段式——

```
itr(call) = 30   若该次建图调用发生于第 8 个关键帧之前（含）
itr(call) = 50   否则
```

- **阈值 8 的来源（校准自本仓测量，非调参）**：40 帧 = pt 序列前 8 个关键帧
  （KF 每 10 帧一枚，40 帧 run 的 KF 模式 0/5/.../35），而 itr 不敏感性恰在
  40 帧内实测（极差 0.015cm）；敏感性在全长才出现（8.25cm 极差）。
- **假设（两条，L1 方向级）**：
  - H-A（算力）：早期低 itr 不伤 ATE ⇒ 相对 fixed-50 省早期建图步数；
  - H-B（精度）：早期少优化**可能更好**——幼地图被 150 步过优化会嵌入漂移
    （150→300 单调劣化的延长线），若实测 scheduled 优于 fixed-50 且超地板，
    是 L2 信号。
- **实现**：`Mapping.adaptive_itr.enabled`（默认 **false** ⇒ 逐位不变）+ `itr_early`/
  `itr_late`/`kf_threshold` 三参数；改动点 = 建图调用读 itr 处（feature 分支，
  代码保护例外流程全套装：默认关逐位一致 + 单测两态 + 2060 冒烟）。

## §2 设计（L1：渐进阶梯，机制主场 1 seed × 3 臂）

| 臂 | 配置 | 定义 | run |
|---|---|---|---|
| A | `instrument_person_tracking`（默认） | fixed itr=150（判读口径） | 1 |
| B | `itrsweep50` 仪器派生（**既有**，复用 P3-D2-032 批 run） | fixed itr=50（已知最优带） | 复用 |
| C | `adaptive_itr_person_tracking`（新） | 调度 30→50 | 1 |

- B 复用合法性：itr=50 臂与本批同 HEAD 链（核心路径零改动自 A4 批沿用）+
  单变量 = `mapping_itr_num` + save_dir（契约单测锁定）；若锚链断裂则补跑 1 run 桥接。
- **总新 run = 2**（A 可复用默认判读口径既有 run——若复用条件同 §2-B 核法则复用，
  否则新跑；上限 3 run ≈ 2h GPU）。

## §3 判据（机械出口，判读器 fail-closed）

- **M1 机制门（C 必须真调度）**：per-call itr 日志 = 前 8 KF 全 30、其后全 50
  （日志证据落盘；任何一步不符 ⇒ `MECH_INVALID`，rc=2）。
- **M2 等价门（ATE parity vs 最优固定点）**：`|ATE_C − ATE_B| ≤ 0.5cm`（0.5cm 判读地板）。
- **M3 省算力门**：`mapping_iterations(C) < mapping_iterations(B)`
  （预期 ≈ −5%（8/58 KF 早期 × (50−30)/50）——**预注册预期值**，门只设方向）。
- **四条出口（互斥）**：
  - `L1_PASS`：M1 ∧ M2 ∧ M3 —— 进 3-seed L2 提名（新 D2）；
  - `L1_ATE_GAIN`：M1 ∧ `ATE_C < ATE_B − 0.5`（H-B 成立信号，优先级最高）
    —— 直接进 3-seed L2 提名（精度主张）；
  - `L1_NO_VALUE`：M1 ∧ (¬M2 ∨ 无算力节省) —— **止损**：机制无增值身份，
    E 轴降级为配置结论（fixed-50 优于默认 ~3cm 进讨论节），调度器代码保留默认关；
  - `INSTRUMENT_INVALID`：前置门（rc0/帧数 580/R-valid 锚）失败。
- **n=1 一律方向级**（纪律：L1 看数再动，L2 才 3 seed）。

## §4 时间盒与止损

硬顶 **2026-11-10 20:00**（实现+单测+冒烟 ≤ 明日；L1 run ≈ 2h，排在 P 批后）。
`L1_NO_VALUE` 即终态（不追加 run、不换信号重试——换信号 = 新 prereg）。

## §5 本件不主张什么

- 不主张 ATE 改善（H-B 只是方向假设，`L1_ATE_GAIN` 才升格）；
- 不主张跨口径可比（仪器口径内自洽；部署口径迁移属批 2 语境）；
- CaRtGS/G-Aware/UP-SLAM 为 ADJACENT 必引（差异表见 §0），论文写作时照
  novelty 工件 §4 清单执行；
- 评测协议不是贡献。

## §6 反悔

revert 实现提交串即回到"novelty 已扫、未立项"状态；判据改动只落本件一处
（amendment 带日期）。
