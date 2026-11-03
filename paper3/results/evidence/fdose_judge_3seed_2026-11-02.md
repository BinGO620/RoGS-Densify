# FDose 3-seed 出口判定（anchor seed0，n=3；机械应用 prereg §6）

**判据**：`prereg_fdose_2026-10-31.md` §5/§6 + **Amendment A4（`P3-D2-014`，post-data 仪器修正，阈值沿用 A1）**；逐序列地板 **3.83 cm**（n=3 口径）

## 每 seed 装置门与 A4 读数（只消费 gate 工件，不在此重算）

| seed | role | gate | F3a′ 均值 | F3a′ ≥1.10 事件 | 跨臂比 | 池基线 C/A | gate 路径 |
|---|---|---|---:|---:|---:|---:|---|
| 0 | diagnostic_rerun | PASS | **1.3144×** | 98% | 1.1253× | 0.874× | `paper3/results/evidence/fdose_gate_seed0_a4_2026-11-02.json` |
| 1 | confirmation | PASS | **1.3265×** | 100% | 1.1276× | 0.861× | `paper3/results/evidence/fdose_gate_seed1_a4_2026-11-02.json` |
| 2 | confirmation | PASS | **1.3074×** | 98% | 1.1118× | 0.884× | `paper3/results/evidence/fdose_gate_seed2_a4_2026-11-02.json` |

## seed0 首跑 vs 诊断重跑（G2 致命项：必须并陈，不得静默替换）

| 口径 | k0 ATE | G ATE | S ATE | S−G | G−k0 | S−k0 |
|---|---:|---:|---:|---:|---:|---:|
| 首跑（first_run） | 11.3884 | 12.1314 | 11.0829 | -1.0485 | +0.7430 | -0.3055 |
| 诊断重跑（selected） | 11.3884 | 11.4452 | 12.7753 | +1.3301 | +0.0568 | +1.3869 |

- **方向翻转**：S−G -1.0485 → +1.3301 cm（已翻转）⇒ n=1 装置抖动，任何方向不得作结论。
- L2 ATE 漂移：G -5.7% / S +15.3%（同 config 同 seed 重跑，<20% 带内商定地板）。
- 选用诊断重跑的理由：P3-D2-013 甲案：诊断重跑只开 trace_pool:true（纯日志开关，F1 逐位等价 Σsel=211320，L2 ATE 漂移 G −5.7%/S +15.3% <20% 带内）；首跑 trace 无 pool_only 行，按 A4 §2.5 F3a′ 不可判。首跑/重跑均保留、不得静默替换。

| 臂 | ATE (cm) | online 高斯 | refined 高斯 | 帧数 |
|---|---:|---:|---:|---:|
| k0 | 11.3884 | 47478 | 47478 | 580 |
| G | 11.4452 | 39783 | 39783 | 580 |
| S | 12.7753 | 65929 | 70929 | 580 |

| Δ | 值 (cm) |
|---|---:|
| S − G（主判据） | +1.3301 |
| G − k0（报告项） | +0.0568 |
| S − k0（报告项） | +1.3869 |

## 每 seed 原始读数（机读，不手填）

| seed | 臂 | ATE (cm) | online 高斯 | refined 高斯 | 帧数 | run 目录 |
|---|---|---:|---:|---:|---:|---|
| 0 | k0 | 11.3884 | 47478 | 47478 | 580 | `results/paper3_bpw/fdose_k0_person_tracking/datasets_bonn/fdose_k0_person_tracking/seed_0/2026-11-01-17-11-11` |
| 0 | G | 11.4452 | 39783 | 39783 | 580 | `results/paper3_bpw/fdose_G_person_tracking/datasets_bonn/fdose_G_person_tracking/seed_0/2026-11-01-21-36-22` |
| 0 | S | 12.7753 | 65929 | 70929 | 580 | `results/paper3_bpw/fdose_S_person_tracking/datasets_bonn/fdose_S_person_tracking/seed_0/2026-11-01-22-19-32` |
| 1 | k0 | 10.2394 | 89891 | 89891 | 580 | `results/paper3_bpw/fdose_k0_person_tracking/datasets_bonn/fdose_k0_person_tracking/seed_1/2026-11-02-12-09-51` |
| 1 | G | 10.2800 | 39849 | 39849 | 580 | `results/paper3_bpw/fdose_G_person_tracking/datasets_bonn/fdose_G_person_tracking/seed_1/2026-11-02-13-41-22` |
| 1 | S | 11.0131 | 39380 | 27316 | 580 | `results/paper3_bpw/fdose_S_person_tracking/datasets_bonn/fdose_S_person_tracking/seed_1/2026-11-02-14-23-11` |
| 2 | k0 | 11.7769 | 76807 | 76807 | 580 | `results/paper3_bpw/fdose_k0_person_tracking/datasets_bonn/fdose_k0_person_tracking/seed_2/2026-11-02-12-53-59` |
| 2 | G | 10.6967 | 35508 | 35508 | 580 | `results/paper3_bpw/fdose_G_person_tracking/datasets_bonn/fdose_G_person_tracking/seed_2/2026-11-02-15-05-15` |
| 2 | S | 11.1257 | 35641 | 35641 | 580 | `results/paper3_bpw/fdose_S_person_tracking/datasets_bonn/fdose_S_person_tracking/seed_2/2026-11-02-15-46-49` |

