# 剂量过供给验证批判决 —— 2026-11-08 02:3x（P3-D2-041；G2 审查后定稿）

**判决（机械，按 `prereg_dose_oversupply_2026-11-07.md` §4）**：

- **H1（churn→增益同序）：证伪**。实测增益序 = crowd(+0.72) > balloon(+0.24) >
  **mnobox(−0.50)**，与预测序 crowd > mnobox > balloon 相比 **mnobox 倒挂**
  ⇒ **`SEQUENCE_DEPENDENT`**。
- **H2（左端点）：按更正后的形态二 = 实测形态**。三测点 ATE 排序
  **tau4x(−2.63) < 默认(0) < dose_zero(+3.62)**（中位）⇒ 最小值位于 [0, 1×] 内部、
  零端点明确最差 ⇒ **内部最优成立（ATE 轴上）**；
  **限定（G2-致命2）**：tau4x 点带剂量混杂标记（地图 0.22×、static PSNR
  −1.07~−1.43dB、归因未决，`dose_scan_verdict` 的 INCONCLUSIVE 不撤销）⇒
  不作「减量更好」的归因主张，只主张 **ATE 轴位置**。

**一句话**：剂量过供给**存在但序列相关**——ATE 轴上默认值在 pt/crowd 侧可回收
（2.63 / 0.72cm，前者归因未决）、在 mnobox 减量反而有害（−0.50）；**churn 不预测
方向**（可证伪预测被诚实处决）；地图规模收益普适（全序列 tau4x 0.197–0.255×）。
判读 JSON：`dose_oversupply_judge_2026-11-08.json`。

---

## 一、读数（3090 双卡，全长，**17 run** 全 rc0=yes，4 对 R-valid 全 `R1_bitwise_identical`）

### 1.1 H1 三序列（tau4x vs off，n=2/序列）

| 序列 | off ATE (s0/s1) | tau4x ATE (s0/s1) | gain (−medΔ) | 地图比 | 判定 |
|---|---|---|---|---|---|
| crowd (928f) | 3.4004 / 2.0305 | 2.0322 / 1.9570 | **+0.7208** | 0.2429 / 0.2553 | 可判为正（>0.5cm） |
| mnobox (778f) | 1.9930 / 2.0323 | 2.4653 / 2.5690 | **−0.5045** | 0.1994 / 0.1971 | 可判为负（两 seed 同号变差） |
| balloon (439f) | 2.9904 / 2.8302 | 2.7318 / 2.6113 | +0.2388 | 0.2246 / 0.2390 | 低于 0.5cm 地板（仅方向） |

- 帧数口径：**各序列期望帧数 = rgb.txt 行数 − 2**（crowd 928 / mnobox 778 /
  balloon 439 / pt 580）——prereg 原文 582/441/780 系笔误，带日期更正（prereg §3）。
  run 全部为全长（`max_frames=0`，rc0=yes）。
- 消费 run（M3 针）：judge JSON per_seed 内逐 run 锚（crowd off = MaskStat L2 批
  `2026-11-07-04-13-12`/`05-29-18` 等）。

### 1.2 H2 左端点（pt，dose_zero 4 run：s0×2 R-valid + s1 + s2）

| 臂 | ATE (s0/s1/s2) | 地图 (s0/s1/s2) | static PSNR |
|---|---|---|---|
| 默认（复用 off 基线） | 13.5941 / 13.9182 / 13.7268 | 51073 / 46028 / 51296 | 28.58 / 28.85 / 28.56 |
| dose_zero（densify 全关） | 14.2871 / 19.9406 / 17.3438 | **7450 / 7799 / 7421** | **21.93 / 22.52 / 22.58** |
| **Δ (zero − 默认)** | **+0.693 / +6.022 / +3.617（中位 +3.617）** | **≈0.15×** | **−6.3 ~ −6.6 dB** |

**报告项（G2-重大3 补兑现，prereg §4）**：
- dose_zero 地图 = 默认的 **0.146–0.152×**、static PSNR 掉 **6.3–6.6dB** ⇒
  「全关」在地图规模与渲染上都是灾难，ATE 只劣化 +3.62 ——
  过供给叙事的物理基础（致密化贡献了 85% 的地图与大部分渲染质量）。
