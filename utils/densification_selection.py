"""Phase 0 (2026-10-27): BPW — Budget-matched Persistence-Weighted densification.
Phase 1 (2026-10-30): CGB — Coverage-Gap Budget densification (BPW 之后的第 11 次尝试).

Specs: `paper3/results/evidence/phase0_mechanism_spec_2026-10-27.md` (BPW) and
`paper3/results/evidence/prereg_cgb_2026-10-30.md` (CGB).

The standard 3DGS densifier selects every Gaussian whose accumulated positional
gradient exceeds a fixed threshold; each selected *source point* is then cloned
(parent kept, +1 child) or split (parent replaced by 2 children, net +1). Both
branches are net +1 per selected source point, so the number of net-added
Gaussians for an event equals the number of selected source points. That is the
budget BPW holds fixed.

BPW changes WHICH source points are selected. Candidates are ranked by a
persistence-weighted evidence score instead of the raw mean gradient:

    e_i = accum_i / (denom_i + p0)

which is algebraically the mean gradient ``accum_i / denom_i`` shrunk towards
zero by ``p0`` pseudo-observations. Here ``denom_i`` is the per-Gaussian
observation counter maintained unconditionally by
``add_densification_stats`` (incremented every time the Gaussian is seen, reset
to zero on every densify event), so it measures "how many times has this
Gaussian been watched since it last grew". A barely-observed Gaussian is damped
regardless of how large its few-sample gradient happens to be; a repeatedly
observed one keeps its full mean gradient. This separates *placement* from
*budget*: the number of new Gaussians per event is identical to the reference
arm by construction, so any difference is attributable to where they were
created.

Why not ``static_obs_count``: that field is only maintained when the
``AlphaLifecycle`` block is active, which is off in the default configuration.
Relying on it would silently defect the mechanism (measured 2026-10-28: under
the default config the selector degenerated to an arbitrary index order). ``denom``
is maintained by the base densifier and needs no extra switch.

Budget definition (exact):

    P0     = { i : accum_i / denom_i >= tau_base }      # reference selection
    budget = |P0|                                        # net adds by the reference
    P      = { i : g_i >= tau_low * tau_base }           # widened candidate pool
    S      = the |budget| points of P with the largest e_i   (ties by index)

The pool must be strictly wider than P0: if P == P0, greedy acceptance takes
everything and BPW is an exact no-op. The placebo arm shares the widened pool and
the same |budget| and differs only in the ranking key, which is what isolates the
ranking signal from the budget.

Config (``SelectiveDensification`` block):
    enabled: true
    signal: "persistence_budget"
    p0: 8.0                    # half-saturation / prior pseudo-count (locked a priori)
    tau_low_factor: 0.5        # candidate pool = factor * base threshold
    placebo: false             # true -> rank by a deterministic permutation of e
    placebo_seed: 7

Entry points return ``None`` when inactive, so callers fall back to the original
scalar path exactly (bit-identical promise).

CGB in one paragraph: the reference selection is kept *entirely*, and a fixed
``floor(swap_frac * |ref_sel|)`` batch is added from the widened pool, ranked by
``mean_grad * sparsity ** gamma``. ``gamma=1`` rewards spatially sparse space,
``gamma=0`` is the same dose ranked by plain gradient -- a dose-matched control that
isolates placement from amount. This is deliberately NOT a re-ranking of a fixed
budget: BPW did that and the prescreen showed its weight is nearly independent of
gradient (Spearman 0.07), i.e. it mostly re-drew points noisily.

FDose (2026-10-31, path ② of P3-D2-009): CGB's "equal dose" only held for the 5%
increment -- the retained reference set was 95.2% of the injected dose and it was
exactly the part that forked between arms (dose and placement shared one feedback
loop). FDose removes the retained set and makes the *total* per-event count an
**exogenous plan**:``K_i`` comes from a frozen JSON file (built from a reference-arm
trace before any treated arm runs), and each arm picks exactly ``K_i`` points from its
own pool by ``mean_grad * sparsity ** gamma``. The dose can no longer depend on the
arm's own placement history, so pruning (``K_i`` below the arm's own ``|ref_sel|``) is
part of the design and must be reported per event. What this does NOT cut is the map
state: candidate sets still grow independently, so the estimand is "map difference
under the same exogenous dose", not "two arms on one map"
(spec: `paper3/results/evidence/prereg_fdose_2026-10-31.md`).
"""

