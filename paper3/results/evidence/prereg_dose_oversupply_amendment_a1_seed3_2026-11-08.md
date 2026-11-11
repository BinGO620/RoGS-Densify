# 剂量过供给验证批 · Amendment A1（第三 seed 补批）—— 2026-11-08

**状态**：判据锁定于本批任何 run 之前（本件随 runner 同 commit 入库，先于派发）。
**母件**：`prereg_dose_oversupply_2026-11-07.md`（判据、出口、单变量约定全部沿用，唯一变化 = seed 集 0/1 → 0/1/2）。
**账本**：P3-D2-042。
**触发**：用户 2026-11-08 拍板「冲投稿：现在立项 GPU 增量」；DISCIPLINE「Seed 两级纪律」：
**晋级确认与论文数字必须 3 seeds** —— 过供给批判决（`dose_oversupply_verdict_2026-11-08.md`）
的论文数字现为 n=2（判决 §三 自我限定「不主张第三 seed 后不变」），投稿前补齐第三 seed。

---

## §1 范围（6 臂 × seed 2 = 7 run，仪器口径不变）

| 序列 | off 臂（新跑） | tau4x 臂（新跑） | 帧数期望 |
|---|---|---|---|
| crowd | `instr_off_crowd` s2 ×1 | `instrument_dose_tau4x_crowd` s2 ×**2**（**R-valid 锚对**） | 928 |
| balloon | `instr_off_balloon` s2 ×1 | `instrument_dose_tau4x_balloon` s2 ×1 | 439 |
| moving_nonobstructing_box | `instr_off_moving_nonobstructing_box` s2 ×1 | `instrument_dose_tau4x_moving_nonobstructing_box` s2 ×1 | 778 |

- pt 侧（dose_zero / off / tau4x）已各 3 seed（母件 §3.1/既有基线），**不在本批**。
- balloon 不补 tau4x R-valid 锚（锚对本批只留 crowd 一处，见 §3）。
- 全长（`max_frames=0`）、仪器口径三开关 + 三环境锁不变（runner = `run_instrument.sh` 原件）。

## §2 判据继承与唯一变化

- 母件 §4 全部沿用：gain(seq) = −median{Δ(tau4x − off) per seed}；0.5cm 地板；
  四条 H1 出口 + INSTRUMENT_INVALID fail-closed。
- **n=3 语义显式化**（母件写的是两 seed 语境）：
  - 「异号 ⇒ 未判（UNJUDGED，不取中位假装有值）」在 n=3 下 = **任两 seed 异号即未判**
    （判读器 `signs` 集合基数 >1 ⇒ 未判，代码语义不变，无需改码）；
  - 中位数 = 3 样本中位。
- **判读命令钉死（G3-C5 整改，2026-11-08 落纸；roots 为实测目录）**：
  `judge_dose_oversupply.py --seeds 0 1 2`（判读器已参数化）+
  `--zero-root results/paper3_bpw/instrument_dose_zero_person_tracking/datasets_bonn/instrument_dose_zero_person_tracking`
  `--zero-default-root results/paper3_bpw/instrument_maskstat_off/datasets_bonn/instrument_maskstat_off`
  `--zero-frames 580`。三对 roots 字面量 = `instr_off_<seq>`/`instrument_dose_tau4x_<seq>`
  的 `datasets_bonn/<同名>` 子目录（完整命令见判读器 docstring usage）。
  **H2 措辞更正**：母件 H2 本就按 s0/s1/s2 三 seed 出中位（verdict §1.2 表），
  本批只是 seed 集不变地沿用；"自动升为 n=3"系表述失准，更正于此。
  判读器 h2 同步加 fail-closed（三 seed 任一缺失 ⇒ 不出中位，不再静默降级）。

## §3 R-valid 锚对与消费规则（预声明，防事后挑 run）

- 锚对 = `instrument_dose_tau4x_crowd` seed 2 ×2 run（`run_instrument.sh <arm> 2 0 2`，
  内置 `compare_three_way.py` 逐位比对）。**R2 ⇒ 整批作废不报数**（仪器失效，
  查三项开关/环境是否真生效）。
