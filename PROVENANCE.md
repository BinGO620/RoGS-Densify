# PROVENANCE — how this repository relates to monogs-ours

- **Source**: `/data/monogs-ours` @ `d0cddb9f7` (branch `feat/adaptive-itr`; 2026-11-10
  back-port: E-axis L2 stop-loss closure + F-axis novelty evaluation node). Previous
  baselines: `1b9e3fff7` (2026-11-03, FDose n=6 closure) and before that `31b0f0367`
  (2026-10-31). monogs-ours itself is **never split or modified**; it is kept as the
  backup repository.
- **How it was built**: manifest copy (copy list) from the source → subtraction
  (removed paper-2-specific mechanisms) → verification.
  Rebuild command: `python /data/monogs-export/copy_by_manifest.py --manifest
  /data/monogs-export/manifests/rogs_densify.yaml --dst <new-dir>`, then replay the
  surgical edits from the table in this file.

## Organization principles

1. Decoupling by subtraction, not rewriting: only delete files and branches; never
   rename or restructure `slam_frontend/slam_backend`.
2. Layout matches monogs-ours: any file can be diffed byte for byte against the
   backup repository.
3. "This paper's code" = the two tables below, listed explicitly.
4. Same-origin core: the shared core files of RoGS-SLAM / RoGS-Map / RoGS-Densify
   come from the same source commit; cross-repo `diff -r utils/` differences = each
   paper's mechanism differences.
5. Explicit inheritance: paper 1's (MMM 2027) mechanism modules stay in this repo as
   the common baseline platform for the experiment arms (enabled by default in
   `combined_prune/method.yaml`); this repo does not modify them.
6. The config inheritance chain is kept as-is (`inherit_from`/`method_from`).
7. Criterion artifacts live in-repo with the code; tests are split into mechanism
   (CPU unit) and pipeline (smoke) layers.

## Table 1: this paper's (paper 3) mechanism files

| File | Role |
|---|---|
| `utils/densification_selection.py` | Densification selection kernel: three forms — BPW (`persistence_budget`) / CGB (`coverage_gap`, judged DESIGN-INVALID) / FDose (`frozen_dose`) |
| `utils/selective_densification.py` | Predecessor/fallback path (the `SelectiveDensification` static_prob ledger form, Phase 1) |
| Two dispatch sites in `utils/slam_backend.py` | `compute_coverage_gap_knobs`/`compute_frozen_dose_knobs`/`compute_per_gaussian_knobs` wiring (core edits; see below) |
| `configs/experiments/paper3_bpw/` | 21 arm configs (bpw off/on/negctl, cgb g0/g1, fdose k0/G/S, p0 sweep) |
| `configs/experiments/combined_prune/method.yaml` | Method core (shared with paper 1; the `method_from` target) |
| `scripts/paper3_bpw/` | Runners (run_fdose_l1/run_three_arms/run_p0_sweep/...) + judges (judge_fdose/check_fdose_gate/make_dose_plan/judge_p0a/judge_cgb_l1/check_cgb_gate/derive_seq_floors/summarize_three_arms etc.) |
| `tests/densification/`, `tests/paper3_bpw/` | Three-form selection unit tests + judge gates (40+65 tests) |
| `results/paper3_bpw/` | Criterion artifacts (per-run tracking/mapping/efficiency CSV, config.yml, summary/trj_final/stats_final JSON, console.log, .done, FDose selection_trace) |
| `paper3/PREREGISTRATION.md`, `paper3/PROBLEM.md`, `paper3/results/evidence/` | Pre-registration (criteria locked first), problem definition, review/verdict evidence (67 items) |

## How the surgery is executed (scripted since 2026-11-03)

Table 2's subtraction surgery is **no longer replayed by hand**:
`/data/monogs-export/manifests/rogs_densify.yaml` has a `delete:` section listing the
9 CVM-only modules and an `overlay:` section listing the post-surgery versions of
three core files
(`/data/monogs-export/overlays/{slam.py,utils/slam_backend.py,utils/slam_frontend.py}`).
`copy_by_manifest.py` applies the overlay last ⇒ one command rebuilds **including the
surgery**.

**Evidence (measured 2026-11-03)**: before upgrading we ran a pure-superset copy; all
9 modules came back and the core surgery (slam.py 61 lines / backend 190 / frontend
43) was overwritten — the same root cause as the 2026-11-01 RoGS-Map incident.
After the fix, re-running gave `deleted=9`, 0 resurrected modules, and 0 residual
edits in all three core files.

