# MaskStat 预注册 Amendment A2（2026-11-05，写于 3090 权威批判读后；G2-3090 重大② 回写）

> 母文书 = `prereg_maskstat_2026-11-04.md`；账本 `P3-D2-016/017`；本修正案不改变任何
> 数值阈值，只把**判据机实现与母文书的解释分歧**回写，并如实标注写于数据后。

## A2-1 rule 1 的装置门含 G6（回写）

母文书 §4 rule 1 原文只列「G1–G5 任一不过」；§3 G6（非爆炸门：on 终态高斯 ≤ off×1.10）
列在报告项，且 §4 rule 6 称高斯比「不参与 PASS/FAIL」。**判据机实现
（`scripts/paper3_bpw/judge_maskstat.py`）自 v2（G2 整改 2026-11-04）起把 G6 并入
rule 1：任一 seed 的 on/off refined 高斯比 > 1.10 ⇒ rule 1 DEVICE_FAIL。**

理由（回写依据）：
- 剂量爆炸是**装置级失效**（机制臂多放高斯 = 剂量混杂），与 G1–G5 同级；若不拦，
  「机制死/不可判」的出口会在剂量混杂下误判（CGB/FDose 教训：剂量不可排除时出口全部失真）。
- 本解释在 3090 权威批判读中**实际决定出口**（seed0 refined 比 1.132 > 1.10 ⇒ rule 1），
  故必须回写，不得留"实现超前于文书"的状态。

**回写后 §4 rule 1 生效口径**：G1–G5 任一不过，**或**任一 seed 的
`gauss_ratio_on_over_off_refined > 1.10` ⇒ rule 1 DEVICE_FAIL。§4 rule 6 的
「不参与 PASS/FAIL」相应收窄为「高斯比不参与 rule 2–5 的判据，但参与 rule 1 非爆炸门」。

## A2-2 列语义（G2-3090 次-3/次-4）

- 判决表中「高斯比」= **refined 口径**（`refined_num_gaussians`）；online 口径比值
  更大（seed0 1.250），两口径同向 ⇒ rule 1 结论对列选择稳健，但列名必须如实标注。
- `refined − online` 在本批 3 个 run 恰为 +5000 的机制未逐行定位（一次 KF 插入量级），
  已在判决中如实并列两列；后续若重开机制须补逐列对拍。

## A2-3 判据机 provenance（G2-3090 重大①）

`judge_maskstat.py` 自本日起在判决 md/json 写入批次 provenance
（manifest 路径 / judge 时 HEAD / 机器 / 时刻），判决本体自含审计锚。

## A2-4 反悔

本修正案只回写解释与文书，不改阈值、不改数据；revert 本提交即回到
「实现超前于文书」状态（G2-3090 重大② 复现）。
