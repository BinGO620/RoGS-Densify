# results/paper3_bpw — 论文 3 致密化实验的原始输出

> **判据/结论不在这里**：判决书与预注册在 `paper3/results/evidence/`，
> 状态在 `paper3/STATUS.md`，账本在 `paper3/DECISIONS.md`。
> 本文件只做**目录导航 + 每批的口径备注**（防跨批混引）。

## 臂命名

| 前缀 | 含义 |
|---|---|
| `bpw_off_*` | Phase 0 基线（`SelectiveDensification.enabled: false`，与主线逐位一致） |
| `bpw_on_*` | Phase 0 机制臂（BPW：固定源点预算内按 `accum/(denom+p0)` 重排） |
| `bpw_negctl_*` | Phase 0 负对照（BPW 的确定性置换 placebo） |
| `sweep_p0_*` | BPW 的 p0 敏感性扫描（4 个 p0 值 × person_tracking） |
| `cgb_g0_*` / `cgb_g1_*` | CGB 两臂：`γ=0` 控位对照（设计意图是等剂量，**L1 实测只在事件 1 成立**）/ `γ=1` 稀疏加权机制 |
| `fdose_k0_*` | FDose 参考剂量臂（自计划，`K_i` = 本事件 `\|ref_sel\|`）：**计划源**，也是剂量参考 |
| `fdose_G_*` / `fdose_S_*` | FDose 两臂：`γ=0`（按计划取 K_i 个最高梯度点）/ `γ=1`（同样 K_i，`g·s` 稀疏加权） |
| `fdose_{G,S}_smoke40` | 40 帧冒烟（`debug_*` config + 截断计划），**只验装置门，不供判读** |

## 目录布局

MonoGS 原生层级，**中间有 `datasets_bonn/`**：

```
results/paper3_bpw/<arm>_<seq>/datasets_bonn/<run_name>/seed_<n>/<YYYY-MM-DD-HH-MM-SS>/
```

判读一律用**显式 run 路径**（`.../seed_0/<timestamp>/`）——
`judge_p0a.py` 的 `latest_run()` 硬编码 `*_balloon`，多序列会静默取错臂。

## 每批口径备注

### Phase 0（BPW，2026-10-27 ~ 10-30）

- `bpw_{off,on,negctl}_{balloon,person_tracking}`，seed 0/1/2。
- **`*_person_tracking_trace` / `*_balloon` 的 `_trace` 变体**：与对应正式臂**逐位相同**的
  config，只多 `trace_selection: true`（默认关的诊断日志）。其 ATE **不供判读**
  （同 seed 重跑散布已知，出现过 −26.78% 的先例）；trace 只供机制诊断。
- 渲染：`mapping_raw.csv` 的 `mask_type=full` 行在 Bonn 上**恒 NaN**
  （run 内 eval 采样网格与 KF 网格重合）。**判读只用 `mask_type=static`（P-A 静态背景）行。**

### CGB（2026-10-30 ~ ）

- `cgb_{g0,g1}_person_tracking`，seed 0。两臂只差 `gamma`。
  ⚠ **源点数只在事件 1 相等**（2638/2638）；从事件 2 起两臂地图分叉、`ref_sel` 分叉，
  共同事件中 Σ 差 +7.79%。"逐事件等剂量"这个说法**已被 L1 实测证否**，
  见 `paper3/results/evidence/verdict_cgb_l1_2026-10-30.md` §4.2。读这批数据时
  **不得**把它当成等剂量对照。
- `cgb_selection_trace.csv` 的列集在 2026-10-30 18:21 之后多了 `max_scale`
  （Amendment A1 §3b）；**跨提交的两臂 trace 表头可能不一致**，分析该列前先核表头。
  冒烟批（`*_2026-10-30-18-14-41`）就是这种不一致状态，只作装置验证。
- 冒烟批带 `--max-frames 40`，帧数与全长不同 ⇒ **不得与全长 run 混比**
  （`judge_cgb_l1.py` 有帧数一致性闸）。

### FDose（2026-10-31 ~ ）

- 三臂只差两处：`gamma` 与 `dose_plan_path`。k0 自计划（`dose_plan_path: null`），
  G/S 消费**同一份冻结计划**；计划由 `scripts/paper3_bpw/make_dose_plan.py` 从 k0 的
  trace 生成，落在 `results/paper3_bpw/dose_plan/<seq>_seed<n>.json`（含 sha256 与 `n_plan`）。
- **剂量由计划外生**：两臂逐事件取恰好 K_i 个点，`K_i` 可能小于本臂自己的 `|ref_sel|`
  （即修剪，`trim` 为负）—— 这是设计的一部分，不是 bug。
- **事件序号 ≥ `n_plan` 之后注入 0**（`plan_overflow=1`）。两臂的 densify 事件数本来就不同
  （实测 61/63/64），沿用末位剂量会让总剂量随事件数分叉。
- `fdose_selection_trace.csv` 默认**只写 `sel` 行**（未选中的池点不写）：
  池是选中集的 3–5 倍，全量 dump 会把单臂推到 50 MB 量级。需要离线诊断时在 config 里
  设 `trace_pool: true`。

## 选点 trace 的体积（2026-10-30 实测）

`*_selection_trace.csv` 按「判据工件」入库（与 `bpw_selection_trace.csv` 同一先例），
但**单文件会到 50 MB 量级**：CGB L1 的 `cgb_selection_trace.csv` 分别为
53.2 MB（g1）/ 49.5 MB（g0），gzip 后可压到 19.1 / 17.3 MB（≈2.8×）。

- 本次 push 收到 GitHub 的 **50 MB 推荐上限警告**（未拒收，remote HEAD 已对齐）。
- **后续建议**：跑前把 `trace_selection` 关掉，改用 `--trace-every N`（当前未实现）
  或只对**单个序列的单臂**开 trace；若必须全开，先 `gzip` 再入库并同步改判据机的读入。
- **不要**为了压体积去删已有 trace —— 按 `DISCIPLINE.md` 禁止事项 H1，删前必须核
  `git ls-files` 与再生成本（重跑一臂 ≈45 min 在线 + 45 min refinement）。

## 重数据与解跟踪

`.ply`、`render_*` 图、`plot/trj_N.json`、`plot/stats_N.json` 按 Git 跟踪政策**不入库**
（见 `DISCIPLINE.md`「Git 跟踪政策」）。判据工件（`tracking_raw.csv` / `efficiency_raw.csv` /
`mapping_raw.csv` / `console.log` / `config.yml` / `plot/trj_final.json` 等）入库。

⚠ **删任何 run 目录前必须核 `git ls-files`**（`DISCIPLINE.md` 禁止事项 H1；
2026-09-30 曾因此永久丢失 7 个 run 的原始产物）。
