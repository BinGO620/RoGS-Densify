# E 轴 · Amendment A3（L2 三 seed 确认批：判据 + 派发记录）—— 2026-11-10

**状态**：判据锁定于**本批任何 run 之前**（本件随判读器/runner 同 commit 入库，先于派发）。
**母件**：`prereg_adaptive_itr_schedule_2026-11-08.md`；A1（精度化）/ A2（G3 整改）沿用。
**账本**：P3-D2-047（L1 判决 `L1_ATE_GAIN`，n=1 方向级）⇒ 本件是其 §六 L2 提名的执行落纸（用户 2026-11-10 拍板「可以」）。

---

## §1 设计（n=3 确认批：4 新 run）

| 臂 | 配置 | 已有 | 本批新跑 |
|---|---|---|---|
| C（调度 30→50） | `adaptive_itr_person_tracking` | s0 ×2（R-valid 锚对，ATE 9.8258） | **s1、s2 各 1 run** |
| B（fixed-50，对照臂） | `itrsweep50_maskstat_off` | s0 ×1（ATE 10.6579） | **s1、s2 各 1 run** |
| A（默认 150，参照） | `instrument_maskstat_off`（与 A 臂配置解析后只差 save_dir） | s0/s1/s2 三 seed 全长 rc0 | 不跑（复用） |

- 全部全长 580 帧、仪器口径三开关 + 三环境锁、seed ∈ {1,2} 新跑；**单卡串行**
  （仪器口径惯例；本批无逐位比对对，但保持同批同卡消除并发变量）。
- **总新 run = 4 ≈ 2.0h GPU**（C ≈29min/run、B ≈30min/run，实测自 L1 批）。
- runner = `scripts/paper3_bpw/run_adaptive_itr_l2.sh`（同款 fail-closed 前置 + 实测 pins 落纸）。

## §2 判据（机械出口，判读器 `judge_adaptive_itr_l2.py` fail-closed）

对每个 seed ∈ {0,1,2}：取该臂合格 run（`.done` rc0 + 帧数 580 + 读数有限；
**三臂同规**，A2 后无豁免），算 **Δ_s = ATE_C(s) − ATE_B(s)**。

前置门（任一不过 ⇒ `L2_INSTRUMENT_INVALID`，rc=2）：3 seed × 2 臂全齐、rc0、帧数、
读数有限（NaN/Inf = 读数不存在，不得判）。

四条互斥出口（按序机械路由）：

1. **`L2_SIGN_UNSTABLE`**：Δ_s 的符号集合基数 > 1（任两 seed 异号；Δ=0 记非负）
   —— **止损**：未判出稳定增益，E 轴机制身份不成立，降级为配置结论
   （调度代码默认关保留；fixed-50 优于默认 ~3cm 进讨论节）。不追加 run、不换判据。
2. **`L2_CONFIRMED_TRADEOFF`**：三 seed 全 Δ<0 ∧ median Δ ≤ −0.5cm
   ∧（渲染代价闸触发：median static PSNR(C) < median(B) − 0.5dB
   **或** median depth L1(C) > median(B) + 1.0cm）
   —— 精度主张成立**但必须并陈渲染代价**，不得主张「无代价」。
3. **`L2_CONFIRMED`**：三 seed 全 Δ<0 ∧ median Δ ≤ −0.5cm ∧ 渲染代价闸未触发
   —— **精度主张成立（n=3）**：E 轴获机制贡献候选身份（对象/信号/终点/场景
   四维差异化见母件 §0）。
4. **`L2_DIRECTION_ONLY`**：三 seed 全 Δ<0 ∧ median |Δ| < 0.5cm
   —— 方向稳定但量级未过判读地板：只记方向级结论，不构成主张，不进贡献栏。

**报告项**（不参与路由）：每 seed 的 `mapping_iterations(C/B)` 与节省（M3 为构造性，
只验机制覆盖）、每 seed static PSNR/depth L1、A 臂三 seed 参照读数
（`instrument_maskstat_off`，报告 C/B 相对默认的量级）。

**n=3 语义**：中位 = 3 样本中位；符号判定逐 seed 独立（无 UNJUDGED 单 seed 概念——
前置门已保证三 seed 全有效，符号不稳定直接走出口 1）。

## §3 与 L1 判决的关系

- L1（`L1_ATE_GAIN`，s0：Δ=−0.8321）**不撤销**；本批是 its L2 确认。
- s0 的 Δ 进入 L2 的三 seed 集合（C s0 = 19-17-31 那次读数；B s0 = 21-03-01）。
- 若出口为 `L2_SIGN_UNSTABLE`：L1 的方向级读数**保留为历史事实**（不追溯改写），
  但 E 轴最终身份 = 配置结论（两代读数并存，论文引用 n=3 结果——沿 A1 seed3 批
  的诚实条款同款）。

## §4 派发记录

- 派发机：远程 3090（`jiangwenheng@172.16.227.24`），仓 `/home/jiangwenheng/cron/monogs-ours`，
  Python `anaconda3/envs/monogs-ours-3090/bin/python`；派发前 `sync_to_remote` 三方一致 +
  nvidia-smi 实时占用（机器主人优先，单卡串行）。
- 判读命令（判据先行落纸；pins 由 runner 实测打印）：
  `judge_adaptive_itr_l2.py --b-root <B臂root> --c-root <C臂root> --seeds 0 1 2
  [--b-pin 0=2026-11-09-21-03-01] [--c-pin 0=2026-11-09-19-17-31]
  --out paper3/results/evidence/adaptive_itr_l2_judge_2026-11-10.json`

  > ⛔ **2026-11-10 更正（判据中性；§2 判据字面未动）**：本行旧版写作
  > `--b-pin-0/--c-pin-0`，该形式**不可执行**——解析器只接受 `--b-pin SEED=RUNDIR`
  > （`judge_adaptive_itr_l2.py:100-114`）。实际执行形式以 runner
  > `run_adaptive_itr_l2.sh:70-71` 与批日志末尾落纸为准（本批已按可执行形式跑完，读数不受影响）。
  > 同族第二次出现（「判读命令占位符」类，A2 §3 已升级警告）；再复发即致命。

## §5 时间盒与止损

- 硬顶 **2026-11-11 12:00**（4 run ≈2h + 判读/判决 ≈1h，余量充足）。
- `L2_SIGN_UNSTABLE` 即终态（同母件止损条款：不追加 run、不换信号）。
- 本件不主张：L2 出口不分 Voraussage——一切以判读器机械路由为准。

## §6 本件不主张什么

- 不预设 L2 结果；`L2_CONFIRMED` 只是**候选身份**，进贡献栏仍须通过论文叙事纪律
  （组件准入 = 叙事服务）与用户拍板。
- A 臂参照读数来自 `instrument_maskstat_off`（与 A 臂解析后配置只差 save_dir），
  引用时注明该等价性（G2 已核）。
