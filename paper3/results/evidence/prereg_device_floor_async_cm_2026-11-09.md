# async 口径 crowd/mnobox 自差包络补测预注册（P 批 amendment）—— 2026-11-09

**状态**：判据锁定于任何 run 之前。**账本**：P3-D2-043 附注（C4 实测升级；上游缺陷登记 = `device_floor_crowd_mnobox_verdict_2026-11-09.md` §二.3）。
**背景**：`device_floor_crowd_mnobox_verdict_2026-11-09.md` §二.3 登记的 prereg 设计
缺陷——async 迁移判读器的 ATE 包络需要 **async 口径**自差，P 批误测仪器口径（构造性 0）。
本件补正确的测量。

## §1 设计（4 run，async 部署口径，全长）

| 序列 | 配置 | seed × run |
|---|---|---|
| crowd | `async_off_crowd` | s2 ×2 |
| moving_nonobstructing_box | `async_off_moving_nonobstructing_box` | s2 ×2 |

- seed 2 取空目录（async_off_* 的 s0/s1 已被批 2 消费）；runner =
  `run_device_floor_async_cm.sh`（直接 slam.py，无仪器环境，.done 锚含
  caliber=async_deploy + head）。
- 派发前预检 seed_2 为空（同 G3-C1 防线）。

## §2 判据（机械）

1. **L2（async 无逐位门）**：每对 2 run 报 `ate_selfdiff_cm = |ATE_1 − ATE_2|`、
   `gauss_range_pct`——写入 `device_floor_async_cm_2026-11-09.json`。
2. **出口**：两序列各得一个 async 自差估计值（2-run 极差，下界估计口径）；
   任一 run rc≠0 补跑一次，二次止损该序列。
3. **接线**：`judge_dose_async_migration.py` 的 `--envelope-cm` 支持按对传参
   （amendment 实现 + 单测）——crowd/mnobox 对改用实测 async 包络（**升级
   `envelope_provenance` 为 `measured`**）；pt 对维持 2.14cm（device_floor_3090）。
4. 已跑批次的读数与判决不改（历史 C4 provisional 状态保留作记录）。

## §3 时间盒

硬顶 2026-11-09 20:00（4 run ≈ 2–4h，GPU 现空）。
