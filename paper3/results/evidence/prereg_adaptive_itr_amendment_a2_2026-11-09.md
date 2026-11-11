# E 轴 L1 · Amendment A2（G3 审查整改：A/B 改新跑 + 判据链加固 + 派发前置）—— 2026-11-09

**状态**：判据锁定于**任何 L1 run 之前**（G3 审查（关卡③）在派发前执行，本件是其整改落纸）。
**母件**：`prereg_adaptive_itr_schedule_2026-11-08.md`；前一修正案 `prereg_adaptive_itr_amendment_a1_2026-11-09.md`。
**账本**：P3-D2-046（本件登记其附注）。
**G3 结论**：`Reject`（2 致命 / 11 重大 / 8 次要），报告 `/tmp/slam_critic_g3_adaptive_itr_2026-11-09.md`。

> **纪律声明**：critic 的结论只作线索。下面每一条都经**主 Agent 独立复核**（复核手段 = 本地实测 / 远程只读查询 / 算术重算），标注「**成立**」或「**不采纳**+理由」。

---

## §1 致命项处置

### 致命 A（派发链断裂）—— **成立，已修**

- 复核：`git ls-remote --heads origin feat/adaptive-itr` **空**（分支未 push，属实）；
  远程 `/data/monogs-ours` 与 `/data/conda_envs/monogs-ours/bin/python` **均不存在**（实测 `ls`），
  远程解释器 = `/home/jiangwenheng/anaconda3/envs/monogs-ours-3090/bin/python`，仓路径 = `/home/jiangwenheng/cron/monogs-ours`。
- **处置**：
  1. runner `run_adaptive_itr_l1.sh` 头注写死远程派发必须显式覆盖 `MONOGS_REPO`/`MONOGS_PY`；
  2. 新增**前置 fail-closed 三查**：路径/解释器存在、`utils/adaptive_itr.py` 与三臂 config 在位
     （后者正是「远程 HEAD 是旧代码 ⇒ 跑了只是 fixed-150」的防线）；
  3. 派发前必须先跑 `sync_to_remote.sh` 三方一致（本件不复制纪律条文，见 DISCIPLINE「本地→远程工作流」）。

### 致命 B（B 臂读数不可用）—— **成立，已修（改为新跑）**

- 复核（远程只读）：`itrsweep50_maskstat_off` s0 `2026-11-05-21-43-29` 的
  `efficiency_raw.csv` 中 `mapping_iterations = 'N/A'`、`mapping_calls = 'N/A'`（实测字符串）；
  `backend_timing.json` 有 6915/231；`console.log` 中 `MonoGS: Done.` **0 命中**（止于 offline eval
  中途，`per_frame_ape.csv` 581 行仅说明 tracking 段跑完）；无 `.done`。
- ⇒ A1 §4/§5 的「复用」判定**不成立**，且 A1 §5.1 的「读数有限」陈述不实。
- **处置（两件）**：
  1. **A/B 改为新跑**（四臂同 HEAD 同批）⇒ 复用→新跑后，跨批锚链、缺 `.done`、
     `efficiency_raw` 缺列三个缺口**同时消失**；总新 run 由 2 增至 **4**（仍在母件
     「≤3 run ≈2h GPU」的量级内，实际 ≈4×50min ≈3.3h；母件的时间盒性质按 §6 顺延说明）。
  2. **判读器迭代数来源改为「backend_timing 优先，efficiency 兜底」**：两处都在时必须一致
     （`iterations_consistent`），避免把 `N/A` 当读数解析。这同时修掉了同类复发面——
     历史批里 `efficiency_raw.csv` 的这两列可能缺失（该 run 早于 `_wait_for_backend_timing`）。

## §2 重大项处置（逐条）

