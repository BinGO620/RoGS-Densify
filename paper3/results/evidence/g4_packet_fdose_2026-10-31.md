# G4 派发包 — 论文 3 FDose 族（整改核销轮）

**包型**：`G4 remediation-verify`（`slam-critic.md` §0.1；判定优先级 G4 > G2 > G3 > G1）
**账本**：`P3-D2-010`（FDose 落点）/ `P3-D2-011`（呈报，仍待答复；本包不核销它）
**被审对象**：`feat/bpw-densification` 上 FDose 族的 G3 整改（起点 `91e9ffcfb` 之后至派发时 HEAD）
**上一轮**：G3 dispatch，判 **Reject**（1 致命 + 8 重大 + 7 次要）
**派发形态**：**独立会话**（`DISCIPLINE.md`「收口审查关卡」治理原则 4）；报告落 `/tmp`，
主会话只 `grep -A` 读相关小节。

---

## 1. 派发包必带的上轮问题清单（§0.4.2 要求）

逐条从 `/tmp/slam_critic_report_fdose_g3.md` 摘出，**核销对象**：

### 致命（1，已被复核反驳——**本轮请独立复核该反驳是否成立**）

| # | 原报 | 主 Agent 的反驳 | 反驳的工件锚 |
|---|---|---|---|
| F-1 | 「等剂量」只控源点数 K_i，未控实际注入原语数；split 占比 G 29.2% / S 36.0% ⇒ S 多 5.3% | 审查方算 clone/split 界时漏 `cameras_extent=6.0`（init 界 1.80 m 而非 0.30 m、map 0.06 m 而非 0.01 m）⇒ 真值 +0.71% | `critic_verify_fdose_g3_2026-10-31.md` §一（四种界假设对照表）+ `check_fdose_gate.py::gross_primitives` 的 `bounds_m` 字段；决定性核验 = init 站点 11,759 个被选点里 `max_scale > 1.80` 的 **= 0** |

> 反驳被接受的部分：**残余通道真实存在**（gross +0.71% / 40 帧 net +2.8%，差额来自 prune），
> 已按 A2 要求三口径并陈 + 分站点上报。**请核「三口径是否真的并陈、有没有哪里单列引用」。**

### 重大（8，全部声称已整改）

| # | 问题 | 声称落地位置 |
|---|---|---|
| M1 | 派发起点过期 + D2-011 用户未答复 | 起点已在包内冻结；D2-011 仍是**未答**状态（本包不要求核销，见 §4） |
| M2 | prereg §0 第三条与 §4.2 R2 自相矛盾（「保住全量」vs `N_plan` 截断丢 13–22%） | prereg §0 带日期更正 + 78–87% 实际保留率 |
| M3 | F5 两条子句未实装（`backend_timing.json` 无注入计数；k0-vs-off 中位差无代码） | prereg §4.1 F5 加 ⛔废止 + 收窄到两条可判子句 |
| M4 | 账本登记门对 `paper3/` 整族失明（glob / 账本路径 / 编号正则三层） | `health_check.py` 三层修复 + 补 5 份历史文书账本号 |
| M5 | `_fdose_event_idx` 跨地图重建不清零 | `BackEnd.reset()` 清零 + **`_fdose_ordinal_must_be_zero` 标志 + `RuntimeError` 守卫**（本会话补实） |
| M6 | 无 `done` 锚点 | runner 写 `.done` + **`check_fdose_gate.py::done_anchor` / `--require-done` 并入 verdict**（本会话补实） |
| M7 | `judge_fdose` 跨 seed 靠手填 Δ + `read_arm` 隐式取末行 | `--runs <JSON>` 显式清单 + `_read_one` 拒绝歧义表（K12/K12b/K13/K13b/K13c） |
| M8 | 两个 densify 站点共用一个事件序数、截断只砍尾部 | prereg §2 站点表 + `per_site_dose` + **`f1_by_site` 产出 `F1_init`/`F1_map` 并入 verdict**（本会话补实） |

### 次要（7，全部声称已整改）

