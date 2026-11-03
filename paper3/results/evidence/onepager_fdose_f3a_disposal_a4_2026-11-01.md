# 呈报：FDose Amendment A4（F3a 统计量改造 + trace_pool 永久化）——`P3-D2-014`

**日期**：2026-11-01　**性质**：D2（判据变更须用户批准）　**上游**：`P3-D2-013`（已答 = 甲）
**证据**：`fdose_f3a_decay_diagnosis_2026-11-01.{md,json}`（零 GPU 第一层）+
`fdose_f3a_achievable_diagrerun_2026-11-01.{md,json}`（trace_pool 重跑 2×2 分解，本呈报的数字全部出自这两件，可复跑）

## 一句话

死因钉死：**γ 键全程满功率**（同池反事实 achievable_S 段中位 1.290–1.392 零衰减、均值
**1.314**、96% 事件 ≥1.15），但两臂候选池的 γ=0 基线漂移 **C/A 0.925→0.712 单调崩塌**，
恒等式 `observed = achievable_S × 池基线` 成立 ⇒ 旧 F3a（跨臂 observed）晚段量到的是
**混杂对键效应的抵消**，不是 γ 失效。

## A4 条文（批准后我落字 + 实装 + 测试）

1. **F3a′ 替换 F3a 成硬门**：对机制臂 S，逐事件在**其自身池**上算
   `mean_s(top-K by g·s^γ) / mean_s(top-K by g)`（stable 平局序）；门沿用 A1 阈值结构
   （均值 ≥1.15 且 ≥60% 事件 ≥1.10）。G 臂同式计算恒 ≈1.000 作 sanity。
   *数据余量*：seed0 反事实 1.314 / 96% / 98%，对 1.15 / 60% 门余量健康。
2. **`trace_pool: true` 对 FDose 族永久化**：F3a′ 的数据源（约 56MB/臂；判据 CSV 照既有
   入库政策）。两个既有 config（`fdose_G/S_person_tracking.yaml`）的「临时」注释改正式。
3. **跨臂 F3a 降报告项**：与池基线 C/A 并陈（这条混杂量化正是 §0「候选集仍各自长」的
   实测形态，判决书必须带）。
4. **R6 升级为真池口径**：池规模逐事件可从 trace 直读（不再依赖 console 正则），
   相对差中位+IQR 照旧报告。
5. **实装与门禁**：`check_fdose_gate.py` 增同池统计（+`--require-pool`：正式批必须
   有池行）、测试（含「池行缺失 ⇒ FAIL」负对照）、KEY_REGISTRY 同步；R6/R7 判读不变。
6. **seeds 1/2 解锁**：A4 落地 + 全量门禁绿后按原流程跑（每臂 trace +~56MB）。

## 不变的东西

F1/F2/F4/F5 判定逻辑、`.done` 锚点、`--expect-frames` 帧数闸、`--runs` schema、
§6 出口与 MDE 表、剂量三口径（A2）全部不动；本件只动 F3a 的**统计量**与**数据源**。

## 成本与反悔

- 成本：零 GPU（seed0 数据已齐）；seeds 1/2 每臂多 ~56MB trace。
- 反悔：A4 落字前 = `git revert f9813d659..7b7dfc723` 区间相关提交即回甲案前；
  落字后 = `git revert` A4 提交（判据回跨臂口径——不建议，会把正确运行判死）。
