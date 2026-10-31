"""Phase 1: selective densification — per-Gaussian densify knobs from the
static_prob ledger.

Design (resources/notes/phase1_selective_densification_brief.md + Phase 1 plan):
the static_prob per-Gaussian ledger (v1 P3b, residual-EMA) modulates the two
A4-proven aggressive clone knobs (grad threshold 0.0002->0.0001,
percent_dense 0.01->0.02) so they apply STRONGLY on dynamic-side Gaussians and
NEUTRALLY on static-side ones, instead of globally.

Signal transform (TAT-style, TAD-GS ECCV26): mult = beta + (1-beta)*s^alpha,
s = static_prob in [0,1]; s=1 (static) -> mult=1 (default knobs), s->0
(dynamic) -> mult=beta (most aggressive). aggressiveness a = (1-mult)/(1-beta)
in [0,1]; both knobs lerp linearly from default (a=0) to aggressive (a=1).

Signals:
  static_prob              (B2) residual-EMA ledger as-is
  static_prob_complement   (B3) s -> 1-s: aggressive on the STATIC side
  static_prob_permuted     (B4) placebo: values permuted deterministically per
                                densify event (seed + iteration), proportions
                                preserved
  persistence_budget       (BPW, Phase 0 2026-10-27) budget-matched top-k by
                                persistence; see compute_budget_matched_knobs

Occlusion mitigation (Codex Q3 + ADD-SLAM): Gaussians with fewer than
min_observations ledger observations keep DEFAULT knobs (masked to s=1) --
insufficient evidence must not read as "dynamic".

Config section `SelectiveDensification` (inherited default enabled:false ->
compute_per_gaussian_knobs returns (None, None) and every call site takes the
original scalar path, bit-identical). The frontend ledger-update hook is
gated separately by `update_ledger` so arms B0-B4 can share an identical
frontend WITHOUT enabling StaticProb's tracking soft weighting (which would
confound tracking with densification).
"""

import torch

DEFAULTS = {
    "enabled": False,
    "update_ledger": False,
    "beta": 0.3,
    "alpha": 1.0,
    "grad_thr_default": 0.0002,
    "grad_thr_aggressive": 0.0001,
    "percent_dense_default": 0.01,
    "percent_dense_aggressive": 0.02,
    "signal": "static_prob",
    "ledger_update": "residual",   # residual | depth_signed (ladder rung 2)
    "depth_margin": 0.05,          # |z_gauss - obs| gate, meters
    "memory_beta": 0.90,
    "min_observations": 0,
    "static_anchor": 1.0,
    "placebo_seed": 7,
    "log_every": 10,
}


def get_sel_dens_config(config):
    return config.get("SelectiveDensification", {})


def selective_densification_enabled(config):
    return bool(get_sel_dens_config(config).get("enabled", False))


def selective_ledger_update_enabled(config):
    """Frontend hook gate: keep the residual-EMA ledger live for arms that need
    it WITHOUT touching StaticProb's tracking-soft-weight behavior."""
    cfg = get_sel_dens_config(config)
    return bool(cfg.get("update_ledger", False)) and bool(cfg.get("enabled", False))


