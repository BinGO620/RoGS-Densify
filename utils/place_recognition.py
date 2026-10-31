"""NetVLAD place-recognition backend for loop-closure appearance retrieval
(submap_lcd M1, LCD-Splat route).

Checkpoint: Patch-NetVLAD base NetVLAD (VGG16 encoder, Pitts30k training,
WPCA-4096 head), MIT license, HuggingFace TobiasRobotics/Patch-NetVLAD
(pitts_WPCA4096.pth.tar). Architecture and preprocessing follow
QVPR/Patch-NetVLAD (models_generic.py / tools/datasets.py): torchvision
VGG16 features up to conv5_3, NetVLAD pooling (64 clusters, per-descriptor
L2 norm = Relja preL2, intra-norm, final L2), 1x1-conv WPCA whitening;
input resize 640x480 + ImageNet normalization.

Config keys (LoopClosure section): app_backend="netvlad", netvlad_ckpt
(path to the .pth.tar), netvlad_sim_thresh (cosine threshold — calibrate
once, freeze for all sequences, DISCIPLINE #8).

Brand stance: tracking layer stays prior-free; this backend only feeds the
loop-closure retrieval channel (mature retrieval component allowed there).
"""
import hashlib
import os

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# Patch-NetVLAD input contract (their tools/datasets.py)
RESIZE_H, RESIZE_W = 480, 640
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class NetVLADPool(nn.Module):
    """NetVLAD pooling, inference form of QVPR/Patch-NetVLAD netvlad.py
    (no faiss/sklearn — those are only needed for from-scratch init)."""

    def __init__(self, num_clusters=64, dim=512):
        super().__init__()
        self.num_clusters = num_clusters
        self.dim = dim
        self.conv = nn.Conv2d(dim, num_clusters, kernel_size=(1, 1), bias=False)
        self.centroids = nn.Parameter(torch.rand(num_clusters, dim))

    def forward(self, x):
        N, C = x.shape[:2]
        x = F.normalize(x, p=2, dim=1)  # preL2 (per-descriptor, Relja)
        soft_assign = F.softmax(self.conv(x).view(N, self.num_clusters, -1), dim=1)
        x_flatten = x.view(N, C, -1)
        # residuals vs centroids, cluster loop (memory-lean: materializing
        # (N, K, C, P) at once is ~2.3GB for 16 frames at 480x640)
        vlad = x.new_zeros(N, self.num_clusters, C)
        for c in range(self.num_clusters):
            residual = x_flatten - self.centroids[c].unsqueeze(-1)
            residual = residual * soft_assign[:, c:c + 1, :]
            vlad[:, c, :] = residual.sum(dim=-1)
        vlad = F.normalize(vlad, p=2, dim=2)  # intra-normalization
        vlad = vlad.view(x.size(0), -1)
        return F.normalize(vlad, p=2, dim=1)  # final L2


def _build_model():
    import torchvision

    enc = torchvision.models.vgg16(weights=None).features[:-2]
    pool = NetVLADPool(num_clusters=64, dim=512)
    wpca = nn.Sequential(nn.Conv2d(64 * 512, 4096, kernel_size=(1, 1)), nn.Flatten())
    model = nn.Module()
    model.add_module("encoder", enc)
    model.add_module("pool", pool)
    model.add_module("WPCA", wpca)
    return model


def _load_state_dict(model, ckpt_path):
    ckpt = torch.load(ckpt_path, map_location="cpu")
    state = ckpt.get("state_dict", ckpt)
    state = { (k[len("module."):] if k.startswith("module.") else k): v
              for k, v in state.items() }
    # their WPCA is Sequential(conv, flatten): keys WPCA.0.*; ours matches
    missing, unexpected = model.load_state_dict(state, strict=False)
    loadable = {"encoder", "pool", "WPCA"}
    real_missing = [k for k in missing if k.split(".")[0] in loadable]
    if real_missing:
        raise RuntimeError(
            f"NetVLAD checkpoint load failed, missing keys: {real_missing[:8]}..."
        )
    if unexpected:
        raise RuntimeError(
            f"NetVLAD checkpoint has unexpected keys: {unexpected[:8]}..."
        )


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class NetVLADBackend:
    """Lazy-loaded NetVLAD descriptor extractor. Missing checkpoint is a hard
    error (no silent fallback to the thumbnail backend)."""

    def __init__(self, ckpt_path, device="cuda:0"):
        if not os.path.isfile(ckpt_path):
            raise FileNotFoundError(
                f"NetVLAD checkpoint not found: {ckpt_path} — download "
                "pitts_WPCA4096.pth.tar (HF TobiasRobotics/Patch-NetVLAD) to "
                "this path, see results/submap_lcd/README.md"
            )
        self.ckpt_path = ckpt_path
        self.device = device
        model = _build_model()
        _load_state_dict(model, ckpt_path)
        model.eval().to(device)
        self.model = model
        for p in self.model.parameters():
            p.requires_grad_(False)
        self.sha256 = _sha256(ckpt_path)

    def _preprocess(self, image, static_weight):
        """image: (3,H,W) float RGB in [0,1] (MonoGS original_image);
        static_weight: (H,W) in [0,1], 0 on dynamic pixels (like the masked
        thumbnail channel)."""
        img = image * static_weight
        mean = torch.tensor(IMAGENET_MEAN, device=img.device).view(3, 1, 1)
        std = torch.tensor(IMAGENET_STD, device=img.device).view(3, 1, 1)
        img = (img - mean) / std
        if img.shape[-2:] != (RESIZE_H, RESIZE_W):
            img = F.interpolate(
                img.unsqueeze(0), size=(RESIZE_H, RESIZE_W), mode="bilinear",
                align_corners=False,
            ).squeeze(0)
        return img

    @torch.no_grad()
    def model_forward(self, batch):
        """NetVLAD descriptors for an ALREADY-normalized image batch
        (N,3,H,W) — used by the threshold calibration script whose
        preprocessing mirrors _preprocess but needs no static weights."""
        feat = self.model.encoder(batch)
        vlad = self.model.pool(feat)
        desc = self.model.WPCA(vlad.unsqueeze(-1).unsqueeze(-1))
        return F.normalize(desc, dim=1)

    @torch.no_grad()
    def describe_batch(self, images, static_weights):
        """images: list of (3,H,W); returns (N, 4096) float32, L2-normalized."""
        batch = torch.stack([self._preprocess(im, w) for im, w in
                             zip(images, static_weights)]).to(self.device)
        feat = self.model.encoder(batch)
        vlad = self.model.pool(feat)
        desc = self.model.WPCA(vlad.unsqueeze(-1).unsqueeze(-1))
        return F.normalize(desc, dim=1).float().cpu().numpy()

    def describe(self, image, static_weight):
        return self.describe_batch([image], [static_weight])[0]