| # | 问题 | 复核 | 处置 |
|---|---|---|---|
| 1 | M1 日志模式从未在真实 console 命中（全仓 `grep` = 0） | **成立**（旧前缀被 rich 吞） | 改前缀为无方括号 `adaptive_itr KF#`；**已在新冒烟实测命中**（§4）；单测守护稳定子串 |
| 2 | M1 第③④项可因缺键静默跳过（fail-open） | **成立** | 改为**缺键即失败**：C 臂必须带双计数且 `iterations_consistent is True`；A/B 必须带 0/0 |
| 3 | R-valid 可空转通过（空目录 / 同一 pin 传两次 / 缺件被当 N/A） | **成立**（实跑复现） | 三条硬门：pin 去重、两目录必须存在、可比对件数 ≥ `MIN_COMPARED_FILES=6` |
| 4 | A1 §2 算错（114/107/6865/6725；且误引 `(50−20)/50`） | **成立** | A1 §2 已按实测改正：115 次 per-KF 调用、B=6915、**C=6775**、节省 140 = **−2.02%**；母件字面 `(50−30)/50` 正确 |
| 5 | M3 门无判别力（M1 成立则必真） | **成立** | 不采纳「改门」建议（改门 = 改判据）；**如实登记**为「M3 是构造性门，`L1_PASS` 实质 = M1∧M2」，判决书须并陈 |
| 6 | M2 的 0.5cm 门 < itr=50 三 seed 极差 0.61cm | **成立（且是实质问题）** | **不采纳「改判据」**（判据先行不可回改）；在 §5 显式登记：M2 只答「同 seed 的调度 vs 固定点等价」，**不答** seed 抽样方差；L2 三 seed 时 `L1_PASS` 不得升格为「等价」主张 |
| 7 | 默认关逐位一致证据锚在旧 HEAD（`a959c14e3`），中间 `ce8c8405d` 改了 backend | **成立** | **已在派发 HEAD 复跑**：`2e7357f18` 的 A@40 与旧码 A@40 = **12 件 0 diff = R1**（§4） |
| 8 | A1 §91「`2df2b2d22..HEAD` 核心路径零改动」不实（实际 2 条） | **成立** | A1 §4 已加 ⛔ 更正注（引 A2 §3） |
| 9 | `INSTRUMENT_INVALID` 返回 rc=0，只有 MECH_INVALID 是 rc=2 | **成立** | 改：INSTRUMENT_INVALID 也 **rc=2**（与 `judge_dose_a4_instrument.py:289` 既有惯例一致） |
| 10 | M1 阈值读当前仓 config，不读被审 run 的 `config.yml` | **成立** | 改：新增 `run_params()` 从**run 内 config.yml** 读三参数（不可复算问题消除） |
| 11 | B 臂工件只在远程 ⇒ 本地跑判读必 INVALID | **成立** | A/B 改新跑后本批四臂同机产出；判读命令落纸时明确「在派发机（远程）执行」 |

## §3 次要项处置

- **reset() 不复位 early/late 计数** —— **成立**，已改为随 `reset()` 归零（防二次 init 假 MECH_INVALID）。
- **冒烟日志入库 301KB 非权威** —— **成立**，本批冒烟日志按 Git 跟踪政策属「判据工件」外的过程件；
  保留（它们是「机制真触发」的原始证据），但在 §4 明确标注非权威、不进判读。
- **smoke 行混入正式 tables** —— **成立**：冒烟 run 与正式 run 共用 arm 根 ⇒ `tables/*.csv` 追加了行。
  **处置**：不改文件（原始输出不可编辑）；在 §6 写明「`tables/` 是跨 run 追加聚合表，判读只用 run 内副本」，
  并要求正式批派发前先确认 `tables/` 末行对应的 run_id 是正式 run（判读器已按 run 目录读、不读 tables）。
- **判读命令留占位符** —— ⛔ 本条原表述不实（2026-11-10 更正，G2 重大-2）：当时 runner
  末尾打印的仍是字面占位符 `<A_RUN>` 等，并非「实测目录名」。已修：runner 批末按臂根
  自动取本批时间戳目录落纸（`pin()` 函数）。**同族第二次出现**（G3 轮次要 → 本轮重大），
  按类登记规则：再复发即致命。