def compute_per_gaussian_knobs(config, gaussians, iteration_count):
    """Return (grad_threshold_vec, percent_dense_vec), each (N,1) on the
    Gaussian device, or (None, None) when the feature is disabled."""
    cfg = get_sel_dens_config(config)
    if not cfg.get("enabled", False):
        return None, None
    beta = min(float(cfg.get("beta", DEFAULTS["beta"])), 0.999)
    alpha = float(cfg.get("alpha", DEFAULTS["alpha"]))
    thr_d = float(cfg.get("grad_thr_default", DEFAULTS["grad_thr_default"]))
    thr_a = float(cfg.get("grad_thr_aggressive", DEFAULTS["grad_thr_aggressive"]))
    pd_d = float(cfg.get("percent_dense_default", DEFAULTS["percent_dense_default"]))
    pd_a = float(
        cfg.get("percent_dense_aggressive", DEFAULTS["percent_dense_aggressive"])
    )
    min_obs = int(cfg.get("min_observations", DEFAULTS["min_observations"]))
    signal = str(cfg.get("signal", DEFAULTS["signal"]))
    anchor = float(cfg.get("static_anchor", DEFAULTS["static_anchor"]))

    s = gaussians.static_prob.detach().squeeze(-1).clamp(0.0, 1.0)  # (N,)
    # Calibrated renormalisation (incubation histogram, 2026-09-03): the raw
    # residual-EMA ledger compresses into [0.4, 1.0] (p50≈0.86) -- feeding it
    # raw would give the typical "static" Gaussian a 10-20% aggression dose
    # and the true dynamic tail almost none. s_anchor maps the empirical
    # static plateau to mult=1 (default knobs); anchor=1.0 disables.
    if anchor < 1.0:
        s = (s / anchor).clamp(0.0, 1.0)
    if signal == "static_prob_complement":
        s = 1.0 - s
    elif signal == "static_prob_permuted":
        seed = int(cfg.get("placebo_seed", DEFAULTS["placebo_seed"])) + int(
            iteration_count
        )
        gen = torch.Generator(device="cpu").manual_seed(seed)
        s = s.cpu()[torch.randperm(s.numel(), generator=gen)].to(s.device)
    elif signal != "static_prob":
        raise ValueError(f"Unknown SelectiveDensification.signal: {signal}")

    if min_obs > 0:
        obs = gaussians.static_obs_count.detach().squeeze(-1)
        s = s.masked_fill(obs < min_obs, 1.0)

    mult = beta + (1.0 - beta) * torch.pow(s, alpha)
    a = ((1.0 - mult) / (1.0 - beta)).clamp(0.0, 1.0)
    thr_vec = thr_d + a * (thr_a - thr_d)
    pd_vec = pd_d + a * (pd_a - pd_d)
    return thr_vec.unsqueeze(-1), pd_vec.unsqueeze(-1)


