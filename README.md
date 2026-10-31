# RoGS-Densify

**动态场景 3D 高斯地图的时间感知致密化策略**（研究内容三 / 论文 3，进行中）。

在动态场景 3DGS-SLAM（RoGS-SLAM 平台，见[继承说明](#继承的平台)）之上，研究地图**在线
生长过程中的致密化决策**：每个 densify 事件该把预算花在哪些高斯上。当前机制形态为
**FDose**（冻结剂量计划：从 k0 臂 trace 冻结逐事件剂量 K_i，G/S 臂用不同选点键消费同
一份外生计划）。研究状态与判据见 `paper3/PREREGISTRATION.md` 与 `paper3/results/evidence/`。

> 三仓库关系：`RoGS-SLAM`（论文1，可靠观测）→ `RoGS-Map`（论文2，地图表示与维护）→
> 本仓库（论文3，地图生长）。本仓库的实验臂继承论文1 的完整方法作为基线平台。

## Installation

```bash
git clone --recursive https://github.com/BinGO620/RoGS-Densify.git
cd RoGS-Densify
./setup_env.sh        # conda env + 编译两个 CUDA 扩展 + 下载数据集
conda activate rogs-densify
```

要求：CUDA 11.8 工具链；GPU ≥ 6GB（论文数字产自 RTX 3090）。

## Usage

```bash
# 单跑一臂（person_tracking 序列，580 帧 ≈ 34 min on RTX 2060）
python slam.py --config configs/experiments/paper3_bpw/bpw_off_person_tracking.yaml --seed 0 --eval

# 冒烟（40 帧）
python slam.py --config configs/experiments/paper3_bpw/bpw_off_person_tracking.yaml --seed 0 --eval --max-frames 40

# FDose 三段式（stage1 计划源 → freeze 冻结剂量计划 → stage2 两机制臂）
bash scripts/paper3_bpw/run_fdose_l1.sh stage1
bash scripts/paper3_bpw/run_fdose_l1.sh freeze
bash scripts/paper3_bpw/run_fdose_l1.sh stage2

# 判据（正式批必须 --require-done）
python scripts/paper3_bpw/check_fdose_gate.py --runs <run 目录> --require-done
python scripts/paper3_bpw/judge_fdose.py --runs <显式 run 清单 JSON>

# 门禁测试（105 个）
pytest tests/densification tests/paper3_bpw tests/test_config_valid.py -q
```

## 配置与实验臂

配置 = YAML 继承链：`configs/rgbd/tum/base_config.yaml`（全默认+全开关，默认关闭）
→ `configs/rgbd/bonn/{base_config,<seq>}.yaml`（数据/标定）→ `method_from
configs/experiments/combined_prune/method.yaml`（论文1 方法主干，见继承说明）→
`configs/experiments/paper3_bpw/<arm>.yaml`（**臂间只差 `SelectiveDensification` 块**）。

| 臂 | 机制 | 配置 |
|---|---|---|
| off | 预算匹配致密化（参考实现，选中集=梯度阈值集） | `bpw_off_person_tracking.yaml` |
| on / negctl | BPW（持久性加权，Phase 0 已过） | `bpw_{on,negctl}_person_tracking.yaml` |
| k0 / G / S | FDose（计划源 / 梯度键 / 稀疏键） | `fdose_{k0,G,S}_person_tracking.yaml` |

## 继承的平台（论文1 方法，已冻结）

本仓库的运行主干包含论文1（MMM 2027, RoGS-SLAM）的四个方法组件，作为所有实验臂的
共同基线平台，`method.yaml` 中默认开启：K 统一关键帧覆盖（`DynamicKeyframe`）、
R 鲁棒重加权（`RobustTracking`）、L 可靠性信号（`ReliabilitySignal`，光流一致性）、
D lineage 生命周期（`DeferredCommit`）+ 可选语义掩码（`SemanticMask`）。
这些组件**属于论文1，本仓库不修改**；其方法说明见 RoGS-SLAM 仓库。

## Project Structure

```
slam.py                  # 唯一入口（--config/--seed/--eval/--max-frames）
utils/                   # SLAM 核心 + 机制模块（裁剪与修改清单见 PROVENANCE.md）
gaussian_splatting/      # 3DGS 渲染器（MonoGS 派生）
configs/                 # 数据集配置 + 实验臂
scripts/paper3_bpw/      # 批跑 runner + 判据机（judge/check/plan）
tests/                   # 门禁测试（mechanism 层 CPU 单测）
results/paper3_bpw/      # 判据小件（逐 run CSV/JSON/config）+ evidence/
paper3/                  # 预注册（PREREGISTRATION/PROBLEM）+ 审查证据
submodules/              # diff-gaussian-rasterization-w-pose + simple-knn（pin SHA）
```

## Provenance

本仓库由 monogs-ours@`31b0f0367` 按依赖闭包裁剪重建：复制清单、删改明细、验证记录见
[PROVENANCE.md](PROVENANCE.md)。

## Acknowledgements

Built on [MonoGS](https://github.com/muskie82/MonoGS) and
[3D Gaussian Splatting](https://github.com/graphdeco-inria/gaussian-splatting).
