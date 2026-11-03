# FDose 机制门 F1–F5（prereg `prereg_fdose_2026-10-31.md` §4.1）

**输入**：
- `plan`: `results/paper3_bpw/dose_plan/person_tracking_seed0.json`
- `g`: `results/paper3_bpw/fdose_G_person_tracking/datasets_bonn/fdose_G_person_tracking/seed_0/2026-11-01-17-56-10/fdose_selection_trace.csv`
- `s`: `results/paper3_bpw/fdose_S_person_tracking/datasets_bonn/fdose_S_person_tracking/seed_0/2026-11-01-18-40-48/fdose_selection_trace.csv`
- `k0`: `results/paper3_bpw/fdose_k0_person_tracking/datasets_bonn/fdose_k0_person_tracking/seed_0/2026-11-01-17-11-11/fdose_selection_trace.csv`

**计划**：57 事件，ΣK = 211320，K ∈ [526, 7124]，中位 3397；n_init = 11（来源 plan）；sha256 = `56839a1352a55ef28114fd8caf1bdde85e45f7ffffd6a9ea2504205d16b9917a`

| 子门 | G 臂 | S 臂 | 判 |
|---|---|---|---|
| F1 剂量恒等 | 67 事件，错 0 | 66 事件，错 0 | ✅ |
| F2 计划忠实 | 越界事件 19（规格=注入 0） | 计划 N_plan 57 | ✅ |
| F3a γ 活性（硬门） | 臂均 mean(s) 1.405 | 臂均 mean(s) 1.541 | ❌（S/G 比 均值 **1.11×**、中位 1.09、范围 [0.88, 1.32]、> 1.10 的事件 47%，共 57 事件；点数加权口径见 JSON `ratio_pooled`） |
| F3b 索引 Jaccard（**报告项**） | — | — | 均值 0.082，中位 0.060，最大 0.721（两臂索引空间不可比，此值反映地图分叉，并入 R6 报告） |

## F3a 逐事件稀疏度比（前 8 / 后 4）

| 事件 | mean(s) G | mean(s) S | 比 |
|---:|---:|---:|---:|
| 0 | 1.138 | 1.278 | 1.12× |
| 1 | 1.231 | 1.348 | 1.09× |
| 2 | 1.346 | 1.513 | 1.12× |
| 3 | 1.544 | 1.814 | 1.17× |
| 4 | 1.449 | 1.744 | 1.20× |
| 5 | 1.331 | 1.634 | 1.23× |
| 6 | 1.620 | 2.025 | 1.25× |
| 7 | 1.233 | 1.554 | 1.26× |
| 53 | 1.699 | 1.714 | 1.01× |
| 54 | 1.594 | 1.704 | 1.07× |
| 55 | 1.453 | 1.787 | 1.23× |
| 56 | 1.442 | 1.860 | 1.29× |

| F4 池约束 | 池外 0 | 池外 0 | ✅ |
| F5 组件生效 | Σsel 211320 | Σsel 211320 | ✅（计划 ΣK 211320；两臂 Σsel 均等于计划 ΣK；k0 Σsel 262823） |

**k0 报告项**（Amendment A3：F5② 降为报告 —— k0 自计划臂跑满全事件，计划 = k0 前缀冻结，`Σsel_k0 ≥ ΣK_plan` 结构上必然）：Σsel_k0 = 262823 vs ΣK_plan = 211320（✅）；plan_overflow=1 标记 0 个（应恒 0，✅）；越界 flag 判错 7 条（G/S 语义，对 k0 不判）。

**F1 分站点**（M8：两个 densify 站点共用一个事件序数、clone/split 界不同；按计划事件逐个核对，整段缺失也算该段的错）：

| 臂 | F1_init（ord < 11） | F1_map（ord 11..57） |
|---|---|---|
| G | 11 事件，错 0 | 46 事件，错 0 |
| S | 11 事件，错 0 | 46 事件，错 0 |

**done 锚点**（M6；必需）：G `results/paper3_bpw/fdose_G_person_tracking/datasets_bonn/fdose_G_person_tracking/seed_0/2026-11-01-17-56-10/fdose_G_seed0.done（finished_rc0=yes）`；S `results/paper3_bpw/fdose_S_person_tracking/datasets_bonn/fdose_S_person_tracking/seed_0/2026-11-01-18-40-48/fdose_S_seed0.done（finished_rc0=yes）`

## 剂量差读数（两臂 sel 之差，逐事件；本设计的剂量外生 ⇒ 应为恒 0）

- G 臂的 sel − K_plan：中位 +0，范围 [+0, +0]（≡0 才算合规；F1 已逐事件判过）
- S 臂的 sel − K_plan：中位 +0，范围 [+0, +0]（≡0 才算合规；F1 已逐事件判过）

## 逐事件 Jaccard（前 8 / 后 4）

| 事件 | Jaccard | |sel_G| | |sel_S| |
|---:|---:|---:|---:|
| 0 | 0.721 | 2638 | 2638 |
| 1 | 0.457 | 2976 | 2976 |
| 2 | 0.235 | 1494 | 1494 |
| 3 | 0.133 | 674 | 674 |
| 4 | 0.101 | 641 | 641 |
| 5 | 0.083 | 644 | 644 |
| 6 | 0.070 | 625 | 625 |
| 7 | 0.062 | 535 | 535 |
| 53 | 0.049 | 6186 | 6186 |
| 54 | 0.045 | 6306 | 6306 |
| 55 | 0.058 | 6762 | 6762 |
| 56 | 0.059 | 7124 | 7124 |


## 剂量三口径（A2：源点数 / gross 原语 / 分站点）

| 口径 | G | S | 比 |
|---|---:|---:|---:|
| 源点数 Σsel（F1 已强制相等） | 211320 | 211320 | 1.0000 |
| gross 原语（clone+1 / split+2） | 242370 | 252251 | **1.0408** |
| ├ split 占比 | 14.69% | 19.37% | — |
| ├ 站点界 (init / map) | 1.80 m / 0.06 m | 同 | — |
| 分站点剂量 init / map | 11915 / 199405（init 占 5.6%） | 11915 / 199405 | — |

> ⚠ F1 是**计划侧**恒等式，对「两臂候选集是否相同」完全盲（prereg §4.1 注）；
> gross 原语不是 F1 的子门，它是 A2 要求并陈的第二口径（源点数相等 ≠ 净高斯数相等）。

**结论**：机制门未全过 ⇒ 装置失效，冻结读数、先修装置（不得解释机制）