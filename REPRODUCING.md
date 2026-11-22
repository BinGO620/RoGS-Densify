# Reproducing Paper 3 (RoGS-Densify)

Step-by-step instructions to reproduce the results of the temporal-aware
densification study (research content 3; target venue *The Visual Computer*).

The question is where the densification budget goes: for each densify event,
which Gaussians should receive it. The current mechanism is **FDose** — a frozen
dose plan that freezes per-event doses `K_i` from a k0-arm trace, consumed by the
G and S arms through different selection keys.

Everything runs from this repository alone. The run pipeline includes the
Paper-1 method components (K/R/L/D + optional semantic mask) as the common
baseline platform, enabled by default in `method.yaml`. Those components belong
to Paper 1 and are not modified here.

---

## 0. Requirements

| Item | Requirement |
|---|---|
| OS | Linux x86_64 |
| GPU | NVIDIA, ≥ 6 GB VRAM (paper numbers produced on RTX 3090) |
| Toolchain | CUDA 11.8 (`nvcc`), `gcc`/`g++`, `git` |
| Conda | Miniconda or Anaconda |
| Disk | ~15 GB for the Bonn sequences |
| Python | provided by the conda environment (3.10) |

---

## 1. Clone with submodules

```bash
git clone --recursive https://github.com/BinGO620/RoGS-Densify.git
cd RoGS-Densify
```

Or, if already cloned:

```bash
git submodule update --init --recursive
git submodule status      # both lines must start with a commit hash
```

---

## 2. Create the environment

```bash
./setup_env.sh
conda activate rogs-densify
```

`setup_env.sh` creates the `rogs-densify` conda environment, builds the two CUDA
extensions, and downloads the Bonn dataset if missing. It is idempotent.

By hand:

```bash
conda env create -f environment.yaml
conda activate rogs-densify
python -m pip install ./submodules/simple-knn ./submodules/diff-gaussian-rasterization
bash scripts/download_bonn.sh
```

Smoke-check:

```bash
python -c "import torch, diff_gaussian_rasterization, simple_knn._C; print(torch.__version__, torch.cuda.is_available())"
```

---

## 3. Smoke test (fast)

```bash
python slam.py --config configs/experiments/paper3_bpw/bpw_off_person_tracking.yaml \
  --seed 0 --eval --max-frames 40
```

A 40-frame run is a pipeline check, not a paper number.

---

## 4. Single arm, full length

```bash
# person_tracking, 580 frames, roughly 34 min on an RTX 2060
python slam.py --config configs/experiments/paper3_bpw/bpw_off_person_tracking.yaml --seed 0 --eval
```

Arms differ **only** in the `SelectiveDensification` block. The available arms:

| Arm | Mechanism | Config |
|---|---|---|
| off | budget-matched densification (reference; selected set = gradient-threshold set) | `bpw_off_person_tracking.yaml` |
| on / negctl | BPW (persistence weighting; Phase 0 passed) | `bpw_{on,negctl}_person_tracking.yaml` |
| k0 / G / S | FDose (plan source / gradient key / sparse key) | `fdose_{k0,G,S}_person_tracking.yaml` |

---

## 5. FDose three-stage pipeline

FDose is deliberately exogenous: doses are frozen from the k0 arm, then consumed
by the G and S arms. Run the stages in order:

```bash
bash scripts/paper3_bpw/run_fdose_l1.sh stage1    # k0 trace -> per-event dose plan
bash scripts/paper3_bpw/run_fdose_l1.sh freeze    # freeze the plan
bash scripts/paper3_bpw/run_fdose_l1.sh stage2    # G and S arms consume the same plan
```

`run_fdose_l1.sh` resolves the repository root from its own location. To point it
at a different checkout, set `MONOGS_REPO`; to use a different interpreter, set
`MONOGS_PY`.

---

## 6. Judging

The judges are fail-closed: they exit non-zero rather than emit a number when an
input is missing.

```bash
# formal batch must pass --require-done (guards against half-finished runs)
python scripts/paper3_bpw/check_fdose_gate.py --runs <run-dir> --require-done

# per-run judgement from an explicit run list
python scripts/paper3_bpw/judge_fdose.py --runs <run-list.json>
```

Criterion keys are registered in `scripts/02_analysis/prereg_criterion_keys.py`;
run it to confirm every key the pre-registration declares is actually produced:

```bash
python scripts/02_analysis/prereg_criterion_keys.py
# expect MISSING_TOTAL = 0
```

---

## 7. Run the test suite

```bash
pytest tests/densification tests/paper3_bpw tests/test_config_valid.py -q
```

Expected: 105 tests pass. These gate the mechanism layer on CPU.

---

## Reproducibility notes

- **Single-variable arms.** Every arm differs from its reference only in the
  `SelectiveDensification` block. Do not change the dataset config or the method
  block while comparing arms.
- **Instrument vs deployment protocol.** The instrumented configuration
  (single-threaded dataset and reliability paths plus deterministic rasterizer
  backward) and the async deployment configuration are never mixed. Same-config
  same-seed reruns are bitwise identical under the instrumented protocol;
  wall time and peak memory are not.
- **Budget is a cap, not an outcome.** The created-primitive count is a fixed
  per-run budget (`capped at 850,000`), binding in every run. It is a budget
  limit, not a measured result.
- **No accuracy-preservation claim.** The takeover cost is reported honestly;
  the paper does not claim accuracy parity.
- **What is not in this repo.** The closed exploration families (dose-response,
  adaptive-itr, device-floor probes, and others) are archived with their raw
  logs; they do not enter the paper's claims. Only the criteria that back the
  paper's tables are in the live paths.
- **No hidden dependency on other repos.** This repository does not read from
  the RoGS-SLAM or RoGS-Map checkouts. The triple-repo layout is a development
  history; each repo is independently runnable.

If a step fails, open an issue with the failing command, full error text,
`nvidia-smi`, `nvcc --version`, and `conda list | grep -E "torch|numpy"`.