def find_loop_candidates_netvlad(cameras, kfs, cfg, device="cuda:0"):
    """Drop-in replacement for loop_closure.find_loop_candidates using
    NetVLAD global descriptors as the appearance channel.

    Mask semantics mirror _masked_gray_thumb: dynamic pixels (if the camera
    retained a mask) are zeroed so movers do not contribute to place
    identity. Config keys: netvlad_ckpt (required), netvlad_sim_thresh,
    min_gap, max_loops_per_kf. Returns the same (i, j, score) contract,
    plus a one-line diagnostic log (round brackets — rich Console mangles
    square ones).
    """
    from utils.logging_utils import Log

    backend = _shared_backend(cfg, device)
    ks = [k for k in kfs
          if getattr(cameras[k], "original_image", None) is not None]
    descs = {}
    batch = 16
    for s in range(0, len(ks), batch):
        chunk = ks[s:s + batch]
        images = [cameras[k].original_image for k in chunk]
        weights = []
        for k in chunk:
            h, w = images[len(weights)].shape[1:]
            mask = getattr(cameras[k], "dynamic_mask", None)
            if mask is None:
                weights.append(torch.ones(h, w, device=images[len(weights)].device))
            else:
                m = mask.detach().float()
                if m.dim() == 3:
                    m = m.squeeze(0)
                weights.append(1.0 - m)
        out = backend.describe_batch(images, weights)
        for k, d in zip(chunk, out):
            if np.isfinite(d).all():
                descs[k] = d
    Log(f"LoopClosure netvlad (backend ckpt sha256 {backend.sha256[:12]}): "
        f"{len(descs)}/{len(kfs)} KFs described")
    return candidates_from_descriptors(
        descs, kfs,
        min_gap=int(cfg.get("min_gap", 25)),
        sim_thresh=float(cfg.get("netvlad_sim_thresh", 0.5)),
        max_loops_per_kf=int(cfg.get("max_loops_per_kf", 3)),
    )


_SHARED_BACKEND = {}


def _shared_backend(cfg, device):
    """One backend instance per (ckpt, device) per process — the VLAD model
    is ~600MB on GPU and loop closure runs once per sequence."""
    key = (os.path.abspath(cfg["netvlad_ckpt"]), str(device))
    if key not in _SHARED_BACKEND:
        _SHARED_BACKEND[key] = NetVLADBackend(cfg["netvlad_ckpt"], device=device)
    return _SHARED_BACKEND[key]


def candidates_from_descriptors(descs, kfs, min_gap=25, sim_thresh=0.5,
                                max_loops_per_kf=3):
    """Same (i, j, score) contract and semantics as
    loop_closure.find_loop_candidates: i/j are KF indices, j > i + min_gap,
    score >= sim_thresh, each KF i keeps its best `max_loops_per_kf`
    partners, dedup per pair, sorted by score descending.

    descs: dict {kf_index: L2-normalized descriptor vector}.
    """
    usable = [k for k in kfs if k in descs]
    if len(usable) < 2:
        return []
    D = np.stack([np.asarray(descs[k], dtype=np.float32) for k in usable])
    sims = D @ D.T
    pairs = []
    for a_idx, i in enumerate(usable):
        best = []
        for b_idx, j in enumerate(usable):
            if j <= i + min_gap:
                continue
            sim = float(sims[a_idx, b_idx])
            if sim >= sim_thresh:
                best.append((sim, i, j))
        best.sort(reverse=True)
        pairs.extend(best[:max_loops_per_kf])
    # deduplicate (keep highest similarity per pair)
    seen = {}
    for sim, i, j in pairs:
        key = (i, j)
        if key not in seen or sim > seen[key]:
            seen[key] = sim
    return sorted(((i, j, s) for (i, j), s in seen.items()), key=lambda x: -x[2])
