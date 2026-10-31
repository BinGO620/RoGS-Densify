# FDose 派发前核查（本会话，2026-10-31）—— 上一轮「已补实」里仍有 4 项不成立

**性质**：主 Agent 对 `e3e46073a`（HEAD）的只读核查，零 GPU。目的不是重开审查，而是
在**停止推进**前把「盘上事实 vs 文书自报」的差额钉死，避免下一会话沿用假事实。
**结论**：上一轮 G4 前置自检（`critic_verify_fdose_g3_2026-10-31.md` §八）自报的 4 项里，
**M8 仍未落地**、**「回归复跑逐位一致」在盘上无证据**；另新发现 3 条同类/邻近问题。
**本轮未做任何修改**（除本文件与收尾文档），未派 G4，未跑 580 帧。

---

## 0. 核查坐标

| 项 | 值 |
|---|---|
| HEAD | `e3e46073a`（`feat/bpw-densification`，本地 == origin） |
| 工作树 | 干净（`git status --porcelain` 空） |
| GPU | 未使用；本轮无任何 run |
| 依据 | `DISCIPLINE.md`「口径与工件核验」#12③ / `slam-critic.md` §0.3（类登记）/ P38（自报整改不实） |

---

## 1. M8 仍是半实（自报「已补实」不成立）

上一轮 §八 写：「`f1_by_site()` 产出 `F1_init`/`F1_map` 并入 verdict；测试 K10c」✅。
盘上三条都不成立：

### 1.1 键名不是 `F1_init` / `F1_map`

`scripts/paper3_bpw/check_fdose_gate.py:163-185`

```python
def f1_by_site(ev, meta, plan_k, n_init):
    out = {}
    for site, lo, hi in (("init", 0, n_init), ("map", n_init, None)):
        ...
        out[site] = {"n_events": n_ev, "ok": not wrong, "events_with_wrong_k": wrong}
    out["ok"] = out["init"]["ok"] and out["map"]["ok"]
    return out
```

实际输出键 = `init` / `map`（`:171`），**不是** prereg §2 声明的 `F1_init` / `F1_map`。
全仓 `F1_init` 只出现在 docstring/注释/文档（`:7`、`:164`），**没有任何实际输出键**。

### 1.2 没并入 verdict

`check_fdose_gate.py:485-491`

```python
res["verdict"] = "PASS" if all([
    not arms["G"]["events_with_wrong_k"],
    not arms["S"]["events_with_wrong_k"],
    f2, f3a_pass,
    arms["G"]["below_pool_total"] == 0, arms["S"]["below_pool_total"] == 0, f5_ok,
    done_ok,
]) else "FAIL"
```

`all([...])` 里**没有** `res["f1_by_site"]`。分站点结果只挂在 JSON（`:473-474`）与 MD 表
（`:324-333`）里当旁观数据 ⇒ **「init 段整段失效」不会让门变红**，这正是 M8 要防的盲区
（合并计数 `events_with_wrong_k` 会把某一整段的失效平均掉）。

> 逻辑上分站点失败必然也体现在合并项上（同一批事件），所以不是「漏判」；
> 但 prereg 的措辞是「按站点分列报」，报告项与门的区别在这里被抹平了 ⇒ 属
> **文书声明 ⊃ 实装**（`slam-critic.md` §0.3 的类，与 M3 同源）。

### 1.3 `make_dose_plan.py` 完全没写 `n_init`

`grep -c n_init scripts/paper3_bpw/make_dose_plan.py` = **0**。
计划 dict（`make_dose_plan.py:105-123`）只有 `protocol/source/n_plan/overflow_dose/sequence/seed/k/sum_k/k_min/k_max/k_median/per_event`。
判据机侧 `check_fdose_gate.py:392-394` 用 CLI 默认 `--n-init 11`，**计划与判据机之间无契约绑定**：
换序列/改 `init_itr_num` 后若忘了传 `--n-init`，`per_site_dose` 与 `gross_primitives` 的
站点界会静默算错，且**无任何断言守护**。

> 数值本身在 person_tracking 580 帧下没问题：`init_itr_num=1050` / `init_gaussian_update=100`
> ⇒ init 站点恰好 11 个事件，与默认 11 一致。缺的是**契约**，不是当前数值。

---

