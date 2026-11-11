# crowd/mnobox 自差包络补测预注册（测量口径 #6 门核算扩展）—— 2026-11-08

**状态**：判据锁定于本批任何 run 之前（本件随 runner 同 commit 入库，先于派发）。**账本**：P3-D2-042 附注（G3-C4 后续）。
**触发**：G3-C4 整改——async 迁移判读器把 crowd/mnobox 的 ATE 包络标为
`pt_config_extrapolated_provisional`（device_floor_3090 只测了 pt 系 config）；
本批补测两序列的**仪器口径同 config 同 seed 自差**，升级 C4 为实测包络。

## §1 设计（4 run，仪器口径，全长）

**seed 取 3 的理由**：两臂 seed_0/1 已被过供给批与 MaskStat L2 批消费（其读数已入判决，
不可触碰），seed_2 刚由 A1 补批占用；自差包络是装置属性（同 config 同 seed 重跑），
seed 编号本身不影响包络有效性，取空目录 seed_3 以保证 R-valid 比对与判读消费
无歧义（G3-C1 同源防线）。

| 序列 | 配置 | 臂 | run 数 |
|---|---|---|---|
| crowd | `instr_off_crowd` | off | **s3** ×2 |
| moving_nonobstructing_box | `instr_off_moving_nonobstructing_box` | off | **s3** ×2 |

- 仪器口径三开关 + 三环境锁不变（runner = `run_instrument.sh` 原件，内置 R-valid）。
- 全长（crowd 928 / mnobox 778 = rgb 行数 − 2，PITFALLS #1197 口径）。

## §2 判据（机械）

1. **R-valid（每序列）**：同 config 同 seed 2 run ⇒ `compare_three_way.py` 判
   R1_bitwise_identical；R2 ⇒ 仪器失效整批作废。
2. **包络提取（本批产出）**：逐序列记
   `ate_selfdiff_cm = |ATE_run1 − ATE_run2|`、`gauss_range_pct = 极差/中位`、
   `kf_ate_selfdiff_cm` 同式——写入
   `device_floor_crowd_mnobox_2026-11-08.json`。
3. **门核对接线**：包络落地后，async 迁移判读器 crowd/mnobox 对的
   `envelope_provenance` 由 `pt_config_extrapolated_provisional` 升级为
   `measured`（amendment 落字 + 判读器加 `--envelope-cm` 按序列传参；不改已跑批次
   的历史读数，只影响未来批）。
4. **fail-closed**：任一 run rc≠0 补跑一次，二次止损该序列（该序列包络缺测 ⇒
   C4 维持 provisional，不影响其余）。

## §3 队列位置与时间盒

- **位置**：批 2（async 迁移，硬顶 11-09 14:00）之后接续；`run_device_floor_
  crowd_mnobox.sh` 双卡各一序列链（crowd ≈128min / mnobox ≈108min，并行 ≤2.2h）。
- **硬顶 2026-11-09 20:00**。

## §4 不主张什么

- 本批是装置表征批（L2 类），不是判效批——包络数字不进论文正文，只作判读器
  门宽依据；单序列单 seed 对的极差是包络的**下界估计**（两样本），判决引用时注明
  "2-run 极差估计"。
- 不改任何已跑批次的读数与判决。