## 每 seed R6/R7（报告项；缺 trace 显式 missing）

| seed | R6 池相对差中位 | R6 池 Jaccard 均值 | R7 事件数差 | R7 \|偏移\| p90 | R7 触发 |
|---|---:|---:|---:|---:|---|
| 0 | 0.0161 | 0.196 | +0 | 300 | 是 ⚠ |
| 1 | -0.0049 | 0.213 | +2 | 300 | 是 ⚠ |
| 2 | -0.0237 | 0.208 | +2 | 600 | 是 ⚠ |

## R6/R7 残余混杂量化（prereg §4.2 报告项）

| 项 | 读数 |
|---|---|
| R6 候选集漂移：\|pool\| 相对差（中位；IQR；范围） | +0.0161；[-0.0260, +0.0813]；[-0.1987, +0.2740]（65 共同事件） |
| R6 池 gauss_idx Jaccard（**跨索引不可比**，量化地图分叉） | 均值 0.196 / 中位 0.170 |
| R7 序数—时间错位：iter_S−iter_G（中位；\|偏移\| p90；极值） | -150.0000；+300.0000；[+0.0000, +300.0000] |
| R7 两臂事件总数差 | S−G = +0（G 65 / S 65） |
| R7 触发「剂量按数量相等，不按地图时刻相等」 | **是 ⚠**（\|偏移\| p90 +300.0000 vs 事件间隔中位 +150.0000，或事件数差 > 2） |

**功效核算（§5）**：sd = 1.491（来源 bpw_on vs bpw_off, person_tracking, 3 seeds）⇒ n=3 的 MDE(95%) = **3.70 cm**

**n=6 信息价值（规则 4 的处置依据）**：MDE(6) = 1.565 cm；已有三 seed 合计 2.492 cm ⇒ 新增三 seed 平均需 > **2.299 cm** 才能让 n=6 越过 MDE，否则机械出口为 INCONCLUSIVE（规则 5）。

## 判定

> **EXTEND — 方向一致但未过 MDE，允许扩到 n=6（§6 规则 4）**

- 本地 2060 产物（远程 3090 仍 Connection refused）⇒ 按 G-算力条标「非权威」，不得进论文表；本判决为 provisional。
- F1 是计划侧恒等式，不证明两臂候选集相同（prereg §0/§4.1）。
- `G−k0`/`S−k0` 是报告项：两臂与 k0 的注入形态不同，不参与 PASS/FAIL（§6 规则 6）。
- n=3 只用于按 §6 规则 4 判断是否扩展，**不构成方向或效果结论**（prereg §5：n=1 一律不可判；n=3 方向一致性只决定 EXTEND）。
- A4 是 **post-data 仪器修正**（写于 seed0 全长数据后、seeds 1/2 前）：形态由仪器可判性决定，阈值 1.15/1.10/60% 沿用 Amendment A1 未放宽，ATE 未用于选门；seed0 首跑/重跑方向翻转已如实并陈（n=1 抖动，任何方向不得作结论）。
- 负结果、评测协议与「不退化」均**不得**作论文贡献或 headline（DISCIPLINE「论文叙事纪律」；prereg §8）。
- 剂量按数量相等，不按地图时刻相等（prereg §4.2 R7 触发：0, 1, 2, anchor(seed 0)）——两臂同序数事件的地图时刻不同步。
