# RoGS-Densify

> **Status: inactive since 2026-11-27.** This snapshot belongs to an earlier line
> of research content 3 — temporal-aware densification for dynamic 3DGS maps.
> That line was stopped after the arm-level effect proved to lie below the
> measurement floor of the available hardware: repeated runs at an identical
> configuration and seed differed by up to **96.8%** in terminal map size, and
> enabling the full PyTorch determinism suite still left **65.3%** divergence.
> At that resolution, arm-to-arm differences of the size the mechanism was meant
> to produce are not measurable, so the line was closed rather than continued.
>
> The current research content 3 is
> [**RoGS-Takeover**](https://github.com/BinGO620/RoGS-Takeover), which addresses
> cross-session map takeover through a lifecycle state consistency contract.
>
> This repository is kept as a record of the exploration — the instrumentation,
> the regime probes, and the dose-frontier measurements — not as an active
> codebase. The corresponding research records remain in the private source
> repository.

**Temporal-aware densification for dynamic 3D Gaussian maps** (research content 3,
earlier line; stopped 2026-11-27).

Built on a dynamic-scene 3DGS-SLAM platform (RoGS-SLAM; see
[the inherited platform](#inherited-platform-paper-1-method-frozen)), this work
studies the **densification decisions made while a map grows online**: for each
densify event, which Gaussians should receive the budget. The current mechanism
is **FDose** — a frozen dose plan that freezes per-event doses `K_i` from a k0-arm
trace, then has the G and S arms consume the same exogenous plan through
different selection keys. Study status and criteria are in
`paper3/PREREGISTRATION.md` and `paper3/results/evidence/`.

> Three-repo relation: `RoGS-SLAM` (paper 1, reliable observations) →
> `RoGS-Map` (paper 2, map representation and maintenance) → this repo
> (paper 3, map growth). This repo's experiment arms inherit paper 1's full
> method as their baseline platform.

## Installation

```bash
git clone --recursive https://github.com/BinGO620/RoGS-Densify.git
cd RoGS-Densify
./setup_env.sh        # conda env + build two CUDA extensions + download datasets
conda activate rogs-densify
```

Requirements: CUDA 11.8 toolchain; GPU ≥ 6 GB (paper numbers were produced on an
RTX 3090).

For a full step-by-step walkthrough — requirements, CUDA checks, environment,
dataset download, the FDose three-stage pipeline, judges, and the test suite —
see **[REPRODUCING.md](REPRODUCING.md)**.

## Usage

```bash
# One arm (person_tracking, 580 frames, ~34 min on an RTX 2060)
python slam.py --config configs/experiments/paper3_bpw/bpw_off_person_tracking.yaml --seed 0 --eval

# Smoke test (40 frames)
python slam.py --config configs/experiments/paper3_bpw/bpw_off_person_tracking.yaml --seed 0 --eval --max-frames 40

# FDose three stages (stage1 plan source -> freeze -> stage2 two mechanism arms)
bash scripts/paper3_bpw/run_fdose_l1.sh stage1
bash scripts/paper3_bpw/run_fdose_l1.sh freeze
bash scripts/paper3_bpw/run_fdose_l1.sh stage2

# Judges (a formal batch must pass --require-done)
python scripts/paper3_bpw/check_fdose_gate.py --runs <run-dir> --require-done
python scripts/paper3_bpw/judge_fdose.py --runs <explicit-run-list.json>

# Gates (105 tests)
pytest tests/densification tests/paper3_bpw tests/test_config_valid.py -q
```

## Configuration and experiment arms

Config = a YAML inheritance chain: `configs/rgbd/tum/base_config.yaml` (all
defaults and switches, all off) → `configs/rgbd/bonn/{base_config,<seq>}.yaml`
(data/calibration) → `configs/experiments/combined_prune/method.yaml` (paper 1's
method core; see the inherited-platform section) →
`configs/experiments/paper3_bpw/<arm>.yaml` (**arms differ only in the
`SelectiveDensification` block**).

| Arm | Mechanism | Config |
|---|---|---|
| off | budget-matched densification (reference; selected set = gradient-threshold set) | `bpw_off_person_tracking.yaml` |
| on / negctl | BPW (persistence weighting; Phase 0 passed) | `bpw_{on,negctl}_person_tracking.yaml` |
| k0 / G / S | FDose (plan source / gradient key / sparse key) | `fdose_{k0,G,S}_person_tracking.yaml` |

## Inherited platform (paper 1 method, frozen)

This repo's runtime core contains paper 1's (MMM 2027, RoGS-SLAM) four method
components as the common baseline platform for all experiment arms, enabled by
default in `method.yaml`: **K** unified keyframe coverage (`DynamicKeyframe`),
**R** robust re-weighting (`RobustTracking`), **L** reliability signal
(`ReliabilitySignal`, optical-flow consistency), **D** lineage lifecycle
(`DeferredCommit`), plus an optional semantic mask (`SemanticMask`). These
components **belong to paper 1 and are not modified here**; for the method
description see the RoGS-SLAM repository.

## Project Structure

```
slam.py                  # single entry point (--config/--seed/--eval/--max-frames)
utils/                   # SLAM core + mechanism modules (pruning/edits in PROVENANCE.md)
gaussian_splatting/      # 3DGS renderer (MonoGS-derived)
configs/                 # dataset configs + experiment arms
scripts/paper3_bpw/      # batch runners + judges (judge/check/plan)
tests/                   # gates (mechanism-layer CPU unit tests)
results/paper3_bpw/      # criterion artifacts (per-run CSV/JSON/config) + evidence/
paper3/                  # pre-registration (PREREGISTRATION/PROBLEM) + review evidence
submodules/              # diff-gaussian-rasterization-w-pose + simple-knn (SHA-pinned)
```

## Testing

```bash
pytest tests/densification tests/paper3_bpw tests/test_config_valid.py -q
# 316 passed
```

## Provenance

This repository was rebuilt from monogs-ours@`31b0f0367` by dependency-closure
pruning; the copy list, deletions, and verification record are in
[PROVENANCE.md](PROVENANCE.md).

## Acknowledgements

Built on [MonoGS](https://github.com/muskie82/MonoGS) and
[3D Gaussian Splatting](https://github.com/graphdeco-inria/gaussian-splatting).

## License

Released for **non-commercial research and evaluation use only**, inherited from
the Inria/MPII Gaussian-Splatting License that covers the rasterizer submodule.
See [LICENSE](LICENSE) for the combined terms and the per-component table.

## Citation

If you use this code, please cite the paper — see [CITATION.cff](CITATION.cff).
