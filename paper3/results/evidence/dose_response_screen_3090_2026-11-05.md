# 剂量-响应筛查报告（ADC 主阈值 τ 扫描；P3-D2-018）

> 预注册 = `prereg_dose_response_2026-11-04.md` + Amendment A1（seed1 扩批 2×/4×）+ Amendment A2（M8 简化臂边界 / M9 功效核算 / M10 措辞）。唯一变量 = `opt_params.densify_grad_threshold`。**简化臂边界（A2-1）**：四臂均在 `combined_prune/method.yaml` 基座（`SelectiveDensification.enabled=false`）上跑，结论只描述该简化臂与 person_tracking 序列。
> **批次说明**：3090 权威复跑（2026-11-04 22:17 ~ 11-05 01:39 CST，HEAD 1ee5b05f5，两卡并行、卡内串行）：四臂×2seed 全重跑；1× 臂 = `maskstat_off` 配置（prereg §1 复用口径的 3090 版，非 dose_tau1x——该配置不存在）。本地 2060 旧读数仅作跨机对拍参照，不参与判读。

## 装置门（先于读数）

- **D1 剂量真的变了**（终态 `online_num_gaussians` 随 τ 单调不增，且最高/最低剂量臂降幅 ≥ 3%；±3% 装置抖动带）：**FAIL**（2 seed 分别成立）
  - seed 0: 剂量单调不增=False，最高/最低剂量臂降幅 49.55% (下界 3%) ⇒ **FAIL**
  - seed 1: 剂量单调不增=True，最高/最低剂量臂降幅 69.40% (下界 3%) ⇒ **PASS**
  - **列敏感性（G2-3090 次-4，两读法并陈）**：D1 用 prereg 字面列 `num_gaussians`（=online，逐位相同）；若改用 refined 列，单调性判定可能翻转（如 3090 seed0：online 47973→50122 倒挂 FAIL，refined 52973→50122→42980 单调 PASS）。出口以 prereg 字面列为准，refined 读法仅作并陈。

## 每 seed 四臂读数（机读，不手填）

### seed 0

| τ_scale | 阈值 | ATE (cm) | online 末态高斯 | refined 末态高斯 | 完毕锚点 | run |
|---:|---:|---:|---:|---:|---|---|
| 0.5× | 0.0001 | 11.8448 | 75,284 | 75,284 | done | `results/paper3_bpw/dose_tau05x_person_tracking/datasets_bonn/dose_tau05x_person_tracking/seed_0/2026-11-04-22-17-47` |
| 1× | 0.0002 | 11.3558 | 47,973 | 52,973 | done | `results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/maskstat_off_person_tracking/seed_0/2026-11-05-00-44-00` |
| 2× | 0.0004 | 12.4991 | 50,122 | 50,122 | done | `results/paper3_bpw/dose_tau2x_person_tracking/datasets_bonn/dose_tau2x_person_tracking/seed_0/2026-11-04-23-09-05` |
| 4× | 0.0008 | 14.5228 | 37,980 | 42,980 | done | `results/paper3_bpw/dose_tau4x_person_tracking/datasets_bonn/dose_tau4x_person_tracking/seed_0/2026-11-04-22-17-47` |

### seed 1

| τ_scale | 阈值 | ATE (cm) | online 末态高斯 | refined 末态高斯 | 完毕锚点 | run |
|---:|---:|---:|---:|---:|---|---|
| 0.5× | 0.0001 | 11.5173 | 113,071 | 113,071 | done | `results/paper3_bpw/dose_tau05x_person_tracking/datasets_bonn/dose_tau05x_person_tracking/seed_1/2026-11-04-22-43-41` |
| 1× | 0.0002 | 12.1748 | 68,062 | 68,062 | done | `results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/maskstat_off_person_tracking/seed_1/2026-11-05-01-09-13` |
| 2× | 0.0004 | 11.0159 | 38,279 | 43,279 | done | `results/paper3_bpw/dose_tau2x_person_tracking/datasets_bonn/dose_tau2x_person_tracking/seed_1/2026-11-04-23-29-46` |
| 4× | 0.0008 | 8.9711 | 34,601 | 34,601 | done | `results/paper3_bpw/dose_tau4x_person_tracking/datasets_bonn/dose_tau4x_person_tracking/seed_1/2026-11-04-22-42-03` |

## 形态与平台（prereg §3 + A1 判据）

| seed | ATE 极差 (cm) | 形态 | 谷底 τ | 2×−4× (cm) | 2×−1× | 4×−1× | 平台 |
|---|---:|---|---:|---:|---:|---:|---|
| 0 | 3.17 | PLATEAU | 1× | 2.02 | 1.14 | 3.17 | YES |
| 1 | 3.20 | PLATEAU | 4× | 2.04 | 1.16 | 3.20 | YES |

- **平台跨 seed 一致性检查 = True**（判据：2×−4×、2×−1×、4×−1× 三差**全部** < 地板 3.83cm 才记 True；见 `platform_ok`）。**注意：True 只表示「差低于装置分辨率」，按 PREREGISTRATION §3.2 读作「不可判」，不是「平台已确认」。**

## 渲染代价报告项（非判据；PREREGISTRATION §3.1：渲染不作跟踪好坏判据）

| seed | τ | PSNR | SSIM | LPIPS | depth L1 (cm) | 掩码口径 |
|---|---:|---:|---:|---:|---:|---|
| 0 | 0.5× | 28.9647 | 0.9032 | 0.1554 | 23.6178 | static |
| 0 | 1× | 27.6427 | 0.8920 | 0.1656 | 18.6864 | static |
| 0 | 2× | 27.6249 | 0.8823 | 0.1927 | 21.2060 | static |
| 0 | 4× | 26.9497 | 0.8757 | 0.1947 | 19.0274 | static |
| 1 | 0.5× | 29.0823 | 0.9067 | 0.1482 | 19.5469 | static |
| 1 | 1× | 28.9282 | 0.9036 | 0.1529 | 20.3186 | static |
| 1 | 2× | 26.9132 | 0.8724 | 0.1961 | 22.4299 | static |
| 1 | 4× | 28.1631 | 0.8920 | 0.1755 | 16.8965 | static |

> 读法：名称为「online 末态高斯」，不是 refined 终态；渲染质量随剂量下降**单调变差**。两者不同轴——「跟踪不敏感」不等于「地图免费」，写论文时须并陈。

## 出口（prereg §4 + A1）

- **DEVICE_FAIL**：D1 不成立（剂量未真的变化或不单调），本批作废，不加 run。

## 不主张什么

- n=2 不构成效应结论；读数是形态描述，不是显著性。
- 「差异 < 地板」= **不可判**（PREREGISTRATION §3.2），不是「等值」、不是「ATE 不动」。
- 剂量下降本身不是收益；「平台」不等于「致密化无用」。
- 0.5× 侧 U 形左臂仅 seed0 单点，不得写成跨 seed 结论。
- τ 是原版 ADC 的既有旋钮，本批不构成机制创新。
- **简化臂外推边界**：四臂均在 `combined_prune/method.yaml` 基座（`SelectiveDensification.enabled=false`）上跑；结论只描述该简化臂上的 τ 敏感度，不外推到完整系统或其它序列。
- **事件序数**：不同 τ 臂的 densify 事件时刻不同，逐事件配对不可构造；本报告只做臂级终态比较。
- 读数以 `--runs` 清单所指 run 目录为准（本批为 3090 权威复跑；本地 2060 旧读数仅作跨机对拍参照）。

