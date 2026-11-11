"""剂量轴反向扫：配置契约 + 判读器门禁单测（prereg_dose_reverse_2026-11-06）。

守护：
  ① **单变量**：tau2x / tau4x 仪器臂与 off 臂的解析后配置只在 `densify_grad_threshold`
     （+ save_dir / inherit_from）上不同；**`percent_dense` 必须保持基线 0.01**
     （这是本件与 A4 的关键区别——A4 把 pd 抬到 0.02，本件不动 pd，剂量只经阈值通道变化）。
  ② **仪器开关齐全**。
  ③ **判据常数与 prereg 一致**：0.5cm 地板、ratio 带 [0.5, 1.5]、PSNR 降 ≤0.5dB、580 帧。
  ④ **出口机械路由**（含 6 条负对照，其中 ratio 双侧与 PSNR 闸是本件新增防守）。
  ⑤ **汇合出口优先级定死**（MONOTONE 先于 BOTH_SIDES_WORSE，两条有包含关系）。
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG_DIR = ROOT / "configs/experiments/paper3_bpw"
JUDGE = ROOT / "scripts/paper3_bpw/judge_dose_scan.py"
N = 580

CLAIM_FLOOR_CM = 0.5
RATIO_LO = 0.5
RATIO_HI = 1.5
PSNR_DROP_DB = 0.5


def _resolved(name):
    sys.path.insert(0, str(ROOT))
    from utils.config_utils import load_config

    return load_config(str(CFG_DIR / f"{name}.yaml"))


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat(v, key))
        else:
            out[key] = v
    return out


ALLOWED_DIFF = {"opt_params.densify_grad_threshold", "Results.save_dir", "inherit_from"}


# ─────────────────── ① 单变量（核心）───────────────────
@pytest.mark.parametrize("arm,grad", [("instrument_dose_tau2x_person_tracking", 0.0004),
                                      ("instrument_dose_tau4x_person_tracking", 0.0008)])
def test_reverse_arm_is_single_variable(arm, grad):
    """反向臂 vs off：差异集合恰为 grad 阈值 + 两条路径键；pd 必须不动。"""
    off = _flat(_resolved("instrument_maskstat_off"))
    a = _flat(_resolved(arm))
    diff = {k for k in set(off) | set(a) if off.get(k) != a.get(k)}
    assert diff == ALLOWED_DIFF, (
        f"{arm} 非单变量！额外差异: {sorted(diff - ALLOWED_DIFF)}")
    assert a["opt_params.densify_grad_threshold"] == pytest.approx(grad)
    # 关键：percent_dense 必须保持基线（本件与 A4 的区别就在此）
    assert a["opt_params.percent_dense"] == pytest.approx(off["opt_params.percent_dense"]), \
        "percent_dense 被动过 —— 那就不再是纯 grad 轴，与 A4 无法区分"
    assert a["opt_params.percent_dense"] == pytest.approx(0.01)


@pytest.mark.parametrize("arm", ["instrument_dose_tau2x_person_tracking",
                                 "instrument_dose_tau4x_person_tracking"])
def test_reverse_arm_has_no_mechanism(arm):
    c = _resolved(arm)
    assert c["SelectiveDensification"]["enabled"] is False
    assert (c.get("Mapping") or {}).get("maskstat_dens_stats", False) is False
    assert (c.get("E2") or {}).get("trace_events", False) is False
    assert (c.get("MissStreak") or {}).get("enabled", False) is False


# ─────────────────── ② 仪器开关 ───────────────────
@pytest.mark.parametrize("arm", ["instrument_dose_tau2x_person_tracking",
                                 "instrument_dose_tau4x_person_tracking"])
def test_instrument_switches(arm):
    c = yaml.safe_load((CFG_DIR / f"{arm}.yaml").read_text())
    assert c["Training"]["single_thread"] is True
    assert c["Dataset"]["single_thread"] is True
    assert c["Rasterizer"]["deterministic_backward"] is True
    assert set(c) <= {"inherit_from", "Training", "Dataset", "Rasterizer", "Results"}, set(c)


# ─────────────────── ③ 判据常数 ───────────────────
def test_judge_constants_match_prereg():
    txt = JUDGE.read_text()
    assert f"CLAIM_FLOOR_CM = {CLAIM_FLOOR_CM}" in txt
    assert f"RATIO_LO = {RATIO_LO}" in txt
    assert f"RATIO_HI = {RATIO_HI}" in txt
    assert f"PSNR_DROP_DB = {PSNR_DROP_DB}" in txt
    assert "N_FRAMES_EXPECTED = 580" in txt


# ─────────────────── ④/⑤ 出口路由 ───────────────────
def _run(base, seed, ate, gauss, psnr=28.5, refined=None, rc0="yes"):
    """写一个 run 目录。**mapping_raw.csv 必须写成真实管线的两行格式**
    （`full` 行 + `static` 行）：判读器按 `mask_type` 选行，单行 fixture 会让
    PSNR 闸静默失效（2026-11-06 本条测试就是因此漏过闸）。
    真实管线里 `full` 行的 psnr 恒为 nan —— fixture 也照此写，别把 full 写成有值。
    """
    d = base / f"seed_{seed}" / f"2026-01-01-00-00-{seed:02d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tracking_raw.csv").write_text(
        "method,run_id,status,ate_rmse_cm\n"
        f"X,{d.name},OK,{ate}\n")
    (d / "efficiency_raw.csv").write_text(
        "method,run_id,online_num_gaussians,refined_num_gaussians\n"
        f"X,{d.name},{gauss},{refined if refined is not None else gauss}\n")
    (d / "mapping_raw.csv").write_text(
        "method,run_id,mask_type,psnr,depth_l1_cm\n"
        f"X,{d.name},full,nan,MISSING\n"
        f"X,{d.name},static,{psnr},23.5\n")
    with (d / "per_frame_ape.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_id", "ape_cm"])
        for i in range(N):
            w.writerow([i, 1.0])
    (d / "instrument_run1_seed0.done").write_text(
        f"arm=x\nrc={0 if rc0 == 'yes' else 1}\nfinished_rc0={rc0}\n")
    return d


def _judge(off, arms):
    cmd = [sys.executable, str(JUDGE), "--off-root", str(off),
           "--seeds", "0", "1", "2"]
    for name, path in arms.items():
        cmd += ["--arm", f"{name}={path}"]
    return subprocess.run(cmd, capture_output=True, text=True)


def _verdict_line(stdout):
    for line in stdout.splitlines():
        if line.startswith("JOINT VERDICT: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(f"无 JOINT VERDICT:\n{stdout}")


def _verdict_line_arm(stdout, arm):
    """取某臂的出口名（`=== arm <name>: VERDICT ===` 行）。"""
    marker = f"=== arm {arm}: "
    for line in stdout.splitlines():
        if line.startswith(marker):
            return line[len(marker):].rstrip(" =")
    raise AssertionError(f"无 arm {arm} 出口行:\n{stdout}")


def _setup(tmp_path, off_triples, arm_triples, arm_dir):
    for s, (oa, og, ops) in enumerate(off_triples):
        _run(tmp_path / "off", s, oa, og, psnr=ops)
    for s, (aa, ag, aps) in enumerate(arm_triples):
        _run(arm_dir, s, aa, ag, psnr=aps)


OFF_T = [(13.6, 50000, 28.5), (13.9, 46000, 28.8), (13.7, 51000, 28.5)]


def test_exit_positive_default_overdosed(tmp_path):
    """ATE 改善 + ratio 在带内 + PSNR 不掉 ⇒ POSITIVE_DEFAULT_OVERDOSED。"""
    _setup(tmp_path, OFF_T, [(11.0, 25000, 28.5), (11.5, 23000, 28.8),
                             (11.2, 25500, 28.5)], tmp_path / "tau2x")
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x"})
    assert r.returncode == 0, r.stderr
    assert _verdict_line_arm(r.stdout, "tau2x") == "POSITIVE_DEFAULT_OVERDOSED"


def test_exit_ratio_too_low_is_confound(tmp_path):
    """**本件新增防守**：ATE 改善但高斯数塌到 0.5× 以下 ⇒ DOSE_CONFOUND（不是正面）。"""
    _setup(tmp_path, OFF_T, [(11.0, 10000, 28.5), (11.5, 9000, 28.8),
                             (11.2, 10000, 28.5)], tmp_path / "tau2x")   # ratio ≈ 0.2
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x"})
    assert _verdict_line_arm(r.stdout, "tau2x") == "DOSE_CONFOUND"
    assert "地图可能退化" in r.stdout


def test_exit_ratio_too_high_is_confound(tmp_path):
    """ratio 超过 1.5 ⇒ DOSE_CONFOUND（沿用 A4 的上界）。"""
    _setup(tmp_path, OFF_T, [(11.0, 150000, 28.5), (11.5, 140000, 28.8),
                             (11.2, 160000, 28.5)], tmp_path / "tau2x")
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x"})
    assert _verdict_line_arm(r.stdout, "tau2x") == "DOSE_CONFOUND"


def test_exit_psnr_drop_blocks_positive(tmp_path):
    """ATE 改善 + ratio 正常，但 static PSNR 掉 1dB ⇒ DOSE_CONFOUND。"""
    _setup(tmp_path, OFF_T, [(11.0, 25000, 27.5), (11.5, 23000, 27.8),
                             (11.2, 25500, 27.5)], tmp_path / "tau2x")
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x"})
    assert _verdict_line_arm(r.stdout, "tau2x") == "DOSE_CONFOUND"
    assert "PSNR" in r.stdout


def test_exit_below_claim_floor(tmp_path):
    _setup(tmp_path, OFF_T, [(13.3, 48000, 28.5), (13.6, 44000, 28.8),
                             (13.5, 49000, 28.5)], tmp_path / "tau2x")
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x"})
    assert _verdict_line_arm(r.stdout, "tau2x") == "BELOW_CLAIM_FLOOR"


def test_exit_seed_unstable(tmp_path):
    _setup(tmp_path, OFF_T, [(10.0, 48000, 28.5), (15.0, 44000, 28.8),
                             (12.0, 49000, 28.5)], tmp_path / "tau2x")
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x"})
    assert _verdict_line_arm(r.stdout, "tau2x") == "SEED_UNSTABLE"


def test_exit_missing_rc_anchor_invalid(tmp_path):
    _setup(tmp_path, OFF_T, [(11.0, 25000, 28.5), (11.5, 23000, 28.8),
                             (11.2, 25500, 28.5)], tmp_path / "tau2x")
    for p in (tmp_path / "tau2x" / "seed_1").rglob("instrument_*.done"):
        p.unlink()
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x"})
    assert _verdict_line_arm(r.stdout, "tau2x") == "INSTRUMENT_INVALID"


def test_joint_both_sides_worse(tmp_path):
    """两臂都 WORSE 但**不单调**（tau4x 更差的程度轻于 tau2x）⇒ BOTH_SIDES_WORSE。

    注意：若同时满足单调（越低越差），则按 §3.3 优先级走 MONOTONE_WORSE_DOWN
    （见下一条测试）。本条刻意构造非单调，才能孤立测到 BOTH_SIDES_WORSE。
    """
    _setup(tmp_path, OFF_T, [(16.0, 45000, 28.5), (16.5, 41000, 28.8),
                             (16.2, 46000, 28.5)], tmp_path / "tau2x")   # med ≈ +2.5（更差）
    _setup(tmp_path, OFF_T, [(14.7, 40000, 28.5), (15.0, 37000, 28.8),
                             (14.8, 41000, 28.5)], tmp_path / "tau4x")   # med ≈ +1.0（也差但轻）
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x",
                                  "tau4x": tmp_path / "tau4x"})
    assert _verdict_line(r.stdout) == "BOTH_SIDES_WORSE"


def test_joint_monotone_precedes_both_worse(tmp_path):
    """**优先级**：两臂都 WORSE 且越低越差 ⇒ MONOTONE_WORSE_DOWN（不是 BOTH_SIDES_WORSE）。"""
    _setup(tmp_path, OFF_T, [(15.0, 45000, 28.5), (15.5, 41000, 28.8),
                             (15.2, 46000, 28.5)], tmp_path / "tau2x")   # med ≈ +1.4
    _setup(tmp_path, OFF_T, [(17.0, 40000, 28.5), (17.5, 37000, 28.8),
                             (17.2, 41000, 28.5)], tmp_path / "tau4x")   # med ≈ +3.4（更差）
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x",
                                  "tau4x": tmp_path / "tau4x"})
    assert _verdict_line(r.stdout) == "MONOTONE_WORSE_DOWN"


def test_joint_down_side_has_effect(tmp_path):
    """tau2x 判正面 ⇒ DOWN_SIDE_HAS_EFFECT（覆盖两臂均 WORSE 的路由）。"""
    _setup(tmp_path, OFF_T, [(11.0, 25000, 28.5), (11.5, 23000, 28.8),
                             (11.2, 25500, 28.5)], tmp_path / "tau2x")
    _setup(tmp_path, OFF_T, [(16.0, 40000, 28.5), (16.5, 37000, 28.8),
                             (16.2, 41000, 28.5)], tmp_path / "tau4x")
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x",
                                  "tau4x": tmp_path / "tau4x"})
    assert _verdict_line(r.stdout) == "DOWN_SIDE_HAS_EFFECT"


def test_json_keys(tmp_path):
    """prereg §7 声明的机械键必须真出现（呈现层与判据不得脱钩）。"""
    _setup(tmp_path, OFF_T, [(15.0, 45000, 28.5), (15.5, 41000, 28.8),
                             (15.2, 46000, 28.5)], tmp_path / "tau2x")
    out = tmp_path / "j.json"
    r = _judge(tmp_path / "off", {"tau2x": tmp_path / "tau2x"})
    cmd = [sys.executable, str(JUDGE), "--off-root", str(tmp_path / "off"),
           "--seeds", "0", "1", "2", "--arm", f"tau2x={tmp_path / 'tau2x'}",
           "--out", str(out)]
    subprocess.run(cmd, capture_output=True, text=True)
    rep = json.loads(out.read_text())
    for key in ("per_arm", "joint_verdict", "claim_floor_cm",
                "gauss_ratio_band", "psnr_drop_cap_db", "n_frames_expected"):
        assert key in rep, f"缺机械键 {key}"
    arm = rep["per_arm"]["tau2x"]
    for key in ("verdict", "median_delta_ate_cm", "same_sign", "min_gauss_ratio",
                "max_gauss_ratio", "max_psnr_drop_db", "per_seed"):
        assert key in arm, f"缺臂级机械键 {key}"
    assert rep["gauss_ratio_band"] == [RATIO_LO, RATIO_HI]
