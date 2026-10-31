"""Route B: sliding-window photometric BA (SWBA) — online KF-pose correction.

R1-R8 established that POST-HOC KF pose-graph correction has no working point on
this architecture: short edges are locally consistent (correction 0.1cm, blind to
10cm drift), long edges push the wrong way (correction 0.6-2.8cm, ATE flat/worse).
The two mechanisms that DO work (hard_tracking_mask -15%, masked_icp weakly
positive) act during tracking. Route B completes that pattern: optimize the recent
keyframe poses against the window WHILE the error is still small and local,
before it propagates into subsequent frames.

Design (all default-off, ``SWBA.enabled``):

  - On each new keyframe K, build photometric edges between K and the previous
    window members, reusing the FD-validated two-sided photometric edge from
    DBALite (person-masked, affine brightness, geometric inlier gating).
  - Free block = the last ``n_free`` KFs (new KF + predecessors); anchors = the
    ``n_anchors`` KFs before them (FIXED gauge). Only the recent tail is touched,
    so a bad edge can damage at most n_free poses, never the global shape.
  - Optimized poses are written back into ``frontend.cameras`` immediately — the
    next frame's tracking() initializes from ``cameras[cur-n]``, so corrections
    feed back into tracking (what R4 lacked: a write-back channel).
  - Non-KF frames inside the corrected segment are re-anchored by linearly
    interpolating the two boundary KFs' correction twists (frame-index weight),
    so the exported full trajectory reflects the fix without tearing.

Per-KF geometry (depth/mask/gray grids) is computed once on KF insertion from
the frontend camera (no dataset reload) and cached; entries older than the
oldest window member are trimmed each step.
"""

import math

import torch
import torch.nn.functional as F

from gaussian_splatting.utils.graphics_utils import getWorld2View2
from utils.coarse_pose import _se3_exp
from utils.dba_lite import _precompute_kf_geom, _se3_log
from utils.logging_utils import Log


def get_swba_config(config):
    return config.get("SWBA", {})


def swba_enabled(config):
    return bool(get_swba_config(config).get("enabled", False))


def build_kf_geom(cam, cfg, device):
    """Per-KF pose-independent geometry from the frontend camera (depth tensor +
    cached dynamic mask + RGB). Returns None if unusable (no depth / too few pts)."""
    depth = getattr(cam, "depth", None)
    if depth is None:
        return None
    if not torch.is_tensor(depth):
        import numpy as np

        depth = torch.from_numpy(depth)
    depth = depth.to(device).float()
    if depth.dim() == 3:
        depth = depth.squeeze(0)
    color = getattr(cam, "original_image", None)
    gray = None
    if color is not None and color.dim() == 3 and color.shape[0] == 3:
        c = color.detach().float()
        gray = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    mask = getattr(cam, "dynamic_mask", None)
    if mask is not None:
        mask = mask.detach().to(device)
        if mask.dim() == 3:
            mask = mask.squeeze(0)
        if mask.dtype != torch.bool:
            mask = mask > 0.5
    return _precompute_kf_geom(
        depth,
        mask,
        float(cam.fx),
        float(cam.fy),
        float(cam.cx),
        float(cam.cy),
        cfg,
        device,
        gray=gray,
    )


