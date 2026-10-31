"""MASt3R matching-based loop-closure verification (submap_lcd M2).

Replaces the frozen photometric verifier for candidate loop pairs:
MASt3R dense reciprocal matches survive the appearance/viewpoint drift that
killed photometric verification on long-gap revisits (R18: 0/40 verified;
M2 smoke: E-matrix rotation recovered to sub-degree on exactly those pairs).

Route per pair (both orders of inference):
  1. MASt3R inference (a,b) and (b,a): per-view SELF pointmaps are
     geometry-sane (unlike the cross-view regression, which collapses to
     identity on Bonn pairs — see evidence/incubation_m1.md).
  2. fast_reciprocal_NNs on the two pointmaps -> pixel matches.
  3. Gate A: essential-matrix RANSAC with the known K -> inliers (2D
     geometric consistency, depth-free).
  4. Metric pose: 3D-3D Umeyama on sensor-depth deprojected matches
     (cam.depth — same depth the SLAM already consumes; no new prior) ->
     T_ba (cam_b frame -> cam_a frame), with inlier/residual stats.

Config keys (LoopClosure): verifier="mast3r", mast3r_ckpt, mast3r_min_matches,
mast3r_min_ema_inliers... threshold provenance: calibrated on pt1 positives
(GT revisits) vs negatives (non-revisit pairs), frozen across sequences.
"""
import os
import sys
import tempfile

import numpy as np
import torch
import cv2

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in ("submodules/dust3r", "submodules/dust3r/croco", "submodules/mast3r"):
    _full = os.path.join(_REPO_ROOT, _p)
    if os.path.isdir(_full) and _full not in sys.path:
        sys.path.insert(0, _full)

_SHARED = {}


def _shared_model(ckpt_path, device):
    key = (os.path.abspath(ckpt_path), str(device))
    if key not in _SHARED:
        from mast3r.model import AsymmetricMASt3R
        model = AsymmetricMASt3R.from_pretrained(ckpt_path).to(device)
        model.eval()
        for p in model.parameters():
            p.requires_grad_(False)
        _SHARED[key] = model
    return _SHARED[key]


def _cam_to_bgr_png(cam, tmpdir, name):
    """Save cam.original_image (3,H,W RGB [0,1]) as a PNG for dust3r
    load_images (byte-identical preprocessing to the smoke route)."""
    img = cam.original_image.detach().clamp(0, 1).cpu().numpy()
    rgb8 = (img.transpose(1, 2, 0) * 255).astype(np.uint8)
    path = os.path.join(tmpdir, name)
    cv2.imwrite(path, cv2.cvtColor(rgb8, cv2.COLOR_RGB2BGR))
    return path


def _depth_np(cam, H, W):
    d = getattr(cam, "depth", None)
    if d is None:
        return None
    if torch.is_tensor(d):
        d = d.detach().cpu().float().numpy()
    d = np.asarray(d, dtype=np.float32).squeeze()
    if d.shape != (H, W):
        d = cv2.resize(d, (W, H), interpolation=cv2.INTER_NEAREST)
    d = d.copy()
    d[d <= 0] = np.nan
    dyn = getattr(cam, "dynamic_mask", None)
    if dyn is not None:  # movers: RGB changed, depth did not — kill them
        m = dyn.detach().cpu().float().numpy().squeeze()
        if m.shape != (H, W):
            m = cv2.resize(m, (W, H), interpolation=cv2.INTER_NEAREST)
        d[m > 0.5] = np.nan
    return d


