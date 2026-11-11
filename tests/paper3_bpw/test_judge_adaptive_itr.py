"""Adaptive itr L1 判读器测试（prereg §3 + amendment A1，P3-D2-045）。

守护：
  ① **M1 机制门**：真调度（序数 2..8 = itr_early、≥9 = itr_late）才过；四类违例
     （无调度行 / 序数不连续 / 某行值不符 / 控制臂出现调度行）必判 MECH_INVALID 且 rc=2。
  ② **M2/M3 与四出口路由**：ATE parity 0.5cm 与迭代节省的方向门，出口按序机械路由
     （L1_ATE_GAIN 优先于 L1_PASS；L1_NO_VALUE 覆盖两门任一不过）。
  ③ **前置门 fail-closed**：C 臂 R-valid 锚对分叉 ⇒ INSTRUMENT_INVALID；
     任一臂缺 .done ⇒ INSTRUMENT_INVALID（B 臂豁免已随 Amd A2「A/B 新跑」删除，G2 重大-1）。
  ④ **判据常数与 prereg/amendment 一致**（0.5cm / 580 帧 / −2.02% 实测密度预期）。

判读器路由走**真实 main() 路径**（subprocess），fixture 形状与真实产出一致
（PITFALLS #1198：不得手写与实现不一致的 payload）。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts/paper3_bpw/judge_adaptive_itr_l1.py"
N = 580
THRESHOLD = 8
EARLY, LATE = 30, 50


def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)] + [",".join(map(str, r)) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _schedule_log(n_calls, threshold=THRESHOLD, early=EARLY, late=LATE,
                  corrupt_ordinal=None, corrupt_value=None):
    lines = []
    for i in range(n_calls):
        ord_ = 2 + i
        frame = 5 * ord_
        itr = early if ord_ <= threshold else late
        if corrupt_ordinal is not None and i == corrupt_ordinal:
            ord_ = ord_ + 3
        if corrupt_value is not None and i == corrupt_value[0]:
            itr = corrupt_value[1]
        lines.append(f"MonoGS: adaptive_itr KF#{ord_} (frame {frame}) itr={itr}")
    return lines


def _make_run(root, arm, seed, ts, ate, iters, *, frames=N, schedule=True,
              with_done=True, done_rc0=True, n_calls=None,
              corrupt_ordinal=None, corrupt_value=None,
              backend_counts=None, cfg_enabled=None):
    d = Path(root) / f"seed_{seed}" / ts
    d.mkdir(parents=True, exist_ok=True)
    _write_csv(d / "per_frame_ape.csv", ["frame", "ape_cm"],
               [[i, 1.0] for i in range(frames)])
    _write_csv(d / "tracking_raw.csv", ["ate_rmse_cm"], [[ate]])
    _write_csv(d / "efficiency_raw.csv",
               ["online_num_gaussians", "mapping_iterations", "mapping_calls"],
               [[50000, iters, 231]])
    _write_csv(d / "mapping_raw.csv", ["mask_type", "psnr"], [["static", 29.0]])
    # C 臂的调度行数 = 114（115 KF - 1 init）；A/B 臂无
    calls = n_calls if n_calls is not None else (114 if schedule else 0)
    log_lines = ["MonoGS: Initialized map"]
    if schedule:
        log_lines += _schedule_log(calls, corrupt_ordinal=corrupt_ordinal,
                                   corrupt_value=corrupt_value)
    (d / "console.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    timing = {"mapping_iterations": iters, "mapping_calls": 231}
    if backend_counts is None:
        early = sum(1 for i in range(calls) if 2 + i <= THRESHOLD) if schedule else 0
        late = calls - early if schedule else 0
        timing["adaptive_itr_early_calls"] = early
        timing["adaptive_itr_late_calls"] = late
    else:
        timing["adaptive_itr_early_calls"], timing["adaptive_itr_late_calls"] = backend_counts
    (d / "backend_timing.json").write_text(json.dumps(timing), encoding="utf-8")
    # R-valid 比对集所需的其余件（内容固定 ⇒ 同臂两 run 逐位相同）
    # config.yml：判读器从**被审 run 自己的** config.yml 读调度参数（G3-重大10）
    if cfg_enabled is None:
        cfg_enabled = schedule
    cfg_lines = ["save_dir: placeholder", "Mapping:"]
    if cfg_enabled:
        cfg_lines += [
            "  adaptive_itr:",
            "    enabled: true",
            f"    itr_early: {EARLY}",
            f"    itr_late: {LATE}",
            f"    kf_threshold: {THRESHOLD}",
        ]
    else:
        cfg_lines += ["  lifecycle_mode: prune"]
    (d / "config.yml").write_text("\n".join(cfg_lines) + "\n", encoding="utf-8")
    for f in ("plot/stats_final.json", "plot/trj_final.json",
              "plot/trj_full_final.json"):
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_text('{"same": 1}', encoding="utf-8")
    for f in ("deferred_commit_events.csv", "reliability_signal/frames.csv"):
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_text("x\n1\n", encoding="utf-8")
    if with_done:
        (d / f"instrument_run1_seed{seed}.done").write_text(
            f"arm={arm}\nseed={seed}\nrc={0 if done_rc0 else 1}\n"
            f"finished_rc0={'yes' if done_rc0 else 'no'}\nhead=deadbeef\n",
            encoding="utf-8")
    return d


def _tree(tmp_path, *, a_ate=13.6, b_ate=10.7, c_ate=10.8,
          a_iters=18415, b_iters=6915, c_iters=6725,
          c_two_runs=True, c_schedule=True, c_cfg_enabled=None,
          corrupt_ordinal=None, corrupt_value=None,
          c_backend_counts=None, a_done=True):
    a_root = tmp_path / "a"
    b_root = tmp_path / "b"
    c_root = tmp_path / "c"
    _make_run(a_root, "instrument_person_tracking", 0, "2026-11-06-21-00-53",
              a_ate, a_iters, schedule=False, with_done=a_done)
    _make_run(b_root, "itrsweep50_maskstat_off", 0, "2026-11-09-21-03-01",
              b_ate, b_iters, schedule=False)   # Amd A2 后 B 新跑 ⇒ .done 必检
    c1 = _make_run(c_root, "adaptive_itr_person_tracking", 0, "2026-11-09-20-00-01",
                   c_ate, c_iters, schedule=c_schedule, cfg_enabled=c_cfg_enabled,
                   corrupt_ordinal=corrupt_ordinal, corrupt_value=corrupt_value,
                   backend_counts=c_backend_counts)
    pins = [c1.name]
    if c_two_runs:
        c2 = _make_run(c_root, "adaptive_itr_person_tracking", 0, "2026-11-09-21-00-01",
                       c_ate, c_iters, schedule=c_schedule, cfg_enabled=c_cfg_enabled)
        pins.append(c2.name)
    return a_root, b_root, c_root, pins


def _run(tmp_path, roots, pins=None, out_name="judge.json"):
    a_root, b_root, c_root = roots[0], roots[1], roots[2]
    out = tmp_path / out_name
    argv = [sys.executable, str(JUDGE),
            "--a-root", str(a_root), "--b-root", str(b_root), "--c-root", str(c_root),
            "--seed", "0", "--frames", str(N), "--out", str(out)]
    if pins:
        argv += ["--c-runs", *pins]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return proc, report


# ─────────────────── 出口路由 ───────────────────
def test_l1_pass_parity_and_saving(tmp_path):
    """|Δ|=0.1cm ≤ 0.5 且节省 190 迭代 ⇒ L1_PASS。"""
    roots = _tree(tmp_path)
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert rep["verdict"] == "L1_PASS", rep
    assert rep["m1"]["ok"] and rep["m2"]["ok"] and rep["m3"]["ok"]
    assert rep["m3"]["saving_iterations"] == 6915 - 6725
    assert rep["m3"]["saving_pct"] == round(100 * 190 / 6915, 3)


def test_l1_ate_gain_takes_priority(tmp_path):
    """C 显著优于 B（>0.5cm）⇒ L1_ATE_GAIN，即使 M2 不过。"""
    roots = _tree(tmp_path, c_ate=10.7 - 0.6)
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert proc.returncode == 0
    assert rep["verdict"] == "L1_ATE_GAIN"
    assert rep["m2"]["ok"] is False


def test_l1_no_value_when_parity_fails(tmp_path):
    """C 更差 >0.5cm 且未到 L1_ATE_GAIN ⇒ L1_NO_VALUE（止损）。"""
    roots = _tree(tmp_path, c_ate=10.7 + 0.8)
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert rep["verdict"] == "L1_NO_VALUE"
    assert "等价门不过" in " ".join(rep["reasons"])


def test_l1_no_value_when_no_saving(tmp_path):
    """迭代数未减少（=B）⇒ L1_NO_VALUE（即使 ATE parity 成立）。"""
    roots = _tree(tmp_path, c_iters=6915)
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert rep["verdict"] == "L1_NO_VALUE"
    assert rep["m2"]["ok"] is True and rep["m3"]["ok"] is False


# ─────────────────── M1 机制门 ───────────────────
def test_mech_invalid_when_no_schedule_lines(tmp_path):
    """config 启用但 console 无调度行 ⇒ 机制未触发 ⇒ MECH_INVALID。"""
    roots = _tree(tmp_path, c_schedule=False, c_cfg_enabled=True)
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert proc.returncode == 2, "MECH_INVALID 必须 rc=2（fail-closed）"
    assert rep["verdict"] == "MECH_INVALID"
    assert "无任何调度行" in " ".join(rep["reasons"])


def test_mech_invalid_on_ordinal_gap(tmp_path):
    roots = _tree(tmp_path, corrupt_ordinal=5)
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert proc.returncode == 2
    assert rep["verdict"] == "MECH_INVALID"
    assert "序数不连续" in " ".join(rep["reasons"])


def test_mech_invalid_on_wrong_itr(tmp_path):
    """第 9 个调度调用（序数 10，应 late=50）写成 30 ⇒ 机制门红。"""
    roots = _tree(tmp_path, corrupt_value=(8, 30))
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert proc.returncode == 2
    assert rep["verdict"] == "MECH_INVALID"
    assert "不符两段式" in " ".join(rep["reasons"])


def test_mech_invalid_when_backend_counts_disagree(tmp_path):
    """日志对但 backend_timing 计数不符（静默组件纪律：两处须互印证）。"""
    roots = _tree(tmp_path, c_backend_counts=(7, 200))
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert proc.returncode == 2
    assert rep["verdict"] == "MECH_INVALID"
    assert "不一致" in " ".join(rep["reasons"])


def test_mech_invalid_when_control_arm_has_schedule_lines(tmp_path):
    """A 臂（默认关）出现调度行 ⇒ 非单变量 ⇒ MECH_INVALID。"""
    a_root, b_root, c_root, pins = _tree(tmp_path)
    _make_run(a_root, "instrument_person_tracking", 0, "2026-11-06-22-00-53",
              13.6, 18415, schedule=True)   # 后写的 run 更新 ⇒ 会被选中
    proc, rep = _run(tmp_path, (a_root, b_root, c_root), pins=pins)
    assert proc.returncode == 2
    assert rep["verdict"] == "MECH_INVALID"
    assert "A 臂出现" in " ".join(rep["reasons"])


# ─────────────────── 前置门 fail-closed ───────────────────
def test_instrument_invalid_when_c_anchor_pair_diverges(tmp_path):
    """C 臂两 run 读数不同 ⇒ R-valid 分叉 ⇒ INSTRUMENT_INVALID。"""
    a_root, b_root, c_root, pins = _tree(tmp_path)
    # 第二 run 写不同 ATE ⇒ 逐位比对必分叉
    _make_run(c_root, "adaptive_itr_person_tracking", 0, "2026-11-09-21-00-01",
              99.0, 6725, schedule=True)
    proc, rep = _run(tmp_path, (a_root, b_root, c_root), pins=pins)
    assert proc.returncode == 2, "INSTRUMENT_INVALID 必须 rc=2（fail-closed）"
    assert rep["verdict"] == "INSTRUMENT_INVALID"
    assert rep["r_valid"]["ok"] is False


def test_instrument_invalid_when_only_one_c_run(tmp_path):
    roots = _tree(tmp_path, c_two_runs=False)
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert rep["verdict"] == "INSTRUMENT_INVALID"
    assert "R-valid" in " ".join(rep["reasons"])


def test_instrument_invalid_when_a_arm_missing_done(tmp_path):
    """A 臂缺 .done ⇒ INSTRUMENT_INVALID（三臂同规）。"""
    roots = _tree(tmp_path, a_done=False)
    proc, rep = _run(tmp_path, roots, pins=roots[3])
    assert rep["verdict"] == "INSTRUMENT_INVALID"
    assert "A" in rep["arm_errors"]


def test_b_arm_requires_done_after_a2(tmp_path):
    """B 臂缺 .done ⇒ INSTRUMENT_INVALID（A1 §5.1 豁免已删，G2 重大-1）。

    守护的事实：A2 把 B 改为**新跑**后，旧批 run（无 .done，可能被 stash 恢复）
    不得再被静默采纳。
    """
    a_root = tmp_path / "a"
    b_root = tmp_path / "b"
    c_root = tmp_path / "c"
    _make_run(a_root, "instrument_person_tracking", 0, "2026-11-09-20-15-37", 13.6, 18415,
              schedule=False)
    _make_run(b_root, "itrsweep50_maskstat_off", 0, "2026-11-05-21-43-29", 10.7, 6915,
              schedule=False, with_done=False, frames=N)   # 旧批 B：帧数齐但无 .done
    c1 = _make_run(c_root, "adaptive_itr_person_tracking", 0, "2026-11-09-19-17-31",
                   10.8, 6775)
    c2 = _make_run(c_root, "adaptive_itr_person_tracking", 0, "2026-11-09-19-46-32",
                   10.8, 6775)
    proc, rep = _run(tmp_path, (a_root, b_root, c_root), pins=[c1.name, c2.name])
    assert rep["verdict"] == "INSTRUMENT_INVALID"
    assert "B" in rep["arm_errors"]


def test_b_arm_wrong_frame_count_is_invalid(tmp_path):
    a_root = tmp_path / "a"
    b_root = tmp_path / "b"
    c_root = tmp_path / "c"
    _make_run(a_root, "instrument_person_tracking", 0, "2026-11-06-21-00-53", 13.6, 18415,
              schedule=False)
    _make_run(b_root, "itrsweep50_maskstat_off", 0, "2026-11-05-21-43-29", 10.7, 6915,
              schedule=False, with_done=False, frames=41)   # 冒烟 run，非全长
    c1 = _make_run(c_root, "adaptive_itr_person_tracking", 0, "2026-11-09-20-00-01",
                   10.8, 6725)
    c2 = _make_run(c_root, "adaptive_itr_person_tracking", 0, "2026-11-09-21-00-01",
                   10.8, 6725)
    proc, rep = _run(tmp_path, (a_root, b_root, c_root), pins=[c1.name, c2.name])
    assert rep["verdict"] == "INSTRUMENT_INVALID"
    assert "B" in rep["arm_errors"]


# ─────────────────── 判据常数 ───────────────────
def test_judge_constants_match_prereg():
    txt = JUDGE.read_text()
    assert "CLAIM_FLOOR_CM = 0.5" in txt
    assert "N_FRAMES_EXPECTED = 580" in txt
    # amendment A1 §2：两套预期值并列（母件 −5% 与实测密度 −2.02%），只作报告项
    assert "EXPECTED_SAVING_PCT = -2.02" in txt
    assert '"expected_pct_prereg": -5.0' in txt


def test_report_prints_both_expected_savings(tmp_path):
    """M3 报告项必须并列母件 −5% 与实测密度 −2.02%。"""
    roots = _tree(tmp_path)
    _, rep = _run(tmp_path, roots, pins=roots[3])
    assert rep["m3"]["expected_pct_prereg"] == -5.0
    assert rep["m3"]["expected_pct_measured_density"] == -2.02
