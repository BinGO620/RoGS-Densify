# MaskStat crowd L2 判决 —— 2026-11-07 07:4x（P3-D2-040 开放区收尾）

**判决（机械，按 `prereg_maskstat_crowd_l2_2026-11-07.md` §3）**：
**`SEED_UNSTABLE`**（n=2 异号；未触发 EXTEND 线）⇒ **未检出可判收益**。

**一句话**：在 churn 最高（28.9%）的 crowd 上，最接近「压制动态区生长」的既有机制
（MaskStat）作用量充分（G4 PASS），但 ATE 读数跨 seed 异号（−0.32 / +0.50）——
戊边界的开放区在 ATE 级得到第一个（诚实的）null 读数。

---

## 一、判决数据（3090 双卡，crowd 全长 928 帧，rc0=yes × 6）

| seed | off ATE | on ATE | Δ (on−off) | 高斯比 |
|---|---|---|---|---|
| 0 | 3.4004 | 3.0819 | **−0.3185** | 0.9368 |
| 1 | 2.0305 | 2.5279 | **+0.4974** | 1.1487 |

- median Δ = +0.09cm（无方向）；0.5cm 门槛未达 ⇒ 不触发 EXTEND_SEED2。
- **G4 作用量门 PASS**：on 臂 map 段 27750 行中 76.8% 的调用 share_w_lt_1 > 0
  （均值 0.466）、mean_w = 0.863、mean_mask_ratio = 0.137 ⇒ 掩码加权真实改变了
  致密化统计输入（作用量比 pt 更大：pt mean_w 0.906）。
  **口径注（G2-次要①）**：上列 G4 数字取 seed0 单 run（27750 行 = 单 run 的 map 段；
  两 seed 合计 83250 行），seed1 量级相同（未并陈）。
- **前置门**：两臂 seed0 各两 run `R1_bitwise_identical`（same=12 diff=0）；
  6/6 帧数 = 928；6/6 `finished_rc0=yes`。
- **机制自身开销（G2-次要⑥，如实登记）**：on 臂 backend 语义掩码调用 186 次
  （off 臂 0；semantic_timing/summary.json total 1114 vs 928），耗时 ~23.8s——
  这是 MaskStat 在 mapping 段算权重的固有成本，属机制代价的一部分，
  不是两个臂「同成本不同结果」的比较。

## 二、两处如实登记

1. **prereg 帧数笔误**：原文写「全长 580 帧」，crowd 实际全长 928
   （更正见 prereg 内 2026-11-07 07:3x 注）。run 本身就是全长，判据意图满足，
   出口路由不受影响。判读器硬编码 580 曾把本批误判 INVALID，已修
   （`--expect-frames`，提交 `926a5f100`）。
2. **高斯比异常（prereg §3 预登记的登记义务）**：seed1 ratio = 1.1487 > 1.10。
   pt 上 MaskStat 不改地图规模（比 ≈1.0），crowd seed1 的 +15% 偏离与 seed0 的
   −6% 方向相反 ⇒ 更像 seed 间抖动而非机制性膨胀（n=2 无法分辨）；
   按约登记，不作解释性收编。

## 二bis、G2 审查处置（Accept-with-conditions：0 致命 / 4 重大 / 6 次要；全部已处置）

| # | 条件 | 处置 |
|---|---|---|
| 重大1 | 批日志 02:57:04 印 HEAD=a1975d1ff「早于」该 commit（03:02:10） | **钟差解释成立**：实测 remote 落后 local 6m07s（P3-D2-024 同款 ~6m11s）；02:57:04(远端) = ~03:03(本地) ⇒ 批在 commit 后 1 分钟启动，**判据先于 run 成立**；prereg 头部自署时间笔误已更正（prereg 时序锚更正注） |
| 重大2 | --expect-frames 无回归单测 | 已补 2 用例（928+flag ⇒ SEED_UNSTABLE 非 INVALID；默认 580 ⇒ INVALID 且 rc=2），随本判决 commit；全量 pytest **581 passed** |
| 重大3 | 「两条路径键」计数与 run config.yml diff 不符 | prereg 计数更正 + 工件 `maskstat_crowd_l2_config_diff_2026-11-07.txt`（两口径 diff 全文）；单变量结论经审查方独立复算成立 |
| 重大4 | 「判读器误判 INVALID」无可复跑工件 | 复现件 `maskstat_crowd_l2_expect580_repro_2026-11-07.txt`（现行判读器不带 flag 重跑 ⇒ 同款 INVALID）+ §五补判读命令行 |
| 次要① | G4 数字为 seed0 单 run 口径 | §一加口径注 |
| 次要② | 更正注漏改 §3 硬门行 | prereg §3 硬门行同步更正为 928 |
| 次要③ | 出口词三套不同名（脚本 DIRECTIONAL_EFFECT / prereg EXTEND_SEED2） | **登记映射**：脚本 DIRECTIONAL_EFFECT@n=2 ≡ 本 prereg EXTEND_SEED2；本案出口 SEED_UNSTABLE 同名，无实际影响；n=2 命中延长线时以 prereg 词为准 |
| 次要④ | KEY_REGISTRY 未登记 | 已补 `prereg_maskstat_crowd_l2_2026-11-07.md` 行（MISSING_TOTAL=0） |
| 次要⑤ | 兄弟判读器（judge_dose_scan / judge_dose_a4）同样硬编码 580 | 登记为债务：两族现仅 pt（580 正确），未来扩序列时须同款参数化（本判决不改，避免无消费方的代码改动） |
| 次要⑥ | on 臂 semantic_calls 1114 vs off 928 | §一登记：机制自身开销（backend 186 次掩码调用） |