- churn×gain 配对（40 帧账本 churn 为预测子）：pt 16.7%→+2.63*、crowd 28.9%→+0.72、
  mnobox 21.2%→−0.50、balloon 17.6%→+0.24（*pt 点带混杂标记）——
  **散点无单调关系**，H1 证伪的量化形态。
- tau4x 各序列 PSNR/depth_l1：crowd static −0.87/−0.92/−0.43dB（depth_l1 反向改善
  20.3/18.5/19.7 vs off 23.5/22.0/23.9）；mnobox/balloon 同向小幅——已在
  `dose_scan_verdict` 报告，此处不重复展开。

### 1.3 前置门

- R-valid 4 对（dose_zero s0、crowd/balloon/mnobox tau4x s0）全部
  `R1_bitwise_identical`（批日志 `dose_oversupply_batch_20261107.log`，15557 行，
  比对段逐对指向本批 run 时间戳：14-58-32/16-10-25、19-21-11/19-56-32、
  20-50-28/21-50-41 等）。
- 17/17 帧数 = 各序列全长、17/17 `finished_rc0=yes`。

## 二、判读

### 2.1 H1 证伪意味着什么（如实、不粉饰）

预测「churn 高 ⇒ 过供给重 ⇒ 减量收益大」在 mnobox 上**方向相反**：churn 第二高
（21.2%）却是唯一减量有害的序列。可复核的事实：

- crowd 的减量收益（+0.72）与 churn 最高（28.9%）**方向一致**——预测在这一端成立；
- mnobox 的减量伤害（−0.50）说明其 churn 的**性质**与 crowd 不同——同为 ~20-29% 周转，
  两序列死亡的基元构成不同。
- **候选解释（未验证，仅登记；G2-重大6 要求的语气限定）**：crowd 死的可能是
  「短暂可见性」基元（动态内容遮挡 ⇒ 减量无妨），mnobox 死的基元中可能至少
  一部分是跟踪所需的（移动盒子区域的重构依赖持续致密化 ⇒ 减量有害）。
  区分两种死法需要逐事件配对分析（E2 多阈值列的原始动机），本件不做，
  登记为开放问题。**单一 churn 标量不区分两种死法** ⇒ churn 不能作为
  剂量处方的诊断量。

### 2.2 H2 内部最优（ATE 轴上）= 标定故事的承重墙

pt 三测点 tau4x(−2.63) < 默认(0) < dose_zero(+3.62)：
- **零端点明确最差**（+3.62，且地图 0.15×、PSNR −6.5dB）⇒ 致密化不是负资产，
  「把致密化关掉」不成立（与旧栈 A6 方向一致：audit §2.1 表口径 +25.6%，
  55.80 vs 44.44；NOTES 均值口径 43.87 下 +27.2%——两口径并存声明）；
- **ATE 轴最小值在 ÷4**（三测点中）⇒ [0, 1×] 内部存在更优剂量 ⇒ 默认不在最优点；
- **限定**：÷4 点的改善带剂量混杂标记（归因未决）⇒ 「内部最优」是 **ATE 轴位置**
  的陈述，不是「÷4 配置全面更优」的陈述。

### 2.3 研究内容三的最终形态（数据说了算）

> **动态在线 SLAM 致密化的实证表征**：
> ① 选择轴（五类机制）无净收益——管线自调节承担了选择职能（五条链）；
> ② 剂量轴**存在且序列相关**——pt 内部最优（ATE 轴：全关 +3.62 / 默认 / 减量 −2.63
>    归因未决），crowd 过供给（+0.72 可回收），mnobox 欠供给（减量 −0.50）；
> ③ 地图规模收益普适（tau4x 全序列 **0.197–0.255×**）；
> ④ churn 不预测增益方向（可证伪假设，证伪）——单一周转标量不区分
>    「短暂可见性死」与「跟踪所需死」。

正面产物：剂量-响应前沿的测量与表征（4 序列 × 多臂）、内部最优的证明
（ATE 轴）、以及一个诚实的否证（churn 诊断）。**没有「按 churn 自动调剂量」的
处方**——这是本批最重要的负结果，防止后来者（包括我们自己）用周转率想当然调参。

## 三、本判决不主张什么

- 所有增益/伤害都是 n=2（每序列两 seed）——方向可判（同号），**不主张精确量值**，
  不主张第三 seed 后不变。
