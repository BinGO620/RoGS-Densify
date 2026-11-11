reason: 150 帧在本地 2060 (5.78GiB) OOM（跑完 11 个 densify 事件后）
date: 2026-11-06 14:0x
frames_completed: ~100 of 150
useful_observation: 该 run 的 trace 显示 ms_p50/p90/p99 全为 0.00，n_gt30=88/18402（0.48%）
  ⇒ miss_streak 在 person_tracking 上也高度集中在 0（几乎每帧可见）
  但多阈值列(n_gt1/3/5/10/20)当时还没实现，无法定 M ⇒ 需重跑
verdict: DEVICE_RESOURCE_FAIL；读数不完整
