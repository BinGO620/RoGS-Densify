# det-raster L1 判决（P3-D2-027，2026-11-05）

**判据出处**：`prereg_det_raster_2026-11-05.md` §2
**判据**：det-ON + 开关 ON，`person_tracking` 40 帧 × 2 run 同 seed ⇒ 10 件判据件逐位一致
（含 KF 模式）+ rc=0×2 ⇒ R-feasible，进 L2。
**硬顶**：2026-11-12（未触及）。

---

## 判决：**R-infeasible（部分否证）** —— det-raster 未使整臂逐位一致

| 轮次 | 修正 | 结果 | 判据件 |
|---|---|---|---|
| 轮 2 | 修 convert_det 到 render/preprocess 之间 | R2_divergent | 9/9 异 |
| 轮 3 | + `PYTHONHASHSEED=0`（env 预置） | R2_divergent | 9/9 异 |

（轮 1 = 错误基座，日志已归入 `voided/`，不作判据。）

两轮有效探针均 rc=0×2：
- 轮 2：ATE **1.1842 / 1.1635 cm**（差 0.021 cm）— run 目录 `2026-11-05-10-35-06` /
  `2026-11-05-10-45-23`
- 轮 3：ATE **1.1771 / 1.1664 cm**（差 0.011 cm）— run 目录 `2026-11-05-11-10-46` /
  `2026-11-05-11-00-22`

**但判据件全不同（9/9）** ⇒ 严格判据未过。

> **证据完整性登记（自查）**：轮 2 的 run2 目录 `2026-11-05-10-45-23` 在收口清理时
> 被我误删（原想移出 `.void` 临时目录，实际连带删除）。其 ATE 1.1635 与
> `detraster_full_20261105.log` 中的 runner 输出仍可核；**10 件判据件的 md5 无法再复算**。
> 判决依据以轮 3（两 run 目录均在）为准。轮 2 的 9/9 结论来自当轮 runner 现场比对输出，
> 未受影响，但按纪律标注为「判据件已不可复算」。

---

## 但「rasterizer backward 假设」本身被**证实为真**

这一点必须与整臂判决分开陈述，否则会把已确立的事实一起否定掉。

### 证据 1：真实规模 A/B（决定性）
`scripts/paper3_bpw/deterministic_probe/real_data_ab.py`，480×640 / 40 000 点，
同一进程、同一数据、仅翻转一个开关：

| det | 同 seed 两跑 |
|---|---|
| **OFF** | **6/6 梯度张量全部 DIFF**（复现原始分叉） |
| **ON**  | **全部 IDENTICAL** |

### 证据 2：跨进程复现
同配置两次独立解释器（`/tmp/crossproc_test.py`）：渲染、深度、6 个梯度张量
**逐位一致**（diff 无输出）。

### 证据 3：仪器在真实管线里确实生效
在 `gaussian_renderer/__init__.py` 临时插桩，7 帧真实 SLAM run（1878 次 render 调用）：

```
548 det_bw=True has_config=True raster_key=True pid=<frontend>
1330 det_bw=True has_config=True raster_key=True pid=<backend>
```
**1878/1878 全部 det_bw=True**，两个进程（含 spawn 子进程）都正确取到开关。
⇒ 不存在「开关没接上」这一解释。

### 证据 4：forward 与 torch 层均确定
- rasterizer forward（det ON/OFF 皆然）：img/radii/depth/opacity/n_touched 两跑一致。
- `CUBLAS_WORKSPACE_CONFIG=:4096:8` + `use_deterministic_algorithms(True, warn_only=False)` 下：
  `eigvalsh` / `solve` / `median` / `topk` / `sort` / `argsort` / `nonzero` /
  `matmul(4096²)` / `unique` / `bincount` / `index_add` / `scatter_add` / `interpolate`
  全部两跑一致。
- `simple_knn.distCUDA2`（1k/20k/60k/300k 点）：同进程与**跨进程**均一致。
- OpenCV `solvePnPRansac` / `findEssentialMat(RANSAC)`：三次一致。
- torchvision `nms`：6 次一致。

---

## 残差分叉的精确定位（本轮新证据）

按 render 调用序插桩（`DETRASTER_TRACE`，记录 P / means3D / render / depth / opacity /
max_radii2D / xyz_gradient_accum / denom / static_prob 的逐调用 md5）后逐进程比对：

**前端进程（code 侧）**
- 调用 #1–#548：**全部字段逐一相同**（含 P、kfIDs、max_radii2D、gradAcc、denom）。
- 调用 #549：**P 相同（19030→17094 两侧同值）**，但 `means3D` / `max_radii2D` /
  `xyz_gradient_accum` / `denom` **全部不同**。

**后端进程**
- 首个分叉 idx=2102，`P` 也不同（16774 vs 16772）⇒ 是前端分叉的**下游后果**。

### 这个形态说明什么
第 549 次调用处在一次 **prune（剪枝）之后**：P 从 19030 降到 17094，两侧**降到同一个数**，
但**被删掉的是不同的子集**。而 prune 前一次调用（#548）时两侧的 `xyz_gradient_accum` /
`denom` / `max_radii2D` 还完全相同。

⇒ 差异产生在「同一份相同输入 → prune mask」这一步之内，且 mask 的基数相同、成员不同。
`densify_and_prune` 的 mask 由 `opacity < min_opacity`、`max_radii2D > max_screen_size`、
`scaling.max > 0.1*extent` 三路逻辑或构成——这三路输入在 #548 时逐位相同。
这是**下一步（L2）要查的确定目标**，本轮未定位到具体算子。

---

## 对判决文案的修正（prereg 自我更正）

`run_detraster_probe.sh` 原 R2 分支文案为：

> R-infeasible: det-ON 两 run 仍分叉 ⇒ **分叉源不在 rasterizer backward 累加**

**该文案不成立**，因为上面的证据 1/2 已证明 backward 累加确是分叉源之一且已被消除。
已改为：

> R-infeasible: det-ON 两 run 仍分叉 ⇒ **除 rasterizer backward 之外尚有至少一个分叉源**
> （该源已证实在 prune 决策的成员选择上）；rasterizer backward 假设本身仍成立。

---

## 结论分层（供后续引用，避免口径混引）

1. **det-raster 机制有效**：修掉跨 block float atomicAdd 后，rasterizer 反向在单机、
   跨进程、真实规模下都逐位确定。这是一个**可复用的确定性组件**（patch 已入库：
   `paper3/results/evidence/detraster_patch/det_raster_L1.patch`，md5 `44eafc56…`）。
2. **单靠它不足以让整臂逐位一致**：prune 成员选择上另有一个（至少一个）分叉源。
3. **臂级可判性仍未取得**：E3（臂级终点）依旧「自差内不可判」，机制门 E1/E2 的读数
   依旧带 ±0.02 cm 量级噪声。比起修复前（±2.14 cm ATE 摆动、gaussian 数 −30%~+97%）
   已显著收窄，但**未达到逐位一致**。

---

## 诚实负结果声明

- 本轮**没有**取得 R-feasible，不构成 L2 入场券。
- 本轮**没有**任何评测协议/工具链工作被当作贡献；det-raster 是**测量仪器修复**，
  按 P3-D2-027 立项书定位，它是恢复臂级判效力的必要条件，本身不是论文贡献点。
- 硬顶 2026-11-12 尚有 7 天；是否继续追第二个分叉源，取决于「prune 成员选择」是否
  能在不改主线语义的前提下确定化。