顺带修复（处置重大2/复现件时暴露）：`judge_maskstat_instrument` 的 INSTRUMENT_INVALID
退出码原为 0（G3-M6 同款 fail-open，前轮整改只覆盖了 judge_dose 两族）⇒ 已改 rc=2
并写进回归测试。

## 三、判读：开放区的 ATE 级第一读数

自调节泛化探针（`selfreg_generalization_2026-11-07.md`）把戊边界切成两半：
低 churn 区（pt 16.7% / balloon 17.6%）已判（四机制零/负），高 churn 区（crowd 28.9%）
开放。本件在开放区放下了**第一个 ATE 级读数**：

- 机制作用量充分（G4 PASS，且比 pt 更强）⇒ 「没效果」不是「没生效」；
- 但 Δ 异号、量级 ±0.3–0.5cm（crowd 本身是易序列，off 已 2.0–3.4cm）⇒ 无可主张收益；
- 结合 pt 的负向（+0.65cm）与四族的零/负，**「统计纯度轴」在两个 churn 区都没有正面读数**。

**边界刻画的当前形态**（供戊章骨架用）：
- 观测资格门族：结构性无着力点（denom 四序列饱和）；
- 统计纯度族：pt 负向（低 churn）、crowd 异号（高 churn，n=2）——两个区都无正面读数；
- 剂量：↑ 有害（干净），↓ 与地图坍缩混杂（不可判）；
- 自调节：普适存在但强度序列相关（16.7–28.9%）——**churn 梯度本身就是
  「何时需要关注致密化」的候选指标**（这是研究内容三剂量章的衔接点）。

## 四、本判决不主张什么

- n=2 异号 ⇒ 不主张「MaskStat 在 crowd 上无影响」，只主张「未检出可判收益」。
- crowd 是易序列（off 2.0–3.4cm），天花板效应可能压缩可判区间——如实登记，
  不据此把「无收益」外推到难序列。
- 仪器口径绝对值不与 async/文献比。
- 评测协议不是贡献。

## 五、工件与审查

- 判读 JSON：`maskstat_crowd_l2_judge_2026-11-07.json`（928 口径，钉死帧数）。
- 原始 run：`results/paper3_bpw/instr_off_crowd/`（3 run）+
  `results/paper3_bpw/instrument_maskstat_on_crowd/`（3 run）+ 批日志
  `maskstat_crowd_l2_20261107.log`（含两臂 R-valid 比对）。
- **判读命令（G2-重大4 要求留痕）**：
  `python scripts/paper3_bpw/judge_maskstat_instrument.py --off-root results/paper3_bpw/instr_off_crowd/datasets_bonn/instr_off_crowd --on-root results/paper3_bpw/instrument_maskstat_on_crowd/datasets_bonn/instrument_maskstat_on_crowd --seeds 0 1 --expect-frames 928 --out paper3/results/evidence/maskstat_crowd_l2_judge_2026-11-07.json`（远端 3090 执行）。
- 复现件：`maskstat_crowd_l2_expect580_repro_2026-11-07.txt`（同一命令去掉 --expect-frames ⇒ 复现判读器修复前的 INVALID）。
- slam-critic G2 = **Accept-with-conditions**（0 致命 / 4 重大 / 6 次要），条件全处置见 §二bis；报告 `/tmp/slam_critic_g2_maskstat_crowd_l2_2026-11-07.md`。
