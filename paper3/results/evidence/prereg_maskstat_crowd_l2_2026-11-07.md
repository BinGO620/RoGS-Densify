# MaskStat crowd L2 预注册（P3-D2-040 开放区收尾）—— 2026-11-07 03:4x

**状态**：判据锁定于任何 crowd MaskStat run 之前。**判据结构整体沿用
`prereg_maskstat_instrument_2026-11-05.md` §3（逐字沿用出口与门槛），本件只改：**
序列（pt → crowd）、seed 数（首轮 2 seeds，命中延长线再补 seed 2）、动机（自调节泛化
探针测得 crowd churn = 28.9%，pt 的 1.7×——高 churn 区的既有机制 ATE 级从未测试，
`selfreg_generalization_2026-11-07.md` §二 出路 1）。

---

## §1 设计

| 臂 | 配置 | 说明 |
|---|---|---|
| off | `instr_off_crowd`（已存在） | crowd 基线（机制零键） |
| on | `instrument_maskstat_on_crowd`（本件派生） | off + Mapping.maskstat 自持块（4 个自持键 + 总开关，与 pt on 臂同构） |

- 单变量约定沿用 pt 族：机制 = `Mapping.maskstat_*` 整块（off 无此块、on 有），
  解析后 diff = 5 个 maskstat 键 + 两条路径键。
  **计数更正（2026-11-07 07:5x，G2-重大3 处置）**：上句为判据视角（load_config 解析后）；
  run 内 config.yml 的 diff 还含 `Dataset.sequence`（config basename 标签，
  rng 由两臂同值的 `rng_sequence: crowd` 决定，非行为变量）等注入键——
  两口径的完整 diff 见工件 `maskstat_crowd_l2_config_diff_2026-11-07.txt`。
  单变量结论经 G2 独立复算成立。
- 序列 crowd **全长**（仪器口径，`mapping_itr_num=150`（族口径不变））。

> **更正（2026-11-07 07:3x，判读前发现）**：本件原文误写「全长 580 帧」——580 是
> person_tracking 的全长；crowd 实际全长 = **928 帧**（rgb.txt 930 行 ⇒ 加载 928 帧）。
> 6 个 run 实际跑的就是全长 928 帧（`max_frames=0`，全 rc0），判据意图（「全长」）
> 已满足；判读器已补 `--expect-frames`（提交 `926a5f100`）并按 928 判读。
> 此更正不改变任何出口路由。**§3 硬门表中的「帧数 = 580」同步更正为「帧数 = 928」**
> （同一次笔误，G2-次要② 指出原更正注漏改该行）。
>
> **时序锚更正（2026-11-07 07:5x，G2-重大1 处置）**：本件头部原自署「03:4x」、
> 更正注自署「07:3x」，均为**笔误**（实际创建时刻分别为 local ~02:55–03:02 与
> ~06:55–07:01，以 git 提交时间为准：prereg 入 commit `a1975d1ff` = local
> 03:02:10；更正入 `fc72ee0a9` = local 07:01:26）。批日志头部 `02:57:04` 为
> **远端时钟**（实测 remote 落后 local 6m07s，与 P3-D2-024 记录的 ~6m11s 一致；
> 本地 `date` 07:11:35 vs 远端 `date` 07:05:28，2026-11-07 实测）⇒ 折算后
> 批启动（local ~03:03）在 prereg 提交（local 03:02:10）**之后**约 1 分钟——
> **判据先于 run 成立**。DISCIPLINE「本地→远程工作流·跨机时间戳纪律」
> （跨机比时先对钟、以工件锚链为准）即为此类比对而设。
- **预期管理（预先写死）**：MaskStat 在 pt 上是**负向**（+0.65cm）；本件没有正面先例，
  crowd 的高 churn 是「值得看一眼」的理由，不是「预期有益」的证据。最可能的出口是
  负向或不可判——两个结果都完成戊的边界刻画（「最近似的机制在高 churn 处也无益/无差异」）。

## §2 run 布局（6 run）

| # | 臂 | seed | 用途 |
|---|---|---|---|
| 1–2 | off | 0 | R-valid（两 run 须 R1） |
| 3 | off | 1 | 主臂 |
| 4–5 | on | 0 | R-valid（两 run 须 R1；on 臂多跑 MaskRCNN，新非确定源必须验） |
| 6 | on | 1 | 主臂 |

双卡：GPU0 = off 链；GPU1 = on 链。约 50min/run ⇒ ~2.5h。

## §3 前置门与判据（沿用族 prereg，逐字）

- **R-valid**：两臂 seed0 各两 run `compare_three_way.py` 判 `R1_bitwise_identical`；
  任一 R2 ⇒ 整批作废。
- **硬门**：帧数 = **928**（crowd 全长；原笔误 580，见 §1 更正注）；`finished_rc0=yes`（缺锚点即拒）。
- **G4 作用量门**（沿用原族 rule 2）：on 臂 `share_w_lt_1 < 5%` 或 `mean_w > 0.98`
  ⇒ 机制无作用量，止损记「已排除」（crowd 预期 share_w_lt_1 很大，此门预期过）。
- **出口**（n=2）：
  - 同号且 \|median Δ\| ≥ 0.5cm ⇒ **`EXTEND_SEED2`**（补 seed 2 后按三 seed 规则终判；
    方向如实记录，负向即关闭、正向即论文 3 首个正面机制读数候选）；
  - 同号且 \|median Δ\| < 0.5cm ⇒ `BELOW_CLAIM_FLOOR`；
  - 异号 ⇒ `SEED_UNSTABLE`；
  - 高斯比作为报告项并陈（不设 1.5 闸——MaskStat 不改剂量，pt 实测比 ≈1.0；
    若 crowd 上比偏离 >10% 如实登记为异常）。
- 判读器：`judge_maskstat_instrument.py`（原样复用，换根目录）。

## §4 本件不主张什么

- crowd 的 churn 高 ≠ 机制有益的先验（§1 预期管理）。
- 本件不复活剂量轴、不新增机制设计（MaskStat 是既有实现，config-only）。
- 单序列 L2 ⇒ 无论出口如何都不主张跨序列泛化；正读数进 L3 前须预注册扩展。
- 评测协议不是贡献。

## §5 时间盒

硬顶 2026-11-07 12:00。到点按已完成最高阶段收尾，不加 run。