import json
import os

import numpy as np
import torch

from utils.logging_utils import Log

from utils.selective_densification import get_sel_dens_config

DEFAULTS = {
    "enabled": False,
    "signal": "static_prob",
    "p0": 8.0,
    "tau_low_factor": 0.5,
    "placebo": False,
    "placebo_seed": 7,
    "budget_scale": 1.0,
    # --- coverage_gap (CGB, 2026-10-30) ---
    "swap_frac": 0.05,
    "gamma": 1.0,
    "sparsity_k": 6,
    # --- frozen_dose (FDose, 2026-10-31; path ② of P3-D2-009) ---
    "dose_plan_path": None,   # None => self-plan: K_i = |ref_sel| at this event
    "trace_pool": False,      # true => also dump unselected pool candidates (huge)
}


def get_bpw_config(config):
    """Merged BPW config with defaults (never mutates the input)."""
    cfg = dict(DEFAULTS)
    cfg.update(get_sel_dens_config(config) or {})
    return cfg


def bpw_active(config):
    """True only when the BPW signal is explicitly selected and enabled."""
    sel = get_sel_dens_config(config) or {}
    return bool(sel.get("enabled", False)) and str(sel.get("signal", "")) == (
        "persistence_budget"
    )


def cgb_active(config):
    """True only when the CGB signal is explicitly selected and enabled.

    Separate entry point from ``bpw_active`` on purpose: the two mechanisms must
    never run in the same event, and keeping distinct predicates means an arm
    labelled ``coverage_gap`` can never silently fall through to BPW's ranking
    (or to the scalar reference path) without that showing up as a wrong count in
    the ``[cgb]`` log line.
    """
    sel = get_sel_dens_config(config) or {}
    return bool(sel.get("enabled", False)) and str(sel.get("signal", "")) == (
        "coverage_gap"
    )


def fdose_active(config):
    """True only when the FDose signal is explicitly selected and enabled.

    Its own predicate, for the same reason ``cgb_active`` has one: an arm labelled
    ``frozen_dose`` that silently fell through to the scalar path would report a
    clean-looking run with an unused plan, and the only witness would be a
    zero-injection count in ``efficiency_raw.csv``.
    """
    sel = get_sel_dens_config(config) or {}
    return bool(sel.get("enabled", False)) and str(sel.get("signal", "")) == "frozen_dose"


def compute_sparsity(xyz, k=6):
    """Per-Gaussian spatial sparsity ``s = knn_k / median(knn_k)`` (>1 = sparse).

    ``xyz`` is an (N,3) tensor (any device); returns a float32 tensor on the same
    device. The k-th nearest-neighbour distance is the sparsity proxy: it is large
    exactly where the map has few neighbours, and it needs no length calibration
    (dividing by the median makes it a pure ratio, so no ``cell_size`` or scene
    extent has to be tuned per sequence).

    Why ``knn`` and not a voxel histogram: the two disagree in sign. A count of the
    3x3x3 voxel neighbourhood measures *occupancy* and is HIGH in dense areas, while
    ``knn`` is LOW there. Only the second one is a "reward sparse space" key, and
    the prescreen table this mechanism was designed against
    (`ranking_key_prescreen_2026-10-30.md`) was computed with ``knn``; a voxel count
    here would silently invert the mechanism.

    Deterministic (``cKDTree`` is exact for distinct points, ties broken by index)
    and read-only: this is a *ranking* input, never model state.
    """
    from scipy.spatial import cKDTree

    device = xyz.device
    pts = xyz.detach().to("cpu", torch.float64).numpy()
    n = int(pts.shape[0])
    if n < 2:
        return torch.ones(n, dtype=torch.float32, device=device)
    kk = int(min(max(1, int(k)) + 1, n))
    dist, _ = cKDTree(pts).query(pts, k=kk)
    knn = np.asarray(dist[:, -1], dtype=np.float64)
    med = max(float(np.median(knn)), 1e-9)
    return torch.from_numpy((knn / med).astype(np.float32)).to(device=device)


