# E 轴实现验证：默认关逐位一致 + C 臂机制真触发（2060 冒烟，非权威）—— 2026-11-09

**账本**：P3-D2-045（立项）。**预注册**：`prereg_adaptive_itr_schedule_2026-11-08.md`。
**本件性质**：**本地 2060 冒烟 + 逐位比对**，按纪律「算力归属」§本地 2060 只作 pilot/对拍，
其读数**非权威、不进任何判读计数或判决读数**。L1 三臂正式读数须在远程 3090 出。

---

## 一、默认关逐位一致（代码保护例外流程 ③ 判据）

**方法**：同一配置（`instrument_person_tracking`，itr=150 默认关）、同 seed 0、同 40 帧、
同仪器前置，分别在**改动前** HEAD（`c583b12be`，git worktree 分离检出）与
**改动后** HEAD（`a959c14e3`）各跑 1 run，用 `scripts/paper3_bpw/deterministic_probe/
compare_three_way.py` 的比对口径（逐位件 + 易变列剔除 CSV + save_dir 掩蔽 config）做 md5 比对。

| 项 | 改动前 | 改动后 |
|---|---|---|
| run | `…/seed_0/2026-11-09-13-27-08` | `…/seed_0/2026-11-09-13-39-28` |
| HEAD | `c583b12be` | `a959c14e3` |
| ATE (cm) | 1.1682 | 1.1682 |
| `mapping_calls` | 15 | 15 |
| `mapping_iterations` | 2107 | 2107 |
| `adaptive_itr_*_calls` | （无该键） | 0 / 0 |
| console `adaptive_itr` 行 | — | **0 行** |

**比对结果：12 件判据工件逐位相同（0 diff）⇒ R1_bitwise_identical。**
（比对集 = `per_frame_ape.csv` / `plot/{stats_final,trj_final,trj_full_final}.json` /
`tracking_raw.csv` / `efficiency_raw.csv` / `mapping_raw.csv` / `deferred_commit_events.csv` /
`reliability_signal/frames.csv` / `config.yml`(save_dir 掩蔽)。`detprobe_*_lastrow.txt`
两侧均不存在 ⇒ 记 N/A，非差异。）

⇒ **默认关行为与主线逐位一致**；`backend_timing.json` 新增的两键在关臂恒 0、
console 无调度行（机制在关闭路径上零消费）。

**工件位置**：改动前的 run 由 `git worktree`（`/home/cb/data/monogs-ours-preitr`，
分离检出 `c583b12be`）产出，已**逐件 md5 对拍后**复制进本仓
`results/paper3_bpw/instrument_person_tracking/…/seed_0/2026-11-09-13-27-08/`
（tracking_raw / per_frame_ape / efficiency_raw / console.log / config.yml 五件 md5 全同）。
worktree 目录保留未删（其 results 未跟踪，按纪律「删前核跟踪状态」不动）。

## 二、C 臂机制真触发（DISCIPLINE 9「组件生效验证」）

**run**：`adaptive_itr_person_tracking` seed 0，`--max-frames 60`，
`…/seed_0/2026-11-09-13-07-43`，rc=0，60 帧完成（`per_frame_ape.csv` 61 行）。

**逐调用日志**（console.log 原样，共 11 行）：

```
KF#2 (frame 5) itr=30      KF#7 (frame 30) itr=30
KF#3 (frame 10) itr=30     KF#8 (frame 35) itr=30
KF#4 (frame 15) itr=30     KF#9 (frame 40) itr=50
KF#5 (frame 20) itr=30     KF#10 (frame 45) itr=50
KF#6 (frame 25) itr=30     KF#11 (frame 50) itr=50
                           KF#12 (frame 55) itr=50
```

- **两段式在预注册阈值处精确切换**：序数 2–8（frame 5–35）全 30，序数 9 起（frame 40+）全 50。
  序数 1 = 初始化关键帧（frame 0，走 `init_itr_num`=1050，不计入调度，与 impl note §2.1 一致）。
- **落盘计数**：`backend_timing.json` → `adaptive_itr_early_calls: 7` / `late_calls: 4`。
- **总迭代数对账**：`mapping_iterations = 1471` = 1050（init）+ 7×30 + 4×50 + 11×1
  （每 KF 的 prune 调用）——**逐项精确相符**，无隐藏消费点。

## 三、本件不主张

- 不主张任何 ATE/算力结论：本件是 2060 冒烟、40/60 帧短跑，C 臂读数（ATE 1.3258 vs
  A@40 1.1682）**不同帧数不可比**，只用于验机制触发。
- 不主张 C 臂在 580 帧上的行为——L1 正式读数走远程 3090（prereg §2）。
