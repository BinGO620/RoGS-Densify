# 剂量-响应筛查报告（ADC 主阈值 τ 扫描；P3-D2-018）

> **provisional**（本地 2060，非权威；不进论文表）。预注册 = `prereg_dose_response_2026-11-04.md` + Amendment A1（seed1 扩批 2×/4×）+ Amendment A2（M8 简化臂边界 / M9 功效核算 / M10 措辞）。唯一变量 = `opt_params.densify_grad_threshold`；1× 臂复用既有 `maskstat_off` 全长 run。**简化臂边界（A2-1）**：四臂均在 `combined_prune/method.yaml` 基座（`SelectiveDensification.enabled=false`）上跑，结论只描述该简化臂与 person_tracking 序列。

## 装置门（先于读数）

- **D1 剂量真的变了**（终态 `online_num_gaussians` 随 τ 单调不增，且最高/最低剂量臂降幅 ≥ 3%；±3% 装置抖动带）：**PASS**（2 seed 分别成立）
  - seed 0: 剂量单调不增=True，最高/最低剂量臂降幅 90.82% (下界 3%) ⇒ **PASS**
  - seed 1: 剂量单调不增=True，最高/最低剂量臂降幅 64.21% (下界 3%) ⇒ **PASS**
  - **列敏感性（G2-3090 次-4，两读法并陈）**：D1 用 prereg 字面列 `num_gaussians`（=online，逐位相同）；若改用 refined 列，单调性判定可能翻转（如 3090 seed0：online 47973→50122 倒挂 FAIL，refined 52973→50122→42980 单调 PASS）。出口以 prereg 字面列为准，refined 读法仅作并陈。

## 每 seed 四臂读数（机读，不手填）

### seed 0

| τ_scale | 阈值 | ATE (cm) | online 末态高斯 | refined 末态高斯 | 完毕锚点 | run |
|---:|---:|---:|---:|---:|---|---|
| 0.5× | 0.0001 | 14.3685 | 173,654 | 173,654 | done | `results/paper3_bpw/dose_tau05x_person_tracking/datasets_bonn/dose_tau05x_person_tracking/seed_0/2026-11-04-12-20-20` |
| 1× | 0.0002 | 9.3029 | 74,977 | 74,977 | console_done | `results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/maskstat_off_person_tracking/seed_0/2026-11-04-03-22-44` |
| 2× | 0.0004 | 10.5178 | 28,501 | 28,501 | done | `results/paper3_bpw/dose_tau2x_person_tracking/datasets_bonn/dose_tau2x_person_tracking/seed_0/2026-11-04-13-10-52` |
| 4× | 0.0008 | 10.4638 | 15,944 | 15,944 | done | `results/paper3_bpw/dose_tau4x_person_tracking/datasets_bonn/dose_tau4x_person_tracking/seed_0/2026-11-04-13-50-18` |

### seed 1

| τ_scale | 阈值 | ATE (cm) | online 末态高斯 | refined 末态高斯 | 完毕锚点 | run |
|---:|---:|---:|---:|---:|---|---|
| 1× | 0.0002 | 12.1694 | 65,086 | 65,086 | console_done | `results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/maskstat_off_person_tracking/seed_1/2026-11-04-04-54-57` |
| 2× | 0.0004 | 12.5489 | 34,257 | 34,257 | console_done | `results/paper3_bpw/dose_tau2x_person_tracking/datasets_bonn/dose_tau2x_person_tracking/seed_1/2026-11-04-14-33-45` |
| 4× | 0.0008 | 12.1067 | 23,297 | 28,297 | console_done | `results/paper3_bpw/dose_tau4x_person_tracking/datasets_bonn/dose_tau4x_person_tracking/seed_1/2026-11-04-15-12-48` |

## 形态与平台（prereg §3 + A1 判据）

| seed | ATE 极差 (cm) | 形态 | 谷底 τ | 2×−4× (cm) | 2×−1× | 4×−1× | 平台 |
|---|---:|---|---:|---:|---:|---:|---|
| 0 | 5.07 | U_SHAPE | 1× | 0.05 | 1.21 | 1.16 | YES |
| 1 | 0.44 | PLATEAU | 4× | 0.44 | 0.38 | 0.06 | YES |

- **平台跨 seed 一致性检查 = True**（判据：2×−4×、2×−1×、4×−1× 三差**全部** < 地板 3.83cm 才记 True；见 `platform_ok`）。**注意：True 只表示「差低于装置分辨率」，按 PREREGISTRATION §3.2 读作「不可判」，不是「平台已确认」。**
- 0.5× 只有 seed0（A1 明示不补）⇒ **U 形左臂是单 seed 描述，不进跨 seed 结论**。

## 渲染代价报告项（非判据；PREREGISTRATION §3.1：渲染不作跟踪好坏判据）

| seed | τ | PSNR | SSIM | LPIPS | depth L1 (cm) | 掩码口径 |
|---|---:|---:|---:|---:|---:|---|
| 0 | 0.5× | 28.9772 | 0.9079 | 0.1430 | 22.0890 | static |
| 0 | 1× | 29.0391 | 0.9054 | 0.1510 | 18.8463 | static |
| 0 | 2× | 28.5311 | 0.8952 | 0.1722 | 18.4033 | static |
| 0 | 4× | 27.7658 | 0.8829 | 0.1971 | 17.1760 | static |
| 1 | 1× | 28.9342 | 0.9020 | 0.1585 | 21.4425 | static |
| 1 | 2× | 28.1589 | 0.8931 | 0.1763 | 17.0585 | static |
| 1 | 4× | 26.9419 | 0.8807 | 0.1953 | 19.0562 | static |

> 读法：名称为「online 末态高斯」，不是 refined 终态；渲染质量随剂量下降**单调变差**。两者不同轴——「跟踪不敏感」不等于「地图免费」，写论文时须并陈。

## 出口（prereg §4 + A1）

- D1/D3 成立；n=2；平台跨 seed 一致性 = True（一致性 = True 仅指差 < 地板，按 §3.2 读作不可判）。
- **平台读数（描述性，非效应主张）**：2×、4× 与 1× 的 ATE 两两差均 < 地板 3.83cm。差异低于装置分辨率 ⇒ 按 PREREGISTRATION §3.2 记「**不可判**」；方向一致性只作线索，不得写成「ATE 不动」「等值」或「平台已确认」。
- 仍不作显著性与效应量主张（n=2；0.5× 左臂单 seed）；进论文表须 3090 复跑。

## 不主张什么

- n=2 不构成效应结论；读数是形态描述，不是显著性。
- 「差异 < 地板」= **不可判**（PREREGISTRATION §3.2），不是「等值」、不是「ATE 不动」。
- 剂量下降本身不是收益；「平台」不等于「致密化无用」。
- 0.5× 侧 U 形左臂仅 seed0 单点，不得写成跨 seed 结论。
- τ 是原版 ADC 的既有旋钮，本批不构成机制创新。
- **简化臂外推边界**：四臂均在 `combined_prune/method.yaml` 基座（`SelectiveDensification.enabled=false`）上跑；结论只描述该简化臂上的 τ 敏感度，不外推到完整系统或其它序列。
- **事件序数**：不同 τ 臂的 densify 事件时刻不同，逐事件配对不可构造；本报告只做臂级终态比较。
- 全部产自本地 2060 ⇒ provisional。