def compute_evidence(grads, persistence, p0):
    """Persistence-weight evidence e_i = g_i * p_i / (p_i + p0) (vector form)."""
    p0 = max(float(p0), 1e-6)
    p = persistence.clamp_min(0.0)
    return grads * p / (p + p0)


def compute_evidence_from_counts(accum, denom, p0):
    """Equivalent, numerically preferred form: accum / (denom + p0).

    ``accum``/``denom`` are the raw accumulators the reference densifier uses, so
    this avoids rebuilding the mean gradient only to multiply it back.
    """
    p0 = max(float(p0), 1e-6)
    return accum / (denom.clamp_min(0.0) + p0)


def select_budget_matched(evidence, pool, budget):
    """Pick exactly ``min(budget, |pool|)`` highest-evidence points from ``pool``.

    Returns a boolean tensor shaped like ``evidence``. Ties break by index via
    ``topk``'s stable ordering, so results are deterministic across reruns.
    """
    n = int(evidence.shape[0])
    accepted = torch.zeros(n, dtype=torch.bool, device=evidence.device)
    k = min(int(budget), int(pool.sum().item()))
    if k <= 0:
        return accepted
    masked = torch.where(pool, evidence, torch.full_like(evidence, float("-inf")))
    top = torch.topk(masked, k=k, largest=True, sorted=False).indices
    accepted[top] = True
    return accepted


def _selection_trace_dir(config):
    """Default-off selection-trace CSV path (diagnostic only; no data path uses it).

    Off unless ``SelectiveDensification.trace_selection: true``. Deterministic
    ``<save_dir>/bpw_selection_trace.csv``, where ``save_dir`` is the *run-scoped*
    ``Results.save_dir`` (timestamp dir) so a trace never collides across runs.
    The trace records, per densify event, the world positions of the source points
    the selector actually chose (accepted) vs those the reference arm would have
    chosen (ref_sel). Purpose: the Phase-0 autopsy showed the budget-matched arm
    re-ranked *placement* while the per-event net add was later largely reverted by
    prune; the trace is what lets us say WHERE the surviving choices were made
    without re-running with debuggers. CPU-only, appends per event.
    """
    if not bool(config.get("SelectiveDensification", {}).get("trace_selection", False)):
        return None
    save_dir = config.get("Results", {}).get("save_dir")
    if not save_dir:
        return None
    try:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "bpw_selection_trace.csv")
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "iter,kind,gauss_idx,x,y,z,mean_grad,denom,evidence,ref_grad_in_pool\n"
                )
        return path
    except OSError:
        return None


