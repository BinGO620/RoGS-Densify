"""MaskStat 仪器判读器的门禁单测（P3-D2-031）。

守护 prereg §3.2 的四类出口必须机械可判，且**不得**把
「run 还没跑完」误当成数据。
"""
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/paper3_bpw/judge_maskstat_instrument.py"
N = 580


def _run(base: Path, seed: int, ate: float, gauss: int, frames: int = N):
    d = base / f"seed_{seed}" / f"2026-01-01-00-00-{seed:02d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tracking_raw.csv").write_text(
        "method,run_id,source_dir,status,notes,ate_rmse_cm,ate_error_std_cm,"
        "rpe_trans_rmse_cm,keyframe_ate_rmse_cm\n"
        f"X,{d.name},x,OK,n,{ate},0.4,1.3,{ate}\n")
    (d / "efficiency_raw.csv").write_text(
        "method,run_id,source_dir,num_gaussians,mapping_iterations\n"
        f"X,{d.name},x,{gauss},2000\n")
    with (d / "per_frame_ape.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_id", "uid", "is_keyframe", "dist_to_nearest_kf", "mask_coverage", "ape_cm"])
        for i in range(frames):
            w.writerow([i, i, 1 if i % 5 == 0 else 0, 0, 0.1, 1.0])
    return d


def _judge(off: Path, on: Path, seeds):
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--off-root", str(off), "--on-root", str(on),
         "--seeds", *map(str, seeds)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_directional_effect(tmp_path):
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 9.0), (10.5, 9.2), (11.0, 9.8)]):
        _run(off, s, a, 20000)
        _run(on, s, b, 19000)
    assert "DIRECTIONAL_EFFECT" in _judge(off, on, [0, 1, 2])


def test_below_claim_floor(tmp_path):
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 9.9), (10.5, 10.4), (11.0, 10.9)]):
        _run(off, s, a, 20000)
        _run(on, s, b, 20000)
    assert "BELOW_CLAIM_FLOOR" in _judge(off, on, [0, 1, 2])


def test_seed_unstable(tmp_path):
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 8.0), (10.0, 12.0), (10.0, 8.5)]):
        _run(off, s, a, 20000)
        _run(on, s, b, 20000)
    assert "SEED_UNSTABLE" in _judge(off, on, [0, 1, 2])


def test_incomplete_run_is_not_data(tmp_path):
    """未跑完的 run（无 per_frame_ape.csv）不得被当成数据。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s in range(3):
        _run(off, s, 10.0, 20000)
        _run(on, s, 9.0, 20000)
    # 在 on 臂 seed0 塞一个只有 console.log 的未完成 run（目录名更大 ⇒ 是「最新」）
    half = on / "seed_0" / "2026-12-31-23-59-00"
    half.mkdir(parents=True)
    (half / "console.log").write_text("running...\n")
    assert "DIRECTIONAL_EFFECT" in _judge(off, on, [0, 1, 2])


def test_short_run_is_not_full_length(tmp_path):
    """40 帧的探针 run 不得冒充全长（帧数闸）。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s in range(3):
        _run(off, s, 10.0, 20000, frames=40)
        _run(on, s, 9.0, 20000, frames=40)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--off-root", str(off), "--on-root", str(on),
         "--seeds", "0", "1", "2"], capture_output=True, text=True)
    assert "INSTRUMENT_INVALID" in out.stdout
    assert out.returncode == 2, "INVALID 必须 rc=2（fail-closed，2026-11-07 起）"


