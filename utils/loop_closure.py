"""R15: lightweight loop closure layer on top of SWBA (no pretrained models).

Design (2026-09-05, after R13/R14 exhausted the SWBA parameter space):

LCD-Splat (Sensors 2026) showed loop closure + pose-graph optimization
reaches 1.1/1.3cm on the person_tracking family with a lightweight stack.
Our route goes one step lighter: ZERO new pretrained models.

  1. Loop CANDIDATE retrieval: per-keyframe global descriptor from masked
     grayscale thumbnails (person mask excluded). We already have the mask
     (SemanticMask), the grayscale (dba_lite `_gray_from_color`), and the
     KF cameras retain RGB. Similarity = cosine over downsampled masked
     histograms. Candidates = high-similarity pairs with large index gap.
  2. Loop CONSTRAINT verification: reuse the SWBA/DBALite photometric
     edge machinery (frozen inlier set, anchor-only affine, analytic
     two-sided jacobians) to compute a verified relative pose between the
     candidate pair. Low inlier count or high residual -> reject.
  3. Graph optimization: KF pose graph with odometry edges (window SWBA
     already provides short-baseline consistency) + verified loop edges,
     optimized by the same GN+line-search solver, gauge-fixed on KF0.
     Corrections write back to frontend cameras (SWBA's proven channel).

Why this works where post-hoc DBALite failed (R1-R8): those edges were
TEMPORAL (short = blind, long = contaminated). Loop edges are
GEOMETRICALLY VERIFIED re-observations of the SAME place — the residual
is computed on the same machinery but between frames that genuinely
overlap, so the drift is observable by construction.

Scope (minimal viable R15):
  - Runs at sequence end (offline pass over the KF chain) — online
    detection is a later optimization, correctness first.
  - Default-off (``LoopClosure.enabled``).
"""

import math
import os

import torch
import torch.nn.functional as F

from gaussian_splatting.utils.graphics_utils import getWorld2View2
from utils.coarse_pose import _se3_exp
from utils.dba_lite import _se3_log
from utils.swba import _edge_frozen, build_kf_geom
from utils.logging_utils import Log


def get_loop_config(config):
    return config.get("LoopClosure", {})


def appearance_backend(cfg):
    """Retrieval backend selector: "thumb" (default, masked 32x32 grayscale
    thumbnail) or "netvlad" (submap_lcd M1, Patch-NetVLAD descriptors).
    Unknown values fail loudly — silent fallbacks broke exp51 once already."""
    backend = str(cfg.get("app_backend", "thumb")).lower()
    if backend not in ("thumb", "netvlad"):
        raise ValueError(f"unknown LoopClosure.app_backend: {backend}")
    return backend


def loop_closure_enabled(config):
    return bool(get_loop_config(config).get("enabled", False))


def _masked_gray_thumb(cam, size=32, device="cpu"):
    """Masked grayscale thumbnail as a retrieval descriptor.

    Person mask (if the camera retained one) is zeroed so movers do not
    contribute to place identity. Returns a flattened L2-normalized
    histogram-of-gradients-free descriptor (raw downsampled intensities
    suffice for indoor revisits at this scale).
    """
    color = getattr(cam, "original_image", None)
    if color is None:
        return None
    g = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]  # (H,W)
    mask = getattr(cam, "dynamic_mask", None)
    if mask is not None:
        m = mask.detach().to(g.device).float()
        if m.dim() == 3:
            m = m.squeeze(0)
        g = g * (1.0 - m)
    t = F.interpolate(g[None, None], size=(size, size), mode="bilinear",
                      align_corners=False)[0, 0]
    t = t - t.mean()
    n = t.norm()
    if n < 1e-6:
        return None
    return (t / n).flatten().to(device)