**Intermediate files are not snapshotted (2026-11-03)**: FDose's
`results/paper3_bpw/**/fdose_*_selection_trace.csv` (23 files / 906 MB) are **no
longer tracked**. The criterion chain does not depend on them: since A4 each seed's
F3a′/share/pool baseline is frozen into the gate JSON and verdicts consume only gate
artifacts; the judge's R6/R7 are report-only and report an explicit `missing_trace`
when the trace is absent.
**Traceability**: the full set is kept at the same path in monogs-ours (single source
of truth); take it from the source repo if a recompute is needed.
(Verified 2026-11-03: after untracking, the judge still returns rc=0 inside the
snapshot repo and reproduces INCONCLUSIVE verbatim.)

**Maintenance rule**: if monogs-ours' three core files change for real, replay the
surgery per Table 2 to produce new overlays before back-porting; otherwise the
overlay will clobber the new changes.

## Table 2: changes to the core files (relative to the same-named monogs-ours files)

Purpose: remove the files and wiring of paper 2's (CVM2027) mechanisms. All deletions
are **default-off branches**, so the mainline (all paper-3 arms) behaves identically.

### slam.py

| Source lines | Removed |
|---|---|
| 41–47 | `loop_closure`/`dba_lite` top-level imports |
| 419–461 | P2b/DBA-oracle/DBA-v0/LoopClosure closing three-arm block (`dba_lite_oracle_enabled`/`dba_lite_enabled`/`loop_closure_enabled` branches) |
| 470–479 | DynPort causal-mask finalization after saving the final PLY (`dynport_causal_log`) |

### utils/slam_backend.py

| Source lines | Removed |
|---|---|
| 142 | `dba_lite` import |
| 1595–1601 | P2a DBA diagnostic block (start of `color_refinement`) |
| 1786–1787, 1794–1796 | DynPort comment and the `dynport_time_s`/`dynport_frames` keys in `save_timing_stats` |
| 1837–1850 | DynPort tracking-isolation block in `push_to_frontend` (dynamic-row opacity set to 0) |
| 1858–2008 | The four methods `_dynport_setup`/`_dynport_step`/`_dynport_fit`/`_dynport_sync_occ` |
| 204–208 | `__init__`'s `_dynport*` attributes |
| 2211–2213 | Main-loop `_dynport_step` call site |

### utils/slam_frontend.py

| Source lines | Removed |
|---|---|
| 52 | `swba` import |
| 413–415 | `__init__`'s Route B SWBA initialization |
| 2928–2962 | Route B SWBA health gate and `on_new_keyframe` call block in `run()` |

## Removed modules (9, paper-2/CVM2027 only)

`utils/{swba, loop_closure, place_recognition, mast3r_verify, dba_lite,
dyn_port_buffer, dyn_port_online, dyn_port_offline, dynport_causal_log}.py`

(They remain in the RoGS-Map repository.)

## Retained decisions (recorded honestly)

1. **Default-off platform switch set** kept rather than deleted: `transient_map`/
   `object_transient`/`mope_layer`/`obsdebt`/`occupancy_memory`/`depth_reanchor`/
   `flow_mask*`/`mask_quality`/`mask_stability`/`causal_render_log`/`mapping_probe`/
   `oracle_pose`/`gtmc_mask`/`bootstrap_vo`/`full_frame_pose`/`coarse_pose`/
   `visibility_window`/`reliable_tracking`/`tri_reliability`/`alpha_lifecycle` etc.
   Rationale: they are part of `base_config.yaml`'s switch surface and are woven into
   the core through top-level imports, i.e. part of the frozen platform; all are
   default-off with zero behavioral impact on any paper-3 arm. Deleting them has low
   payoff and high surgical risk.
2. **`configs/rgbd/`** keeps only the sequences paper 3 uses (bonn:
   base/person_tracking/balloon; tum: base_config); other sequence configs are not
   included.
3. **Criterion-artifact selection**: CGB's (judged DESIGN-INVALID) and BPW's
   `*_selection_trace.csv` in `results/paper3_bpw` (about 165 MB of per-event dumps)
   are not included; their verdicts/summaries remain in
   `paper3/results/evidence/`. All selection traces of the live FDose line are kept.
