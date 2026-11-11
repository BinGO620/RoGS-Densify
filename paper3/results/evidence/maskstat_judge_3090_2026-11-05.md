# MaskStat L1 出口判定（n=2；机械应用 prereg §4）

**判据**：`paper3/results/evidence/prereg_maskstat_2026-11-04.md` §2–§4；地板 3.83 cm（固定口径）；sd=1.491（bpw_on vs bpw_off, person_tracking, 3 seeds）

## 每 seed 双臂读数（机读，不手填）

| seed | off ATE | on ATE | Δ(on−off) | 高斯比(on/off, refined) | 机制作用量(share_w<1) | G6 |
|---|---:|---:|---:|---:|---:|---|
| 0 | 11.3558 | 11.2295 | -0.1263 | 1.132 | 0.771 | FAIL |
| 1 | 12.1748 | 11.6700 | -0.5048 | 0.718 | 0.772 | PASS |

**mean Δ = -0.3155 cm；方向一致 = True；MDE(n) = 13.396 cm（n=2 时仅方向参考）**

## 判定

> **规则 1 — DEVICE_FAIL — 装置门未过（G6 剂量非爆炸：on 臂高斯膨胀 >10%）**

**批次 provenance**：manifest=`paper3/results/evidence/maskstat_runs_3090_2026-11-05.json`；judge 时 HEAD=fc3021e10；机器=local；判决时刻=2026-11-05 02:15:50 +0800。
> 批次说明：3090 权威复跑（HEAD 1ee5b05f5）：off = 剂量-响应 1× 臂同 run；on 臂含 MaskRCNN。跨机对拍：本地 2060 provisional 判决（P3-D2-017）读数不参与本判读。

## 出口后续动作

- rule 1（DEVICE_FAIL）⇒ 冻结读数、不加 run；装置门阈值是否需按机标定由装置自差诊断批（device_floor）定，结论入账本。
- rule 5（INCONCLUSIVE）⇒ 记「已排除方向」（NOTES），n 扩满再收口。
- rule 3（PROMOTE）⇒ 按 prereg §4 晋级流程扩 seed。

## Caveats

- n=2 的 ATE 是方向参考：MDE(2)=13.396cm（sd=1.491 固定口径），不构成效果结论（prereg §3）。
- 本批若产自本地 2060 ⇒ 非权威 provisional，不得进论文表（G-算力条）。
- 剂量下降本身不是收益（P3-D2-004）；终态高斯比只作机制作用量量化。
- 机制输入 = 运行期 MaskRCNN 掩码（机制输入，非评测仪器）；判决不消费掩码。
- 负结果、评测协议与「不退化」不得作论文贡献或 headline（DISCIPLINE 论文叙事纪律）。

