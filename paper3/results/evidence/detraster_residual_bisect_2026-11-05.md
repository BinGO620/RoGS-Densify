# det-raster 残差分叉定位（P3-D2-028 续，2026-11-05）

**目标**：L1 判决（`detraster_L1_verdict_2026-11-05.md`）已确认 rasterizer backward 被修好，
但整臂仍 9/9 件不同。本轮把「还剩什么在分叉」钉死到具体机制。

结论先说：**分叉不在数值，在调度。** 具体是两处结构性来源，都与设备无关：

1. **async 背景自由跑**（主因）：backend 在队列空时无上限地跑 `map()`，
   每个 KF 之间跑了多少次优化迭代 = **墙上时钟决定**。
2. **`densify_and_prune` 的成员选择**（同一机制的下游表现，不是独立的浮点分叉）。

---

## 一、async 自由跑（决定性证据）

`utils/slam_backend.py:2121-2135` 的 `_run_loop`：

```python
if self.backend_queue.empty():
    ...
    self.map(self.current_window)          # ← 不限次数
    if self.last_sent >= 10:
        self.map(self.current_window, prune=True, iters=10)
        self.push_to_frontend()
```

只要前端还没来得及塞消息，backend 就一直跑。每跑一轮 `map()` 会
`add_densification_stats` / 改 `max_radii2D` / 可能触发 `densify_and_prune`。

**实测**（同 config 同 seed，20 帧，det-raster ON，`PYTHONHASHSEED=0`，确定性套件全开）：

| run | backend iteration 数 | 前端 render 调用 |
|---|---|---|
| run1 | 735 个不同 iteration（最大 it=1858） | 727 |
| run2 | 700 个不同 iteration（最大 it=1819） | 728 |

⇒ 同一份数据、同一个 seed，backbone 跑了**不同的总迭代数**。这不是浮点问题，
是**调度本身不确定**。

### 为什么之前没发现
`prereg_det_raster` 的判据只问「两 run 逐位一致吗」。async 模式下这个问题的答案
在**任何**实现下都是「不一致」——即使所有算子都逐位确定。det-raster 把
算子的不确定性消掉了，于是剩下的是**架构级的不确定性**（并发调度），
它一直存在，只是以前被更大的浮点噪声掩盖。

---

## 二、`single_thread=True` 复测：仍分叉，但形态变了

把 `Training.single_thread` 设 true（`mapping_itr_num=150` 固定，不再自由跑），
20 帧 ×2：

| | run1 | run2 |
|---|---|---|
| ATE | 1.0436 cm | 1.0350 cm |
| KF 数 | 3 | 3 |
| 前端 render 调用 | 727 | 728 |

后端 trace：**1854 vs 1886 次调用，前段逐位完全一致**（P 变化点序列 16 个全部同位置）。
前端 trace：**前 548 次调用逐位完全一致**（含 P、means3D、image、depth、opacity、
位姿增量），第 549 次起分叉。

第 549 次调用恰好是 **P 从 19030 降到 17094** 的那一次（一次 prune）。
两侧降到**同一个基数**、删掉**不同成员** ⇒ 该 prune 的 mask 不同。

### 已确立的部分
trace 显示第 548 次调用时两侧的 `P` / `means3D` / `image` / `depth` / `opacity` 哈希
完全相同；`keyframe_diag.csv` 显示**前 6 个 KF 决策行完全一致**（`cur_idx` 1..6，
`point_ratio_2`、`dist`、`create_kf` 全同）。

### 尚未确立的部分（不能声称「输入相同」）
**先修正一个我自己的误判**：这次 P 下降（19030→17094）**不是** `prune=True` 分支
造成的——该分支要求 `len(current_window) == window_size == 12`，而分叉发生在
14 帧短跑的前段（窗口还没满）。因此它是 `densify_and_prune()`
（`gaussian_model.py:1436`）里的 `prune_points(prune_mask)`，mask 由
opacity / max_radii2D / scaling 三路构成（a/b/c 式）。

（`prune=True` 分支本身仍值得查，但它不是本轮的嫌疑人。其 mask 由 `n_obs`
决定，而 `n_obs` 来自多帧 `occ_aware_visibility` 的累加：

```python
self.gaussians.n_obs.fill_(0)
for window_idx, visibility in self.occ_aware_visibility.items():
    self.gaussians.n_obs += visibility.cpu()
```

`occ_aware_visibility[kf] = (n_touched > 0).long()`。）

可行的下一步：逐帧记录 `n_touched` 的 `>0` 布尔图 md5 与 `n_obs` 的 md5，
确认两侧在 prune 时刻是否确有差异。若相同 ⇒ mask 计算内部有问题；
若不同 ⇒ 分叉在更早的 `n_touched` 边界（`test_T > 0.5f` 这个硬阈值）。

---

## 三、已排除的候选（都实测过，非逐位确定不成立）