def test_rc_nonzero_run_is_excluded_even_with_full_frames(tmp_path):
    """rc!=0 的 run 不得因「帧数恰好 580」而被当成数据（2026-11-05 OOM 回归）。

    真实事件：instrument_maskstat_on seed0 在 KF430 因 2060 显存耗尽退出（rc=1），
    runner 当时仍写了 .done。若只看帧数，一个刚好在末帧前 OOM 的 run 会混入判读。
    """
    off, on = tmp_path / "off", tmp_path / "on"
    for s in range(3):
        _run(off, s, 10.0, 20000)
        _run(on, s, 9.0, 20000)
    # seed0 换成 rc=1 的「完整帧数」run，且目录名最新（会被优先选中）
    bad = _run(on, 0, 5.0, 20000)
    (bad / "instrument_run1_seed0.done").write_text(
        "arm=instrument_maskstat_on\nstage=instrument\nrun=1\nseed=0\n"
        "rc=1\nelapsed_s=2888\nmax_frames=0\nfinished_rc0=no\n")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--off-root", str(off), "--on-root", str(on),
         "--seeds", "0", "1", "2"], capture_output=True, text=True)
    assert "INSTRUMENT_INVALID" in out.stdout, "rc!=0 的 run 必须被判无效"
    assert "rc=1" in out.stdout, "报错须指明是 rc!=0 的 run"
    assert out.returncode == 2, "INVALID 必须 rc=2（fail-closed，2026-11-07 起）"


def test_rc_zero_done_marker_is_accepted(tmp_path):
    """finished_rc0=yes 的 run 正常参与判读（正对照，防把闸门做成一律拒绝）。"""
    off, on = tmp_path / "off", tmp_path / "on"
    for s, (a, b) in enumerate([(10.0, 9.0), (10.5, 9.2), (11.0, 9.8)]):
        _run(off, s, a, 20000)
        d = _run(on, s, b, 19000)
        (d / f"instrument_run1_seed{s}.done").write_text(
            f"arm=instrument_maskstat_on\nstage=instrument\nrun=1\nseed={s}\n"
            "rc=0\nelapsed_s=1800\nmax_frames=0\nfinished_rc0=yes\n")
    assert "DIRECTIONAL_EFFECT" in _judge(off, on, [0, 1, 2])


# ───── 2026-11-07 crowd L2 回归：帧数期望必须随序列变（--expect-frames）─────
def test_expect_frames_flag_accepts_crowd_length(tmp_path):
    """928 帧 run + --expect-frames 928 ⇒ 正常判读（非 INVALID）。

    事件：判读器曾硬编码 580 ⇒ crowd 全长 928 帧 run（全 rc0）被误判
    INSTRUMENT_INVALID，整批判读被阻塞一轮。
    """
    off, on = tmp_path / "off", tmp_path / "on"
    _run(off, 0, 3.4, 24000, frames=928)
    _run(on, 0, 3.1, 23000, frames=928)   # Δ0 = -0.3
    _run(off, 1, 3.4, 24000, frames=928)
    _run(on, 1, 3.7, 23000, frames=928)   # Δ1 = +0.3（异号）
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--off-root", str(off), "--on-root", str(on),
         "--seeds", "0", "1", "--expect-frames", "928"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "SEED_UNSTABLE" in out.stdout   # Δ 异号 ⇒ SEED_UNSTABLE
    assert "INVALID" not in out.stdout


def test_default_580_rejects_928_frame_runs(tmp_path):
    """不带 flag（默认 580）面对 928 帧 run ⇒ INVALID（旧行为的守护性回归）。

    这条钉住的是「默认值向后兼容」：pt 族判读不受影响，且不会静默放过
    帧数不符的 run。INVALID 退出码 = 2（fail-closed，与 judge_dose 族一致）。
    """
    off, on = tmp_path / "off", tmp_path / "on"
    for s in (0, 1):
        _run(off, s, 3.4, 24000, frames=928)
        _run(on, s, 3.1, 23000, frames=928)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--off-root", str(off), "--on-root", str(on),
         "--seeds", "0", "1"], capture_output=True, text=True)
    assert "INSTRUMENT_INVALID" in out.stdout
    assert out.returncode == 2, "INVALID 必须 rc=2（fail-closed）"
