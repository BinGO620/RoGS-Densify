# crowd/mnobox 自差包络补测判决 —— 2026-11-09（G3-C4 后续；含 prereg 设计缺陷登记）

**账本**：P3-D2-042 附注（G3-C4 后续；设计缺陷如实登记见 §二.3）。

**判决（机械，prereg §2）**：4/4 run rc0、两序列 R-valid **双双 R1_bitwise_identical**
（same=12 diff=0）；自差包络 crowd **0.0cm** / mnobox **0.0cm**（高斯极差 0%）。

## 一、读数

| 序列 | ATE (run1/run2) | 自差 | 高斯 (run1/run2) | R-valid |
|---|---|---|---|---|
| crowd (928f) | 3.0744 / 3.0744 | **0.0** | 24967 / 24967 | R1 ✓ |
| mnobox (778f) | 2.1622 / 2.1622 | **0.0** | 27937 / 27937 | R1 ✓ |

锚点：4× `.done` head=fcf3bdf53 finished_rc0=yes（`device_floor_cm_batch_20261108.log`，
00:50 收工 gpu0/gpu1 rc=0）。

## 二、判读（含 prereg 设计缺陷的诚实登记）

1. **仪器口径在 crowd/mnobox 的有效性获直接确认**（R-valid ×2）——此前该两序列只有
   crowd tau4x s2 锚对一处（A1 批），本批把 off 基线臂也补齐了逐位验证。
2. **自差 0.0 是逐位一致的构造性结果**（判据件逐位相同 ⇒ 派生指标定义性相同），
   不是独立的噪声测量——它的信息量 = "R1 成立"本身。
3. **prereg 设计缺陷（如实登记）**：本件 §一 声称"升级 C4 为实测包络"，但 async 迁移
   判读器（`judge_dose_async_migration.py`）的 ATE 包络作用对象是 **async 口径**读数，
   其所需自差 = **async 口径**同 config 同 seed 重跑——本批测的是仪器口径（构造性 0），
   **达不到该目的**。C4 维持 provisional（async 判决已按包络三档诚实处置，未受影响）。
   async 口径自差补测另立：`prereg_device_floor_async_cm_2026-11-09.md`（amendment，
   判据先行，已入库接续派发）。
4. 监视器 grep 词不匹配（"包络补测 结束" vs 实际 "自差包络批 结束"）致轮询超时未报
   完成——批次本身 00:50 正常收工，登记为监视器小缺陷。

## 三、不主张什么

- 0.0 不主张为"两序列零噪声"（构造性结果）；
- 不改 async 判决任何读数（其 C4 provisional 状态由 async 自差批决定）；
- 评测协议不是贡献。

## 四、工件

- JSON `device_floor_crowd_mnobox_2026-11-09.json`（远端生成、本地核验）；
- 批日志 `device_floor_cm_batch_20261108.log`（回传本地）；
- raw run 判据件存远端（仓内惯例）。
