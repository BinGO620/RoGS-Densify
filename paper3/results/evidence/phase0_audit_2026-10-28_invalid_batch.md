# Phase 0 首轮三臂跑：作废判定与根因

**日期**：2026-10-28
**状态**：判决 = 本批**作废（INVALID）**，但不是因为 budget 公式
**上位**：`.claude/handoff/HANDOFF.md`（其"next_actions[0] = 修 budget 计算"的归因需要修正）

---

## 1. 结论先说

首轮三臂（balloon 439 帧）的 ATE 不可用，这一点交接包是对的。
但交接包把原因归到 **budget 估算公式**（`#{accum/denom >= τ_base}` 与 `clone/split` 实际分支不是一一对应），
**这个归因不成立**。真正的原因在上游：

> **三条臂不是因果孪生（causal twin）。它们跑在三条不同的随机流上。**

因此本批连"同输入、同预算、只差排序键"的前提都没有建立。
在修 budget 之前修 budget，等于在一个更底层的混杂上继续叠加。

## 2. 证据

### 2.1 三臂的 RNG base key 不同

`utils/causal_twin.py:149`：

```python
def base_rng_key(config) -> tuple:
    dataset = config.get("Dataset", {}) if isinstance(config, dict) else {}
    seq = dataset.get("sequence") or dataset.get("dataset_path") or ""
    seed = config.get("seed", 0) if isinstance(config, dict) else 0
    return (str(seq), int(seed))
```

`slam.py:735-736` 在运行期把 `config["Dataset"]["sequence"]` 覆写为 **config 文件名去扩展名**：

```python
sequence_id = get_script_sequence_id(config, args.config)   # → basename(config_path)
config["Dataset"]["sequence"] = sequence_id
```

三份配置文件名不同 ⇒ `sequence` 不同 ⇒ `base_rng_key` 不同：

| 臂 | 运行期 `Dataset.sequence` | `base_rng_key` |
|---|---|---|
| off | `bpw_off_balloon` | `('bpw_off_balloon', 0)` |
| on | `bpw_on_balloon` | `('bpw_on_balloon', 0)` |
| negctl | `bpw_negctl_balloon` | `('bpw_negctl_balloon', 0)` |

（实测见 §5 复现命令）

### 2.2 这条 key 会改变首帧初始化

`causal_twin.CounterRNG` 的 key 决定：

- `gaussian_model.py:398` —— 初始点云 keyed 下采样
  `subsample_indices(n_pts, keep_k, "init_downsample", event)`
  ⇒ 三臂的**初始高斯位置集合不同**，不是同一张地图起步。
- `utils/slam_backend.py:714`（`map()` 内）—— 随机 KF 采样 `randperm(..., "map_perm", iteration)`
  ⇒ 训练看到的视角顺序不同。

实测首帧初始化抽样索引前 6 位：

```
off     [2, 16, 41, 61, 96, 156]
on      [24, 52, 62, 76, 90, 133]
negctl  [55, 68, 91, 94, 95, 145]
```

### 2.3 这直接解释了"第一个 densify 事件就已不同"

日志中三个臂的**第一个** densify 事件（iter=1）就互不相同：

| 臂 | iter=1 pool | iter=1 budget |
|---|---:|---:|
| on | 4219 | 2276 |
| negctl | 4184 | 2188 |

如果两臂从同一状态出发、预算规则相同（`budget = |{g_i >= τ_base}|`），这个数不可能不同。
它不同，只能因为**分母 `denom` 与分子 `accum` 所依据的高斯集合本身不同** —— 即 §2.2。

### 2.4 为什么 budget 公式不是主因

交接包指出的"估 budget 与真实分支不一一对应"是一个真实的设计风险，但它解释不了：

- 为什么差异出现在**第一个事件**（此时还没有任何历史漂移）；
- 为什么 pool 大小（4219 vs 4184）先于 budget 就分了叉。pool 只依赖 `accum/denom` 的逐点取值，
  与 budget 公式无关。

⇒ budget 公式是**次要**问题。主因是随机流未对齐。

## 2.5 修复随机流后：第二处独立缺陷浮出水面

对齐 `rng_sequence` 后重跑 80 帧短冒烟，三臂的**首事件**一致了：

| 臂 | iter=1 pool | iter=1 budget |
|---|---:|---:|
| on | 4186 | 2187 |
| negctl | 4186 | 2187 |

但逐事件预算从 **iter=201 起重新分叉**（on 1142 / negctrl 1095），
最终高斯数仍不等：off 26843 / on 29548 / negctl 20867（80 帧）。

⇒ 这是与随机流**无关的第二个缺陷**：预算恒等式 `budget = |{g_i >= τ_base}|`
与 `densify_and_clone` / `densify_and_split` 的实际净增不是一一对应。
已知的两个来源（spec §3 已列出，但未验证）：
- clone 分支额外受 `scale <= percent_dense * extent` 约束；
- split 分支受 `scale > bound` 约束且被 prune 反向抵消；
- `_dynport_protect` 会豁免部分点（默认关，但路径存在）。

**因此"修 budget 公式"仍是必要的第二步**，只是它必须排在对齐随机流之后 ——
否则两处混杂无法分离。这正是交接包缺失的那半步。

## 3. 对下一步的修正

交接包的 next_actions[0] 应替换为：

1. **【新，最高优先级】把三臂钉在同一随机流上。**
   在 `sweep` / 配置层固定 `Dataset.sequence` 为语料名（如 `balloon`），而不是让它回退到
   config 文件名。可选做法：
   - 三份 YAML 里显式写 `Dataset: {sequence: balloon}`；或
   - `slam.py:156` 的 `get_script_sequence_id` 改为优先读一个与实验臂无关的 `Dataset.sequence`
     （臂名只影响 `save_dir`）。
   验收：三臂在同一 seed 下的首帧初始点云**逐元素一致**（可加单测）。
2. **然后**再处理 budget 公式与真实分支的对应关系（交接包原条目，降为第 2 步）。
3. 重跑三臂，先验 §3.1 的"预算匹配 + 初始云一致"两条，再看 ATE。
4. 换更难序列前，先完成 1–3。

## 4. 不要做的事

- 不要在随机流未对齐时，把本批 ATE 差值当"机制无效"的证据 —— 它与"机制无效"不可区分。
- 不要只改 budget 公式就重跑：那样两臂仍从不同初始云起步，混杂照旧。
- 不要因此调整 p0 / τ_lo：二者仍按 spec 先验锁定（p0=8.0，τ_lo=0.5·τ_base），本次不涉及。

## 5. 复现命令

```bash
cd /data/monogs-ours
/data/conda_envs/monogs-ours/bin/python - <<'EOF'
import sys, yaml
sys.path.insert(0, '/data/monogs-ours')
from utils.causal_twin import base_rng_key
for arm in ("off", "on", "negctl"):
    cfg = yaml.safe_load(open(f"configs/experiments/paper3_bpw/bpw_{arm}_balloon.yaml"))
    # main() 的覆写值 = config 文件 basename（见 slam.py:156-160, 735-736）
    cfg.setdefault("Dataset", {})["sequence"] = f"bpw_{arm}_balloon"
    cfg["seed"] = 0
    print(arm, base_rng_key(cfg))
EOF
```

以及日志证据：

```bash
for arm in on negctl; do
  grep -m2 'pool=' results/paper3_bpw/bpw_${arm}_balloon/datasets_bonn/*/seed_0/*/console.log
done
```

## 6. 边界

本文件只否定"本批数据可用于判决"与"budget 公式是主因"两点。
它不主张修复后机制一定有效；也不主张 budget 公式可以不管。