def update_ledger_depth_signed(
    config, gaussians, viewpoint, image, visibility_filter=None
):
    """Ladder rung 2 (Phase 1b): depth-SIGNED ledger update.

    Rung-1 failure (Phase 1a verdict): the photometric residual mislabels
    static background BEHIND the moving object as dynamic (occlusion-
    confounded attribution), so dynamic-side aggression over-densifies
    occlusion boundaries and tracking degrades.

    Gate: a Gaussian's residual evidence is trusted ONLY when the Gaussian
    lies ON the observed surface at its pixel, |z_gauss - obs(u,v)| <=
    depth_margin. Otherwise the observation carries no information about that
    Gaussian and the EMA update is SKIPPED for it this frame:
      - z > obs + margin: occluded static background (Codex/ADD-SLAM case)
      - z < obs - margin: stale ghost floating in front of real geometry
    """
    if gaussians is None or gaussians.get_xyz.shape[0] == 0:
        return
    import numpy as np

    from utils.static_prob import (
        compute_residual_evidence,
        get_static_prob_config,
        update_static_prob_from_evidence,
    )

    obs = getattr(viewpoint, "depth", None)
    if obs is None:
        # No observed depth (monocular frame): fall back to rung-1 behaviour.
        update_static_prob_from_evidence(
            config,
            gaussians,
            viewpoint,
            compute_residual_evidence(config, image, viewpoint),
            visibility_filter,
        )
        return

    cfg = get_sel_dens_config(config)
    beta = float(cfg.get("memory_beta", 0.90))
    margin = float(cfg.get("depth_margin", 0.05))
    default = float(cfg.get("initial_static_prob", 0.7))
    gaussians.ensure_static_memory_state(default)

    xyz = gaussians.get_xyz.detach()
    device = xyz.device
    ones = torch.ones((xyz.shape[0], 1), dtype=xyz.dtype, device=device)
    xyz_h = torch.cat((xyz, ones), dim=1)
    cam_points = xyz_h @ viewpoint.world_view_transform.to(device=device)
    z = cam_points[:, 2]
    valid = z > 0.01
    u = viewpoint.fx * (cam_points[:, 0] / torch.clamp(z, min=1e-6)) + viewpoint.cx
    v = viewpoint.fy * (cam_points[:, 1] / torch.clamp(z, min=1e-6)) + viewpoint.cy
    h = int(viewpoint.image_height)
    w = int(viewpoint.image_width)
    valid = valid & (u >= 0) & (u < w) & (v >= 0) & (v < h)
    if visibility_filter is not None:
        valid = valid & visibility_filter.detach().to(device=device, dtype=torch.bool)
    if not valid.any():
        return

    if isinstance(obs, np.ndarray):
        obs_t = torch.from_numpy(obs).to(device=device, dtype=z.dtype)
    else:
        obs_t = obs.to(device=device, dtype=z.dtype)
    obs_t = obs_t.view(-1)[-h * w:].view(h, w)

    uu = torch.clamp(u[valid].round().long(), 0, w - 1)
    vv = torch.clamp(v[valid].round().long(), 0, h - 1)
    idx = torch.nonzero(valid, as_tuple=False).squeeze(1)

    ev = compute_residual_evidence(config, image, viewpoint)  # (1,H,W) dyn in [0,1)
    dyn = ev[0, vv, uu].view(-1)  # (M,)
    obs_z = obs_t[vv, uu].view(-1)  # (M,) -- 显式一维，避免 (M,)-(M,1) 广播出 (M,M)
    on_surface = (z[idx] - obs_z).abs() <= margin  # (M,)

    # EMA only where the Gaussian matches the observed surface; skip otherwise.
    # Event-level stats banked for later confusion/calibration analysis
    # (Codex 2026-09-03: preserve auditable evidence for lifecycle claims).
    with torch.no_grad():
        signed = (z[idx] - obs_z)
        stats = getattr(gaussians, "_seldens_gate_stats", None)
        if stats is None:
            stats = {"on": 0.0, "behind": 0.0, "front": 0.0, "signed_sum_on": 0.0, "events": 0}
            gaussians._seldens_gate_stats = stats
        stats["on"] += float(on_surface.sum().item())
        stats["behind"] += float((signed > margin).sum().item())
        stats["front"] += float((signed < -margin).sum().item())
        stats["signed_sum_on"] += float(signed[on_surface].abs().mean().item()) if on_surface.any() else 0.0
    idx_on = idx[on_surface]
    if idx_on.numel() == 0:
        return
    gaussians.static_prob[idx_on] = (
        beta * gaussians.static_prob[idx_on]
        + (1.0 - beta) * torch.clamp(1.0 - dyn[on_surface], 0.0, 1.0).view(-1, 1)
    )
    gaussians.static_obs_count[idx_on] += 1.0


def log_sel_dens_state(config, gaussians, iteration_count, tag=""):
    """Cheap one-line diagnostics at densify events (only when enabled)."""
    cfg = get_sel_dens_config(config)
    if not cfg.get("enabled", False):
        return
    log_every = max(1, int(cfg.get("log_every", DEFAULTS["log_every"])))
    if int(iteration_count) % log_every != 0:
        return
    with torch.no_grad():
        s = gaussians.static_prob.detach().squeeze(-1).clamp(0.0, 1.0)
        n = int(s.numel())
        frac_dyn = float((s < 0.3).float().mean().item()) if n else 0.0
        mean_s = float(s.mean().item()) if n else 1.0
    from utils.logging_utils import Log

    extra = ""
    stats = getattr(gaussians, "_seldens_gate_stats", None)
    if stats and stats["events"] >= 0:
        tot = stats["on"] + stats["behind"] + stats["front"]
        if tot > 0:
            extra = (
                f" gate[on={stats['on']/tot:.3f} behind={stats['behind']/tot:.3f} "
                f"front={stats['front']/tot:.3f}] |signed|_on={stats['signed_sum_on']/max(stats['on'],1):.3f}m"
            )
            stats["events"] += 1
            # reset to per-event windows (accumulated since last densify event)
            stats["on"] = stats["behind"] = stats["front"] = stats["signed_sum_on"] = 0.0
    Log(
        f"[seldens]{tag} iter={iteration_count} n={n} "
        f"mean_static_prob={mean_s:.3f} frac_dyn(<0.3)={frac_dyn:.3f}{extra}"
    )