- 全部为仪器口径（单线程 + det-raster）；绝对值不与 async/文献比。
- balloon +0.24 低于 0.5cm 地板：只记方向，不算「改善」。
- 地图规模 0.2× 的效率收益在仪器口径下测得；async 部署下的对应收益**未测**。
- churn 假设的证伪限于「标量 churn 对 tau4x 增益」（4 序列样本）——不排除更细的
  逐事件/逐区域表征（但那属于新立项）。
- 评测协议不是贡献。

## 四、锚链与等价性（G2-重大2 处置）

H2 默认臂三 seed 的锚点（c2978f891 / c599d965a / 58164bb15）早于 A4 批
`250554d8e`。等价性论证（沿用已审查的结论链，此处显式写明）：

1. 三个旧锚点之间核心代码**逐字节相同**（`git diff c2978f891..c599d965a` 与
   `c599d965a..58164bb15` 对 `utils/ gaussian_splatting/ slam.py submodules/` 均空；
   submodule pin 同为 `b35ed864`）；
2. `c2978f891..HEAD` 的 +249 行全部落在 config-gated 分支内（E2/miss_streak/
   obs_gate），gate 键在两臂解析配置中不存在 ⇒ 分支不可达（可达性与 seed 无关）；
3. **端到端桥**：off s0 在 HEAD `250554d8e` 重跑与旧基线 `R1_bitwise_identical`
   （P3-D2-038 §2.2）；
4. **跨卡桥**：同 config 同 seed 两卡各 1 run `R1_bitwise_identical`
   （2026-11-06 探针）。

⇒ 默认臂三 seed 合法复用。

## 五、工件与审查

> **2026-11-08 A1 补批追注（P3-D2-042）**：本判决读数为 n=2 批次；第三 seed 补批已收口
> （`dose_oversupply_seed3_verdict_2026-11-08.md`）——出口不变（SEQUENCE_DEPENDENT），
> crowd 升至 +1.220（三 seed 同号）、mnobox −0.472（三 seed 同号）、**balloon 降级为
> UNJUDGED**（三 seed 异号，+0.24 亚地板方向读数不成立）。论文与大论文引用一律以
> n=3 读数为准，本件 n=2 读数保留作出口史。


- 判读 JSON：`dose_oversupply_judge_2026-11-08.json`（per_seed 含 run 锚）。
- 批日志：`dose_oversupply_batch_20261107.log`（15557 行，4 对 R-valid 比对段在列）。
- 原始 run：`results/paper3_bpw/instrument_dose_zero_person_tracking/`（4）+
  `instrument_dose_tau4x_{crowd,balloon,moving_nonobstructing_box}/`（各 3）+
  `instr_off_{balloon,moving_nonobstructing_box}/`（各 2）；crowd off 复用
  `instr_off_crowd/`（MaskStat L2 批）。
- 判读命令（留痕）：
  `judge_dose_oversupply.py --pair crowd:...:...:928 --pair mnobox:...:...:778 --pair balloon:...:...:439 --seeds 0 1 --zero-root ... --zero-default-root ... --zero-frames 580 --out paper3/results/evidence/dose_oversupply_judge_2026-11-08.json`（远端 3090）。
- **判读器两处修正**（判读中发现，先于判决提交 `cb1ecd21e`）：route_h1 接线 bug
  （读嵌套 payload vs main 摊平存储；单测构造嵌套形状没抓到 ⇒ 真实数据首跑
  KeyError；单测已改摊平口径作回归）+ 帧数期望修正（--pair 显式传 928/778/439/580）。
- **已知偏差登记（G2-次要③）**：判读器 PREDICTION_CONFIRMED 门比 prereg 严
  （脚本要求三序列全 >0.5，prereg 只要求 crowd >0.5）——本批未触发该出口
  （排序先错），不改代码（避免判读后改判据），未来批使用前须对齐。
- **机器门**：全量 pytest 597 passed；`prereg_criterion_keys.py` MISSING_TOTAL=0；
  `health_check.py` FAIL=0（收口 commit 附 rc）。
- slam-critic G2 = **Reject → 整改后定稿**（0 级别的两条致命为文本级：H2 形态
  错分 + tau4x 混杂未并陈；4+6 条重大/次要全处置，处置明细见各节内联标注；
  报告 `/tmp/slam_critic_g2_dose_oversupply_2026-11-08.md`）。
