# 作废日志（2026-11-05 早期，勿引用）

这三份是 det-raster 首版（**错误基座** = compressed-3dgs 内陈旧 rasterizer 副本）阶段的产物，
不含 projmatrix_raw，安装即打破环境；此外首版还有 convert_det 位置错误。留档仅为 provenance，
**任何判决/数字不得引用本目录**。

- `detraster_probe_20261105-083223.log` — 错误基座首次探针（11s，环境崩）
- `detraster_pilot.log` — 错误基座 pilot
- `detraster_full_20261105-083259.log` — 错误基座全量尝试

有效日志（正确基座 `43e21bff`）：
- `../detraster_smoke_20261105-102032.log` — 40 帧 smoke（rc=0，ATE 1.27cm）
- `../detraster_full_20261105.log` — 轮2 全长 ×2（convert_det 已修正，R2）
- `../detraster_full_hs_20261105.log` — 轮3 全长 ×2（+PYTHONHASHSEED=0，R2）