## 2. 「回归复跑逐位一致」在盘上无证据

`paper3/STATUS.md` §「G4 前置自检」写：「回归（改动后 40 帧冒烟 trace 复跑装置门）：
verdict PASS；F1 分站点 G/S 各 init 11 事件 + map 6 事件全绿；gross 24,416 / 24,589 …
与 `fdose_smoke40_2026-10-31.md` 已入档读数逐位一致」。

盘上时间线（`ls -la --time-style`）：

| 文件 | mtime |
|---|---|
| `paper3/results/evidence/fdose_gate_smoke_2026-10-31.{json,md}` | **16:00:16** |
| `scripts/paper3_bpw/check_fdose_gate.py`（含 M6/M8 补实） | **17:27:10** |

该 JSON 的顶层键（实读）：`generated_by / source / plan / arms / f2_* / f3a_sparsity /
f3b_index_jaccard / f5_activity / per_site / gross_primitives / verdict` ——
**没有 `done`、没有 `f1_by_site`**。

⇒ 入档的冒烟读数来自 **16:00 的旧代码**；17:27 补实后**没有任何新落盘的 gate 产物**。
「改动后复跑、分站点全绿」这句话**无法用盘上工件复现**（可能跑过但只落 /tmp 且未提交，
也可能没跑）。按 P38，自报「已复跑」而无可复跑工件 ⇒ **记为不成立**。

---

## 3. prereg §4.1 F5 ② 的 k0 子句与装置自相矛盾（预注册内部矛盾，非代码 bug）

`prereg_fdose_2026-10-31.md:175`：

> **F5 组件生效**：① G/S 两臂 `Σsel == ΣK_plan` 且 `ΣK_plan > 0`；
> ② 若给了 `--k0`，k0 的 `Σsel` 也须 == `ΣK_plan`

但 k0 是**自计划臂**（`dose_plan_path: null`，K_i = 本事件 `|ref_sel|`），它**跑满全部事件**；
而 G/S 只投递计划前缀 `N_plan=57`。冒烟实测（`fdose_gate_smoke_2026-10-31.json:365`）：
**k0 Σsel = 28,212，计划 ΣK = 23,979** ⇒ 结构上**永远不可能相等**。

⇒ 这与 M2（§0 第三条「保住全量」vs §4.2 R2 截断）是**同一类**：预注册条文与自己的
装置规则矛盾。代码侧的处理是对的（`check_fdose_gate.py:441-445` 只把 k0 的 Σsel 拼进
`note`，不参与 `f5_ok`），但**预注册正文没改** ⇒ 若照条文实现，正式批会因 k0 恒不等而恒 FAIL。

---

## 4. R6 / R7 声明「必须报」，两个判据机均无产出

`prereg_fdose_2026-10-31.md:208-212`：
- **R6 候选集漂移（必须报）**：同序数事件两臂 `|pool|` 的相对差**中位 + IQR**、候选集交集占比；
- **R7 序数—时间错位（必须报）**：`iter_A(j) − iter_B(j)` 的**中位 + p90 + 极值**、两臂事件总数差。

实际：`grep -c "r6\|R6\|r7\|R7" scripts/paper3_bpw/judge_fdose.py` = **0**（完全无代码）；
`check_fdose_gate.py` = 1，仅 `:305` 一句注释「此值…并入 R6 报告」，而**并入动作没人做**。

⇒ 「必须报」的两条**主要残余混杂量化**（R6 是 §0 明写的主要混杂、R7 是 §0 第三条未切断项）
在判决时**没有任何脚本产出**。属 M3 同源类（prereg 声明的证据通道未实装）。

---

## 5. 判据机/runner 的四处邻近缺陷（本会话新核出）

| # | 位置 | 事实 |
|---|---|---|
| 5.1 | `judge_fdose.py:154-157`、`:175-180` | 帧数闸只查「三臂彼此一致」，**不查等于 580** ⇒ 三臂同为 40 帧的冒烟也能过；「冒烟混进全长」无闸 |
| 5.2 | `judge_fdose.py:49` | `_read_one(..., expect_frames=None)` 形参**声明后从未使用**（死参数），别被「已加帧数闸」的措辞骗 |
| 5.3 | `judge_fdose.py:169`、`:183` | `--runs` JSON 缺 `G`/`S` 键时，`:183` 抛**未捕获 `KeyError`**（不是清晰 `rc=2`）；schema 无校验，seed 集合与 `--seed` 也不校验一致 |
| 5.4 | `run_fdose_l1.sh:85` | `run=$(ls -dt ... \| head -1)` 用 **mtime 取最新** 定位 run 目录 —— 正是 `prereg_fdose` §9 明禁的「`latest_run()` 隐式取 run 目录」同族；同 seed 重跑时 `.done` 可能落到与判据机读取的 trace **不同**的目录 |