- **锚对本批只留一处（crowd tau4x s2）的理由**：锚对的职责 = 验证**本批派发时刻的
  仪器状态**（同一装置、同一时钟窗、同一 HEAD），一处即覆盖；六臂各自的
  s0/s1 已在母件批各有 R-valid 锚（4 对），同臂 s2 与 s0/s1 同 config 仅差 seed，
  仪器状态不随 seed 变。balloon/mnobox tau4x s2 不另设锚。
- 锚对两 run 都留盘；判读消费规则 = `collect()` 既有规则（同 seed 多 run 时取
  排序后最后一个 rc0 全长 run，即时间戳较大者）——**预声明于派发前**，非事后选择。
- crowd off s2 单 run；crowd off 的 s0/s1 复用 MaskStat L2 批（母件 §3.4 已核等价）。

## §4 硬门（沿母件，逐序列参数化）

- 帧数 = 各序列全长（crowd 928 / balloon 439 / mnobox 778 = rgb.txt 行数 − 2，
  PITFALLS #1197 口径；`--pair` 显式传参）；
- `.done` 锚 `finished_rc0=yes`（缺即拒，rc 闸）；
- 新批锚对 R1（§3）。

## §5 布局与时间盒

**派发机器落纸（G3 次要整改，2026-11-08）**：远程 3090（`jiangwenheng@172.16.227.24`，
双卡），仓路径 `/home/jiangwenheng/cron/monogs-ours`，Python
`/home/jiangwenheng/anaconda3/envs/monogs-ours-3090/bin/python`；派发前先
`sync_to_remote.sh` 三方一致 + nvidia-smi 实时占用检查。runner 以
`MONOGS_REPO=/home/jiangwenheng/cron/monogs-ours
MONOGS_PY=/home/jiangwenheng/anaconda3/envs/monogs-ours-3090/bin/python` 覆盖默认值。

两卡链（`scripts/paper3_bpw/run_dose_seed3_batch.sh`，同臂禁并发）：

- GPU0：crowd tau4x s2 ×2（R-valid）→ balloon tau4x s2 → balloon off s2
  （≈222min——按 crowd off s1 实测 75min/run 修正，原 188min 估计偏乐观）
- GPU1：crowd off s2 → mnobox tau4x s2 → mnobox off s2（≈172min）

**硬顶 2026-11-09 08:00**。单 run rc≠0 补跑最多一次；二次失败止损该臂
（该臂缺失 ⇒ 判读 INSTRUMENT_INVALID，按 fail-closed 报，不缺臂硬判）。
runner 派发前预检六个臂的 `seed_2` 目录不存在既有 run（防判读 collect() 被旧 run
顶替，与 G3-C1 同源防线）。

## §6 n=3 读数与 n=2 判决的关系（诚实条款）

- 本批产出 = **论文数字用读数**（3 seeds）；母件判决（n=2）不撤销，两者并存登记。
- 若 n=3 出口与 n=2 出口不同（如某序列翻号变 UNJUDGED），**如实登记并回溯标注**
  （`dose_oversupply_verdict` 加带日期追注），不得只报好读数、不得静默替换。
- 论文（第五章与投稿件）引用 n=3 读数 + 母件 n=2 判决的出口史（口径见各判决文档）。

## §7 等价性

- 本批新增仅本文档 + `run_dose_seed3_batch.sh`（scripts 层，非核心代码）；
  核心路径（`utils/ gaussian_splatting/ slam.py submodules/`）自 A4 批
  `250554d8e` 以来零改动的结论沿母件 §3.4，派发前以
  `git diff 250554d8e..HEAD --stat -- utils/ gaussian_splatting/ slam.py submodules/` 复核为空。
- off 臂 s0/s1 复用合法性沿母件 §3.4（等价门 + crowd 复用 MaskStat L2 批）。

## §8 本件不主张什么

- 不改判据/口径/机制/percent_dense（纯 seed 扩展）；
- 不主张 n=3 中位数的精确量值可比性跨口径（仪器口径内部可比，与 async/文献永不混引）；
- 评测协议不是贡献。