def verify_pair_mast3r(cam_i, cam_j, Tcw_i, K, dist, cfg, device, label=""):
    """MASt3R verification of one candidate loop pair.

    Returns {"T_j": 4x4 torch (refined cam_j-to-world), "n_inliers",
    "median_resid"} on success, None on rejection — same contract as
    loop_closure.verify_loop_edge.
    """
    from dust3r.image_pairs import make_pairs
    from dust3r.inference import inference
    from dust3r.utils.image import load_images
    from mast3r.fast_nn import fast_reciprocal_NNs

    model = _shared_model(cfg["mast3r_ckpt"], device)
    min_matches = int(cfg.get("mast3r_min_matches", 100))
    min_inliers = int(cfg.get("mast3r_min_inliers", 150))
    max_resid = float(cfg.get("mast3r_max_resid_m", 0.10))

    with tempfile.TemporaryDirectory() as tmpdir:
        path_i = _cam_to_bgr_png(cam_i, tmpdir, "a.png")
        path_j = _cam_to_bgr_png(cam_j, tmpdir, "b.png")
        imgs = load_images([path_i, path_j], size=512, verbose=False)
    pair = make_pairs([imgs[0], imgs[1]], symmetrize=False)
    try:
        out = inference(pair, model, device, batch_size=1, verbose=False)
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        if label:
            print(f"MASt3R verify {label}: CUDA OOM at inference, reject pair")
        return None
    pred_i, pred_j = out["pred1"], out["pred2"]

    xy_i, xy_j = fast_reciprocal_NNs(
        pred_i["pts3d"][0].to(device), pred_j["pts3d_in_other_view"][0].to(device),
        subsample_or_initxy1=8, ret_xy=True, device=device)
    xy_i = xy_i.cpu().numpy() if torch.is_tensor(xy_i) else np.asarray(xy_i)
    xy_j = xy_j.cpu().numpy() if torch.is_tensor(xy_j) else np.asarray(xy_j)
    if len(xy_i) < min_matches:
        if label:
            print(f"MASt3R verify {label}: {len(xy_i)} matches < {min_matches}, reject")
        return None

    # gate A: essential-matrix consistency of the 2D matches (depth-free).
    # K is native-resolution; the MASt3R grid is the resized one.
    Hr, Wr = pred_i["pts3d"][0].shape[:2]
    Hn, Wn = cam_i.original_image.shape[1:]
    Ks = K.copy()
    Ks[0, 0] *= Wr / Wn
    Ks[1, 1] *= Hr / Hn
    Ks[0, 2] *= Wr / Wn
    Ks[1, 2] *= Hr / Hn
    E, mask_e = cv2.findEssentialMat(
        xy_i.astype(np.float32), xy_j.astype(np.float32), Ks,
        method=cv2.RANSAC, prob=0.999, threshold=1.0)
    if E is None or mask_e is None or int(mask_e.sum()) < min_inliers:
        n_e = int(mask_e.sum()) if mask_e is not None else 0
        if label:
            print(f"MASt3R verify {label}: E-inliers {n_e} < {min_inliers}, reject")
        return None
    # keep ONLY the E-RANSAC inlier subset — the raw reciprocal matches
    # contain enough wrong pairs to poison the 3D-3D fit (E-rotation is
    # sub-degree on the inliers; full-set Umeyama diverges)
    xy_i = xy_i[mask_e.reshape(-1).astype(bool)]
    xy_j = xy_j[mask_e.reshape(-1).astype(bool)]

    # metric pose: 3D-3D Umeyama on sensor-depth deprojected matches.
    # Match pixels live on the RESIZED grid; sensor depth is NATIVE —
    # map pixels back to the native grid and deproject with the native K.
    Hi, Wi = cam_i.original_image.shape[1:]
    Hj, Wj = cam_j.original_image.shape[1:]
    di = _depth_np(cam_i, Hi, Wi)
    dj = _depth_np(cam_j, Hj, Wj)
    if di is None or dj is None:
        if label:
            print(f"MASt3R verify {label}: no sensor depth, reject")
        return None
    si = np.array([Wn / Wr, Hn / Hr])
    sj = si  # both views share the resized grid
    xy_i_n = xy_i * si
    xy_j_n = xy_j * sj
    x1i = np.clip(xy_i_n[:, 0], 0, Wi - 1).astype(int)
    y1i = np.clip(xy_i_n[:, 1], 0, Hi - 1).astype(int)
    x2i = np.clip(xy_j_n[:, 0], 0, Wj - 1).astype(int)
    y2i = np.clip(xy_j_n[:, 1], 0, Hj - 1).astype(int)
    zi, zj = di[y1i, x1i], dj[y2i, x2i]
    valid = np.isfinite(zi) & np.isfinite(zj) & (zi > 0.1) & (zj > 0.1)
    zi = np.clip(zi, 0.1, 20.0)
    zj = np.clip(zj, 0.1, 20.0)
    if valid.sum() < min_inliers:
        if label:
            print(f"MASt3R verify {label}: depth-valid {int(valid.sum())} < {min_inliers}, reject")
        return None
    Xa = np.stack([(xy_i_n[valid, 0] - K[0, 2]) / K[0, 0] * zi[valid],
                   (xy_i_n[valid, 1] - K[1, 2]) / K[1, 1] * zi[valid],
                   zi[valid]], -1)
    Xb = np.stack([(xy_j_n[valid, 0] - K[0, 2]) / K[0, 0] * zj[valid],
                   (xy_j_n[valid, 1] - K[1, 2]) / K[1, 1] * zj[valid],
                   zj[valid]], -1)

    # Umeyama b->a with adaptive-threshold trimmed refinement
    def _umeyama(src, dst):
        mu_s, mu_d = src.mean(0), dst.mean(0)
        Hm = (src - mu_s).T @ (dst - mu_d) / len(src)
        U, S, Vt = np.linalg.svd(Hm)
        d = np.sign(np.linalg.det(Vt.T @ U.T))
        R = Vt.T @ np.diag([1, 1, d]) @ U.T
        t = mu_d - R @ mu_s
        return R, t

    src, dst = Xb, Xa
    try:
        R, t = _umeyama(src, dst)
    except np.linalg.LinAlgError:
        if label:
            print(f"MASt3R verify {label}: umeyama SVD failure, reject")
        return None
    resid = np.linalg.norm(src @ R.T + t - dst, axis=1)
    thr = max(3.0 * np.median(resid), 0.05)
    for _ in range(4):
        keep = resid <= thr
        if keep.sum() < 8:
            break
        try:
            R, t = _umeyama(src[keep], dst[keep])
        except np.linalg.LinAlgError:
            break
        resid = np.linalg.norm(src @ R.T + t - dst, axis=1)
        thr = max(3.0 * np.median(resid[keep]), 0.05)
    inliers = resid <= max(thr, max_resid)
    n_inl = int(inliers.sum())
    med = float(np.median(resid[inliers])) if n_inl else float("inf")
    if n_inl < min_inliers or med > max_resid:
        if label:
            print(f"MASt3R verify {label}: umeyama inliers {n_inl} med {med*100:.1f}cm "
                  f"(gates {min_inliers}/{max_resid*100:.0f}cm), reject")
        return None

    # T_ba (cam_b frame -> cam_a frame); contract wants refined Tcw_j:
    # X_world = Tcw_i X_a = Tcw_i T_ba X_b  =>  Tcw_j = Tcw_i @ T_ba
    T_ba = np.eye(4)
    T_ba[:3, :3], T_ba[:3, 3] = R, t
    Tcw_i_np = Tcw_i.detach().cpu().numpy()
    Tcw_j = Tcw_i_np @ T_ba
    if label:
        print(f"MASt3R verify {label}: ACCEPT matches {len(xy_i)} E-inl "
              f"{int(mask_e.sum())} umeyama-inl {n_inl} med {med*100:.1f}cm")
    return {"T_j": torch.from_numpy(Tcw_j).float().to(Tcw_i.device),
            "n_inliers": n_inl, "median_resid": med}