def find_geometry_overlap_candidates(cameras, geoms, kfs, cfg, device="cpu"):
    """Viewpoint-free loop candidates.

    Two scoring regimes (config `geo_score_v3`):
      - v2 (default False): cloud-sphere intersection depth from cached KF
        point clouds (R17). Weakness found by the GT audit (diag4/r21b/r22):
        the camera-frame cloud centroid is polluted by person-mask and scene
        changes — a same-spot revisit whose mask moved scores ~0.8 and never
        reaches the quota, while big-sphere or mask-stable non-revisits rank
        first.
      - v3 (True): mask-independent co-location from the ESTIMATED poses —
        camera-center distance + heading-angle penalty. Drift inflates
        distances only by the (small) relative drift; non-revisits sit
        meters apart. Ranks true revisits first regardless of masks.
    """
    min_gap = int(cfg.get("min_gap", 30))
    max_per = int(cfg.get("max_loops_per_kf", 3))
    if bool(cfg.get("geo_score_v3", False)):
        from utils.dba_lite import _se3_log
        import torch as _t
        d0 = float(cfg.get("geo_dist_scale", 0.5))
        hw = float(cfg.get("geo_heading_weight", 1.0))
        centers, fwds = {}, {}
        for k in kfs:
            cam = cameras.get(k)
            if cam is None:
                continue
            T = getWorld2View2(cam.R, cam.T).to(device)
            R = T[:3, :3]
            centers[k] = (-R.T @ T[:3, 3]).to(device)
            fwds[k] = R[:, 2].to(device)  # camera +z (forward) in world
        usable = [k for k in kfs if k in centers]
        pairs = []
        for i in usable:
            best = []
            for j in usable:
                if j <= i + min_gap:
                    continue
                d = float((centers[i] - centers[j]).norm())
                cos_h = float(_t.clamp(fwds[i] @ fwds[j], -1.0, 1.0))
                score = math.exp(-d / d0) * (0.5 + 0.5 * cos_h) ** hw
                best.append((score, i, j))
            best.sort(reverse=True)
            pairs.extend(best[:max_per])
        seen = {}
        for score, i, j in pairs:
            if (i, j) not in seen or score > seen[(i, j)]:
                seen[(i, j)] = score
        out = sorted(((i, j, s) for (i, j), s in seen.items()), key=lambda x: -x[2])
        if bool(cfg.get("geo_cell_diversity", False)):
            # R24: a co-located KF CLUSTER (a stop/plateau where the camera
            # parks for many KFs) generates O(n^2) mutually-co-located pairs
            # that flood any fixed quota (r23-pt2: 82/160 slots to plateau
            # pairs) — redundant constraints from one place crowd out the
            # single useful early-revisit pair. Keep at most `geo_cell_cap`
            # candidates per `geo_cell_size` world-space cell of the camera
            # centers: a plateau shares 1-2 cells, a distant revisit gets
            # its own.
            cell = float(cfg.get("geo_cell_size", 0.5))
            cap = int(cfg.get("geo_cell_cap", 2))
            counts = {}
            kept = []
            for i, j, s in out:
                ki = tuple((centers[i] / cell).floor().long().tolist())
                kj = tuple((centers[j] / cell).floor().long().tolist())
                if counts.get(ki, 0) >= cap or counts.get(kj, 0) >= cap:
                    continue
                counts[ki] = counts.get(ki, 0) + 1
                counts[kj] = counts.get(kj, 0) + 1
                kept.append((i, j, s))
            out = kept
        if out:
            Log("LoopClosure geo-v3 top: "
                + ", ".join(f"{i}->{j}:{s:.3f}" for i, j, s in out[:8]))
        return out
    # v2: cloud-sphere intersection from cached geometry
    stats = {}
    for k in kfs:
        g = geoms.get(k)
        if g is None:
            continue
        pts = g["Ps"]  # camera-frame points
        # camera-frame centroid -> world via the pose the geom was built
        # with is not stored; instead use the norm of camera positions:
        # overlapping VIEWING VOLUMES approximated by |centroid| distance
        # plus radius — good enough as a loose pre-filter because the
        # verification re-projects with actual poses.
        c = pts.mean(dim=0)
        r = torch.quantile(pts.norm(dim=1), 0.95)
        stats[k] = (c, float(r))
    usable = [k for k in kfs if k in stats]
    pairs = []
    for i in usable:
        best = []
        ci, ri = stats[i]
        for j in usable:
            if j <= i + min_gap:
                continue
            cj, rj = stats[j]
            # spheres intersect when centroid distance < r_i + r_j
            if float((ci - cj).norm()) < ri + rj:
                # overlap score: intersection depth (larger = tighter)
                score = ri + rj - float((ci - cj).norm())
                if bool(cfg.get("geo_norm_score", False)):
                    # R21: raw depth rewards LARGE viewing volumes — a
                    # same-spot revisit of a close-up view (small r) loses to
                    # big-sphere non-revisits (GT audit: KF20->KF65, gt dist
                    # 1.6cm, crowded out by 135->253 at 8.58). Normalize to
                    # (0,1]: co-located pairs rank ~1.0 regardless of volume.
                    score = score / (ri + rj)
                best.append((score, i, j))
        best.sort(reverse=True)
        pairs.extend(best[:max_per])
    seen = {}
    for score, i, j in pairs:
        if (i, j) not in seen or score > seen[(i, j)]:
            seen[(i, j)] = score
    return sorted(((i, j, s) for (i, j), s in seen.items()), key=lambda x: -x[2])