def compute_budget_matched_knobs(
    config,
    gaussians,
    base_grad_threshold,
    base_percent_dense,
    iteration_count=0,
    log_fn=None,
):
    """Return (grad_threshold_vec, percent_dense_vec) or None when inactive.

    Both vectors are (N,1). Accepted source points get threshold -1.0 (any
    non-negative gradient passes); all others get +inf. ``percent_dense`` stays
    at the reference value for every point by design: it must not move the
    clone/split boundary, otherwise the net-add accounting would drift.
    """
    if not bpw_active(config):
        return None

    n = int(gaussians.get_xyz.shape[0])
    if n == 0:
        return None

    cfg = get_bpw_config(config)
    p0 = float(cfg.get("p0", DEFAULTS["p0"]))
    budget_scale = float(cfg.get("budget_scale", DEFAULTS["budget_scale"]))
    if budget_scale <= 0:
        raise ValueError("budget_scale must be > 0, got %r" % (budget_scale,))
    tau_lo = float(base_grad_threshold) * float(
        cfg.get("tau_low_factor", DEFAULTS["tau_low_factor"])
    )

    accum = torch.nan_to_num(
        gaussians.xyz_gradient_accum.detach().squeeze(-1), nan=0.0, posinf=0.0, neginf=0.0
    )
    denom = gaussians.denom.detach().squeeze(-1).clamp_min(0.0)

    ref_sel = accum / denom.clamp_min(1.0) >= float(base_grad_threshold)
    # budget_scale < 1 shrinks the per-event quota below the reference arm's.
    # This is the efficiency lever: it asks whether the persistence ranking can
    # reach comparable ATE with fewer new Gaussians. Default 1.0 keeps
    # behaviour bit-identical to the reference arm (and to Phase 0).
    budget = int(ref_sel.sum().item() * budget_scale)

    persistence = denom
    if float(persistence.max().item()) <= 0.0:
        # No observation has ever reached a Gaussian (degenerate first event):
        # every e_i would be identically zero and top-k would pick an arbitrary
        # index order. Rank by raw accumulator instead, which reproduces the
        # reference selection. Logged, so the arm can never silently degrade
        # while looking like the mechanism ran.
        persistence = torch.ones_like(persistence)
        fallback = 1
    else:
        fallback = 0
    if bool(cfg.get("placebo", False)):
        seed = int(cfg.get("placebo_seed", DEFAULTS["placebo_seed"])) + int(
            iteration_count
        )
        gen = torch.Generator(device="cpu").manual_seed(seed)
        perm = torch.randperm(n, generator=gen)
        persistence = persistence[perm.to(persistence.device)]

    evidence = compute_evidence_from_counts(accum, persistence, p0)
    pool = accum / denom.clamp_min(1.0) >= tau_lo

    accepted = select_budget_matched(evidence, pool, budget)

    thr = torch.full((n, 1), float("inf"), device=accum.device, dtype=torch.float32)
    thr[accepted] = -1.0
    pdv = torch.full((n, 1), float(base_percent_dense), device=accum.device)

    if log_fn is not None:
        log_fn(
            "[bpw] iter=%d pool=%d budget=%d accepted=%d mean_p=%.2f fallback=%d"
            % (
                int(iteration_count),
                int(pool.sum().item()),
                budget,
                int(accepted.sum().item()),
                float(persistence.mean().item()),
                int(fallback),
            )
        )

    trace_path = _selection_trace_dir(config)
    if trace_path is not None:
        try:
            xyz = gaussians.get_xyz.detach()
            mean_grad = accum / denom.clamp_min(1.0)
            with open(trace_path, "a", encoding="utf-8") as fh:
                for i in range(n):
                    kind = None
                    if bool(accepted[i]):
                        kind = "accepted"
                    elif bool(ref_sel[i]) and bool(pool[i]):
                        # reference arm would have grown this point; the selector
                        # passed it over (ranked below the accepted top-k).
                        kind = "ref_passed"
                    elif bool(pool[i]):
                        # in the widened pool, below the reference threshold too.
                        kind = "pool_only"
                    if kind is None:
                        continue
                    fh.write(
                        "%d,%s,%d,%.6f,%.6f,%.6f,%.8f,%.1f,%.8f,%d\n"
                        % (
                            int(iteration_count),
                            kind,
                            int(i),
                            float(xyz[i, 0]),
                            float(xyz[i, 1]),
                            float(xyz[i, 2]),
                            float(mean_grad[i]),
                            float(denom[i]),
                            float(evidence[i]),
                            int(bool(ref_sel[i]) and bool(pool[i])),
                        )
                    )
        except Exception as exc:  # diagnostic must never kill the mapping run
            Log(f"[bpw] trace failed at iter {int(iteration_count)}: {exc}")
    return thr, pdv


def _cgb_trace_dir(config):
    """Default-off CGB trace path (``<save_dir>/cgb_selection_trace.csv``)."""
    if not bool(config.get("SelectiveDensification", {}).get("trace_selection", False)):
        return None
    save_dir = config.get("Results", {}).get("save_dir")
    if not save_dir:
        return None
    try:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "cgb_selection_trace.csv")
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "iter,kind,gauss_idx,x,y,z,mean_grad,denom,sparsity,key,max_scale\n"
                )
        return path
    except OSError:
        return None


