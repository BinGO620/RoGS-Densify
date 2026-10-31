# 逐序列地板修正后，SWBA/BA 关闭结论的复核（2026-10-30）

**性质**：判据修正（`PREREGISTRATION.md` §3.2）对既有关闭结论的**影响复核**，不是新判决
**触发**：§3.1 的 0.62cm 全局常数废止，而 SWBA 关闭论证的第 (3) 条
（`NOTES.md`「SWBA / BA 侧整族关闭」）恰好引用了该常数
**数据源**：`results/paper2_fulltable/evidence/manifest_r33.json`（84 run，四臂 × 7 序列 × 3 seed）
+ `paper3/results/evidence/seq_floors_2026-10-30.json`（逐序列地板，机算）
**复现**：见 §4

---

## 1. 结论

**关闭结论不变，且论证更强。**

原论证（0.62cm 常数版）：oracle 完美门上限 +0.401 / +0.463 / +0.504 cm，全部 < 0.62 地板。

复核后（逐序列地板版）：**在全部 7 个序列上，oracle 上限都低于该序列自己的地板**——
不是"平均低于一个常数"，而是"逐序列无一例外"。地板从 0.50（balloon）到 3.83（person_tracking）
不等，而 oracle 上限只在 pt1 与 balloon2 两处非零（+3.36 / +0.17 cm），两处都仍在地板内
（3.83 / 0.72）。

⚠ **pt1 这一条依赖地板取法**（3.83 是四套估计里最保守的），$3 给出两值并陈与
"结论不依赖它"的独立理由。

## 2. 逐序列读数（cm）

| 序列 | baseline | oracle（四臂最优） | 上限增益 | 该序列地板 | 增益是否超地板 |
|---|---:|---:|---:|---:|---|
| balloon | 3.247 | 3.247 | 0.000 | 0.50 | 否 |
| balloon2 | 5.484 | 5.318 | 0.166 | 0.72 | 否 |
| crowd | 2.235 | 2.235 | 0.000 | 0.57 | 否 |
| crowd2 | 2.259 | 2.259 | 0.000 | 1.88 | 否 |
| crowd3 | 1.530 | 1.530 | 0.000 | 0.56 | 否 |
| person_tracking | 11.310 | 7.947 | 3.363 | 3.83 | 否（差 0.47） |
| person_tracking2 | 10.404 | 10.404 | 0.000 | 1.89 | 否 |

逐臂（只取 `max(0, baseline − arm)` 的乐观上界，即假设门每次都对）：

| 臂 | 7 序列平均上限 | 超地板的序列 |
|---|---:|---|
| swbaonly | +0.401 | 无 |
| final | +0.463 | 无 |
| gate | +0.504 | 无 |

⇒ **"任何门控/调度设计的理论天花板不足以支撑可主张的贡献"这条判断，在逐序列地板
口径下依然成立**，且不再依赖任何单一常数。

## 3. 一处需要如实登记的边界

`person_tracking` 的地板 3.830 cm 本身是**三套估计里最保守的那个**（E2 逐臂配对 sd 的最大值，
来自 swbaonly 臂）。按 §3.2 (a′) 的两值并陈要求，这里给出其余三种取法：

| 取法 | 值 (cm) | oracle 增益 3.363 是否超地板 |
|---|---:|---|
| E2 swbaonly（最保守，= 采用值） | 3.830 | 否（差 0.47） |
| E2 final | 2.458 | **是**（+0.91） |
| E2 gate | 3.033 | **是**（+0.33） |
| E3 合并配对 (df=6) | 1.796 | **是**（+1.57） |

⚠ **注意 §1 的乐观句**：pt1 一行写的是"增益 3.363 < 地板 3.83"——这用的是最保守地板；
按本节的其余取法该行会翻转。§1 的表按"地板 = 最保守值"的统一口径写，此处（§3）
才是判定级细节。关闭结论的成立不依赖 pt1 这一行的翻转与否（理由见下）。

**所以 pt1 上"oracle 不超地板"这一条不是稳健的**——它取决于地板取法。
但**这不改变关闭结论**，原因独立于地板：

1. oracle 上限本身就是**不可实现的**（要求每个序列上都提前知道该不该开 SWBA）；
2. 即使取最宽松的地板（E3 = 1.796），可达上限也只覆盖 pt1 一个序列，其余 6 个序列上限
   全在各自地板内（balloon2 的 +0.17 也不超 0.72）；
3. 全 7 序列 SWBA-only **显著更好 0 条 / 显著更差 2 条**（配对 t 检验，与地板取法无关）。

⇒ 正确的表述顺序是：**先看显著性与符号分布（0 更好 / 2 更差），再看 oracle 上限；
后者在 pt1 上的稳健性有保留，但它的作用只是"封死新门控设计"这一支，而这一支已被
第 1、3 条同时封死。**

## 4. 复现

```bash
PY=/data/conda_envs/monogs-ours/bin/python
$PY scripts/paper3_bpw/derive_seq_floors.py \
  --out-json /tmp/floors.json
$PY - <<'EOF'
import json
d=json.load(open('results/paper2_fulltable/evidence/manifest_r33.json'))
F={k:v['floor_cm_conservative'] for k,v in json.load(open('/tmp/floors.json'))['per_sequence'].items()}
arms=d['arms']; seqs=sorted(arms['baseline'])
m={a:{s:sum(p['full_cm'] for p in arms[a][s]['per_seed'])/3 for s in seqs} for a in arms}
for a in ('swbaonly','final','gate'):
    g=[max(0.0, m['baseline'][s]-m[a][s]) for s in seqs]
    print(a, 'mean %+.4f' % (sum(g)/len(g)),
          'over-floor:', [s for s,x in zip(seqs,g) if x >= F[s]])
EOF
```

## 5. 本文件不主张什么

- 不主张 pt1 上 SWBA 有害（n=3 不可判，见 `NOTES.md` 关闭节第 (2) 条）；
- 不为 BPW 族辩护（其失败依据是三 seed 3/3 同向退化 + 3/3 高斯膨胀 + 逐帧块自助，
  与地板口径无关）；
- 不改写任何历史判决书。