| 候选 | 实测 |
|---|---|
| rasterizer forward | img/radii/depth/opacity/n_touched 两跑一致（det ON/OFF 皆然） |
| rasterizer backward | det=OFF 6/6 分叉 → det=ON 0/6（`real_data_ab.py`） |
| `n_touched` 整数 atomicAdd | 跨 3 进程 md5 完全相同 |
| `distCUDA2` | 1k/20k/60k/300k 点，同进程与跨进程全一致 |
| `eigvalsh` / `solve` / `median` / `topk` / `sort` / `argsort` / `unique` / `bincount` / `matmul(4096²)` | 全一致 |
| `index_add` / `scatter_add` / masked `+=` 累加（含 8 次重复掩码累加） | 全一致 |
| cv2 `solvePnPRansac` / `findEssentialMat` | 三次一致 |
| torchvision `nms` | 6 次一致 |
| 语义掩码（MaskRCNN） | uid=0 帧 mask 哈希跨 run 完全相同（`ff999a9154`） |
| `CounterRNG`（densify_split 抖动） | 同 key 同 event 两实例一致；deepcopy 后一致 |
| `torch.max(scaling, dim=1)` tie 情形 | 两跑一致（含 indices） |
| `>=` 边界 tie | 两跑一致 |

---

## 四、下一步的确切靶子

prune mask 的构造（`gaussian_model.py:1463-1473`）：

```python
prune_mask = (self.get_opacity < min_opacity).squeeze()      # (a)
if max_screen_size:
    big_points_vs = self.max_radii2D > max_screen_size        # (b)
    big_points_ws = self.get_scaling.max(dim=1).values > 0.1 * extent   # (c)
    prune_mask = logical_or(logical_or(prune_mask, big_points_vs), big_points_ws)
prune_mask = self._dynport_protect(prune_mask)                 # (d) 默认恒等
self.prune_points(prune_mask)
```

但**本次 prune 走的是另一条路**：`slam_backend.py:852` 的 `prune=True` 分支用的是

```python
to_prune = self.gaussians.n_obs < 3          # prune_mode == "odometry"
# 或 n_obs <= prune_coviz & unique_kfIDs >= sorted_window[2]   # "slam"
```

而 `n_obs` 由 `occ_aware_visibility` 累加而来：
```python
self.gaussians.n_obs.fill_(0)
for window_idx, visibility in self.occ_aware_visibility.items():
    self.gaussians.n_obs += visibility.cpu()
```

`occ_aware_visibility` 是 dict，**迭代顺序**取决于插入顺序 —— 这在 Python 3.7+
是确定的（按插入序），但**插入序本身取决于窗口消息到达顺序**。若两 run 的
`current_window` 构造顺序不同，`n_obs` 的浮点（实为 int64）累加和虽同（整数无误差），
但 `to_prune` 的布尔结果依赖 `n_obs` 的**值**，整数累加与顺序无关 —— 所以这条也不是。

**真正的靶子收窄为**：`occ_aware_visibility` 的内容（每帧 `n_touched > 0` 的布尔图）
在两次 run 里是否逐位相同。

- 若**相同**而 `to_prune` 不同 → 问题在 `n_obs` 累加或 mask 应用层。
- 若**不同** → 分叉在 `n_touched` 本身。而 `n_touched` 的写入条件是
  `if (test_T > 0.5f) atomicAdd(&n_touched[id], 1);`（`forward.cu:369`）——
  这是一个**硬阈值**：两侧 `test_T` 只要差 1 ulp 且恰好跨过 0.5，布尔结果就翻转。
  合成测试里 40 000 点只有 313 个非零（远离边界），但真实管线里 alpha 处于
  `test_T ≈ 0.5` 的像素库远大于此 ⇒ 边界翻转概率不可忽略。

  注意这与「整数 atomicAdd 不确定」是两回事：整数累加本身逐位确定（已实测跨进程一致），
  但**喂给它的布尔输入**可能因上游浮点的 1-ulp 差异而翻转。而上游浮点既然已由
  det-raster 修到逐位确定，则这一路径应当也确定 —— 除非 `test_T` 的计算里有
  尚未覆盖的非确定环节（如 `exp()`/`sqrt()` 的库实现、或 bwd 之外的某处）。

---

## 五、对 L1 判决的影响

**判决不变（R-infeasible）**，但归因要改：

- ❌ 原表述暗示「prune 决策是独立于 rasterizer 的第二个浮点分叉源」。
- ✅ 实际是：**async 调度不确定性**（主因，已在 single_thread 下部分消除）
  + **prune 成员选择的残余不确定性**（single_thread 下仍存在，靶子已收窄）。

关键推论：**40 帧 ×2 逐位一致这个判据，在 async 架构下不可达**。
如果继续追 L2，前提是判据本身要改成可判的形态（例如固定迭代数、或比对前 N 帧的
结构化状态而非终端文件）。

---

## 六、诚实登记

- 本轮**没有**改变 L1 判决，也没有取得 L2 入场券。
- 本轮**新增**了两个确定的机制级认识：async 自由跑是设备无关的分叉源；
  single_thread 下前端前 548 次调用逐位一致（这是「算术层已经干净」的强证据）。
- 本轮**排除**了 10+ 个候选（见第三节），这些排除本身有复用价值。
- 未做完：`occ_aware_visibility` 内容的逐帧 md5 比对（下一步第一件事）。