def compute_coverage_gap_knobs(
    config,
    gaussians,
    base_grad_threshold,
    base_percent_dense,
    iteration_count=0,
    log_fn=None,
):
    """CGB: keep the reference selection, ADD a fixed-size batch in sparse space.

    Returns ``(grad_threshold_vec, percent_dense_vec)`` or ``None`` when inactive.

    Spec: `paper3/results/evidence/prereg_cgb_2026-10-30.md` §2. Per event::

        ref_sel = { i : g_i >= tau_base }              # untouched by this mechanism
        extra_k = floor(swap_frac * |ref_sel|)         # identical across CGB arms
        pool    = { i : g_i >= tau_lo } \\ ref_sel
        key_i   = g_i * s_i ** gamma                   # gamma=1 sparse-reward, 0=plain grad
        extra   = top-extra_k of pool by key
        selected = ref_sel | extra

    Difference from BPW (deliberate, per P3-D2-008): BPW re-ranked a *fixed* budget,
    which the prescreen (`ranking_key_prescreen_2026-10-30.md` Q2) showed is close to
    re-drawing the same points with a noisier weight. CGB never removes a reference
    point; it only adds, and the paired ``gamma=0`` arm adds the same number of
    points chosen by pure gradient. So ``on - off`` measures the cost of the dose and
    ``g1 - g0`` measures the value of the placement, with the dose held equal.

    ``percent_dense`` stays at the reference value for every point: moving it would
    shift the clone/split boundary and make the per-event add count dose-dependent.
    """
    if not cgb_active(config):
        return None

    n = int(gaussians.get_xyz.shape[0])
    if n == 0:
        return None

    cfg = get_bpw_config(config)
    swap_frac = float(cfg.get("swap_frac", DEFAULTS["swap_frac"]))
    gamma = float(cfg.get("gamma", DEFAULTS["gamma"]))
    sparsity_k = int(cfg.get("sparsity_k", DEFAULTS["sparsity_k"]))
    tau_lo = float(base_grad_threshold) * float(
        cfg.get("tau_low_factor", DEFAULTS["tau_low_factor"])
    )
    if not (0.0 <= swap_frac < 1.0):
        raise ValueError("swap_frac must be in [0,1), got %r" % (swap_frac,))

    accum = torch.nan_to_num(
        gaussians.xyz_gradient_accum.detach().squeeze(-1), nan=0.0, posinf=0.0, neginf=0.0
    )
    denom = gaussians.denom.detach().squeeze(-1).clamp_min(0.0)
    mean_grad = accum / denom.clamp_min(1.0)

    ref_sel = mean_grad >= float(base_grad_threshold)
    extra_k = int(swap_frac * int(ref_sel.sum().item()))
    pool = (mean_grad >= tau_lo) & (~ref_sel)

    with torch.no_grad():
        sparsity = compute_sparsity(gaussians.get_xyz, k=sparsity_k)

    # gamma=0 degenerates to the pure-gradient continuation of the reference rule;
    # it is the dose-matched control, not a second mechanism.
    key = mean_grad if gamma == 0.0 else mean_grad * sparsity.pow(gamma)

    thr = torch.full((n, 1), float("inf"), device=accum.device, dtype=torch.float32)
    thr[ref_sel] = -1.0
    pdv = torch.full((n, 1), float(base_percent_dense), device=accum.device)

    extra = torch.zeros(n, dtype=torch.bool, device=accum.device)
    if extra_k > 0 and bool(pool.any()):
        extra = select_budget_matched(
            key.to(accum.device), pool.to(accum.device), extra_k
        ).to(accum.device)
        thr[extra] = -1.0

    if log_fn is not None:
        log_fn(
            "[cgb] iter=%d gamma=%.2f ref=%d pool=%d extra_k=%d extra=%d added=%d "
            "fallback=0"
            % (
                int(iteration_count),
                gamma,
                int(ref_sel.sum().item()),
                int(pool.sum().item()),
                extra_k,
                int(extra.sum().item()),
                int((ref_sel | extra).sum().item()),
            )
        )

    trace_path = _cgb_trace_dir(config)
    if trace_path is not None:
        try:
            xyz = gaussians.get_xyz.detach()
            # max_scale drives the clone/split branch (percent_dense*extent), so
            # logging it is what turns "how many extra points take the split path"
            # from an end-of-run inference on the final map into a per-event reading
            # (Amendment A1 §3b).
            max_scale = gaussians.get_scaling.max(dim=1).values
            with open(trace_path, "a", encoding="utf-8") as fh:
                for i in range(n):
                    kind = None
                    if bool(ref_sel[i]):
                        kind = "ref"
                    elif bool(extra[i]):
                        kind = "extra"
                    elif bool(pool[i]):
                        kind = "pool_only"
                    if kind is None:
                        continue
                    fh.write(
                        "%d,%s,%d,%.6f,%.6f,%.6f,%.8f,%.1f,%.5f,%.8f,%.6f\n"
                        % (
                            int(iteration_count),
                            kind,
                            int(i),
                            float(xyz[i, 0]),
                            float(xyz[i, 1]),
                            float(xyz[i, 2]),
                            float(mean_grad[i]),
                            float(denom[i]),
                            float(sparsity[i]),
                            float(key[i]),
                            float(max_scale[i]),
                        )
                    )
        except Exception as exc:  # diagnostic must never kill the mapping run
            Log(f"[cgb] trace failed at iter {int(iteration_count)}: {exc}")
    return thr, pdv


