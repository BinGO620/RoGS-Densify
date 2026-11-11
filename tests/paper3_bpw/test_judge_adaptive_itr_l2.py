"""Adaptive itr L2 判读器测试（Amd A3 §2，P3-D2-047 提名的确认批）。

守护：① 四出口机械路由（SIGN_UNSTABLE 优先 / CONFIRMED / CONFIRMED_TRADEOFF /
DIRECTION_ONLY）；② 前置门 fail-closed（缺 seed / 缺 .done / C 臂机制未触发）；
③ 渲染代价闸的两条触发路径（PSNR 掉 / depth L1 劣化）；④ 判据常数与 A3 一致。
判读路由走真实 main()（subprocess）。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts/paper3_bpw/judge_adaptive_itr_l2.py"
N = 580
EARLY, LATE, THRESHOLD = 30, 50, 8


def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)] + [",".join(map(str, r)) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_run(root, arm, seed, ts, ate, iters, *, frames=N, schedule=None,
              static_psnr=29.0, static_dl1=20.0):
    """构造 rc0 全长 run。schedule=None ⇒ 按臂推断（C 开/A-B 关）。"""
    d = Path(root) / f"seed_{seed}" / ts
    d.mkdir(parents=True, exist_ok=True)
    _write_csv(d / "per_frame_ape.csv", ["frame", "ape_cm"],
               [[i, 1.0] for i in range(frames)])
    _write_csv(d / "tracking_raw.csv", ["ate_rmse_cm"], [[ate]])
    _write_csv(d / "efficiency_raw.csv",
               ["online_num_gaussians", "mapping_iterations", "mapping_calls"],
               [[50000, iters, 231]])
    _write_csv(d / "mapping_raw.csv",
               ["mask_type", "psnr", "depth_l1_cm"],
               [["full", "nan", "nan"], ["static", static_psnr, static_dl1]])
    if schedule is None:
        schedule = arm.startswith("adaptive")
    lines = ["MonoGS: Initialized map"]
    if schedule:
        calls = 114
        for i in range(calls):
            o = 2 + i
            itr = EARLY if o <= THRESHOLD else LATE
            lines.append(f"MonoGS: adaptive_itr KF#{o} (frame {5*o}) itr={itr}")
    (d / "console.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    early = sum(1 for i in range(114) if 2 + i <= THRESHOLD) if schedule else 0
    late = (114 - early) if schedule else 0
    (d / "backend_timing.json").write_text(json.dumps({
        "mapping_iterations": iters, "mapping_calls": 231,
        "adaptive_itr_early_calls": early, "adaptive_itr_late_calls": late,
    }), encoding="utf-8")
    cfg = ["save_dir: placeholder", "Mapping:"]
    if schedule:
        cfg += ["  adaptive_itr:", "    enabled: true", f"    itr_early: {EARLY}",
                f"    itr_late: {LATE}", f"    kf_threshold: {THRESHOLD}"]
    else:
        cfg += ["  lifecycle_mode: prune"]
    (d / "config.yml").write_text("\n".join(cfg) + "\n", encoding="utf-8")
    for f in ("plot/stats_final.json", "plot/trj_final.json", "plot/trj_full_final.json"):
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_text('{"same": 1}', encoding="utf-8")
    for f in ("deferred_commit_events.csv", "reliability_signal/frames.csv"):
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_text("x\n1\n", encoding="utf-8")
    (d / f"instrument_run1_seed{seed}.done").write_text(
        f"arm={arm}\nseed={seed}\nrc=0\nfinished_rc0=yes\nhead=deadbeef\n",
        encoding="utf-8")
    return d.name


def _tree(tmp_path, b_ate, c_ate, *, b_psnr=29.0, b_dl1=20.0,
          c_psnr=29.0, c_dl1=20.0, seeds=(0, 1, 2), drop=None, c_no_mech=False):
    b_root, c_root = tmp_path / "b", tmp_path / "c"
    for s in seeds:
        if drop and ("b" in drop) and s in drop["b"]:
            continue
        _make_run(b_root, "itrsweep50_maskstat_off", s, f"2026-11-10-0{s}-00-00",
                  b_ate[s], 6915, schedule=False,
                  static_psnr=b_psnr, static_dl1=b_dl1)
        if drop and ("c" in drop) and s in drop["c"]:
            continue
        _make_run(c_root, "adaptive_itr_person_tracking", s, f"2026-11-10-1{s}-00-00",
                  c_ate[s], 6775, schedule=(False if c_no_mech else None),
                  static_psnr=c_psnr, static_dl1=c_dl1)
    return b_root, c_root


def _run(tmp_path, roots, out_name="judge.json"):
    b_root, c_root = roots
    out = tmp_path / out_name
    proc = subprocess.run(
        [sys.executable, str(JUDGE), "--b-root", str(b_root), "--c-root", str(c_root),
         "--seeds", "0", "1", "2", "--out", str(out)],
        capture_output=True, text=True, timeout=120)
    rep = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return proc, rep


# ─────────────────── 出口路由 ───────────────────
def test_l2_confirmed(tmp_path):
    """三 seed 全负 ∧ median −0.83 ≤ −0.5 ∧ 渲染中性 ⇒ L2_CONFIRMED。"""
    roots = _tree(tmp_path, b_ate={0: 10.66, 1: 10.90, 2: 11.27},
                  c_ate={0: 9.83, 1: 10.07, 2: 10.44})
    proc, rep = _run(tmp_path, roots)
    assert proc.returncode == 0, rep
    assert rep["verdict"] == "L2_CONFIRMED", rep
    assert rep["median_delta_ate_cm"] == -0.83
    assert rep["render_report"]["tradeoff_triggered"] is False


def test_l2_sign_unstable_routes_first(tmp_path):
    """任两 seed 异号 ⇒ L2_SIGN_UNSTABLE（即使中位超地板）。"""
    roots = _tree(tmp_path, b_ate={0: 10.66, 1: 10.90, 2: 11.27},
                  c_ate={0: 9.83, 1: 11.50, 2: 10.44})   # seed1 翻正
    proc, rep = _run(tmp_path, roots)
    assert rep["verdict"] == "L2_SIGN_UNSTABLE"
    assert rep["reasons"][0].startswith("Δ 跨 seed 异号")


def test_l2_direction_only_when_below_floor(tmp_path):
    roots = _tree(tmp_path, b_ate={0: 10.66, 1: 10.90, 2: 11.27},
                  c_ate={0: 10.56, 1: 10.80, 2: 11.17})   # Δ = −0.10
    proc, rep = _run(tmp_path, roots)
    assert rep["verdict"] == "L2_DIRECTION_ONLY"


def test_l2_confirmed_tradeoff_on_psnr(tmp_path):
    """ATE 达标但 C 的 PSNR 中位掉 >0.5dB ⇒ TRADEOFF。"""
    roots = _tree(tmp_path, b_ate={0: 10.66, 1: 10.90, 2: 11.27},
                  c_ate={0: 9.83, 1: 10.07, 2: 10.44},
                  b_psnr=29.0, c_psnr=28.3)               # −0.7dB
    proc, rep = _run(tmp_path, roots)
    assert rep["verdict"] == "L2_CONFIRMED_TRADEOFF"
    assert rep["render_report"]["tradeoff_triggered"] is True


def test_l2_confirmed_tradeoff_on_depth(tmp_path):
    roots = _tree(tmp_path, b_ate={0: 10.66, 1: 10.90, 2: 11.27},
                  c_ate={0: 9.83, 1: 10.07, 2: 10.44},
                  b_dl1=20.0, c_dl1=21.2)                 # +1.2cm
    proc, rep = _run(tmp_path, roots)
    assert rep["verdict"] == "L2_CONFIRMED_TRADEOFF"


# ─────────────────── 前置门 fail-closed ───────────────────
def test_invalid_when_seed_missing(tmp_path):
    roots = _tree(tmp_path, b_ate={0: 10.66, 1: 10.90, 2: 11.27},
                  c_ate={0: 9.83, 1: 10.07, 2: 10.44}, drop={"b": {2}})
    proc, rep = _run(tmp_path, roots)
    assert proc.returncode == 2
    assert rep["verdict"] == "L2_INSTRUMENT_INVALID"
    assert any("seed2" in r for r in rep["reasons"])


def test_invalid_when_c_mech_not_fired(tmp_path):
    """C 臂机制未触发（config 未启用或 backend 计数全 0）⇒ INVALID（机制门随行）。"""
    roots = _tree(tmp_path, b_ate={0: 10.66, 1: 10.90, 2: 11.27},
                  c_ate={0: 9.83, 1: 10.07, 2: 10.44}, c_no_mech=True)
    proc, rep = _run(tmp_path, roots)
    assert proc.returncode == 2
    assert rep["verdict"] == "L2_INSTRUMENT_INVALID"
    assert any("机制未触发" in r or "未启用" in r for r in rep["reasons"])


def test_invalid_when_seed_set_wrong(tmp_path):
    roots = _tree(tmp_path, b_ate={0: 10.66, 1: 10.90, 2: 11.27},
                  c_ate={0: 9.83, 1: 10.07, 2: 10.44})
    b_root, c_root = roots
    out = tmp_path / "j.json"
    proc = subprocess.run(
        [sys.executable, str(JUDGE), "--b-root", str(b_root), "--c-root", str(c_root),
         "--seeds", "0", "1", "--out", str(out)], capture_output=True, text=True)
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert proc.returncode == 2 and rep["verdict"] == "L2_INSTRUMENT_INVALID"


# ─────────────────── 判据常数 ───────────────────
def test_judge_constants_match_a3():
    txt = JUDGE.read_text()
    assert "PSNR_TRADEOFF_DB = 0.5" in txt
    assert "DEPTH_TRADEOFF_CM = 1.0" in txt
    assert "CLAIM_FLOOR_CM = 0.5" in txt
    assert "SEEDS_EXPECTED = (0, 1, 2)" in txt
