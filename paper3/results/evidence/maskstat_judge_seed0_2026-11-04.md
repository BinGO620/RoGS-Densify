# MaskStat L1 出口判定（n=1；机械应用 prereg §4）

**判据**：`paper3/results/evidence/prereg_maskstat_2026-11-04.md` §2–§4；地板 3.83 cm（固定口径）；sd=1.491（bpw_on vs bpw_off, person_tracking, 3 seeds）

## 每 seed 双臂读数（机读，不手填）

| seed | off ATE | on ATE | Δ(on−off) | 高斯比(on/off, refined) | 机制作用量(share_w<1) | G6 |
|---|---:|---:|---:|---:|---:|---|
| 0 | 9.3029 | 11.3469 | +2.0440 | 0.815 | 0.757 | PASS |

**mean Δ = +2.0440 cm；方向一致 = True；MDE(n) = — cm（n=2 时仅方向参考）**

## 判定

> **规则 0 — SINGLE_SEED_UNJUDGEABLE — 机制门通过，n=1 按预注册一律不可判（等 seed1）**

## Caveats

- n=1 的 ATE 是方向参考：MDE(1)=—（sd=1.491 固定口径），不构成效果结论（prereg §3）。
- 本批若产自本地 2060 ⇒ 非权威 provisional，不得进论文表（G-算力条）。
- 剂量下降本身不是收益（P3-D2-004）；终态高斯比只作机制作用量量化。
- 机制输入 = 运行期 MaskRCNN 掩码（机制输入，非评测仪器）；判决不消费掩码。
- 负结果、评测协议与「不退化」不得作论文贡献或 headline（DISCIPLINE 论文叙事纪律）。

