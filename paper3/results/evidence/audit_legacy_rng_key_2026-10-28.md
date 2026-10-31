# 历史批次 RNG key 污染核查（2026-10-28）

**范围**：`results/lifecycle_paper2/`（论文 2 的 L1/L2/L3 批次）
**触发**：审计 Phase 0 时发现 `base_rng_key` 从 `Dataset.sequence` 取键，而该字段在运行期被覆写为 **config 文件 basename**（含臂名）。
**结论**：**历史各批次的各臂确实跑在不同的随机流上**（机制确认）。
但**受影响的是 `results/lifecycle_paper2/`，不是论文 2 正文**——正文未引用这批（见 §5）。

---

## 1. 机制链

1. `slam.py:156-160` `get_sequence_id(config, config_path)`：
   若 config 未显式给 `Dataset.sequence`，返回 **config 文件 basename 去扩展名**。
2. `slam.py:735-736`：`config["Dataset"]["sequence"] = sequence_id` —— 运行期无条件覆写。
3. `utils/causal_twin.py:149` `base_rng_key(config)` → `(Dataset.sequence, seed)`。
4. 该 key 驱动 4 个随机站点：
   - `gaussian_model.py:398` 初始点云 keyed 下采样（`subsample_indices`）
   - `gaussian_model.py:1333` split 抖动（`normal_like`，site `densify_split`）
   - `slam_backend.py:714` `map()` 随机 KF 采样（`map_perm`）
   - `slam_backend.py:1598` color refinement 的视角采样（`color_refine`）

## 2. 历史批次实际命名

编号 `L3_{seq}_{arm}_s{seed}` / `l1b_person_tracking_gate` 等。同一序列的不同臂 **config 文件名不同**：

| 臂 | config 文件名 | 运行期 `Dataset.sequence` |
|---|---|---|
| off | `l3_crowd2_off.yaml` | `l3_crowd2_off` |
| exit | `l3_crowd2_exit.yaml` | `l3_crowd2_exit` |

实测自各批保存的 `config.yml`（143 份，全部 `sequence` 与文件名一致、与臂名绑定）：

```
l3_crowd2_off      -> sequence: l3_crowd2_off
l3_crowd2_exit     -> sequence: l3_crowd2_exit
l1b_person_tracking_gate    -> sequence: l1b_person_tracking_gate
l1f_balloon2_obsdebt        -> sequence: l1f_balloon2_obsdebt
...
```

⇒ 同序列的 off 与 exit 臂：**初始点云不同、split 抖动不同、随机 KF 顺序不同、color refinement 采样不同**。

## 3. 影响分级

| 影响 | 是否成立 | 说明 |
|---|---|---|
| 初始点云不同 | **是** | 两个臂从不同种子点云起步，属于算法输入的实质差异 |
| split 抖动不同 | **是** | 影响新高斯位置，但幅度受 std 缩放约束 |
| 随机 KF 采样不同 | **是** | 改变训练视角顺序 |
| 判决是否被推翻 | **未定** | 需定量重放，不能仅凭此推断 |

## 4. 关键：判决对比的是**配对差分**

`scripts/02_analysis/l3_paired_judge.py:84-105` 的判据是：

```python
ds = [(e - o) for o, e in zip(off, ex) ...]   # 逐 seed 配对差分
mean_d = statistics.mean(ds)
thr = max(THRESHOLD_FLOOR_CM, statistics.stdev(off_ok))  # 门槛 = off 臂 seed 内 sd
```

即：**用 off 臂自己的 seed 内 sd 当门槛**，要求 |mean Δ| 超过它。

若各臂不在同一随机流，则 `off` 的 3-seed 离散度里混入了"臂间系统性差异"以外的额外方差来源，门槛 `stdev(off_ok)` 会被**抬高**，从而：

- 对"机制有效"的判决更**保守**（更难 PASS）→ 不构成假阳性风险；
- 但反过来，`mean Δ` 本身也被未配对噪声污染，方向可能被翻转 → **假阴性**风险存在。

**注意**：`stdev(off_ok)` 只取 off 臂内部 3 seed，不直接受 exit 臂 key 影响；受污染的是 **Δ 的计算**（配对假设不成立时，`e - o` 不再是同条件的差）。

## 5. 影响面结论（2026-10-28 定稿）

**经核查：本污染对论文 2 正文无实质影响。** 依据：

1. **正文未引用该批次。** `papers/paper2/paper2_cvm.tex` 中对 `lifecycle_paper2` 的引用次数为
   **0**（`grep -c lifecycle_paper2 papers/paper2/paper2_cvm.tex` → `0`）。
2. **正文声明的数据来源不同。** 正文引用的是 `manifest_offline_L1_L3.json`、
   `dyn_cost_5seq_2026-10-05.md`、`anatomy_census.json` 等，属于
   `results/dynport_offline/` 与 `results/embrace_dyn/` 两批，非 `lifecycle_paper2`。
3. **正文已把 prior stack 定位为坐标参照。** §2（System and Comparison）原文：
   "its measurements are placed here only as a coordinate frame, not as a result of
   this paper"，因此其配置命名惯例不构成正文的推断前提。
4. **唯一沾边处是内部归档。** `papers/paper2/archive/v0_2026-10-10/NARRATIVE.md:169-170`
   有一句「本文判据 = lifecycle_paper2 阶梯」，但那是**旧叙事草稿**，正文已删。

⇒ **不修改论文 2 任何文件。** 本文件作为该结论的登记。

### 5.1 若日后复查，需注意

- 该污染**只影响**"若把 lifecycle_paper2 批次当作严格配对证据"这一用法。
- 对论文 2 现有结论：**无影响**。
- 对论文 3：已通过 `Dataset.rng_sequence` 修复（见 §6），不受影响。

## 6. 与 Phase 0 的关系

Phase 0（论文 3）已通过 `Dataset.rng_sequence` 修复此问题：三臂显式 pin 同一 tag，实测首事件 `pool=4186 budget=2187` 三者一致。历史批次**不**回改，仅登记。

## 7. 复现

```bash
cd /data/monogs-ours

# 1) 确认历史各臂保存的 sequence 与运行 tag 一致（143/143，0 mismatch）
python - <<'PY'
import glob, os, yaml
files = glob.glob("results/lifecycle_paper2/**/config.yml", recursive=True)
bad = []
for f in files:
    c = yaml.safe_load(open(f))
    seq = (c.get("Dataset") or {}).get("sequence")
    tag = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(f))))
    if str(seq) != tag:
        bad.append((f, seq, tag))
print(f"{len(files)-len(bad)}/{len(files)} ok, mismatch={len(bad)}")
PY

# 2) 确认 key 由 sequence 决定（同序列不同臂 -> 不同 key）
python -c "
import sys; sys.path.insert(0,'.')
from utils.causal_twin import base_rng_key
for s in ('l3_crowd2_off', 'l3_crowd2_exit'):
    print(s, base_rng_key({'Dataset': {'sequence': s}, 'seed': 0}))
"
```
