# 剂量前沿 async 迁移检查判决 —— 2026-11-08（P3-D2-043 收口；G2 审查中）

**判决（机械，`prereg_dose_async_migration_2026-11-08.md` §4.5，`--require-head 5661c1cc7`）**：
总出口 = **`MIXED`**（预期出口 `MAP_PSNR_TRANSFERRED_ATE_ENVELOPE` 未落上——预期失败非判据
失败，路由全程机械）。读数分层清晰，迁移状态按对逐条登记。

## 一、读数（17/17 run rc0 全长，`caliber==async_deploy ∧ head==5661c1cc7` 过滤全过）

| 对 | ratio 中位（档） | Δ 中位（档） | 迁移判定 |
|---|---|---|---|
| pt_tau4x | 0.670（UNJUDGEABLE_BAND） | **−2.238（DIRECTION_JUDGED，与仪器同号）** | **ATE 方向迁移成立**；地图规模不迁移 |
| pt_zero | **0.224（TRANSFERRED）** | −2.030（ENVELOPE_UNJUDGEABLE） | 地图塌缩迁移；PSNR 不迁移（−1.41，band） |
| crowd | 0.472（UNJUDGEABLE_BAND） | +0.164（SIGN_UNSTABLE） | 未判出迁移（n=2 异号） |
| mnobox | 0.486（UNJUDGEABLE_BAND） | +0.072（ENVELOPE_UNJUDGEABLE） | 未判出迁移（回到包络内） |

- 逐 seed：pt_tau4x Δ = −2.238/−0.678/−2.633（2/3 超包络；**方向档对包络取值敏感**：
  余量仅 0.098cm、包络本身为 2-run 极差估计——L2 前不作强度主张）；pt_zero Δ = −2.030/−1.736/−2.670
  （**3/3 同号负**——与仪器 +3.62 **反号**，但在包络内，机械档为 ENVELOPE_UNJUDGEABLE）；
  crowd Δ = +0.404/−0.075；mnobox Δ = +0.064/+0.080。
- PSNR：pt_zero 三 seed −1.82/−0.76/−1.41（中位 −1.41，仪器 −6.3~−6.6 **不迁移**）；
  tau4x −0.54/+0.48/+0.28（仪器 −1.07~−1.43，async 下消失）。

## 二、判读（四条，按信息量排序）

1. **减量的 ATE 收益方向在部署口径成立**（本批最重要的正面读数）：pt_tau4x
   n=3 中位 −2.24cm、超包络、与仪器口径 −2.63 同号 ⇒ "默认剂量不在最优"从仪器口径
   仪器结论升格为**部署口径方向可判**（n=3，量值仍不外推、两口径数值不并列表）。
2. **地图规模收益臂依赖地迁移**：zero 的地图塌缩迁移（0.22×，机制性：densify 全关）；
   **tau4x 的 0.2× 增益未判出迁移**（async 0.67×，band）——剂量→规模的响应在部署口径显著变缓
   （async 调度结构不同：建图事件/迭代量由墙钟驱动）。"地图规模收益普适"须收窄为
   "仪器口径普适；部署口径 zero 迁移、tau4x 不迁移"。
3. **序列异质性与渲染代价未判出迁移**：crowd +1.22 → 异号（n=2）；mnobox −0.47 → 包络内
   ~0（n=2）；pt_zero 的 PSNR 差退到 band、tau4x/crowd/mnobox 对本就不设 PSNR 主判档
   ⇒ "减量处方按序列诊断"在部署口径**未判出**（两对 n=2 均不可判，存在性否定给不出），
   渲染代价论点在部署口径未获支持。
4. **零端点反号（诊断级登记）**：async 下 dose_zero 三 seed 一致地低于默认
   （中位 −2.03 在包络内、量值不可判；seed2 −2.670 单 seed 超包络，判读按中位档执行）——与仪器口径 +3.62 反号。机械档不给它任何主张，
   但它与根因分析 (c)（地图策略是二阶量、调度是一阶杠杆）同向：部署口径下地图策略
   的效应更被调度噪声淹没。

## 三、本判决不主张什么

- 不主张 async 口径任何效应量值（包络 2.14cm 内一律不可判）；
- 两口径数值永不并列（比例量/方向性陈述除外，且显式标口径）；
- 母件仪器口径判决不撤销、不修正——本批回答的是"迁移什么"，两口径并存；
- `MIXED` 出口下 FULL_TRANSFER/MAP_PSNR_… 均未落上，任何"全面迁移/全面不迁移"的
  简化表述都不成立；
- 评测协议不是贡献。

## 四、前置门与工件

- 17/17 run `finished_rc0=yes`（批日志 `dose_async_migration_batch_20261108.log`，
  22:07 收工 gpu0/gpu1 rc=0）；帧数 = 580/928/778 全长。
- 判读器 collect 的本批过滤（caliber + head）**实战生效**：pt 系 seed 目录里的
  历史 run（含 2060 provisional 与旧批 .done）全部被拒收——无顶替路径（G3-C1 验证）。
- 判读命令 = prereg §4 落纸命令原样（roots/参数逐字）；JSON
  `dose_async_migration_judge_2026-11-08.json`（远端生成，本地已收编入库）；批日志
  `dose_async_migration_batch_20261108.log` 已回传本地（G2 重大3 处置 2026-11-08）。
- **raw run 与判据件按仓内惯例存远端工作区**（"判据件（远端）"，P3-D2-031/041 先例）；
  本地可复算件 = 判读 JSON + 批日志 + .done 字段（per-seed run 名锚在 JSON 内）。
- 判读命令实参留痕 = 本节 + prereg §4（judge JSON 不含 argv 字段，G2 次要② 登记）；
  crowd 对 JSON 缺 envelope_provenance 键系 SIGN_UNSTABLE 早退路径（G2 次要① 登记，
  判读后不改码）。
- 机器门：judge rc=0（非 RUN_INVALID）。

## 五、G2 审查

`/tmp/slam_critic_g2_async_migration_2026-11-08.md`（判决落盘前派发）。