---

## 6. 已核实为**真落地**的项（避免下一会话重复怀疑）

| 项 | 证据 |
|---|---|
| M5 RuntimeError 守卫 + reset 清零 | `utils/densification_selection.py:668-676`（`raise RuntimeError`，非 assert）+ `utils/slam_backend.py:368-370`（`del _fdose_event_idx` + `_fdose_ordinal_must_be_zero = True`）+ 测试 `tests/densification/test_fdose_selection.py:364`（D14） |
| M6 done 锚点 | `check_fdose_gate.py:188` `done_anchor()`、`:395` `--require-done`、`:482-483` 并进 `done_ok` → `:485-491` verdict；`run_fdose_l1.sh:87-89` 每臂写 `.done` |
| 次要 7（LOG 两路径黏连） | `LOG.md:829` 已是两个独立反引号块；全仓 `densificationtests` 0 命中 |
| quotepath 新类 | `scripts/02_analysis/sweep_citation_claims.py:71` 强制 `core.quotepath=false`；`:174-182` 有「路径不可解析」负对照 + 非 ASCII 自检 |
| M7 显式 run 清单 | `judge_fdose.py:130-134` `--runs`；无 `--delta/--deltas` 手填通道；`_read_one` 四种拒绝歧义分支（`:67-81`） |
| M4 账本门三层 | 上一轮已修（glob/分派账本/`P3-D[123]-\d{3}` 正则） |
| 测试存在性 | D13/D14、K10/K10b/K10c/K10d、K11/K11b、K12/K12b、K13/K13b/K13c 全部真实存在（`tests/paper3_bpw/test_fdose_judges.py:509-700`） |
| KEY_REGISTRY | FDose 族 7 条（`scripts/02_analysis/prereg_criterion_keys.py:80-91`） |

---

## 7. 待办（按优先级，交下一会话）

1. **[阻塞] `P3-D2-011` 用户答复**（「按默认」/「停」）—— 未答则 580 帧不得开跑。
2. **A2 开 Amendment A3**：更正 prereg §4.1 F5 ② 的 k0 子句（结构上不可能相等；改为
   `Σsel ≥ ΣK_plan` 且无 `plan_overflow`，降为报告项）。
3. **M8 真落地**：`f1_by_site()` 输出含字面键 `F1_init`/`F1_map`；分站点 `ok` 并入 verdict；
   测试 K10c 改成「init 段整段错、map 段正常 ⇒ verdict FAIL」。
4. **A4 n_init 契约**：`make_dose_plan.py` 写 `n_init`；gate 默认从 plan 读，`--n-init` 降为覆盖。
5. **A5 R6/R7 落成机器产出**（报告项，不入 PASS/FAIL）。
6. **A6 判据加固**：帧数闸加 `== 580` 绝对值；`--runs` schema 校验；删死参数；`run_arm`
   改为「跑前记录目录集合、跑后取新增者」，不用 `ls -dt`。
7. **A7 重跑冒烟门并落新证据**（不覆盖旧件，另存文件名），核对 F1 1.2063 / pooled 1.1806 /
   gross 24,416 vs 24,589 / init 11,759 = 49.0% 逐位一致 + 新字段有值。
8. **A8 全量门禁**：`pytest tests/densification tests/paper3_bpw`（基线 96 passed）、
   `prereg_criterion_keys.py`（MISSING=0）、`sweep_citation_claims.py`（rc=0）。
9. **A9 派 G4** 核销（含本文件的 5 条新发现）。
10. 全部通过且 D2-011 点头 ⇒ 才跑 580 帧。

---

## 8. 反悔方式

本文件只新增，未改任何代码或既有工件。`git revert` 本会话的收尾提交即回到
`e3e46073a` 的状态（FDose 装置与 G3 整改原样保留）。
