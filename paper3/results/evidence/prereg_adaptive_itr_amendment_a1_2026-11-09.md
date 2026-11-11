# E 轴 L1 · Amendment A1（判据精度化 + 装置门核算 + 派发记录）—— 2026-11-09

**状态**：判据锁定于**任何 L1 run 之前**（本件随判读器/runner 同 commit 入库，先于派发）。
**母件**：`prereg_adaptive_itr_schedule_2026-11-08.md`（机制、臂设计、四条出口、止损条款全部沿用）。
**账本**：P3-D2-045（母件立项）+ 本件登记的 P3-D2-045 附注。
**触发**：实现完成后的机械对账——母件 §3 的两处措辞在实测口径下需要精度化，
以及「测量口径」#6 要求的装置自差准入核算必须留纸。

> **本件不改任何出口的机械路由**。它只做三件事：① 把 M1 的日志口径写成可执行字面；
> ② 把 M3 的预注册预期值按本仓实测 KF 密度重算并并列登记；③ 补装置门核算。

---

## §1 M1 机制门的可执行字面（母件 §3 M1 的精度化）

母件：「per-call itr 日志 = 前 8 KF 全 30、其后全 50（日志证据落盘；任何一步不符 ⇒
`MECH_INVALID`，rc=2）」。

**可执行字面（判读器 `judge_adaptive_itr_l1.py::check_m1` 实现）**：

1. console.log 中匹配 `adaptive_itr KF#<ord> (frame <f>) itr=<i>` 的全部行（**稳定子串，
   不带方括号**——rich 会把 `[...]` 当 markup 静默吞掉，本仓已有同类踩坑）；
2. 序数必须自 **2** 起连续递增（序数 1 = 初始化关键帧，走 `init_itr_num`=1050，
   **不在调度内、也不产生调度行**——见 `impl_adaptive_itr_2026-11-09.md` §2.1）；
3. 每行 itr 必须等于两段式预测值（序数 ≤ 8 ⇒ 30；≥ 9 ⇒ 50）；
4. `backend_timing.json` 的 `adaptive_itr_early_calls`/`adaptive_itr_late_calls`
   必须与日志计数一致（两处互相印证）；
5. `efficiency_raw.csv` 与 `backend_timing.json` 的 `mapping_iterations` 必须一致；
6. **A/B 两臂必须零调度行、且 backend 计数为 0**（单变量：机制只在 C 臂）。

任一不符 ⇒ `MECH_INVALID`（rc=2，fail-closed，不落进任何 PASS/NO_VALUE 出口）。

**为什么序数从 2 起**：母件 §1 的校准句把 40 帧的 8 个关键帧（KF 0/5/…/35）当作
「前 8 个」。实现把初始化关键帧计入序数（#1）但不调度它（其预算硬编码、B 臂同值），
故首个**被调度**的调用是 #2（KF5），early 覆盖 #2–#8 = frame 5–35，KF40（#9）起
走 late。这与校准窗口（≤40 帧全 early）严格一致。

## §2 M3 预注册预期值的两套口径并列（**不替换母件字面**）

母件 §3 M3 括注：「预期 ≈ −5%（8/58 KF 早期 × (50−30)/50）」，按「58 KF」推算。

**实测 KF 密度 = 115 个 keyframe 建图调用 / 580 帧**（console `Candidate insert KF 5…575`，
间隔 5 帧，共 115 枚；`mapping_calls=231 = 1 init + 115 per-KF + 115 prune`）。
按实测密度重算（B 臂 6915 与 `itr_full_580_verdict` 的 itr=50 全长实测值逐数相符）：

| 项 | B（fixed-50） | C（调度） |
|---|---|---|
| per-KF 建图迭代（115 次调用） | 115 × 50 = 5750 | 7 × 30 + 108 × 50 = 5610 |
| 初始化 BA（`init_itr_num`） | 1050 | 1050 |
| prune 调用（iters=1，115 次） | 115 | 115 |
| **`mapping_iterations`** | **6915** | **6775** |
| 预期节省 | — | **−140 迭代 = −2.02%** |

- **B 臂 6915 是实测值**（`backend_timing.json`，与 `itr_full_580_verdict` 的 itr=50 全长
  读数一致；A 臂 18415 = 1050 + 115×150 + 115 亦实测相符）。
- **C 臂 6775 = 1050 + 7×30 + 108×50 + 115**：7 次 early（序数 2–8）+ 108 次 late
  （序数 9–116 中的 108 次）+ 115 次 prune。注意序数上限是 **116**（init 计为 #1，
  115 次 keyframe 调用 ⇒ #2..#116），故 late = 116 − 8 = 108。
- 母件 `(50−30)/50` 是正确字面（本件先前误引为 `(50−20)/50`，已更正）。

**判读器处置**：M3 的**门**只设方向（`iterations(C) < iterations(B)`），两套预期值
（−5% / −2.02%）作为**报告项**并列写进 JSON（`expected_pct_prereg` /
`expected_pct_measured_density`），不参与路由。若实测节省显著偏离 −2.02%
（例如 > 2 倍），判读器不自动失败，但判决书必须解释（可能指向隐藏消费点或调度未全覆盖）。

## §3 装置门核算（DISCIPLINE「测量口径」#6 准入）

**判据性质**：M2（|ATE_C − ATE_B| ≤ 0.5cm）是**臂级终态比较判据** ⇒ 须先过装置自差核算。

**该装置的自差在仪器口径下 = 0.0cm（构造性）**：

