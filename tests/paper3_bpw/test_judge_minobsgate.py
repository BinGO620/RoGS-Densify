"""MinObsGate 判读器门禁单测（prereg §3 四出口机械可判）。"""
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/paper3_bpw/judge_minobsgate.py"
N = 580


def _run(base, seed, ate, gauss, psnr=None):
    d = base / f"seed_{seed}" / f"2026-01-01-00-00-{seed:02d}"
    d.mkdir(parents=True, exist_ok=True)
    ps = f"{psnr}" if psnr is not None else "nan"
    (d / "tracking_raw.csv").write_text(
        "method,run_id,status,ate_rmse_cm\n"
        f"X,{d.name},OK,{ate}\n")
    (d / "efficiency_raw.csv").write_text(
        "method,run_id,online_num_gaussians\n"
        f"X,{d.name},{gauss}\n")
    (d / "mapping_raw.csv").write_text(
        "method,psnr\n"
        f"X,{ps}\n")
    with (d / "per_frame_ape.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_id", "ape_cm"])
        for i in range(N):
            w.writerow([i, 1.0])
    (d / "instrument_run1_seed0.done").write_text(
        f"arm=x\nrc=0\nfinished_rc0=yes\n")
    return d


def _judge(off, on):
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--off-root", str(off), "--on-root", str(on)],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_positive_candidate(tmp_path):
    """M1 负向 + M2 干净 + M3 过 ⇒ POSITIVE_CANDIDATE。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 9.0), (10.5, 9.3), (11.0, 9.9)]):
        _run(off, s, a, 50000, psnr=29.0)
        _run(on, s, b, 51000, psnr=29.2)   # 比率 ~1.02 干净，PSNR 略升
    assert "POSITIVE_CANDIDATE" in _judge(off, on)


def test_negative_closed(tmp_path):
    """M1 过但方向正 ⇒ CLOSED_NEGATIVE。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 11.0), (10.5, 11.6), (11.0, 12.0)]):
        _run(off, s, a, 50000, psnr=29.0)
        _run(on, s, b, 50000, psnr=29.0)
    assert "CLOSED_NEGATIVE" in _judge(off, on)


def test_budget_confound(tmp_path):
    """M1 负向但高斯比超 10% ⇒ BUDGET_CONFOUND。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 9.0), (10.5, 9.3), (11.0, 9.9)]):
        _run(off, s, a, 50000, psnr=29.0)
        _run(on, s, b, 40000, psnr=29.0)   # 比率 0.8，混杂
    assert "BUDGET_CONFOUND" in _judge(off, on)


def test_no_effect_closed(tmp_path):
    """三 seed 异号 ⇒ M1 不过 ⇒ CLOSED_NO_EFFECT。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 9.0), (10.0, 11.0), (10.0, 9.5)]):
        _run(off, s, a, 50000, psnr=29.0)
        _run(on, s, b, 50000, psnr=29.0)
    assert "CLOSED_NO_EFFECT" in _judge(off, on)


def test_tradeoff_on_psnr_crash(tmp_path):
    """M1 负向但 on PSNR 崩 >0.5dB ⇒ TRADEOFF。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 9.0), (10.5, 9.3), (11.0, 9.9)]):
        _run(off, s, a, 50000, psnr=29.0)
        _run(on, s, b, 50000, psnr=27.5)   # 掉 1.5dB
    assert "TRADEOFF" in _judge(off, on)


def test_incomplete_run_invalid(tmp_path):
    """rc!=0 的 run 不得当数据。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s in range(3):
        _run(off, s, 10.0, 50000, psnr=29.0)
        _run(on, s, 9.0, 50000, psnr=29.0)
    bad = _run(on, 0, 5.0, 50000, psnr=30.0)
    (bad / "instrument_run1_seed0.done").write_text("arm=x\nrc=1\nfinished_rc0=no\n")
    assert "INVALID" in _judge(off, on)
