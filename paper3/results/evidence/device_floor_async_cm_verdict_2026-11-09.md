# async 口径 crowd/mnobox 自差包络判决 —— 2026-11-09（C4 实测升级完成）

**账本**：P3-D2-043 附注（C4 实测升级完成）。

**判决（机械，`prereg_device_floor_async_cm_2026-11-09.md` §2）**：
4/4 run rc0（.done 锚 head=5ae19bb28 caliber=async_deploy）；实测 async 自差包络——

| 序列 | ATE (run1/run2) | **自差** | 高斯极差 |
|---|---|---|---|
| crowd (928f) | 2.5279 / 2.1900 | **0.338cm** | 3.54% |
| mnobox (778f) | 2.8064 / 3.1953 | **0.389cm** | 2.36% |

## 判读

1. **两序列的 async 自差远小于 pt 的 2.14cm 外推值**（0.34/0.39 vs 2.14）——G3-C4 的
   外推担忧方向反了：外推值过于保守，crowd/mnobox 的部署口径噪声其实很小。
2. **C4 实测升级，读数不变**：judge v2（`--envelope-crowd 0.3379 --envelope-mnobox
   0.3889`，`dose_async_migration_judge_v2_measured_env_2026-11-09.json`）重判——
   crowd 中位 +0.165 ≤ 0.338 ⇒ ENVELOPE_UNJUDGEABLE（provenance=measured_async，
   原 SIGN_UNSTABLE 不变）；mnobox +0.072 ≤ 0.389 ⇒ 同左。总出口仍 **MIXED**，
   pt 对读数不受影响。**没有任何 async 判决读数因包络升级而改变**。
3. crowd async off ATE 2.19–2.53cm 与论文一 crowd combined 2.29cm（async）同量级
   ——sanity 交叉印证（不同臂不同协议，仅量级参照，不并列表）。

## 不主张什么

- 2-run 极差是自差的下界估计口径（单 seed 对）；量值主张仍限于仪器口径判决；
- 两口径永不混引（本包络只供 async 判读器门宽使用）。

## 工件

- JSON `device_floor_async_cm_2026-11-09.json`（远端生成、本地核验、md5 对拍入库）；
- 批日志 `device_floor_async_cm_batch_20261109.log`（回传本地）；
- judge v2：`dose_async_migration_judge_v2_measured_env_2026-11-09.json`；
- 按对传参实现：`judge_dose_async_migration.py --envelope-crowd/--envelope-mnobox`
  （G3-C4 amendment，2026-11-09）。