| 证据 | 读数 |
|---|---|
| `device_floor_crowd_mnobox_verdict_2026-11-09.md`（仪器口径，crowd 928f / mnobox 778f） | 两序列各 2 run **R1_bitwise_identical**（same=12 diff=0）⇒ ATE 自差 **0.0cm** |
| `dose_a4_instrument_verdict_2026-11-06.md` / `dose_scan_verdict_2026-11-07.md` / `dose_oversupply_verdict_2026-11-08.md` | 仪器口径各批 R-valid 锚对全 `R1_bitwise_identical` |
| `detraster_L2_2x2_2026-11-05.md` | 单线程 × det-ON 格达成 40 帧 ×2 逐位一致 |
| 本次实现验证（`smoke_adaptive_itr_2026-11-09.md`） | 本地 2060 改动前后同为 12 件 md5 全同 |

**结论**：仪器口径下同 config 同 seed 重跑逐位一致 ⇒ **自差 = 0，0.5cm 门带宽 > 自差**，
M2 在该装置上**可执行**（不是「自差内不可判」）。

**限定（必须与读数并陈）**：① 该 0.0 是**逐位一致的构造性结果**，不是独立噪声测量
（同 `device_floor_crowd_mnobox_verdict` §二.2 的措辞）；② 它只对**仪器口径**成立；
async 部署口径的自差见 `device_floor_async_cm_verdict_2026-11-09.md`（实测 0.338/0.389cm），
本批不在 async 口径跑（`Mapping.adaptive_itr` 在 async 下 fail-closed）。
③ 若 C 臂 R-valid 锚对**失败**（两 run 分叉），判读器直接判 `INSTRUMENT_INVALID`——
这同时是「该装置自差不为 0」的实测证据，此时 M2 不得使用。

**n=1 方向级（母件 §3 末条不变）**：本批 single seed，出口是**方向级提名**，
不是 3-seed 确认；`L1_PASS`/`L1_ATE_GAIN` 只提名 L2，不构成论文数字。

## §4 臂与派发记录（母件 §2 的执行落纸）

> **⚠ 本节被 Amendment A2（2026-11-09）实质取代**：G3 审查（`/tmp/slam_critic_g3_adaptive_itr
> _2026-11-09.md`）实测证明 B 臂 `efficiency_raw.csv` 的 `mapping_iterations` 为字面
> `N/A`、无 `.done`、console 无 `MonoGS: Done.`，复用臂 provenance 站不住 ⇒ **A/B 改为
> 新跑**（四臂同 HEAD 同批）。原文保留作痕迹，现行方案见 A2 §1。另：本节原写
> 「`2df2b2d22..HEAD` 核心路径零改动」**不成立**（该区间含 `a959c14e3`/`ce8c8405d`
> 两次 `utils/slam_backend.py` 改动）——已由 A2 §3 更正。

| 臂 | 配置 | run 来源（⛔ 被 A2 §1 取代） |
|---|---|---|
| A | `instrument_person_tracking`（fixed itr=150） | ~~**复用**：`instrument_maskstat_off` s0 `2026-11-06-21-00-53`~~ |
| B | `itrsweep50_maskstat_off`（fixed itr=50） | ~~**复用**：s0 `2026-11-05-21-43-29`~~ |
| C | `adaptive_itr_person_tracking`（调度 30→50） | **新跑 2 run**（同 seed 全长；第 2 个作 R-valid 锚对） |

- 全部 seed 0、580 帧、仪器口径（三开关 + `PYTHONHASHSEED`/`CUBLAS_WORKSPACE_CONFIG`/
  `PYTHONPATH` 三环境锁），runner = `scripts/paper3_bpw/run_instrument.sh` 原件。
- ~~**总新 run = 2**~~ ⇒ **A2 §1 改为总新 run = 4**。远程 3090 双卡：四 run 全排一张卡
  **串行**（R-valid 逐位比对纪律：禁并发）。

## §5 前置门与已知工件缺口（fail-closed 处置）

> **⚠ 本节 1/2 被 Amendment A2 §1/§2 取代**（B 臂不再复用，其 `.done`/锚链问题随之消失）。
> 保留原文作审查痕迹。

1. ~~**B 臂缺 `.done` 锚点**~~ ⇒ **A2：B 臂新跑，`.done` 由 runner 正常产出，必检**。
2. ~~**桥接 run（anchor-chain gap）**~~ ⇒ **A2：四臂同 HEAD 同批，无跨批锚链问题**。
   `L1_PASS`/`L1_ATE_GAIN`（即要提名 L2），则在 L2 派发前补跑 B 臂桥接 1 run 并做
   R-valid 比对**——此条件写在出口侧，不在本批。
3. ~~**A 臂复用而非新跑**~~ ⇒ **A2：A 臂新跑（同批同 HEAD）**。

## §6 时间盒与止损（母件 §4 不变，仅补当前状态）

硬顶 **2026-11-10 20:00**。当前：实现 + 单测 + 冒烟已完成（2026-11-09），
L1 派发待远程 3090 空闲窗口（本会话查得双卡均被机器主人占用 ~92–94% 利用率）。
`L1_NO_VALUE` 即终态（不追加 run、不换信号重试）。

## §7 本件不主张什么

- 不改母件任何出口的机械路由；§2 的两套预期值只作报告项。
- §3 的「自差 0.0」不主张为「该装置零噪声」——它是逐位一致的构造性结果。
- ~~不主张 B 臂读数在无 `.done` 的情况下…~~ ⇒ A2：B 臂新跑，该限定不再适用。
