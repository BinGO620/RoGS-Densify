# 剂量过供给 A1 第三 seed 判决 —— 2026-11-08（P3-D2-042 收口；G2 审查中）

**判决（机械，amendment §2 出口沿母件，`--seeds 0 1 2`）**：H1 出口 = **SEQUENCE_DEPENDENT**
（与母件 n=2 判决同出口，不翻转）。

| 序列 | gain（n=3） | Δ(tau4x−off) per seed | 判读 |
|---|---|---|---|
| crowd | **+1.220** | −1.368 / −0.073 / −1.220 | 三 seed 同号、超地板——比 n=2 的 +0.72 **更强**，可判为正坐实 |
| mnobox | **−0.472** | +0.472 / +0.537 / +0.228 | **倒挂三 seed 坐实**（减量有害） |
| balloon | **UNJUDGED** | −0.259 / −0.219 / **+0.052** | s2 翻正 ⇒ 异号；n=2 的 +0.24 亚地板方向读数**在 n=3 下不成立**，按规则记未判 |

- **地图规模**：四序列 tau4x/off 比 n=3 **中位** crowd 0.243 / balloon 0.239 / mnobox 0.197 / pt 0.224（中位带 **0.197–0.243**，普适 0.2× 维持）；n=2 的 min-max 带（0.197–0.255）不再约束新样本——新样本 0.1907/0.2634 出带，如实登记（G2 重大1 口径更正 2026-11-08：0.196–0.242 系均值带误标中位）。
- **H2**：dose_zero vs 默认 median **+3.617**（三 seed deltas 0.693/6.022/3.617，与母件一致，无变化）。
- **churn×gain 配对（n=3 版）**：pt +2.63* / crowd +1.22 / balloon 未判 / mnobox −0.47
  ——散点仍无单调关系，H1 证伪形态不变（*pt 点带混杂标记）。

## 前置门与机器门

- 新批 **R-valid 锚对**（crowd tau4x s2 ×2）= **R1_bitwise_identical**（批日志
  `dose_seed3_batch_20261108.log`："INSTRUMENT OK: 逐位一致"，18:08 收工 gpu0/gpu1 rc=0）。
- 7/7 run rc0 全长；帧数 = 各序列全长（928/439/778）。
- 判读命令 = amendment §2 落纸命令（roots 实测、`--seeds 0 1 2`、判读器 h2 fail-closed 版）。
- 机器门：judge rc=0；全量 pytest 617 passed（`5661c1cc7` 派发前置，工件
  `pytest_pre_dispatch_2026-11-08.log`）；MISSING_TOTAL=0 实跑工件 =
  `prereg_keys_2026-11-08_a1close.log`（附 rc）。~~原引 pytest 日志含 MISSING_TOTAL=0~~
  系引证错宿主（该日志只含 617 passed）——更正指针在此，实例已登记
  `sweep_citation_claims.py`（G2 重大2 处置 2026-11-08）。

## 判读

1. **论文引用从 n=2 切到 n=3**：crowd +1.22 / mnobox −0.47 / balloon 未判 / 地图中位
   0.196–0.242；ch5 已同步刷新（表 5.2 + 5.1/5.5 正文）。
2. **诚实条款兑现**（amendment §6）：出口与母件相同，但 balloon 读数降级（方向 → 未判）
   ——母判决不撤销，`dose_oversupply_verdict_2026-11-08.md` 已加带日期追注。
3. H1 的否证结论（churn 不预测方向）与"无 churn 处方"在 n=3 下维持。
4. mnobox 倒挂从 n=2 方向读数升为三 seed 同号——**减量有害**的方向坐实
   （负向主张无量值门、判读地板只约束正向，口径不对称如实声明；量值不外推、
   限仪器口径）——G2 次要④ 措辞对齐母件行 29。

## 已知口径注记（G2 次要处置，2026-11-08）

- 判读地板 0.5cm 只约束**正向**主张（prereg §4 claim floor）；负向主张（mnobox）为
  三 seed 同号方向判读，无量值门——口径不对称如实声明。
- crowd tau4x 锚 run1 与 crowd off s2 目录同秒撞名（14-28-04）——不同臂根，
  判读 collect 按 root 分离，消费无歧义（G2 次要⑥）。
- judge JSON 的 `prereg` 字段指向母件 prereg（判读器内置常量）；本批治理文件 =
  Amendment A1（判据链见上），JSON 字段不改（G2 次要⑦）。

## 工件与审查

- 判读 JSON：`dose_oversupply_judge_seed3_2026-11-08.json`（远端生成、本地核验；
  per_seed 逐 run 锚内含）。
- 批日志：`dose_seed3_batch_20261108.log`（远端；R-valid 比对段在列）。
- 原始 run（远端，收口时判据件入库）：`instrument_dose_tau4x_crowd/seed_2`×2、
  `instr_off_{crowd,balloon,moving_nonobstructing_box}/seed_2`×1、
  `instrument_dose_tau4x_{balloon,moving_nonobstructing_box}/seed_2`×1。
- G2 审查：`/tmp/slam_critic_g2_a1_seed3_2026-11-08.md`（本判决落盘前派发）。