def find_loop_candidates(cams, kfs, cfg, device="cpu"):
    """Candidate loop pairs (i, j) by masked-thumb cosine similarity.

    Rules: index gap >= min_gap (default 30 KFs); similarity >= sim_thresh
    (default 0.75); each KF pairs with at most its best `max_loops_per_kf`
    partners (default 1) to avoid dense redundant edges.
    """
    min_gap = int(cfg.get("min_gap", 30))
    sim_thresh = float(cfg.get("sim_thresh", 0.75))
    max_per = int(cfg.get("max_loops_per_kf", 1))
    descs = {}
    for k in kfs:
        d = _masked_gray_thumb(cams[k])
        if d is not None:
            descs[k] = d
    usable = [k for k in kfs if k in descs]
    pairs = []
    for a_idx, i in enumerate(usable):
        best = []
        for j in usable:
            if j <= i + min_gap:
                continue
            sim = float(descs[i] @ descs[j])
            if sim >= sim_thresh:
                best.append((sim, i, j))
        best.sort(reverse=True)
        pairs.extend(best[:max_per])
    # deduplicate (keep highest similarity per pair)
    seen = {}
    for sim, i, j in pairs:
        key = (i, j)
        if key not in seen or sim > seen[key]:
            seen[key] = sim
    return sorted(((i, j, s) for (i, j), s in seen.items()), key=lambda x: -x[2])