# --- FDose (frozen dose plan, 2026-10-31) ------------------------------------
#
# Spec: `paper3/results/evidence/prereg_fdose_2026-10-31.md` §2.
# The plan is keyed by EVENT ORDINAL, not by raw iteration: densify event
# iterations are set by ``iteration_count % gaussian_update_every`` and that
# counter advances per mapping call, which depends on frontend/backend queue
# timing -- two arms of the same config do NOT hit the same iteration list
# (measured 2026-10-30: the two CGB arms fired 63 and 61 events, diverging at
# iteration 1850 vs 1700). Ordinal keying is the only schedule-robust choice.

FDOSE_PLAN_PROTOCOL = "fdose-plan-v1"


def load_dose_plan(path):
    """Read a frozen dose plan -> list[int] of per-event K, or ``None``.

    ``path`` falsy => ``None`` (self-plan mode: K_i = |ref_sel| at that event).
    Raises on a present-but-broken file: a plan that cannot be read must stop the
    arm rather than silently fall back to self-planning, which would turn the
    treated arm into a duplicate of the reference arm while still reporting a
    clean run (the exact "inert treatment arm" failure the activity ledger exists
    to prevent).
    """
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    protocol = payload.get("protocol")
    if protocol != FDOSE_PLAN_PROTOCOL:
        raise ValueError(
            "dose plan protocol mismatch: expected %r, got %r"
            % (FDOSE_PLAN_PROTOCOL, protocol)
        )
    k = payload.get("k")
    if not isinstance(k, list) or not k:
        raise ValueError("dose plan has no non-empty 'k' list")
    return [int(v) for v in k]


def select_topk_stable(key, pool, k):
    """Top-``k`` over ``pool`` by ``key``, with ties broken by ascending index.

    ``select_budget_matched`` uses ``torch.topk(..., sorted=False)``, which returns
    an arbitrary (though reproducible-for-a-given-input) order among equal keys.
    FDose needs a *specified* order, because the dose plan is frozen and replayed
    and the prereg claims the k0 arm reproduces the reference selection "except at
    float ties". Ties are not hypothetical here: every never-observed Gaussian has
    ``accum=0`` and identical keys. This helper makes the tie rule explicit
    (stable argsort on descending key == ascending index within equal keys) so the
    selection is auditable rather than merely reproducible on one machine.
    """
    masked = torch.where(pool, key, torch.full_like(key, float("-inf")))
    order = torch.argsort(-masked, stable=True)
    picked = order[: max(0, min(int(k), int(pool.sum().item())))]
    sel = torch.zeros(key.shape[0], dtype=torch.bool, device=key.device)
    sel[picked] = True
    # 防御：stable argsort 在 -inf 上也"有序"，但 pool 外的点绝不能被选中。
    sel &= pool
    return sel