def _get_Tcw(cam, device):
    return getWorld2View2(cam.R, cam.T).to(device)


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float("nan")
    if n % 2:
        return xs[n // 2]
    return 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def _fit_affine_frame(gi, gj, Tcw_i, Tcw_j, cfg, device):
    """Estimate the per-TARGET-frame affine brightness (a,b) between two frames
    whose poses are BOTH trusted (the fixed anchors). Fitting (a,b) at the
    poses being optimized bakes the pose error INTO the brightness params and
    creates a spurious minimum at the incoming (wrong) pose — verified on a
    synthetic plane: with (a,b) fit at the perturbed pose, the perturbed pose
    scores BETTER than the true one. Returns (a, b) or None."""
    if gi.get("Is") is None or gj.get("graygrid") is None:
        return None
    min_pts = int(cfg.get("min_points", 500))
    fx, fy, cx, cy = gj["fx"], gj["fy"], gj["cx"], gj["cy"]
    hl, wl = gj["hl"], gj["wl"]
    Pi, Ii = gi["Ps"], gi["Is"]
    T_ij = Tcw_j @ torch.linalg.inv(Tcw_i)
    Pj = Pi @ T_ij[:3, :3].T + T_ij[:3, 3]
    z = Pj[:, 2]
    u = fx * Pj[:, 0] / z + cx
    v = fy * Pj[:, 1] / z + cy
    gxn = (u / (wl - 1)) * 2 - 1
    gyn = (v / (hl - 1)) * 2 - 1
    grid = torch.stack([gxn, gyn], dim=-1)[None, None]
    Ij_s = F.grid_sample(gj["graygrid"], grid, align_corners=True, padding_mode="zeros")[0, 0, 0]
    inside = (u >= 0) & (u <= wl - 1) & (v >= 0) & (v <= hl - 1) & (z > gj["min_d"])
    if int(inside.sum()) < min_pts:
        return None
    A = torch.stack([Ii[inside], torch.ones_like(Ii[inside])], dim=-1)
    try:
        sol = torch.linalg.lstsq(A, Ij_s[inside].unsqueeze(-1)).solution.squeeze(-1)
        return float(sol[0]), float(sol[1])
    except Exception:
        return None


def _edge_frozen(gi, gj, Tcw_i, Tcw_j, cfg, device, frozen=None):
    """SWBA photometric edge with FROZEN inlier set + affine brightness params.

    The DBALite photometric edge re-gates inliers and re-fits the per-edge
    affine (a,b) at EVERY pose evaluation. That makes successive cost values
    incomparable (the sample changes under the pose), which derails the solver —
    GN can descend into a spurious minimum by re-selecting agreeable points
    (verified on a synthetic plane: plain GN walked to a 23cm false minimum).
    Here gating + (a,b) are computed ONCE at the incoming poses and frozen for
    the whole optimization; subsequent evaluations only re-sample the target
    image/gradient at the updated projections. Jacobian convention matches
    _edge_photometric_two_sided (left perturbation).

    Returns (r, J_i, J_j, w) or None (below min_points at freeze time).
    If `frozen` (dict from a previous call) is given, reuses it.
    """
    if gi.get("Is") is None or gj.get("graygrid") is None:
        return None
    min_pts = int(cfg.get("min_points", 500))
    fx, fy, cx, cy = gj["fx"], gj["fy"], gj["cx"], gj["cy"]
    hl, wl = gj["hl"], gj["wl"]
    Pi, Ii = gi["Ps"], gi["Is"]

    T_ij = Tcw_j @ torch.linalg.inv(Tcw_i)
    R_ij, t_ij = T_ij[:3, :3], T_ij[:3, 3]
    Pj = Pi @ R_ij.T + t_ij
    z = Pj[:, 2]
    u = fx * Pj[:, 0] / z + cx
    v = fy * Pj[:, 1] / z + cy

    if frozen is None:
        gxn = (u / (wl - 1)) * 2 - 1
        gyn = (v / (hl - 1)) * 2 - 1
        grid = torch.stack([gxn, gyn], dim=-1)[None, None]
        dj_s = F.grid_sample(gj["dgrid"], grid, align_corners=True, padding_mode="zeros")[0, 0, 0]
        Ij_s = F.grid_sample(gj["graygrid"], grid, align_corners=True, padding_mode="zeros")[0, 0, 0]
        inside = (u >= 0) & (u <= wl - 1) & (v >= 0) & (v <= hl - 1)
        valid_dp = (dj_s > gj["min_d"]) & (dj_s < gj["max_d"])
        depth_ok = (dj_s - z).abs() < float(cfg.get("depth_gate", 0.10))
        finite = torch.isfinite(u) & torch.isfinite(v) & torch.isfinite(Ij_s)
        m = inside & (z > gj["min_d"]) & valid_dp & depth_ok & finite
        if gj["mgrid"] is not None:
            mj_s = F.grid_sample(gj["mgrid"], grid, align_corners=True, padding_mode="zeros")[0, 0, 0]
            m = m & (mj_s <= 0.5)
        if int(m.sum()) < min_pts:
            return None
        # affine (a,b) must be provided by the CALLER via cfg["_affine"] — fit
        # only on trusted (anchor) poses, never at the poses being optimized
        ab = cfg.get("_affine")
        if ab is None:
            return None
        frozen = {"idx": m.nonzero(as_tuple=True)[0], "a": ab[0], "b": ab[1]}
        return frozen  # first call returns the frozen state only

    idx = frozen["idx"]
    a = torch.tensor(frozen["a"], device=device)
    b = torch.tensor(frozen["b"], device=device)
    Pj_m, z_m = Pj[idx], z[idx]
    u_m, v_m = u[idx], v[idx]
    gxn = (u_m / (wl - 1)) * 2 - 1
    gyn = (v_m / (hl - 1)) * 2 - 1
    grid = torch.stack([gxn, gyn], dim=-1)[None, None]
    Ij_m = F.grid_sample(gj["graygrid"], grid, align_corners=True, padding_mode="zeros")[0, 0, 0]
    r = (a * Ii[idx] + b) - Ij_m
    grad_m = F.grid_sample(gj["gxygrid"], grid, align_corners=True, padding_mode="zeros")[0, :, 0]  # (2,K)
    gx_m, gy_m = grad_m[0], grad_m[1]

    X, Y = Pj_m[:, 0], Pj_m[:, 1]
    zero, ones = torch.zeros_like(X), torch.ones_like(X)
    dP_rows = torch.stack(
        [
            torch.stack([zero, -z_m, Y], dim=-1),
            torch.stack([z_m, zero, -X], dim=-1),
            torch.stack([-Y, X, zero], dim=-1),
            torch.stack([ones, zero, zero], dim=-1),
            torch.stack([zero, ones, zero], dim=-1),
            torch.stack([zero, zero, ones], dim=-1),
        ],
        dim=1,
    )  # (K,6,3)
    dudx = torch.stack([fx / z_m, torch.zeros_like(z_m), -fx * Pj_m[:, 0] / (z_m * z_m)], dim=-1)  # (K,3)
    dvdx = torch.stack([torch.zeros_like(z_m), fy / z_m, -fy * Pj_m[:, 1] / (z_m * z_m)], dim=-1)  # (K,3)
    # dr/dP = -(dI/du * du/dP + dI/dv * dv/dP): (K,3)
    proj = -(gx_m.unsqueeze(-1) * dudx + gy_m.unsqueeze(-1) * dvdx)
    Jj = (proj.unsqueeze(-2) * dP_rows).sum(dim=-1)  # (K,6)
    # i-side: T_ij <- T_ij Exp(-dx_i) gives dP_j = -R_ij (dx_i x P_i + v_i);
    # chain rule Ji[k,r] = -[(R_ij^T proj) . dPi_rows[r]] — rotate the j-frame
    # gradient into frame i with R^T (proj @ R_ij as row) and flip the sign of
    # the left-perturbation direction, matching dba_lite's FD-validated
    # two-sided composition. The pre-fix line (proj @ R_ij.T, no minus) was
    # globally sign-flipped on all six i columns (FD corr -0.99) and silently
    # corrupted the free-free edge's gradient block for the older free KF.
    Pi_m = Pi[idx]
    Xi, Yi, Zi = Pi_m[:, 0], Pi_m[:, 1], Pi_m[:, 2]
    zero_i, ones_i = torch.zeros_like(Xi), torch.ones_like(Xi)
    dPi_rows = torch.stack(
        [
            torch.stack([zero_i, -Zi, Yi], dim=-1),
            torch.stack([Zi, zero_i, -Xi], dim=-1),
            torch.stack([-Yi, Xi, zero_i], dim=-1),
            torch.stack([ones_i, zero_i, zero_i], dim=-1),
            torch.stack([zero_i, ones_i, zero_i], dim=-1),
            torch.stack([zero_i, zero_i, ones_i], dim=-1),
        ],
        dim=1,
    )  # (K,6,3)
    proj_i = proj @ R_ij
    Ji = -(proj_i.unsqueeze(-2) * dPi_rows).sum(dim=-1)  # (K,6)

    med = r.median()
    mad = 1.4826 * (r - med).abs().median() + 1e-6
    w = torch.clamp((1.5 * mad) / r.abs().clamp(min=1e-6), max=1.0)
    return r, Ji, Jj, w


def _edge_depth_frozen(gi, gj, Tcw_i, Tcw_j, cfg, device, frozen=None):
    """SWBA METRIC depth edge: source points from KF_i's SENSOR depth must
    land on KF_j's SENSOR depth under the current relative pose. Map-independent
    metric anchor (sensor-to-sensor) — pins the window poses to the metric
    scale BEFORE KF commit, at the entry of the mapping-tracking bootstrap loop
    (the map-exit-side fix, DepthReanchor D1, is verdict-negative).

    Freeze discipline (joint_correct README 2.3/2.5b, Codex-reviewed):
      - FROZEN: the source point set, the target sample z_meas (taken at the
        INCOMING pose projection) and the per-edge scale z_ref = median(z_meas).
        NO pose-dependent depth gate in the frozen set — during a scale
        excursion the large-residual static pixels ARE the constraint signal;
        gating them out blinds the solver to the very direction that needs
        correcting. The frozen target is well-matched to the mechanism: scale
        errors move z_pred almost purely along the view axis, so the target
        pixel barely shifts and sampling drift is second-order.
      - Residual is fully analytic: r = (z_pred - z_meas)/z_ref, so the
        Jacobian is exact (no image-gradient approximation — FD test matches
        to machine precision class).
      - Outliers (occlusion, depth noise) are down-weighted by a robust kernel
        at a PHYSICAL noise scale (depth_sigma, meters) — data-driven MAD
        collapses under the coherent systematic shifts this edge exists to
        catch.

    Returns (r, J_i, J_j, w) or None. If `frozen` is None, returns the frozen
    state dict only ({"idx", "z_meas", "z_ref"}).
    """
    if gj.get("dgrid") is None:
        return None
    fx, fy, cx, cy = gj["fx"], gj["fy"], gj["cx"], gj["cy"]
    hl, wl = gj["hl"], gj["wl"]
    Pi = gi["Ps"]

    def _project(T_i, T_j):
        T_ij = T_j @ torch.linalg.inv(T_i)
        Pj = Pi @ T_ij[:3, :3].T + T_ij[:3, 3]
        z = Pj[:, 2]
        u = fx * Pj[:, 0] / z + cx
        v = fy * Pj[:, 1] / z + cy
        return Pj, z, u, v

    if frozen is None:
        _, z, u, v = _project(Tcw_i, Tcw_j)
        gxn = (u / (wl - 1)) * 2 - 1
        gyn = (v / (hl - 1)) * 2 - 1
        grid = torch.stack([gxn, gyn], dim=-1)[None, None]
        dj_s = F.grid_sample(gj["dgrid"], grid, align_corners=True, padding_mode="zeros")[0, 0, 0]
        inside = (u >= 0) & (u <= wl - 1) & (v >= 0) & (v <= hl - 1) & (z > gj["min_d"])
        valid_dp = (dj_s > gj["min_d"]) & (dj_s < gj["max_d"])
        m = inside & valid_dp & torch.isfinite(dj_s)
        if gj["mgrid"] is not None:
            mj_s = F.grid_sample(gj["mgrid"], grid, align_corners=True, padding_mode="zeros")[0, 0, 0]
            m = m & (mj_s <= 0.5)
        if int(m.sum()) < int(cfg.get("min_points", 500)):
            return None
        idx = m.nonzero(as_tuple=True)[0]
        z_meas = dj_s[idx]
        return {"idx": idx, "z_meas": z_meas, "z_ref": float(z_meas.median())}

    idx = frozen["idx"]
    z_meas = frozen["z_meas"]
    z_ref = max(float(frozen["z_ref"]), 1e-6)
    T_ij = Tcw_j @ torch.linalg.inv(Tcw_i)
    R_ij = T_ij[:3, :3]
    Pi_m = Pi[idx]
    Pj = Pi_m @ R_ij.T + T_ij[:3, 3]
    z = Pj[:, 2]
    K = int(z.shape[0])
    # per-evaluation sanity: a step can push the prediction out of range even
    # though the frozen set was valid at the incoming pose
    ok = (z > gj["min_d"]) & torch.isfinite(z)
    if not bool(ok.any()):
        return None

    r = (z - z_meas) / z_ref
    # Jacobian: dz_pred/dP = e_z exactly -> proj = e_z / z_ref, then the same
    # two-sided machinery as the photometric edge (FD-validated conventions).
    zero, ones = torch.zeros_like(z), torch.ones_like(z)
    proj = torch.stack([zero, zero, ones], dim=-1) / z_ref  # (K,3)

    X, Y = Pj[:, 0], Pj[:, 1]
    dP_rows = torch.stack(
        [
            torch.stack([zero, -z, Y], dim=-1),
            torch.stack([z, zero, -X], dim=-1),
            torch.stack([-Y, X, zero], dim=-1),
            torch.stack([ones, zero, zero], dim=-1),
            torch.stack([zero, ones, zero], dim=-1),
            torch.stack([zero, zero, ones], dim=-1),
        ],
        dim=1,
    )  # (K,6,3)
    Jj = (proj.unsqueeze(-2) * dP_rows).sum(dim=-1)  # (K,6)
    # i-side: dP_j = -R_ij (dx_i x P_i + v_i) — the perturbation acts on the
    # SOURCE frame, so the cross-product rows must be built at the SOURCE
    # points P_i (same construction as _edge_frozen's dPi_rows). Building them
    # at P_j leaves the omega_y column with relerr ~1.7 vs FD at a 0.5 m
    # baseline (first J1 screening batch invalidated by exactly this).
    Xi, Yi, Zi = Pi_m[:, 0], Pi_m[:, 1], Pi_m[:, 2]
    dPi_rows = torch.stack(
        [
            torch.stack([zero, -Zi, Yi], dim=-1),
            torch.stack([Zi, zero, -Xi], dim=-1),
            torch.stack([-Yi, Xi, zero], dim=-1),
            torch.stack([ones, zero, zero], dim=-1),
            torch.stack([zero, ones, zero], dim=-1),
            torch.stack([zero, zero, ones], dim=-1),
        ],
        dim=1,
    )  # (K,6,3)
    proj_i = proj @ R_ij
    Ji = -(proj_i.unsqueeze(-2) * dPi_rows).sum(dim=-1)  # (K,6)

    # Robust weight from a PHYSICAL noise scale, not data-driven MAD: under a
    # systematic scale excursion every residual shifts coherently, so the MAD
    # (spread about the median) collapses toward the interpolation noise floor
    # and deflates ALL weights ~uniformly (unit-test-demonstrated) — the
    # constraint survives within-edge but its weight vs the photometric edges
    # in the mixed solver collapses. Sensor depth noise is physically
    # characterized (depth_sigma, meters); |z_pred - z_meas| is metric so
    # z_ref cancels out of the weight.
    sigma = max(float(cfg.get("depth_sigma", 0.02)), 1e-4)
    w = torch.clamp((1.5 * sigma) / (z - z_meas).abs().clamp(min=1e-6), max=1.0)
    w[~ok] = 0.0
    return r, Ji, Jj, w


def optimize_window(cameras, kfs, geom_cache, cfg, device):
    """One SWBA step. ``kfs`` = sorted KF indices (new KF last, all in cameras).

    Edges: new KF <-> every other window member (so it always sees FIXED anchor
    geometry — the correction is local by construction), plus consecutive
    free-free edges for joint observability. Levenberg-Marquardt on the free
    block with a weak prior to the pre-step poses.

    Returns (T_opt dict over free KFs, stats) or None if skipped.
    """
    n_free = max(1, int(cfg.get("n_free", 2)))
    n_anchors = int(cfg.get("n_anchors", 4))
    free = kfs[-n_free:]
    anchors = kfs[-(n_free + n_anchors) : -n_free]
    window = anchors + free
    if not anchors or not free:
        return None
    missing = [k for k in window if k not in geom_cache]
    if missing:
        return None

    new_kf = kfs[-1]
    # DENSE window edges: every pair within n_anchors index distance. Star
    # edges (new-KF-only) leave the older free KFs gauge-free against the
    # anchors — their only constraint runs through the new KF — which made the
    # solver drift the second-newest KF the WRONG way on the synthetic test.
    edges = []
    for a in range(len(window)):
        for b in range(a + 1, min(a + 1 + n_anchors, len(window))):
            edges.append((window[a], window[b]))

    T = {k: _get_Tcw(cameras[k], device) for k in window}
    # Affine (a,b) per edge: identity by default (Bonn exposure is near-
    # constant within a sequence). Fitting (a,b) at the poses being optimized
    # bakes the pose error into the brightness params and creates a spurious
    # minimum at the incoming pose (synthetic proof: with (a,b) lstsq-fit at
    # the perturbed pose, the perturbed pose scores BETTER than the true one).
    # Only anchor-anchor pairs (both poses trusted) are ever fit.
    affine = {}
    for i, j in edges:
        ab = (1.0, 0.0)
        if i in anchors and j in anchors:
            fitted = _fit_affine_frame(
                geom_cache[i], geom_cache[j], T[i], T[j], cfg, device
            )
            if fitted is not None:
                ab = fitted
        affine[(i, j)] = ab
    cfg = dict(cfg)
    cfg["_affine"] = None  # set per-edge below
    T_anchor = {k: T[k].clone() for k in free}
    lam_prior = float(cfg.get("lm_prior", 0.0))
    eye6 = torch.eye(6, device=device)
    col = {k: i for i, k in enumerate(free)}
    nf = len(free)

    # Pass 1: freeze inlier sets at the incoming poses (see _edge_frozen for
    # why re-gating per evaluation breaks the cost landscape). The affine (a,b)
    # comes from cfg["_affine"], estimated by the caller on TRUSTED poses only.
    frozen = {}
    for i, j in edges:
        cfg_e = dict(cfg)
        cfg_e["_affine"] = affine[(i, j)]
        fz = _edge_frozen(geom_cache[i], geom_cache[j], T[i], T[j], cfg_e, device)
        if fz is not None:
            frozen[(i, j)] = (fz, cfg_e)
    if not frozen:
        return None
    edges = [e for e in edges if e in frozen]

    # J1 metric depth edges (default off, SWBA.depth_weight): the same window
    # pairs, frozen the same way at the incoming poses. Design constraints
    # (joint_correct README 2.3/2.5b): NO pose-dependent depth gate in the
    # freeze — during a scale excursion the large-residual static pixels ARE
    # the constraint signal; the target sample is frozen (scale errors move
    # z_pred almost purely along the view axis, so target drift is
    # second-order) and the robust kernel uses a physical noise scale
    # (depth_sigma) because data-driven MAD collapses under coherent shifts.
    depth_w = float(cfg.get("depth_weight", 0.0))
    frozen_d = {}
    if depth_w > 0:
        for i, j in edges:
            if i not in col and j not in col:
                continue  # anchor-anchor pair: no free block, cost-only
            fzd = _edge_depth_frozen(
                geom_cache[i], geom_cache[j], T[i], T[j], cfg, device
            )
            if fzd is not None:
                frozen_d[(i, j)] = fzd
    depth_med0 = None
    depth_med1 = None
    depth_share = None
    if frozen_d:
        rds = []
        for i, j in frozen_d:
            res = _edge_depth_frozen(
                geom_cache[i], geom_cache[j], T[i], T[j], cfg, device,
                frozen=frozen_d[(i, j)],
            )
            if res is not None:
                rds.append(res[0])
        if rds:
            depth_med0 = float(torch.cat(rds).abs().median())

    # photometric Hessian scale for the RELATIVE prior weight (the prior's
    # natural unit would crush the photometric signal; see solver comment)
    phot_scale0 = 0.0
    n_samp = 0
    for (i, j), (fz, cfg_e) in frozen.items():
        res = _edge_frozen(
            geom_cache[i], geom_cache[j], T[i], T[j], cfg_e, device, frozen=fz
        )
        if res is None:
            continue
        r, _, Jj, w = res
        we = w / max(int(r.shape[0]), 1)
        phot_scale0 += float(((Jj * we[:, None]).T @ Jj).diagonal().sum())
        n_samp += 1
    phot_scale0 = phot_scale0 / max(6 * nf * n_samp, 1)  # mean diag scale

    def opt_cost(Tcur):
        c = 0.0
        for (i, j), (fz, cfg_e) in frozen.items():
            res = _edge_frozen(
                geom_cache[i], geom_cache[j], Tcur[i], Tcur[j], cfg_e, device, frozen=fz
            )
            if res is not None:
                r, _, _, w = res
                we = w / max(int(r.shape[0]), 1)
                c += float((we * r * r).sum())
        for (i, j), fzd in frozen_d.items():
            res = _edge_depth_frozen(
                geom_cache[i], geom_cache[j], Tcur[i], Tcur[j], cfg, device, frozen=fzd
            )
            if res is not None:
                r, _, _, w = res
                we = w / max(int(r.shape[0]), 1)
                c += depth_w * float((we * r * r).sum())
        if lam_prior > 0:
            for k in free:
                rp = _se3_log(Tcur[k] @ torch.linalg.inv(T_anchor[k]))
                c += lam_prior * phot_scale0 * float((rp * rp).sum())
        return c

    c0 = opt_cost(T)
    c_init = c0  # R25 health gate: pre-optimization window cost
    lam = float(cfg.get("lm_lambda0", 1e-3))
    for it_idx in range(int(cfg.get("iters", 10))):
        H = torch.zeros(6 * nf, 6 * nf, device=device)
        g = torch.zeros(6 * nf, device=device)
        for (i, j), (fz, cfg_e) in frozen.items():
            res = _edge_frozen(
                geom_cache[i], geom_cache[j], T[i], T[j], cfg_e, device, frozen=fz
            )
            if res is None:
                continue
            r, Ji, Jj, w = res
            we = w / max(int(r.shape[0]), 1)
            wr = we * r
            blocks = []
            if i in col:
                blocks.append((col[i], Ji))
            if j in col:
                blocks.append((col[j], Jj))
            for bi, Jb in blocks:
                g[6 * bi : 6 * bi + 6] += Jb.T @ wr
                Jbw = Jb * we[:, None]
                for bj, Jc in blocks:
                    H[6 * bi : 6 * bi + 6, 6 * bj : 6 * bj + 6] += Jbw.T @ Jc
        # depth-edge normal-equation contributions (same block structure;
        # robust weight is physical-scale based, see _edge_depth_frozen)
        h_depth = 0.0
        for (i, j), fzd in frozen_d.items():
            res = _edge_depth_frozen(
                geom_cache[i], geom_cache[j], T[i], T[j], cfg, device, frozen=fzd
            )
            if res is None:
                continue
            r, Ji_d, Jj_d, w_d = res
            we = w_d / max(int(r.shape[0]), 1)
            wr = depth_w * we * r
            blocks = []
            if i in col:
                blocks.append((col[i], Ji_d))
            if j in col:
                blocks.append((col[j], Jj_d))
            for bi, Jb in blocks:
                g[6 * bi : 6 * bi + 6] += Jb.T @ wr
                Jbw = Jb * (depth_w * we)[:, None]
                for bj, Jc in blocks:
                    blk = Jbw.T @ Jc
                    H[6 * bi : 6 * bi + 6, 6 * bj : 6 * bj + 6] += blk
                    if bi == bj and it_idx == 0:
                        h_depth += float(blk.diagonal().sum())
        if frozen_d and it_idx == 0:
            tot = float(H.diagonal().sum())
            depth_share = h_depth / max(tot, 1e-12)
        if lam_prior > 0:
            # RELATIVE prior weight: scale by the photometric Hessian's mean
            # diagonal (phot_scale0, measured once before iterating) so
            # lam_prior=1.0 means "equal influence", independent of the
            # residual scale. An unscaled prior (natural unit 1.0) dominates
            # the photometric Hessian (~1e-3) 1000:1 and freezes the solve.
            for k in free:
                bi = col[k]
                rp = _se3_log(T[k] @ torch.linalg.inv(T_anchor[k]))
                g[6 * bi : 6 * bi + 6] += lam_prior * phot_scale0 * rp
                H[6 * bi : 6 * bi + 6, 6 * bi : 6 * bi + 6] += (
                    lam_prior * phot_scale0 * eye6
                )
        # GN + backtracking line search. Plain LM damping over-restricts here:
        # the photometric Hessian is strongly anisotropic (rot-vs-translation
        # column norms differ ~100x on textured planes), so a fixed lambda
        # overdamps the stiff directions. Tikhonov floor handles rank deficit.
        diag = H.diagonal().clamp(min=1e-12)
        reg = lam * float(diag.mean())
        try:
            dx = -torch.linalg.solve(H + reg * torch.eye(6 * nf, device=device), g)
        except Exception:
            lam = min(lam * 10, 1e2)
            continue
        improved = False
        t = 1.0
        for _ in range(20):
            Tn = dict(T)
            for k in free:
                d = dx[6 * col[k] : 6 * col[k] + 6] * t
                Tn[k] = _se3_exp(d) @ T[k]
            c_new = opt_cost(Tn)
            if c_new < c0:
                T, c0 = Tn, c_new
                improved = True
                break
            t *= 0.5
        if not improved:
            lam = min(lam * 10, 1e2)
            if lam >= 1e2:
                break
        elif float(dx.norm()) * t < 1e-6:
            break

    dts, drots = [], []
    for k in free:
        xi = _se3_log(T[k] @ torch.linalg.inv(T_anchor[k]))
        drots.append(float(torch.norm(xi[:3])) * 180.0 / math.pi)
        dts.append(float(torch.norm(xi[3:])))
    if frozen_d:
        rds = []
        for i, j in frozen_d:
            res = _edge_depth_frozen(
                geom_cache[i], geom_cache[j], T[i], T[j], cfg, device,
                frozen=frozen_d[(i, j)],
            )
            if res is not None:
                rds.append(res[0])
        if rds:
            depth_med1 = float(torch.cat(rds).abs().median())
    return {
        "T_opt": {k: T[k] for k in free},
        "median_dt_cm": _median(dts) * 100.0,
        "max_dt_cm": max(dts) * 100.0,
        "median_drot_deg": _median(drots),
        "max_drot_deg": max(drots),
        "cost": c0,
        "cost_init": c_init,
        "rel_improve": (c_init - c0) / max(abs(c_init), 1e-9),
        "n_edges": len(edges),
        "n_depth_edges": len(frozen_d),
        "depth_med_resid_init": depth_med0,
        "depth_med_resid_opt": depth_med1,
        "depth_hessian_share": depth_share,
        "new_kf": new_kf,
        "free": free,
        "n_anchors": len(anchors),
    }


class SWBA:
    """Frontend-side sliding-window BA state holder.

    ``on_new_keyframe`` is called by the frontend right AFTER add_new_keyframe
    (KF pose final, before the backend "keyframe" message is queued): caches the
    new KF's geometry, runs the window optimization, applies capped corrections
    to cameras, re-anchors the non-KF segment since the previous KF, trims the
    geometry cache.
    """

    def __init__(self, config):
        self.config = config
        self.cfg = dict(get_swba_config(config))
        for k, v in (
            ("stride", 4),
            ("min_depth", 0.05),
            ("max_depth", 5.0),
            ("grad_thresh", 0.02),
            ("min_points", 500),
            ("depth_gate", 0.10),
            ("n_free", 2),
            ("n_anchors", 4),
            ("lm_prior", 0.0),
            ("lm_lambda0", 1e-3),
            ("iters", 10),
            ("max_update_trans", 0.10),  # m, same LM step guards as DBALite
            ("max_update_rot_deg", 5.0),
            ("depth_weight", 0.0),  # J1 metric depth edge, 0 = off
            ("depth_sigma", 0.02),  # m, physical sensor-depth noise scale
            ("device", "cuda:0"),
        ):
            self.cfg.setdefault(k, v)
        self.device = str(self.cfg["device"])
        self.geom_cache = {}
        self.stats = []
        self.n_applied = 0

    def on_new_keyframe(self, cameras, kf_indices, last_kf_before):
        """Run one SWBA step at the newest KF. Returns stats dict or None."""
        cfg = self.cfg
        kfs = sorted(int(k) for k in kf_indices if int(k) in cameras)
        if not kfs:
            return None
        new_kf = kfs[-1]
        g = build_kf_geom(cameras[new_kf], cfg, self.device)
        if g is None or g["Ps"].shape[0] < int(cfg.get("min_points", 500)):
            return None
        self.geom_cache[new_kf] = g

        result = optimize_window(cameras, kfs, self.geom_cache, cfg, self.device)
        if result is None:
            # first windows of a run (or a cache miss) lack the older KFs'
            # geometry — populate on demand from the frontend cameras, then
            # retry once
            window_len = int(cfg["n_free"]) + int(cfg["n_anchors"])
            for k in kfs[-window_len:-1]:
                if k in self.geom_cache or k not in cameras:
                    continue
                gk = build_kf_geom(cameras[k], cfg, self.device)
                if gk is not None and gk["Ps"].shape[0] >= int(cfg.get("min_points", 500)):
                    self.geom_cache[k] = gk
            result = optimize_window(
                cameras, kfs, self.geom_cache, cfg, self.device
            )
        if result is None:
            return None
        T_opt = result.pop("T_opt")

        # step-size guards (same knobs as DBALite): clamp each free KF's twist
        # R25 health gate: on healthy sequences the window cost is already
        # near its floor — the GN still finds 3-7cm "corrections" that are
        # noise injection (fulltable: crowd2 +2.0cm regression), while on
        # drifting sequences real corrections buy a large cost drop. Apply
        # only when the window photometric cost improved by at least
        # swba_min_rel_improve (0.0 = always apply = pre-R25 behavior).
        rel_improve = float(result.get("rel_improve", 0.0))
        min_ri = float(cfg.get("swba_min_rel_improve", 0.0))
        if rel_improve < min_ri:
            self.n_gate_skipped = getattr(self, "n_gate_skipped", 0) + 1
            result["gate_skipped"] = True
            keep = set(kfs[-(int(cfg["n_free"]) + int(cfg["n_anchors"])) :])
            for k in list(self.geom_cache.keys()):
                if k not in keep:
                    del self.geom_cache[k]
            Log(
                f"SWBA kf={new_kf}: [gate-skip] rel_improve={rel_improve:.1%} "
                f"< {min_ri:.1%} — correction not applied"
            )
            return result

        # R28 direction-coherence adaptive cap: a GLOBAL cap trades pt1's
        # event-window cure (5-10cm coherent corrections) against easy-
        # sequence noise (2.9-6.6cm oscillating corrections) — fulltable
        # r27 screening quantified the tradeoff. The signatures differ:
        # DRIFT = consecutive corrections point the same way (vector mean
        # ~ magnitude), NOISE = they oscillate (mean ~ 0). Effective cap
        # interpolates cap_floor -> max_update_trans by coherence.
        cap_floor = float(cfg.get("swba_cap_floor", cfg["max_update_trans"]))
        hist = getattr(self, "_recent_corr", [])
        cap_t = float(cfg["max_update_trans"])
        if cap_floor < cap_t and len(hist) >= 2:
            import torch as _t
            vecs = _t.stack([h for h in hist[-int(cfg.get("swba_coherence_window", 5)):]])
            coh = float(vecs.mean(0).norm() / max(vecs.norm(dim=1).mean(), 1e-9))
            cap_t = cap_floor + (cap_t - cap_floor) * min(max(coh, 0.0), 1.0)
        else:
            coh = None
        cap_r = float(cfg["max_update_rot_deg"]) * math.pi / 180.0
        capped = False
        T_old = {k: _get_Tcw(cameras[k], self.device) for k in T_opt}
        T_new = {}
        for k, T in T_opt.items():
            xi = _se3_log(T @ torch.linalg.inv(T_old[k]))
            s = 1.0
            if float(torch.norm(xi[3:])) > cap_t:
                s = min(s, cap_t / max(float(torch.norm(xi[3:])), 1e-9))
                capped = True
            if float(torch.norm(xi[:3])) > cap_r:
                s = min(s, cap_r / max(float(torch.norm(xi[:3])), 1e-9))
                capped = True
            if s < 1.0:
                xi = xi * s
                T = _se3_exp(xi) @ T_old[k]
            T_new[k] = T

        # R28: stash applied correction translation directions (KF-local) for
        # the coherence estimate of the NEXT window
        hist = getattr(self, "_recent_corr", [])
        for k in T_new:
            xi_k = _se3_log(T_new[k] @ torch.linalg.inv(T_old[k]))
            hist.append(xi_k[3:].detach().cpu())
        self._recent_corr = hist[-12:]

        # re-anchor the non-KF segment (last_kf_before, new_kf) BEFORE writing
        # back: interpolate the correction twists of the two boundary KFs.
        if last_kf_before is not None and last_kf_before in T_new:
            self._reanchor_segment(
                cameras, last_kf_before, new_kf, T_old, T_new
            )

        for k, T in T_new.items():
            cameras[k].update_RT(T[:3, :3].contiguous(), T[:3, 3].contiguous())
        self.n_applied += 1

        # trim geometry cache beyond the oldest window member
        keep = set(kfs[-(int(cfg["n_free"]) + int(cfg["n_anchors"])) :])
        for k in list(self.geom_cache.keys()):
            if k not in keep:
                del self.geom_cache[k]

        result["capped"] = capped
        self.stats.append(result)
        dline = ""
        if result.get("n_depth_edges"):
            dline = (
                f" | depth n={result['n_depth_edges']}"
                f" med {result.get('depth_med_resid_init')}->"
                f"{result.get('depth_med_resid_opt')}"
                f" share {result.get('depth_hessian_share')}"
            )
        Log(
            f"SWBA kf={new_kf}: {result['n_edges']} edges free={result['free']} "
            f"anchors={result['n_anchors']} |dc| {result.get('rel_improve', 0.0):.1%} "
            f"|dt| med {result['median_dt_cm']:.2f}cm "
            f"max {result['max_dt_cm']:.2f}cm |rot| med "
            f"{result['median_drot_deg']:.2f}° max {result['max_drot_deg']:.2f}°"
            + dline
            + (" [capped]" if capped else "")
        )
        return result

    def _reanchor_segment(self, cameras, kf_prev, kf_new, T_old, T_new):
        """Rigidly re-anchor non-KF frames in (kf_prev, kf_new).

        Each frame's pose is updated by the frame-index-weighted interpolation of
        the two boundary KFs' correction twists (xi = log(T_new @ inv(T_old))),
        so the segment follows the corrected endpoints without tearing. Boundary
        KFs not in the free set contribute a zero twist (their pose is unchanged).
        """
        if kf_new <= kf_prev + 1:
            return
        xi_prev = torch.zeros(6, device=self.device)
        xi_new = torch.zeros(6, device=self.device)
        if kf_prev in T_old and kf_prev in T_new:
            xi_prev = _se3_log(T_new[kf_prev] @ torch.linalg.inv(T_old[kf_prev]))
        if kf_new in T_old and kf_new in T_new:
            xi_new = _se3_log(T_new[kf_new] @ torch.linalg.inv(T_old[kf_new]))
        span = max(kf_new - kf_prev, 1)
        for f in range(kf_prev + 1, kf_new):
            cam = cameras.get(f)
            if cam is None:
                continue
            s = (f - kf_prev) / span
            xi = (1.0 - s) * xi_prev + s * xi_new
            if float(torch.norm(xi)) < 1e-9:
                continue
            Tf = _se3_exp(xi) @ _get_Tcw(cam, self.device)
            cam.update_RT(Tf[:3, :3].contiguous(), Tf[:3, 3].contiguous())
