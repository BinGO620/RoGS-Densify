# 剂量过供给验证批预注册（P3-D2-041）—— 2026-11-07 07:4x

**状态**：判据锁定于本批任何 run 之前（本件随 configs/tests 同 commit 入库，先于派发）。
**方向**：用户 2026-11-07 拍板「剂量过供给：测量、预测与重标定」为研究内容三正题。
**母件**：`prereg_dose_reverse_2026-11-06.md`（单变量约定与 ratio 带）+
`selfreg_generalization_2026-11-07.md`（churn 梯度：crowd 28.9% > mnobox 21.2% > balloon 17.6%，
pt 16.7%）+ `dose_scan_verdict_2026-11-07.md`（pt 上 tau4x = −2.626cm / 0.22× 地图）。

---

## §1 核心可证伪预测（本批存在的理由）

> **H1（churn→增益同序）**：tau4x（grad 0.0008）相对默认的 ATE 改善量
> （gain = −median Δ，越大越好）在三类序列上按 churn 排序：
> **gain(crowd) > gain(mnobox) > gain(balloon)**。
>
> 机理：churn 高 = 短暂可见性出生多 = 剂量过供给越严重 = 重标定的可回收空间越大。

**H1'（pt 上已有读数作为锚）**：gain(pt) = 2.626cm（churn 16.7%）。
H1 若成立，则五点 (churn, gain) 应呈正相关——pt/balloon 低增益、crowd 高增益。

## §2 左端点（前沿形状，无 PASS/FAIL）

**H2（内部最优）**：densify 全关臂（dose_zero）的 ATE 相对默认的位置决定前沿形态。
历史锚：旧栈 A6（无致密化）55.80 vs A0 44.44 = 劣化 **+25.6%**（audit §2.1 表口径；
NOTES 均值口径 43.87 下为 +27.2%——两口径并存，引用时声明），仅方向参考。

> **形态分类更正（2026-11-08 01:5x，G2-致命1 处置）**：原文三形态的不等式链
> 排版错乱（形态二「默认 < dose_zero < tau4x」与其标签「内部最优」不自洽；
> 形态三的不等式与其解释「关掉最好」相矛盾）——属本件写作缺陷，实测数据
> 由此无法按原文归类。更正后的三形态（按「三测点 ATE 排序」语义）：
> - **形态一**：dose_zero 最优（dose_zero < 默认 且 dose_zero < tau4x）
>   ⇒ 致密化整体负资产；
> - **形态二**：**tau4x 最优**（tau4x < 默认 且 tau4x < dose_zero）
>   ⇒ 最小值位于 [0, 1×] 内部、零端点明确更差 ⇒ **内部最优成立**（标定故事最佳形态）；
> - **形态三**：默认最优（默认 < tau4x 且 默认 < dose_zero）⇒ 默认剂量已近最优。
>
> 实测（tau4x −2.63 < 默认 0 < dose_zero +3.62）= **形态二**。
> **附加限定（G2-致命2）**：tau4x 点带剂量混杂标记（地图 0.22×、static PSNR
> −1.07~−1.43dB，归因未决，`dose_scan_verdict` 的 INCONCLUSIVE 不撤销）⇒
> H2 结论限定为「**ATE 轴上**三测点最小值在 ÷4」，不作「减量更好」的归因主张。

## §3 设计（单变量约定沿用 P3-D2-039：percent_dense 三臂全 0.01，纯 grad 轴）

### 3.1 左端点（pt）

| 臂 | 配置 | 定义 |
|---|---|---|
| dose_zero | `instrument_dose_zero_person_tracking`（新） | `opt_params.densify_grad_threshold: 1000000000`（**纯整数字面量**——PyYAML 会把 `1.0e9` 解析成 str 的坑，PITFALLS 已登记） |

clone/split 永不触发（init 段与 map 段同一键）⇒ 地图 = 初始 + KF 插入 − 自调节 prune。
seeds 0/1/2 × 1 run = **4 run**（s0×2 R-valid + s1 + s2；全长）。