F3a 表取事件 0 / F3a 三口径（`ratio_pooled`）/ 死常量已删 / 平局确定性测试 D13 /
F2 的 `covered` 子句收紧（K11/K11b）/ 时长高估 2.5× 更正 / health_check 假缺失（**本会话才真修**）。

---

## 2. 本轮必须核验的四件事（§0.3 G4 验收必查）

1. **逐条核销**：上表每项给「核销 / 未核销 + 证据（命令 + 命中行）」。
   **不接受「已写整改说明」**；凡整改项写成**双动作**（"清零 **+** 断言"、"写锚点 **+** 判据机先核"、
   "加 X **+** 分列报"）的，**每个动作各要一条独立命中**。
2. **类登记表是否增长**：本轮新类必须已进可复跑脚本。本族已登记 `KEY_REGISTRY`（FDose 7 条）；
   本轮新增类 = 「自报整改不实」与「`git ls-files` quotepath 致门崩溃」，
   前者落 `sweep_citation_claims.py` / 后者落同脚本的 selftest 负对照 + `PITFALLS.md`。
   **请核这两条是否真的在脚本里、且负对照能变红。**
3. **程序化门先行**（§0.2，**门崩 = 被审方的问题**）：
   | 门 | 命令 | 期望 |
   |---|---|---|
   | pytest | `python -m pytest tests/densification tests/paper3_bpw -q` | 96 passed |
   | 引用/整改类扫 | `python -I scripts/02_analysis/sweep_citation_claims.py` | rc=0，UNMARKED = 0（**曾被 quotepath 弄成崩溃，请核它真的跑完了**） |
   | 类扫 | `python -I scripts/02_analysis/gate1_class_sweep.py` | rc=0 |
   | KEY_REGISTRY | `python -I scripts/02_analysis/prereg_criterion_keys.py` | MISSING_TOTAL = 0 |
   | 体检 | `python -I scripts/health_check.py` | 无 FAIL |
4. **回归未被整改改动**：用 40 帧冒烟 trace 复跑 `check_fdose_gate.py`，读数必须与
   `fdose_smoke40_2026-10-31.md` 逐位一致（F3a 1.2063 / pooled 1.1806 / gross 24,416 vs 24,589 /
   per_site init 11,759 = 49.0%）。**任何漂移都意味着补实改了被守护的事实。**

---

## 3. 读取清单（瘦包；禁止整读 `DISCIPLINE.md` / `NOTES.md` / `PITFALLS.md` / `LOG.md`）

- `paper3/results/evidence/critic_verify_fdose_g3_2026-10-31.md`（**含 §八 本会话自检**）
- `paper3/results/evidence/prereg_fdose_2026-10-31.md` §0/§2/§4.1/§6
- `paper3/results/evidence/prereg_fdose_amendment_a1_2026-10-31.md` §2
- `paper3/results/evidence/prereg_fdose_amendment_a2_2026-10-31.md` §2.1/§2.4
- `scripts/paper3_bpw/{check_fdose_gate,judge_fdose,make_dose_plan}.py`
- `utils/densification_selection.py`（`compute_frozen_dose_knobs` 与 `fdose_active`）
- `utils/slam_backend.py`（`reset()` / 两处 densify 调用点）
- `scripts/paper3_bpw/run_fdose_l1.sh`
- `paper3/DECISIONS.md` 行 `P3-D2-010` / `P3-D2-011`
- `/tmp/slam_critic_report_fdose_g3.md`（上轮全量）

## 4. 明确**不在**本包范围（写在前面，省一轮）

- **不重审设计本体**（estimand、阈值、臂定义）——G1/G3 已审；只有判据本体变了才回 G1。
- **不核 D2-011**：那是呈报件，等用户答复，不属整改核销项。
- **不跑 580 帧**，不做任何 GPU 动作；本包纯只读 + 本地 CPU 门。
- 论文叙事/措辞不在本包（另一档）。

## 5. 结论口径

`Accept` ⇒ 580 帧可派发（仍须 D2-011 用户点头）；
`Accept-with-conditions` ⇒ 按条件清单自行处置后即可执行（不必再开一轮）；
`Reject` ⇒ 指出**哪些整改未核销**，主 Agent 先补实。
