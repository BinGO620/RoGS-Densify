"""compare_three_way.py 的门禁单测（det-raster 2×2 引发的方法学修正）。

守护三件事：
  ① 易变列（run_id/source_dir/wall-clock）不影响判定 —— 否则「逐位一致」永远误报 R2；
  ② 两侧都不存在的判据件记为 N/A，不算 DIFF；一侧有一侧无才算 DIFF；
  ③ 真正的内容差异必须被抓到（负对照，防止掩蔽过度）。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/paper3_bpw/deterministic_probe/compare_three_way.py"


def _write_run(root: Path, ts: str, *, ate: str, gauss: str, ape: str, extra_col: str = ""):
    d = root / ts
    (d / "plot").mkdir(parents=True, exist_ok=True)
    hdr = "method,run_id,source_dir,ate_rmse_cm,num_gaussians,online_time_s,notes,extra\n"
    row = f"X,{ts},{d},{ate},{gauss},123.456,n,{extra_col}\n"
    (d / "tracking_raw.csv").write_text(hdr + row)
    (d / "efficiency_raw.csv").write_text(
        f"method,run_id,source_dir,online_fps,num_gaussians\nX,{ts},{d},0.24,{gauss}\n")
    (d / "mapping_raw.csv").write_text(f"method,run_id,source_dir,psnr\nX,{ts},{d},33.1\n")
    (d / "per_frame_ape.csv").write_text("frame_id,ape_cm\n" + ape)
    for name in ("stats_final", "trj_final", "trj_full_final"):
        (d / "plot" / f"{name}.json").write_text(json.dumps({"v": 1}))
    (d / "config.yml").write_text(f"seed: 0\nResults:\n  save_dir: {d}\n")


def _run(base: Path, a: str, b: str):
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", str(base), "--samples", a, b],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_volatile_columns_do_not_cause_divergence(tmp_path):
    """① 只有 run_id/source_dir/时间列不同 ⇒ 必须判 R1。"""
    _write_run(tmp_path, "runA", ate="1.1682", gauss="19771", ape="0,1.0\n1,2.0\n")
    _write_run(tmp_path, "runB", ate="1.1682", gauss="19771", ape="0,1.0\n1,2.0\n")
    out = _run(tmp_path, "runA", "runB")
    assert "R1_bitwise_identical" in out, out


def test_real_numeric_difference_is_caught(tmp_path):
    """③ 负对照：ATE / 高斯数 / 逐帧 APE 任一不同 ⇒ 必须判 R2。"""
    _write_run(tmp_path, "runA", ate="1.1682", gauss="19771", ape="0,1.0\n1,2.0\n")
    _write_run(tmp_path, "runB", ate="1.1720", gauss="19771", ape="0,1.0\n1,2.0\n")
    assert "R2_divergent" in _run(tmp_path, "runA", "runB")

    _write_run(tmp_path, "runC", ate="1.1682", gauss="19771", ape="0,1.0\n1,2.0\n")
    _write_run(tmp_path, "runD", ate="1.1682", gauss="25976", ape="0,1.0\n1,2.0\n")
    assert "R2_divergent" in _run(tmp_path, "runC", "runD")

    _write_run(tmp_path, "runE", ate="1.1682", gauss="19771", ape="0,1.0\n1,2.0\n")
    _write_run(tmp_path, "runF", ate="1.1682", gauss="19771", ape="0,1.0\n1,2.5\n")
    assert "R2_divergent" in _run(tmp_path, "runE", "runF")


def test_missing_both_sides_is_na_not_diff(tmp_path):
    """② 两侧都缺 lastrow 快照 ⇒ N/A，不得单独导致 R2。"""
    _write_run(tmp_path, "runA", ate="1.1682", gauss="19771", ape="0,1.0\n")
    _write_run(tmp_path, "runB", ate="1.1682", gauss="19771", ape="0,1.0\n")
    # 两个 run 都没有 detprobe_*_lastrow.txt
    assert not (tmp_path / "runA" / "detprobe_efficiency_raw_lastrow.txt").exists()
    assert "R1_bitwise_identical" in _run(tmp_path, "runA", "runB")
