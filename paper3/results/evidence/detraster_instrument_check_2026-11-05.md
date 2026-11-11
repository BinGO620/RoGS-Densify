# det-raster 仪器有效性自检（P3-D2-027，2026-11-05）

**目的**：在判读 40 帧探针之前，先证明「det 开关确实生效、rasterizer backward 分叉确实被消除」。
否则 R2 分叉无法区分「假设被否」与「仪器没接上」——这是 P3-D2-027 prereg 判据的先决条件。

## 一、三层证据

### 层 1：合成冒烟（小规模，64×64 / 512 点）
`scripts/paper3_bpw/deterministic_probe/synthetic_smoke.py`

| 检查 | 结果 |
|---|---|
| (a) det-ON 同 seed ×2，渲染 + 6 个梯度张量逐位一致 | **PASS**（8/8 IDENTICAL） |
| (b) det-ON vs det-OFF 语义等价 | **PASS**（loss 相对差 0.0；最大逐元素梯度相对差 3.407e-04） |

### 层 2：真实规模 A/B（480×640 / 40 000 点）— **决定性**
`scripts/paper3_bpw/deterministic_probe/real_data_ab.py 40000`

| 配置 | 同 seed 两跑 | 说明 |
|---|---|---|
| **det=OFF** | **6/6 梯度张量全部 DIFF** | 复现原始分叉（跨 block float atomicAdd 顺序不定） |
| **det=ON** | **全部 IDENTICAL** | 定点化 backward 消除该源 |

这是「仪器有效」的直接证据：同一份数据、同一进程、仅翻转一个开关，分叉从 6/6 变 0/6。

### 层 3：跨机二进制一致性
本地 2060 与远程 3090 使用**同一份 `.so`**（md5 `dfd77bb2…`），合成冒烟输出哈希**逐位相同**
（含 (b) 的 3.407e-04）。⇒ 后续 3090 权威探针与本地 2060 快筛在数值语义上同源。

## 二、仪器修正记录（本轮发现并修掉的两个缺陷）

### 缺陷 A：convert_det 调用位置错误（首版）
首版把 `BACKWARD::convert_det`（定点镜像 → float 缓冲）放在 `Rasterizer::backward()` **返回之后**。
但 `BACKWARD::preprocess` 在该函数**内部**、`BACKWARD::render` 之后就已读取 `dL_dmean2D / dL_dconic`
⇒ preprocess 读到的仍是全零镜像。

症状：det-ON 时 `means3D / scales / rotations` 梯度**全为 0**（`nz_on=0` vs `nz_off=1536`），
即修正后的梯度根本没有回传。合成冒烟的 (b) 首轮即报 `max per-elem rel grad diff = 1.000e+00`。

修正：把 5 次 `convert_det` 移入 `rasterizer_impl.cu` 的 `Rasterizer::backward()` 内，
紧接 `BACKWARD::render(...)` 之后、`BACKWARD::preprocess(...)` 之前。

### 缺陷 B：PYTHONHASHSEED 未固定（设备无关分叉源）
40 帧探针首轮 R2_divergent（9/9 判据件不同），但 `rasterizer` 已被层 2 证明修好。
⇒ 残差源与设备无关。定位：CPython 的 `str/bytes` hash 默认**每进程随机化**，
`set` / `dict` 迭代顺序随进程变，下游按序消费处即分叉。

实证（三进程，未固定 seed）：
```
order= ['gamma', 'alpha', 'delta', 'epsilon', 'beta']
order= ['alpha', 'gamma', 'beta', 'epsilon', 'delta']
order= ['alpha', 'beta', 'delta', 'gamma', 'epsilon']
```
固定 `PYTHONHASHSEED=0` 后三次一致。

**陷阱**：在 `sitecustomize.py` 里 `os.environ["PYTHONHASHSEED"]="0"` **无效**——
哈希随机化在解释器启动时已决定。必须由 runner 在**启动前** `export`。

**次生陷阱**：`sitecustomize` 里 `raise` 会被 CPython **吞掉**（仅打印一行
`Error in sitecustomize`，进程继续运行）⇒ 靠 sitecustomize raise 做 fail-closed **不成立**。
真正的闸门放在 runner 的 selfcheck 显式断言（`PYTHONHASHSEED=='0'` 且
`torch.are_deterministic_algorithms_enabled()`），不满足即 `exit 3`。

## 三、对判读的影响

- 层 2 已确立：**rasterizer backward 的跨 block float atomicAdd 确实是分叉源之一，且已被消除**。
- 若固定 `PYTHONHASHSEED` 后 40 帧探针转为 R1 ⇒ 分叉源 = {rasterizer backward, hash 随机化}，两者皆可修 ⇒ 进 L2。
- 若仍 R2 ⇒ 尚有第三源（与设备无关），需继续定位；此时**不得**判 R-infeasible（那是对「rasterizer 假设」的否定，
  而该假设已被层 2 证实为真）。
