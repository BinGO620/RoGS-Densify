# FDose 预注册 Amendment A2（2026-10-31，**看全长数据前**）

**上位**：`prereg_fdose_2026-10-31.md`（判据本体）+ `prereg_fdose_amendment_a1_2026-10-31.md`（F3 拆分）
**性质**：本件**收窄剂量口径**并**补一条必须并陈的读数**。依据 = 40 帧冒烟 trace 的复核 +
`slam-critic` G3 审查的逐条核验（`critic_verify_fdose_g3_2026-10-31.md`）。
**跑全长前完成**：写于任何 580 帧 run 开始前。

---

## 1. 为什么要改：「剂量」在 FDose 里不是一个数，是三个

FDose 控住的是**每事件注入的源点数 K_i**（F1 逐事件严格相等）。但一个被选中的源点
经 densifier 后产生的**新原语数**取决于它走 clone 还是 split：

| 操作 | 条件 | 新原语 |
|---|---|---|
| clone | `max_scale ≤ percent_dense · scene_extent` | **+1** |
| split | `max_scale > percent_dense · scene_extent` | **+2**（父点被删，净 +1） |

`percent_dense` 被 FDose 固定为 0.01（D8 门禁守护），但 **`scene_extent` 是站点相关的**：

| 站点 | `scene_extent` | 界 | 出处 |
|---|---|---|---|
| `initialize_map`（`mapping_iteration % init_gaussian_update`） | `cameras_extent × init_gaussian_extent` = 6.0 × 30 = **180** | **1.80 m** | `slam.py:324` + `slam_backend.py:284-286` |
| `map()`（`iteration_count % gaussian_update_every`） | `cameras_extent × gaussian_extent` = 6.0 × 1.0 = **6.0** | **0.06 m** | `slam_backend.py:306-308` |

⇒ 冒烟实测（FDose 两臂，17 事件，源点数严格相等 23,979）：

| 口径 | G | S | 比 |
|---|---:|---:|---:|
| 源点数 Σsel | 23,979 | 23,979 | **1.0000** |
| gross 原语（clone+1 / split+2） | 24,416 | 24,589 | **1.0071（+0.71%）** |
| └ split 占比 | 1.82% | 2.54% | — |
| 40 帧终态净高斯数 `online_num_gaussians` | 18,019 | 18,516 | **1.028（+2.8%）** |

**读法**：
- 源点数相等**不**等于 gross 原语相等（+0.71%），也不等于净存活数相等（+2.8%）。
- 后者大于前者 ⇒ 差额来自 **prune 的差异**（S 臂选出的点更抗剪）。
- 按同族剂量斜率 **0.025–0.810 cm/1%**（`P3-D2-009` 树内四对）折算：
  gross +0.71% ⇒ **+0.02 ~ +0.57 cm**；net +2.8% ⇒ **+0.07 ~ +2.3 cm**（均低于 n=3 MDE 3.70 cm）。
  ⇒ **不构成判死**，但**必须并陈**，且判决不得再写「剂量完全外生」。

> ⚠ 登记一处**审查方算错、我复核反驳**的经过（保留痕迹）：
> `slam-critic` G3 原报此通道为 **+5.3%**（判致命），因为它用了 init 界 **0.30 m**
> （只算 `percent_dense × init_gaussian_extent`，漏了 `cameras_extent = 6.0`）。
> 正确界 1.80 m 下 init 站点 11,759 个被选点里 `max_scale > 1.80` 的 **= 0**，
> 其「29.2% split」几乎全是虚假 split。量级错约 7 倍 ⇒ 致命降为**必报残余通道**。
> 详见 `critic_verify_fdose_g3_2026-10-31.md` §一。

## 2. 修订内容

### 2.1 剂量三口径并陈（硬性）

判决书与 gate 报告必须**同时**给出：

1. **源点数 Σsel**（F1 的落点，逐事件严格相等）
2. **gross 原语数**（`check_fdose_gate.py::gross_primitives`，按站点正确界重算）
3. **净存活数**（`efficiency_raw.csv` 的 `online_num_gaussians` / `refined_num_gaussians`，
   两列并陈 —— CGB 教训：8 臂中 2 臂两列差 +5,000）

任一缺列 ⇒ 判决不完整。**不得**只用第 1 项就声称「剂量相等」。

### 2.2 分站点上报（硬性）

两个 densify 站点共用同一个事件序数（prereg §2 已补），且**截断只砍尾部 map 事件**：

| 站点 | 冒烟 `ord` 段 | 剂量占比 |
|---|---|---|
| init | `0..10` | **49.0%**（11,759 / 23,979） |
| map | `11..` | 51.0% |

⇒ 报告必须分列 `dose_init` / `dose_map`。**已知后果**：`N_plan=57` 的截断把 map 段的
尾部整体丢掉，而 init 段 100% 保留 —— 所以**可达域 1.35× 是在全程剂量下算的**，
截断后 map 段权重被压低。这条在判决里必须写明（不是缺陷，是适用范围）。

### 2.3 F2 的 `covered` 子句收紧

原 `covered >= min(len(plan_k), 1)` 形同虚设（只要 1 个事件就过）。改为
`covered >= len(plan_k)`：**两臂都必须真的覆盖到计划长度**。

### 2.4 F3a 的三口径

`sparsity_profile` 同时给：事件比值的均值（主判据，1.21×）、事件均值的均值（1.206×）、
**点数加权 pooled（1.181×）**。门 1.15 对**最保守**的 pooled 口径余量 0.03 —— 报告里
必须注明用的是哪个口径，**不得**只报有利的那个。

> 另记一条审查方给出、我采纳的**地板读数**：自然 null（k0 自计划 γ=0 vs G 计划 γ=0，
> 同键、只差本臂自己的地图）的稀疏度比 = **0.9970** ⇒ 跨臂地图漂移本身几乎不动这个量，
> 所以 F3a 的 1.21 里 1.20 是 γ 的信号、1.00 是地板。

### 2.5 平局确定性（补测试 + 改实现）

prereg §7 曾声称门禁含「平局确定性」测试，实为 0 命中（审查 P35 型）。
补：`select_topk_stable()`（stable argsort ⇒ 同键按 `gauss_idx` 升序）+ D13 测试。
这**改变了一次实现**（原用 `torch.topk(sorted=False)`，平局顺序未定义），
对 k0 自计划的等价性影响可忽略（实测 k0 trace 重放 19/19 仍逐位相同）。

## 3. 不改的东西

- §6 六条出口的阈值、顺序、MDE 表**不变**。
- F1/F3a/F4 的判定逻辑不变（F1 仍逐事件严格相等；F3a 仍 1.15× 均值 + 60% 事件 >1.10）。
- §8「不主张两臂在索引空间可比」「不主张剂量完全外生」的边界不变（本件只是把
  「剂量」拆成三个可核的数）。

## 4. 反悔方式

本件与判据机同步（`check_fdose_gate.py` 的 `gross_primitives` / `per_site_dose` /
`select_topk_stable`，测试 K10/K11/D13）。撤销 = `git revert` 本件提交；届时剂量只剩
源点数一个口径 —— **不建议**（会重犯 CGB「单列引用被末端竞态骗」的错）。