> **帧数更正（2026-11-08 01:5x，判读前发现）**：各序列期望帧数 = rgb.txt 行数 − 2
> （pt 580、crowd 928、balloon 439、mnobox 778）——本件原文写 582/441/780 系
> 同一来源笔误（与 2026-11-07 crowd L2 的 580/928 笔误同源）。run 实际全是
> 全长（`max_frames=0`，rc0=yes），判据意图满足；run 总数相应为 **17**（zero 4 +
> 三序列 tau4x 各 3 + balloon/mnobox off 各 2），非原文 16。

### 3.2 L2 泛化（三类序列 × tau4x × 2 seeds）

| 序列 | tau4x 臂 | off 臂 | 帧数 |
|---|---|---|---|
| crowd | `instrument_dose_tau4x_crowd`（新） | **复用** `instr_off_crowd` s0/s1（MaskStat L2 批已产，同代码链） | 928 |
| balloon | `instrument_dose_tau4x_balloon`（新） | `instr_off_balloon` s0/s1（**新跑**） | 439 |
| moving_nonobstructing_box | `instrument_dose_tau4x_moving_nonobstructing_box`（新） | `instr_off_moving_nonobstructing_box` s0/s1（**新跑**） | 778 |

每序列 tau4x × 2 seeds + （balloon/mnobox）off × 2 seeds。

### 3.3 总账

新 run = 4（zero）+ 3（crowd tau4x）+ 5（balloon）+ 5（mnobox）= **17 run**
（原文 13 系漏计 R-valid 复跑与 zero s0×2；实测 17 run 全 rc0）。

### 3.4 批次等价性与单变量

- 代码链自 A4 批（`250554d8e`）以来核心路径零改动（`git diff --stat 250554d8e..HEAD
  -- utils/ gaussian_splatting/ slam.py submodules/ configs/rgbd/ configs/experiments/combined_prune/`
  为空，2026-11-07 复核）⇒ off 臂复用合法（等价门沿 P3-D2-038/039 结论）。
- crowd off 复用自 MaskStat L2 批（`instr_off_crowd` s0×2 / s1，928 帧全 rc0）。
- 单变量机械守护：`dose_tau4x_<seq>` vs `instr_off_<seq>` 解析后 diff 恰为
  {densify_grad_threshold, save_dir, inherit_from}；`dose_zero` vs `instrument_maskstat_off`
  同理——契约单测锁定。

## §4 前置门与判据

- **硬门**：帧数 = 各序列全长（582/928/441/780，per-sequence 断言）；`.done` 的
  `finished_rc0=yes`（缺即拒）；R-valid：dose_zero s0 ×2 + 每序列 tau4x s0 ×2
  （同 config 同 seed 须 R1——`compare_three_way.py`；**不通过 ⇒ 整批作废**）。
- **H1 判读（机械）**：
  - gain(seq) = −median{Δ(tau4x − off) per seed}；某序列两 seed 异号 ⇒ 该序列 gain 记
    「未判」（不取中位假装有值）。
  - **`PREDICTION_CONFIRMED`**：三序列 gain 均可判且严格同序（crowd > mnobox > balloon）
    且 crowd gain > 0.5cm。
  - **`GAIN_NO_PREDICTOR`**：三序列均可判且都 > 0.5cm 但排序错乱。
  - **`SEQUENCE_DEPENDENT`**：部分序列可判为正、部分未判/无增益。
  - **`NO_GENERALIZATION`**：三序列均可判但都 < 0.5cm 或为负。
- **H2 判读**：报告 dose_zero 相对默认的三 seed 中位差与相对 tau4x 的位置（§2 三形态）。
- **报告项**：各臂 online_num_gaussians（地图规模是本故事的一半）；static PSNR /
  depth_l1（渲染代价并陈，不作闸）；waste_ratio（40 帧账本，作为预测子与 gain 配对）。

## §5 本件不主张什么

- tau4x 的 pt 读数是仪器口径；本批同为仪器口径 ⇒ 内部可比；**async 迁移另行检查**
  （自差包络如实报），不在本批。
- H1 相关性即使成立也是 n=4 序列的梯度——不主张普适定律，主张「可操作的诊断量」。
- percent_dense 不动；不改机制；剂量是配置结论。
- 评测协议不是贡献。

## §6 时间盒

硬顶 2026-11-08 12:00。到点按已完成最高阶段收尾，不加 run。
单 run rc≠0 补跑最多一次；二次失败止损该臂。