def _block_standardize_geom(g, grid):
    """R19: per-image blockwise intensity standardization for verification.

    R18 showed the verification wall: long-gap revisits carry appearance
    drift (auto-exposure jumps, viewing-angle shading) that the identity
    affine cannot absorb, so genuine early pairs die at the residual gate
    (0/40 verified) — and a large drift field even corrupts the GN pose
    refinement itself (the solver slides along the brightness field
    chasing photometric misfit; reproduced on the synthetic exposure-jump
    revisit).

    Fix: standardize EACH image blockwise (grid x grid pixel blocks;
    grid=1 means one global block) — subtract block mean, divide block
    std — BEFORE verification. Statistics come from the geom-valid pixels
    of each image's OWN grid only (the _valid mask: depth range + normal +
    depth-gradient + person-free); nothing is fit across the pair, so the
    spurious-minimum trap documented in _fit_affine_frame (brightness
    params fitted at drifted poses absorbing pose error) cannot apply.
    Global gain/offset cancels exactly; smooth spatial shading is
    attenuated up to block granularity. Known limitation for grid>1: the
    std-scaled gxygrid is not the exact gradient of the standardized image
    at block boundaries (exact for grid=1).

    Returns a shallow copy with standardized Is/graygrid (gxygrid rescaled
    by the same block std so Jacobians stay consistent with residuals); g
    unchanged when the geom is unusable for statistics.
    """
    grid_img = g.get("graygrid")
    if grid_img is None:
        return g
    hl, wl = g["hl"], g["wl"]
    eps = 1e-4
    dev = grid_img.device
    valid = g.get("_valid")
    if valid is None:
        valid = torch.ones(hl, wl, dtype=torch.bool, device=dev)
    flat = grid_img[0, 0].reshape(-1)
    vflat = valid.reshape(-1).to(flat.device)
    if int(vflat.sum()) < 32:
        return g  # degenerate stats — skip standardization rather than NaN

    if grid <= 1:
        # global standardization
        sel = flat[vflat]
        mean_b = sel.mean()[None]
        std_b = (sel.var(unbiased=False) + eps).sqrt()[None]
        mean_map = mean_b.expand(hl, wl)[None, None]
        std_map = std_b.expand(hl, wl)[None, None]
    else:
        by = (torch.arange(hl, device=dev) // max(hl // grid, 1)).clamp(max=grid - 1)
        bx = (torch.arange(wl, device=dev) // max(wl // grid, 1)).clamp(max=grid - 1)
        blk = by[:, None] * grid + bx[None, :]  # (hl, wl) block id per pixel
        nb = grid * grid
        idx_f = blk.reshape(-1)
        idx_v = idx_f[vflat]
        sum_b = torch.zeros(nb, device=dev).scatter_add_(0, idx_v, flat[vflat])
        sq_b = torch.zeros(nb, device=dev).scatter_add_(
            0, idx_v, (flat * flat)[vflat])
        cnt_b = torch.zeros(nb, device=dev).scatter_add_(
            0, idx_v, torch.ones(idx_v.shape[0], device=dev))
        mean_b = sum_b / cnt_b.clamp(min=1)
        var_b = (sq_b / cnt_b.clamp(min=1) - mean_b * mean_b).clamp(min=0)
        std_b = (var_b + eps).sqrt()
        mean_map = mean_b[idx_f].reshape(hl, wl)[None, None]
        std_map = std_b[idx_f].reshape(hl, wl)[None, None]

    g2 = dict(g)
    g2["graygrid"] = (grid_img - mean_map) / std_map
    if g.get("gxygrid") is not None:
        g2["gxygrid"] = g["gxygrid"] / std_map  # chain rule on the target grid
    if g.get("Is") is not None:
        # source points: standardize with the same per-image stats; block
        # membership from each point's OWN pixel (pose-independent)
        fx, fy, cx, cy = g["fx"], g["fy"], g["cx"], g["cy"]
        Pi = g["Ps"]
        z = Pi[:, 2]
        u = fx * Pi[:, 0] / z + cx
        v = fy * Pi[:, 1] / z + cy
        inb = ((u >= 0) & (u <= wl - 1) & (v >= 0) & (v <= hl - 1)
               & (z > g["min_d"]) & torch.isfinite(u) & torch.isfinite(v))
        if grid <= 1:
            g2["Is"] = torch.where(inb, (g["Is"] - mean_b[0]) / std_b[0],
                                   torch.zeros_like(g["Is"]))
        else:
            pb = ((v.clamp(0, hl - 1).long() // max(hl // grid, 1)).clamp(max=grid - 1) * grid
                  + (u.clamp(0, wl - 1).long() // max(wl // grid, 1)).clamp(max=grid - 1))
            pb = torch.where(inb, pb, torch.zeros_like(pb))
            Is = torch.where(inb, g["Is"], torch.zeros_like(g["Is"]))
            g2["Is"] = torch.where(inb, (Is - mean_b[pb]) / std_b[pb],
                                   torch.zeros_like(Is))
    return g2


def _icp_realign(geom_i, geom_j, Tcw_i, Tcw_j, cfg, device, label=""):
    """R20/R21 geometric pre-alignment for stage-2 verification.

    At a drifted pose the reprojection depth mismatch can empty the inlier
    set (R19 diagnostic: early pairs died AT FREEZE), so: (a) centroid
    bootstrap — translate the source cloud centroid onto the centroid of
    the target's valid observed surface (both in target cam frame;
    translation-dominated drift keeps rotation drift small); (b)
    point-to-plane GN (re-gated per iteration = standard ICP). The caller's
    photometric gate still decides acceptance — ICP only fixes the START.
    Returns the realigned Tcw_j (== input when the machinery finds nothing).
    """
    from utils.dba_lite import _edge_two_sided
    icp_cfg = dict(cfg)
    icp_cfg["depth_gate"] = float(cfg.get("icp_depth_gate", 0.30))
    icp_cfg["normal_deg"] = float(cfg.get("icp_normal_deg", 30.0))
    Tj_icp = Tcw_j.clone()
    if bool(cfg.get("icp_centroid_boot", True)):
        with torch.no_grad():
            R_ij0 = (Tcw_j @ torch.linalg.inv(Tcw_i))[:3, :3]
            P_src = geom_i["Ps"] @ R_ij0.T
            dgt = geom_j["dgrid"][0, 0]
            vs = (dgt > geom_j["min_d"]) & (dgt < geom_j["max_d"])
            if int(vs.sum()) > 50 and P_src.shape[0] > 50:
                hl, wl = dgt.shape
                fx, fy, cx, cy = (geom_j["fx"], geom_j["fy"],
                                  geom_j["cx"], geom_j["cy"])
                yy, xx = torch.meshgrid(torch.arange(hl, device=device),
                                        torch.arange(wl, device=device),
                                        indexing="ij")
                q = torch.stack([(xx[vs] - cx) / fx * dgt[vs],
                                 (yy[vs] - cy) / fy * dgt[vs],
                                 dgt[vs]], dim=-1)
                d = q.mean(0) - P_src.mean(0)
                T_shift = torch.eye(4, device=device)
                T_shift[:3, 3] = d
                T_ij = Tcw_j @ torch.linalg.inv(Tcw_i)
                Tj_icp = (T_shift @ T_ij) @ Tcw_i
                if label:
                    Log(f"LoopClosure icp-boot {label}: |d|="
                        f"{float(d.norm()):.3f}m")
    icp_iters = 0
    icp_last_n = -1
    icp_dx_total = 0.0
    for _ in range(int(cfg.get("icp_iters", 10))):
        gres = _edge_two_sided(geom_i, geom_j, Tcw_i, Tj_icp, icp_cfg, device)
        if gres is None:
            icp_last_n = -1
            break
        gr, _, gJj, gw = gres
        icp_last_n = int(gr.shape[0])
        icp_iters += 1
        gwe = gw / max(icp_last_n, 1)
        gg = gJj.T @ (gwe * gr)
        gH = (gJj * gwe[:, None]).T @ gJj
        reg = 1e-6 * float(gH.diagonal().clamp(min=1e-12).mean())
        try:
            gdx = -torch.linalg.solve(
                gH + reg * torch.eye(6, device=device), gg)
        except Exception:
            break
        Tj_icp = _se3_exp(gdx) @ Tj_icp
        icp_dx_total += float(gdx.norm())
        if float(gdx.norm()) < 1e-6:
            break
    if label:
        Log(f"LoopClosure icp {label}: iters={icp_iters} "
            f"last_n={icp_last_n} |dx|={icp_dx_total:.4f}")
    return Tj_icp


def verify_loop_edge(geom_i_raw, geom_j_raw, Tcw_i, Tcw_j, cfg, device, label=""):
    """Two-stage verification (R22).

    Stage 1 (plain): frozen photometric edge at the incoming pose — the
    R19b path that verifies well-aligned pairs (tail cluster) at med ~0.02.
    Stage 2 (only when stage 1 rejects and verify_icp_init): centroid
    bootstrap + point-to-plane ICP re-aligns T_j, then the SAME frozen
    verification retries from the aligned pose. r21b showed the bootstrap
    HURTS already-aligned pairs (tail med 0.023 -> 0.086), hence stage 2
    runs only on stage-1 rejects.

    Returns {"T_j", "n_inliers", "median_resid"} or None.
    """
    min_pts = int(cfg.get("min_points", 500))
    max_resid = float(cfg.get("max_median_resid", 0.02))
    geom_i, geom_j = geom_i_raw, geom_j_raw
    if bool(cfg.get("verify_block_affine", False)):
        # R19: blockwise appearance normalization on BOTH images before any
        # edge computation — freeze, GN refinement and the residual gate all
        # operate on standardized intensities.
        grid = int(cfg.get("affine_grid", 1))
        geom_i = _block_standardize_geom(geom_i_raw, grid)
        geom_j = _block_standardize_geom(geom_j_raw, grid)

    def _attempt(T_start, stage):
        edge_cfg = dict(cfg)
        edge_cfg["_affine"] = (1.0, 0.0)  # identity: long-gap pairs must NOT
        # fit exposure at the (possibly drifted) poses — same lesson as SWBA's
        # affine trap. A fixed identity leaves true exposure mismatch in the
        # residual, which the robust weights absorb.
        fz = _edge_frozen(geom_i, geom_j, Tcw_i, T_start, edge_cfg, device)
        if fz is None:
            Log(f"LoopClosure verify({stage}) {label}: "
                f"REJECT at freeze (gating below min_pts)")
            return None
        # small GN on j only (i fixed)
        T_i, T_j = Tcw_i, T_start.clone()
        lam = 1e-3
        for _ in range(int(cfg.get("verify_iters", 10))):
            res = _edge_frozen(geom_i, geom_j, T_i, T_j, edge_cfg, device, frozen=fz)
            if res is None:
                return None
            r, Ji, Jj, w = res
            we = w / max(int(r.shape[0]), 1)
            g = Jj.T @ (we * r)
            H = (Jj * we[:, None]).T @ Jj
            reg = lam * float(H.diagonal().clamp(min=1e-12).mean())
            try:
                dx = -torch.linalg.solve(H + reg * torch.eye(6, device=device), g)
            except Exception:
                return None
            t = 1.0
            improved = False
            Tn = None
            for _ in range(15):
                Tn = _se3_exp(dx * t) @ T_j
                rn = _edge_frozen(geom_i, geom_j, T_i, Tn, edge_cfg, device, frozen=fz)
                if rn is not None:
                    cn = float((rn[3] / max(int(rn[0].shape[0]), 1) * rn[0] * rn[0]).sum())
                    # compare against current cost
                    rcur = _edge_frozen(geom_i, geom_j, T_i, T_j, edge_cfg, device, frozen=fz)
                    cur = float((rcur[3] / max(int(rcur[0].shape[0]), 1) * rcur[0] * rcur[0]).sum())
                    if cn < cur:
                        improved = True
                        break
                t *= 0.5
            if not improved:
                break
            T_j = Tn
            if float(dx.norm()) * t < 1e-6:
                break
        # final residual check
        res = _edge_frozen(geom_i, geom_j, T_i, T_j, edge_cfg, device, frozen=fz)
        if res is None:
            return None
        r, _, _, w = res
        med = float(r.abs().median())
        if int(r.shape[0]) < min_pts or med > max_resid:
            # R19 diagnostic: rejected pairs carry their residual stats into
            # the console log — the next ladder rung is designed from this
            # distribution (med slightly above gate -> normalization shape
            # issue; med far above -> misalignment, not appearance).
            Log(f"LoopClosure verify({stage}) {label}: REJECT n={int(r.shape[0])} "
                f"med={med:.4f} (gate med<={max_resid} pts>={min_pts})")
            return None
        return {"T_j": T_j, "n_inliers": int(r.shape[0]), "median_resid": med}

    out = _attempt(Tcw_j, "plain")
    if out is not None:
        return out
    if bool(cfg.get("verify_icp_init", False)):
        Tj_icp = _icp_realign(geom_i, geom_j, Tcw_i, Tcw_j, cfg, device, label)
        out = _attempt(Tj_icp, "icp")
        if out is not None:
            return out
    return None


def optimize_pose_graph(cams, kfs, loop_edges, cfg, device):
    """KF pose graph: odometry chain edges (consecutive KFs, current
    relative poses as MEASUREMENTS) + verified loop edges (as constraints).
    GN+line-search over all KFs except KF0 (gauge). Odometry measurements
    anchor the local shape; loop edges pull the global layout.

    loop_edges: list of (i, j, verified_T_j) where verified_T_j is j's pose
    consistent with i's CURRENT pose (from verify_loop_edge).
    """
    n = len(kfs)
    if n < 3 or not loop_edges:
        return None
    idx = {k: t for t, k in enumerate(kfs)}
    T = [getWorld2View2(cams[k].R, cams[k].T).to(device) for k in kfs]

    # odometry measurements: consecutive relative transforms
    odo_meas = {}
    for t in range(n - 1):
        odo_meas[t] = T[t + 1] @ torch.linalg.inv(T[t])

    # Gauss-Seidel style: each sweep, per node (KF0 gauge-fixed), try
    # candidate poses derived from its incident edges (loop anchors);
    # keep the odometry-chain cost via _replace_cost. Converges for the
    # sparse loop topologies we accept (few verified edges).
    for sweep in range(int(cfg.get("graph_iters", 30))):
        changed = False
        for t in range(1, n):  # node 0 fixed
            best_T, best_c = T[t], _replace_cost(T, t, T[t], kfs, idx, odo_meas, loop_edges, cfg)
            # candidates: solve from loop edges
            for i, j, rel_v in loop_edges:
                if idx[i] == t:
                    c2 = rel_v @ T[idx[j]]
                    c_cost = _replace_cost(T, t, c2, kfs, idx, odo_meas, loop_edges, cfg)
                    if c_cost < best_c:
                        best_T, best_c = c2, c_cost
                if idx[j] == t:
                    c2 = T[idx[i]] @ torch.linalg.inv(rel_v)
                    c_cost = _replace_cost(T, t, c2, kfs, idx, odo_meas, loop_edges, cfg)
                    if c_cost < best_c:
                        best_T, best_c = c2, c_cost
            if not torch.allclose(best_T, T[t]):
                T[t] = best_T
                changed = True
        if not changed:
            break
    return T


def _replace_cost(T, t, cand, kfs, idx, odo_meas, loop_edges, cfg):
    """cost() with node t replaced by cand (for Gauss-Seidel steps)."""
    states = list(T)
    states[t] = cand
    c = 0.0
    n = len(states)
    for u in range(n - 1):
        rel = states[u + 1] @ torch.linalg.inv(states[u])
        d = _se3_log(rel @ torch.linalg.inv(odo_meas[u]))
        c += float((d * d).sum())
    for i, j, rel_verified in loop_edges:
        rel = states[idx[j]] @ torch.linalg.inv(states[idx[i]])
        d = _se3_log(rel @ torch.linalg.inv(rel_verified))
        c += float((d * d).sum()) * float(cfg.get("loop_weight", 10.0))
    return c


def run_loop_closure(cameras, kf_indices, dataset, config):
    """Entry point (offline, at sequence end before final export).

    Mirrors run_dba_v0's contract: writes optimized poses into
    ``cameras`` via update_RT so the exported trajectory reflects them.
    Default-off (``LoopClosure.enabled``).
    """
    cfg = dict(get_loop_config(config))
    for k, v in (("stride", 4), ("min_depth", 0.05), ("max_depth", 5.0),
                 ("grad_thresh", 0.02), ("min_points", 500),
                 ("depth_gate", 0.10), ("min_gap", 30),
                 ("sim_thresh", 0.75), ("max_loops_per_kf", 1),
                 ("verify_iters", 10), ("max_median_resid", 0.02),
                 ("graph_iters", 30), ("loop_weight", 10.0),
                 ("app_candidates", 20), ("geo_candidates", 20),
                 ("verify_block_affine", False), ("affine_grid", 1),
                 ("verify_icp_init", False), ("icp_iters", 10),
                 ("icp_depth_gate", 0.30),
                 ("verifier", "photometric"),
                 ("mast3r_min_matches", 100), ("mast3r_min_inliers", 150),
                 ("mast3r_max_resid_m", 0.10),
                 ("device", "cuda:0")):
        cfg.setdefault(k, v)
    device = str(cfg["device"])
    kfs = sorted(int(k) for k in kf_indices if int(k) in cameras)
    if len(kfs) < 8:
        Log(f"LoopClosure: {len(kfs)} KFs < 8, skip")
        return

    # 1a. geometry for ALL KFs (needed by both the geometry-overlap channel
    # and the verification step)
    geom = {}
    for k in kfs:
        g = build_kf_geom(cameras[k], cfg, device)
        if g is not None and g["Ps"].shape[0] >= int(cfg["min_points"]):
            geom[k] = g
    missing = sorted(set(kfs) - set(geom))
    if missing:
        Log(f"LoopClosure geom missing ({len(missing)}): {missing[:20]}"
            f"{'...' if len(missing) > 20 else ''}")
    # 1b. candidates: TWO channels with SEPARATE caps. R17 lesson: merging
    # into one ranked list let geometry pairs (score clamped to 1.0) crowd
    # out every appearance pair — 40 candidates, 0 verified, including the
    # tail pairs that R16 verified fine. Per-channel quotas keep the proven
    # appearance throughput while the geometry channel probes for the
    # viewpoint-robust revisits.
    if appearance_backend(cfg) == "netvlad":
        from utils.place_recognition import find_loop_candidates_netvlad
        app_cands = find_loop_candidates_netvlad(cameras, kfs, cfg, device)
    else:
        app_cands = find_loop_candidates(cameras, kfs, cfg, device)
    geo_cands = find_geometry_overlap_candidates(cameras, geom, kfs, cfg, device)
    Log("LoopClosure app-cands: "
        + ", ".join(f"{i}->{j}:{s:.2f}" for i, j, s in app_cands[:12]))
    Log("LoopClosure geo-cands: "
        + ", ".join(f"{i}->{j}:{s:.2f}" for i, j, s in geo_cands[:12]))
    app_cap = int(cfg.get("app_candidates", 20))
    geo_cap = int(cfg.get("geo_candidates", 20))
    quota = {(i, j): sc for i, j, sc in app_cands[:app_cap]}
    for i, j, sc in geo_cands:
        if (i, j) not in quota and len(quota) < app_cap + geo_cap:
            quota[(i, j)] = min(sc, 1.0) * 0.99  # rank below appearance pairs
    cands = sorted(((i, j, s) for (i, j), s in quota.items()), key=lambda x: -x[2])
    if not cands:
        Log("LoopClosure: no candidates, skip")
        return
    # 3. verify (the candidate list is already quota-capped per channel)
    use_mast3r = str(cfg.get("verifier", "photometric")).lower() == "mast3r"
    if use_mast3r:
        import numpy as np
        from utils.mast3r_verify import verify_pair_mast3r
        if not cfg.get("mast3r_ckpt"):
            raise ValueError("LoopClosure.verifier=mast3r requires mast3r_ckpt")
        calib = config["Dataset"]["Calibration"]
        K = np.array([[calib["fx"], 0, calib["cx"]],
                      [0, calib["fy"], calib["cy"]], [0, 0, 1]], dtype=np.float64)
        dist = np.array([calib.get("k1", 0), calib.get("k2", 0),
                         calib.get("p1", 0), calib.get("p2", 0)], dtype=np.float64)
        Log("LoopClosure verifier: mast3r (ckpt "
            + os.path.basename(str(cfg["mast3r_ckpt"])) + ")")
    verified = []
    for i, j, sim in cands:
        if i not in geom or j not in geom:
            continue
        Ti = getWorld2View2(cameras[i].R, cameras[i].T).to(device)
        Tj = getWorld2View2(cameras[j].R, cameras[j].T).to(device)
        if use_mast3r:
            out = verify_pair_mast3r(cameras[i], cameras[j], Ti, K, dist,
                                     cfg, device, label=f"{i}->{j}")
        else:
            out = verify_loop_edge(geom[i], geom[j], Ti, Tj, cfg, device,
                                   label=f"{i}->{j}")
        if out is None:
            continue
        # verified RELATIVE transform (measurement for the graph)
        rel_v = out["T_j"] @ torch.linalg.inv(Ti)
        verified.append((i, j, rel_v, out))
    if not verified:
        Log(f"LoopClosure: {len(cands)} candidates, 0 verified, skip")
        return
    # 4. graph optimization
    loop_rel = [(i, j, rel) for i, j, rel, _ in verified]
    T_opt = optimize_pose_graph(cameras, kfs, loop_rel, cfg, device)
    if T_opt is None:
        return
    # 5. write back
    dts = []
    for t, k in enumerate(kfs):
        T_old = getWorld2View2(cameras[k].R, cameras[k].T).to(device)
        xi = _se3_log(T_opt[t] @ torch.linalg.inv(T_old))
        dts.append(float(torch.norm(xi[3:])))
        T = T_opt[t]
        cameras[k].update_RT(T[:3, :3].contiguous(), T[:3, 3].contiguous())
    Log(
        f"LoopClosure: {len(cands)} candidates -> {len(verified)} verified "
        f"({', '.join(f'{i}->{j}' for i, j, _, _ in verified[:4])}"
        f"{'...' if len(verified) > 4 else ''}); "
        f"corrections |dt| med {sorted(dts)[len(dts)//2]*100:.2f}cm "
        f"max {max(dts)*100:.2f}cm applied to {len(kfs)} KFs"
    )