4. monogs-ours' development-management files
   (DISCIPLINE/DECISIONS/NOTES/LOG/PITFALLS, .zcode/.claude, health_check, the other
   experiment families' configs/scripts/tests/results, papers/, biyelunwen/) are never
   carried over.

## Numeric verification matrix (paper 3 has no published table; verification = gates + equivalence)

| Item | How | Status |
|---|---|---|
| Mechanism selection logic | 40 CPU unit tests in tests/densification (BPW/CGB/FDose three forms) | all green |
| Judges | 65 gates in tests/paper3_bpw (judge/check/plan contracts) | all green |
| FDose 40-frame smoke | all three arms pass; criteria from the same source as `fdose_gate_smoke_2026-10-31.json` (pre-registration evidence ships with the repo) | pass |
| Pruning equivalence | smoke A/B vs the clean source at monogs-ours@31b0f0367 (see below) | pass |
| Full 580 frames | not run (D2-011 awaiting the user's answer + G4 closure; see PREREGISTRATION) | — |
| Config parity | 27 YAMLs byte-identical to monogs-ours@31b0f0367 (parity check 2026-11-01) | ✓ |

## Verification record

| Item | Result |
|---|---|
| AST import closure | 95 files checked, nothing missing (`closure_check.py`) |
| `py_compile` slam.py / slam_frontend.py / slam_backend.py | pass |
| `pytest tests/densification tests/paper3_bpw tests/test_config_valid.py` | **105 passed** (monogs-ours baseline 96 + config validation) |
| Submodule pins | `diff-gaussian-rasterization@43e21bff`, `simple-knn@44f764299` (consistent with the monogs-ours history and upstream MonoGS) |
| 2060 smoke A/B (40 frames, bpw_off, seed 0) | pruned repo vs the clean reference at monogs-ours@31b0f0367: ATE RMSE 1.1688 vs 1.1718 cm (Δ = 0.003 cm ≈ 0.26%, CUDA-nondeterminism level, below the same-config cross-batch noise 0.18–0.62 cm); stats_final/per_frame_ape/tracking_raw all fields agree (only timestamps and noise-level decimal differences). **Subtraction did not change pipeline behavior** |
| **2026-11-10 back-port @ `d0cddb9f7`** | parity all same-origin · pytest **316 passed** · closure_check reports only the two **known tool false positives** (`gui`/`utils`, also reported for the clean source) · 40-frame smoke bpw_off seed0 in the pruned repo **1.1906 cm** vs the historical same-config reference 1.1682 cm (Δ = 0.0224 cm ≈ 1.9%, far below the same-config cross-batch noise band 0.18–0.62 cm) ⇒ equivalence passes · **surgery replayed**: the old overlay had expired (`adaptive_itr` zero hits; slam_backend had grown 156 lines since 11-03), so it was replayed by **exact delete blocks** (not line numbers) — 14 blocks all matched exactly once, diff line counts stayed 61/190/43 (matching Table 2) · **manifest fix**: added the 9 bonn sequence configs (previously only pt/balloon ⇒ gate ② hit 20 FileNotFoundError) + the criterion-key registry script `scripts/02_analysis/prereg_criterion_keys.py` · newly carried over: the E axis (adaptive_itr implementation/criterion chain/33 unit tests/L1+L2 verdicts/F-axis novelty) and the MissStreak/MaskStat A1/E2 P1 mechanisms |
| **2026-11-03 back-port @ `1b9e3fff7`** | parity all same-origin (25/25 configs) · pytest **121 passed** · 40-frame smoke bpw_off in the pruned repo **1.1818 cm** vs the clean-source reference 1.1718 cm (Δ = 0.010 cm ≈ 0.85%, below the cross-batch noise band 0.18–0.62 cm) ⇒ equivalence passes · closure_check reports `gui`/`utils` as **tool false positives** (also reported for the clean source; a package-name resolution issue) · submodule pins stay `43e21bff`/`44f76429` · newly carried over: FDose n=6 verdict artifacts and the seeds 3/4/5 run products |

## Archiving policy (registered 2026-11-04; user instruction, applies to every repo)

- **Keep only the latest in the working area**: outdated versions, drafts, and
  historical snapshots all move into this repo's `archive/` (archive in place, named
  `{semantic}_{YYYY-MM-DD}`), never left scattered at the top level.
- **Archive ≠ delete**: archived items are evidence keys; ledger pointers are not
  rewritten; every archive location gets a `README.md` and is registered in the
  in-repo index.
- **Repo independence**: experiments are always run back in monogs-ours; this repo
  only takes "criterion-confirmed" result snapshots (the four-step sync is in
  monogs-ours `/data/master-thesis/WORKFLOW.md`). This repo carries its own gates and
  PROVENANCE, so it can be re-verified without the monogs-ours working area.
- **Milestone-triggered sync**: only re-run the manifest and full gates and update
  PROVENANCE at milestones (verdict landed, submission, etc.); do not sync routinely
  (to avoid snapshot drift).