- **STATUS/README/NOTES 无 E 轴登记** —— **成立**，本批收口时补 `NOTES.md` 实验清单行。
- **A1「不改路由」未点明 early 计数 8→7** —— 已并入 §1/§2 的措辞（C 臂 early 计数实为 **7**）。
- **本地/远程 tracked 脏文件** —— 本地 0；远程 24 件均为 `results/**/tables/*.csv` 历史追加（既有状态，不属本批引入）。

## §4 整改后的实证（派发前置，均在当前 HEAD `2e7357f18`）

| 项 | 证据 |
|---|---|
| 默认关逐位一致（**派发 HEAD**） | A@40（`2026-11-09-18-29-17`）vs 旧码 A@40（`2026-11-09-13-27-08`）= **12 件 0 diff，R1_bitwise_identical** |
| M1 日志真实形状 | C@40（`2026-11-09-18-19-07`）：`adaptive_itr KF#2 (frame 5) itr=30` … 共 7 行（40 帧 run 的 7 次 per-KF 调用全部 early） |
| C@60 早↔晚切换 | `KF#8 (frame 35) itr=30` → `KF#9 (frame 40) itr=50`（阈值处精确切换） |
| 迭代数对账 | `mapping_iterations = 1471 = 1050 + 7×30 + 4×50 + 11×1`（60 帧 run 实测） |

（两次冒烟均为**本地 2060**、非权威，按 DISCIPLINE「算力归属」不进任何判读计数。）

## §5 判据能力边界（不改判据，但必须与读数并陈）

1. **M3 是构造性门**：调度若真生效（M1 成立），节省必然为正，故 `L1_PASS` 的独立信息量
   实际来自 M1∧M2。判决书须写成「M1∧M2 通过且算力按预期下降」，不得表述为「三个独立门全过」。
2. **M2 的 0.5cm 只覆盖同 seed 等价**：母件是 n=1 方向级设计。`itr=50` 的三 seed
   ATE 极差实测 **0.61cm**（10.658 / 10.895 / 11.266，`itr_low_sweep` 批）> 0.5cm 门
   ⇒ **seed 抽样方差本身已超门带宽**。故 `L1_PASS` 只能读作「本 seed 上与固定点等价」，
   **不得**升级为「调度与 fixed-50 等价」的一般主张；L2 三 seed 若再现方向不一致，
   按 UNCERTAINTY 处置，不判机制失败。
   > ⛔ **2026-11-10 更正（L2 判决登记；判据字面未动）**：本项括号内三值是**批 mean 误标**。
   > 正确三 seed **10.658 / 10.760 / 11.266**（median 10.760、mean 10.895、极差 0.61cm），
   > 出处 = `night_sweep_matrix_2026-11-06.md:19`（P3-D2-032 夜间扫描矩阵），**不是**
   > `itr_low_sweep` 批（该判决是 itr=30 单 seed）。0.61cm 极差与「seed 方差 > 门带宽」
   > 的限制结论**不变且被 L2 强化**（L2 B 三 seed 极差 1.78cm）；见 `P3-D2-048`。

## §6 时间盒与派发

- 硬顶不变：**2026-11-10 20:00**。本批 4 run ≈ 3.3h（单卡串行，含 A/B/C 全部新跑）。
  若到点未跑完 ⇒ 按母件止损条款处理，不追加 run。
- **`tables/` 说明**：各臂根下 `tables/*.csv` 是**跨 run 追加**的聚合表（冒烟 run 也在内）。
  判读器只读 run 目录内副本（`tracking_raw.csv` / `efficiency_raw.csv` / `backend_timing.json`），
  不读 `tables/`。正式判决引用读数时必须给 run 目录路径。
- 派发前置：`sync_to_remote.sh` 三方一致 + `nvidia-smi` 实时占用 + runner 的 fail-closed 三查。

## §7 本件不主张什么

- 不改母件与 A1 的任何**出口路由**；§1 的「A/B 新跑」是**设计变更**（复用→新跑），
  它只影响 run 数与成本，不改变 M1/M2/M3 的字面。
- §4 的两次冒烟是本地 2060、短帧，**不构成任何 ATE/算力结论**。
- §5 的边界声明不撤销 M2 门本身，只限定其可主张范围。
