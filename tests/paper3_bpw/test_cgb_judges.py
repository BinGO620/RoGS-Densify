#!/usr/bin/env python
"""test_cgb_judges.py — 两个判据机的门禁测试（纯 CPU，合成夹具）。

守护两件**判定类**事实（DISCIPLINE「测量口径」#12 可追溯 + exp32 判据设计教训）：

  J1 出口判定的机械性：四类出口（DOSE_HARMFUL / DOSE_MISMATCH / PLACEMENT_POSITIVE /
     PLACEMENT_NULL）必须各由一组构造好的读数**唯一**触发，不能有"两套读数同结论"。
  J2 帧数闸真的挡人：冒烟（40 帧）与全长（580 帧）混比必须被拒——它是本装置最容易
     犯的错（两者 ATE 差一个量级，混读会产生 −10cm 的假"改善"）。
  J3 机制门的方向不能被"写反"骗过：γ=1 与 γ=0 的 trace 对调后，G2 必须判失败。
  J4 机制门的剂量门是精确等式，不是近似。

用法: pytest tests/paper3_bpw/test_cgb_judges.py -v
"""
import csv
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO, "scripts", "paper3_bpw")


def _load(name):
    path = os.path.join(SCRIPTS, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


judge = _load("judge_cgb_l1")
gate = _load("check_cgb_gate")


# ─────────────────────────── 夹具 ───────────────────────────
def _write_run(root, ate_cm, gauss, frames, status="OK"):
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "tracking_raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["method", "sequence", "status", "ate_rmse_cm"])
        w.writerow(["Combined-Prune", "x", status, "%.4f" % ate_cm])
    with open(root / "efficiency_raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["status", "online_num_gaussians", "refined_num_gaussians", "num_frames"])
        w.writerow([status, gauss, gauss, frames])


def _run_judge(tmp_path, g1, g0, off):
    """跑判据机；返回 (rc, report)。**错误路径上不落 JSON**（判据机提前 return 2），
    所以这里允许 report 为 {} —— 测试断言 rc 即可，不能因为缺文件而炸。"""
    jpath = tmp_path / "j.json"
    if jpath.exists():
        jpath.unlink()
    rc = judge.main(
        [
            "--g1", str(g1),
            "--g0", str(g0),
            "--off", str(off),
            "--seq", "person_tracking",
            "--out-json", str(jpath),
        ]
    )
    import json

    report = json.loads(jpath.read_text()) if jpath.exists() else {}
    return rc, report


# 地板：person_tracking = 3.83 cm（来自 seq_floors_2026-10-30.json）
def test_j2_frame_count_mismatch_is_rejected(tmp_path):
    """冒烟 40 帧 vs 全长 580 帧必须被拒，而不是给出荒谬的 −10cm 改善。"""
    _write_run(tmp_path / "g1", 1.19, 24453, 40)
    _write_run(tmp_path / "g0", 1.17, 24855, 40)
    _write_run(tmp_path / "off", 11.54, 66882, 580)
    rc, _ = _run_judge(tmp_path, tmp_path / "g1", tmp_path / "g0", tmp_path / "off")
    assert rc == 2, "帧数不一致时判据机必须返回错误码"


def test_j1_placement_null_when_direction_reversed(tmp_path):
    """g1 比 g0 更差 ⇒ H1 证否（规则 4）。"""
    _write_run(tmp_path / "g1", 12.0, 80000, 580)
    _write_run(tmp_path / "g0", 11.5, 80000, 580)
    _write_run(tmp_path / "off", 11.0, 70000, 580)
    _, rep = _run_judge(tmp_path, tmp_path / "g1", tmp_path / "g0", tmp_path / "off")
    assert rep["verdict"].startswith("PLACEMENT_NULL"), rep["verdict"]


def test_j1_placement_positive_when_direction_right(tmp_path):
    _write_run(tmp_path / "g1", 10.0, 80000, 580)
    _write_run(tmp_path / "g0", 11.5, 80000, 580)
    _write_run(tmp_path / "off", 11.0, 70000, 580)
    _, rep = _run_judge(tmp_path, tmp_path / "g1", tmp_path / "g0", tmp_path / "off")
    assert rep["verdict"].startswith("PLACEMENT_POSITIVE"), rep["verdict"]


def test_j1_dose_mismatch_overrides_placement(tmp_path):
    """剂量差 >5% ⇒ 即使方向对，也不得读作放置效应（Amendment A1 §3a）。"""
    _write_run(tmp_path / "g1", 10.0, 95000, 580)
    _write_run(tmp_path / "g0", 11.5, 80000, 580)   # 差 18.75%
    _write_run(tmp_path / "off", 11.0, 70000, 580)
    _, rep = _run_judge(tmp_path, tmp_path / "g1", tmp_path / "g0", tmp_path / "off")
    assert rep["verdict"].startswith("DOSE_MISMATCH"), rep["verdict"]


def test_j1_dose_harmful_requires_both_conditions(tmp_path):
    """规则 2′：剂量代价真实 **且** 放置无效 才关族。剂量有害但放置有效 ⇒ 不关。"""
    # (i) 两臂都比 off 差 >= 1cm；高斯数都 > 1.15×；(ii) g1 < g0（放置有效）
    _write_run(tmp_path / "g1", 13.0, 85000, 580)
    _write_run(tmp_path / "g0", 13.5, 85000, 580)
    _write_run(tmp_path / "off", 11.0, 70000, 580)
    _, rep = _run_judge(tmp_path, tmp_path / "g1", tmp_path / "g0", tmp_path / "off")
    assert rep["verdict"].startswith("PLACEMENT_POSITIVE_WITH_DOSE_COST"), rep["verdict"]
    assert rep["dose"]["both_worse_than_off_by_1cm"] is True
    assert rep["dose"]["both_inflated_above_1.15x"] is True

    # 同剂量代价，但放置无效（g1 >= g0）⇒ 这时才关族
    _write_run(tmp_path / "g1b", 13.6, 85000, 580)
    rc, rep2 = _run_judge(tmp_path, tmp_path / "g1b", tmp_path / "g0", tmp_path / "off")
    assert rep2["verdict"].startswith("DOSE_HARMFUL"), rep2["verdict"]


def test_j1_missing_metric_is_an_error(tmp_path):
    """缺 efficiency_raw.csv ⇒ 必须报错，不得把 None 当数字算。"""
    _write_run(tmp_path / "g1", 10.0, 80000, 580)
    _write_run(tmp_path / "g0", 11.5, 80000, 580)
    (tmp_path / "off").mkdir()
    with open(tmp_path / "off" / "tracking_raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["status", "ate_rmse_cm"])
        w.writerow(["OK", "11.0"])
    rc, _ = _run_judge(tmp_path, tmp_path / "g1", tmp_path / "g0", tmp_path / "off")
    assert rc == 2


# ─────────────────────── 机制门（check_cgb_gate） ───────────────────────
HDR = "iter,kind,gauss_idx,x,y,z,mean_grad,denom,sparsity,key,max_scale\n"


def _write_trace(path, rows, scale=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(HDR if scale else HDR.replace(",max_scale", ""))
        for i, (kind, g, s, scale_v) in enumerate(rows):
            base = "%d,%s,%d,0,0,0,%.6f,10.0,%.5f,%.8f" % (100, kind, i, g, s, g * s)
            fh.write(base + (",%.6f\n" % scale_v if scale else "\n"))


def _gate_rows(extra_s, ref_s, extra_g=2.5e-4, ref_g=3e-4, n_ref=20, n_extra=1):
    rows = [("ref", ref_g, ref_s, 0.01)] * n_ref
    rows += [("extra", extra_g, extra_s, 0.09)] * n_extra
    return rows


def test_j3_gate_detects_swapped_arms(tmp_path):
    """把 γ=1 与 γ=0 的 trace 对调，G2 必须判失败（方向不能被写反骗过）。"""
    good = tmp_path / "good.csv"      # extra 明显更稀疏
    ctrl = tmp_path / "ctrl.csv"      # extra 与 ref 同密度
    _write_trace(good, _gate_rows(extra_s=3.0, ref_s=1.0))
    _write_trace(ctrl, _gate_rows(extra_s=1.0, ref_s=1.0))

    rc_ok = gate.main(["--g1", str(good), "--g0", str(ctrl), "--out-json", str(tmp_path / "a.json")])
    assert rc_ok == 0
    rc_swapped = gate.main(["--g1", str(ctrl), "--g0", str(good), "--out-json", str(tmp_path / "b.json")])
    assert rc_swapped != 0, "对调两臂后机制门必须失败"

    import json

    assert json.loads((tmp_path / "b.json").read_text())["gate"]["g2_placement"] is False


def test_j4_gate_dose_is_an_exact_equality(tmp_path):
    """G1 是精确等式：|extra| 与 floor(swap_frac·|ref|) 差 1 也必须判失败。"""
    exact = tmp_path / "exact.csv"
    off_by_one = tmp_path / "off.csv"
    # n_ref=20, swap_frac=0.20 ⇒ want=4
    _write_trace(exact, _gate_rows(extra_s=3.0, ref_s=1.0, n_extra=4))
    _write_trace(off_by_one, _gate_rows(extra_s=3.0, ref_s=1.0, n_extra=5))
    rc = gate.main(
        ["--g1", str(off_by_one), "--g0", str(exact), "--swap-frac", "0.20",
         "--out-json", str(tmp_path / "g.json")]
    )
    assert rc != 0
    import json

    rep = json.loads((tmp_path / "g.json").read_text())
    assert rep["gate"]["g1_dose"] is False


def test_j4b_gate_missing_max_scale_is_flagged_not_zero(tmp_path):
    """缺 max_scale 列时必须报 missing，而不是把它当 0（= 从不走 split）。"""
    a = tmp_path / "a.csv"
    _write_trace(a, _gate_rows(extra_s=3.0, ref_s=1.0, n_extra=4), scale=False)
    rc = gate.main(
        ["--g1", str(a), "--g0", str(a), "--swap-frac", "0.20",
         "--out-json", str(tmp_path / "g.json")]
    )
    import json

    rep = json.loads((tmp_path / "g.json").read_text())
    assert all(arm["max_scale_missing"] for arm in rep["arms"])
    assert all(arm["split_frac_extra"] is None for arm in rep["arms"])


# --- J5: 剂量门两列并陈（2026-10-30 slam-critic F1 回归） ---------------------
# 实测背景：cgb_g0 的 L1 臂 online=64,340 / refined=69,340（差恰好 +5,000 = 一个
# `Candidate insert KF: inserted 5000`，末端竞态）。8 臂中 2 臂出现该竞态。
# 若判据机只看一列，会得到 6.45%（γ=1 更多）；换另一列得 1.23% 且符号反转。
# ⇒ 两列符号相反时该门必须判「不可判」，不得判「未过」。

def test_j5_dose_gate_is_ambiguous_when_columns_disagree(tmp_path):
    def write(run, ate, online, refined, frames=580):
        run.mkdir(parents=True, exist_ok=True)
        with open(run / "tracking_raw.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["status", "ate_rmse_cm"])
            w.writerow(["OK", "%.4f" % ate])
        with open(run / "efficiency_raw.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["status", "online_num_gaussians", "refined_num_gaussians", "num_frames"])
            w.writerow(["OK", online, refined, frames])

    # online: g1 > g0（+6.45%）；refined: g1 < g0（-1.23%）⇒ 符号相反
    write(tmp_path / "g1", 13.4841, 68490, 68490)
    write(tmp_path / "g0", 11.2251, 64340, 69340)
    write(tmp_path / "off", 11.5375, 66882, 66882)
    rc, rep = _run_judge(tmp_path, tmp_path / "g1", tmp_path / "g0", tmp_path / "off")
    assert rep["dose"]["ambiguous"] is True
    assert rep["dose"]["columns_agree_in_sign"] is False
    assert rep["verdict"].startswith("DOSE_AMBIGUOUS"), rep["verdict"]
    # 两列数值必须都落盘，不能只报对自己有利的一列
    assert abs(rep["dose"]["relative_gap_online"] - 0.0645) < 1e-3
    assert abs(rep["dose"]["relative_gap_refined"] - 0.0123) < 1e-3


def test_j5b_dose_gate_passes_when_columns_agree(tmp_path):
    def write(run, ate, online, refined, frames=580):
        run.mkdir(parents=True, exist_ok=True)
        with open(run / "tracking_raw.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["status", "ate_rmse_cm"])
            w.writerow(["OK", "%.4f" % ate])
        with open(run / "efficiency_raw.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["status", "online_num_gaussians", "refined_num_gaussians", "num_frames"])
            w.writerow(["OK", online, refined, frames])

    write(tmp_path / "g1", 10.0, 80000, 80200)     # 两列都 > g0，符号一致
    write(tmp_path / "g0", 11.5, 79500, 79700)
    write(tmp_path / "off", 11.0, 70000, 70000)
    _, rep = _run_judge(tmp_path, tmp_path / "g1", tmp_path / "g0", tmp_path / "off")
    assert rep["dose"]["ambiguous"] is False
    assert rep["dose"]["columns_agree_in_sign"] is True
    assert not rep["verdict"].startswith("DOSE_AMBIGUOUS")