def _fdose_trace_dir(config):
    """Default-off FDose trace path (``<save_dir>/fdose_selection_trace.csv``)."""
    if not bool(config.get("SelectiveDensification", {}).get("trace_selection", False)):
        return None
    save_dir = config.get("Results", {}).get("save_dir")
    if not save_dir:
        return None
    try:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "fdose_selection_trace.csv")
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    "event,iter,kind,gauss_idx,x,y,z,mean_grad,denom,sparsity,key,"
                    "max_scale,k_plan,plan_overflow\n"
                )
        return path
    except OSError:
        return None


def compute_frozen_dose_knobs(
    config,
    gaussians,
    base_grad_threshold,
    base_percent_dense,
    iteration_count=0,
    log_fn=None,
):
    """FDose: pick exactly ``K_i`` source points, where ``K_i`` is exogenous.

    Returns ``(grad_threshold_vec, percent_dense_vec)`` or ``None`` when inactive.

    Spec: `paper3/results/evidence/prereg_fdose_2026-10-31.md` §2. Per event::

        K_i   = dose_plan[event_ordinal]          # exogenous; identical across arms
        pool  = { i : g_i >= tau_lo }             # widened candidate pool
        sel   = top-K_i of pool by key_i
        key_i = g_i * s_i ** gamma                # gamma=0 plain grad, 1 sparse

    ``K_i`` may be *below* the arm's own ``|ref_sel|`` -- that is pruning, and it
    is the whole point (a plan frozen from another arm's map asks for fewer points
    than this arm's base rule would take). It is logged per event as
    ``trim=K_i-|ref_sel|`` and must be reported as a distribution, not a median.

    Deliberately NOT kept: CGB's untouched reference set. CGB's retained set was
    95.2% of the injected dose, so "equal dose" there governed only the 5% tail
    and the fork happened in the retained 95% (verdict 2026-10-30 §4.2).
    """
    if not fdose_active(config):
        return None

    n = int(gaussians.get_xyz.shape[0])
    if n == 0:
        return None

    cfg = get_bpw_config(config)
    gamma = float(cfg.get("gamma", DEFAULTS["gamma"]))
    sparsity_k = int(cfg.get("sparsity_k", DEFAULTS["sparsity_k"]))
    tau_lo = float(base_grad_threshold) * float(
        cfg.get("tau_low_factor", DEFAULTS["tau_low_factor"])
    )
    plan = load_dose_plan(cfg.get("dose_plan_path"))

    accum = torch.nan_to_num(
        gaussians.xyz_gradient_accum.detach().squeeze(-1), nan=0.0, posinf=0.0, neginf=0.0
    )
    denom = gaussians.denom.detach().squeeze(-1).clamp_min(0.0)
    mean_grad = accum / denom.clamp_min(1.0)

    ref_sel = mean_grad >= float(base_grad_threshold)
    pool = mean_grad >= tau_lo

    # Event ordinal: the k-th densify event of THIS run (see the module note on
    # why the raw iteration is the wrong key). Stored on the model instance, the
    # same way `_counter_rng_cache` / `_rng_site_counter` are.
    ordinal = int(getattr(gaussians, "_fdose_event_idx", 0))
    # M5 guard: `BackEnd.reset()` clears the counter and raises this flag, so the
    # FIRST densify event after a map rebuild must be ordinal 0. Without the
    # check a stale counter would resume the plan mid-way on a brand-new map --
    # no error, no warning, just mis-dosed points (silent failure, and invisible
    # in every gate because F1 compares against whatever K_i was consumed).
    if getattr(gaussians, "_fdose_ordinal_must_be_zero", False):
        if ordinal != 0:
            raise RuntimeError(
                "FDose: first densify event after a map reset has ordinal=%d, expected 0 "
                "-- the event counter was not cleared by reset(); the plan would resume "
                "mid-way on a new map (M5)." % ordinal
            )
        gaussians._fdose_ordinal_must_be_zero = False
    gaussians._fdose_event_idx = ordinal + 1

    overflow = 0
    if plan is None:
        k_plan = int(ref_sel.sum().item())          # self-plan (reference arm)
    elif ordinal < len(plan):
        k_plan = int(plan[ordinal])
    else:
        # Arm fired MORE events than the plan covers => inject NOTHING from here on.
        # This is what makes the *total* dose equal across arms whose event counts
        # differ: reusing the last planned dose would keep topping up the longer arm
        # and the totals would diverge by however many extra events it fired
        # (measured: arms fire 61 / 63 / 64 events for the same config family).
        # The zero is logged with ``overflow=1`` and the gate treats it as K_i = 0,
        # so an arm cannot smuggle dose past the end of the plan.
        k_plan = 0
        overflow = 1

    with torch.no_grad():
        sparsity = compute_sparsity(gaussians.get_xyz, k=sparsity_k)
    key = mean_grad if gamma == 0.0 else mean_grad * sparsity.pow(gamma)

    thr = torch.full((n, 1), float("inf"), device=accum.device, dtype=torch.float32)
    pdv = torch.full((n, 1), float(base_percent_dense), device=accum.device)

    selected = torch.zeros(n, dtype=torch.bool, device=accum.device)
    n_pool = int(pool.sum().item())
    if k_plan > 0 and n_pool > 0:
        selected = select_topk_stable(
            key.to(accum.device), pool.to(accum.device), min(k_plan, n_pool)
        ).to(accum.device)
        thr[selected] = -1.0

    n_sel = int(selected.sum().item())
    if log_fn is not None:
        log_fn(
            "[fdose] iter=%d ord=%d gamma=%.2f ref=%d pool=%d k_plan=%d sel=%d "
            "trim=%d short=%d overflow=%d"
            % (
                int(iteration_count),
                ordinal,
                gamma,
                int(ref_sel.sum().item()),
                n_pool,
                k_plan,
                n_sel,
                k_plan - int(ref_sel.sum().item()),
                int(n_sel < k_plan),
                overflow,
            )
        )
    trace_path = _fdose_trace_dir(config)
    if trace_path is not None:
        try:
            xyz = gaussians.get_xyz.detach()
            max_scale = gaussians.get_scaling.max(dim=1).values
            # Volume control: the pool is 3-5x the selected set, and the gates
            # (F1 count / F2 plan / F3 Jaccard / F4 pool-bound / F5 activity) only
            # need the SELECTED points' identities plus a per-event pool size.
            # Writing every pool candidate would put a single 580-frame arm at
            # ~50 MB (measured on CGB, GitHub's 50 MB warning). `trace_pool: true`
            # restores the full dump for offline diagnosis only.
            dump_pool = bool(cfg.get("trace_pool", False))
            with open(trace_path, "a", encoding="utf-8") as fh:
                if overflow:
                    # Post-plan events inject nothing, so with the default
                    # (sel-only) dump they would leave NO row at all -- and then
                    # the gate could not verify that they were flagged. One
                    # sentinel row keeps "the plan ran out here" auditable while
                    # still writing no per-point data.
                    fh.write(
                        "%d,%d,%s,%d,0.000000,0.000000,0.000000,0.00000000,0.0,0.0,"
                        "0.00000000,0.000000,%d,1\n"
                        % (ordinal, int(iteration_count), "overflow_zero", -1, k_plan)
                    )
                for i in range(n):
                    if bool(selected[i]):
                        kind = "sel"
                    elif bool(pool[i]) and dump_pool:
                        kind = "pool_only"
                    else:
                        continue
                    fh.write(
                        "%d,%d,%s,%d,%.6f,%.6f,%.6f,%.8f,%.1f,%.5f,%.8f,%.6f,%d,%d\n"
                        % (
                            ordinal,
                            int(iteration_count),
                            kind,
                            int(i),
                            float(xyz[i, 0]),
                            float(xyz[i, 1]),
                            float(xyz[i, 2]),
                            float(mean_grad[i]),
                            float(denom[i]),
                            float(sparsity[i]),
                            float(key[i]),
                            float(max_scale[i]),
                            k_plan,
                            overflow,
                        )
                    )
        except Exception as exc:  # diagnostic must never kill the mapping run
            Log(f"[fdose] trace failed at iter {int(iteration_count)}: {exc}")
    return thr, pdv
