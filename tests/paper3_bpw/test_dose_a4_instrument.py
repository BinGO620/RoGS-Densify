"""剂量轴 A4 仪器口径契约单测（prereg_dose_a4_instrument_2026-11-06 §1.1 / §3 / §6）。

守护四条事实，任一条漂移都会让 A4 判决失去意义：
  ① **单变量**：A4 臂与 off 臂的解析后配置只在两个剂量键（+ save_dir/inherit_from）上不同；
  ② **仪器开关齐全**：A4 仪器臂三项开关在位（否则跑出来的不是尺子）；
  ③ **判据常数与 prereg 一致**：0.5cm 效应门槛、1.5 高斯数比上限、580 帧；
  ④ **四条出口的机械路由**（含三条负对照：核心防守 = ATE 改善但高斯数膨胀判混杂）。
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
JUDGE = ROOT / "scripts/paper3_bpw/judge_dose_a4_instrument.py"
N = 580

# 判据常数（prereg §3.2 / §3.3 锁定；改动即需新 prereg）
CLAIM_FLOOR_CM = 0.5
GAUSS_RATIO_CAP = 1.5


def _resolved(name):
    """解析 inherit_from 链后的配置（裸 yaml.safe_load 看不到继承键）。"""
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


# ─────────────────────── ① 单变量 ───────────────────────
def test_a4_only_differs_in_two_dose_keys():
    """A4 臂 vs off 臂：解析后配置的差异集合必须恰为两个剂量键 + 两条路径键。

    这是「唯一变量」的机械守护。若有人往 A4 臂里顺手加别的键（机制开关、
    数据集、迭代数），本条立刻红——那会让 ATE 差值无法归因到剂量。
    """
    off = _flat(_resolved("instrument_maskstat_off"))
    a4 = _flat(_resolved("instrument_dose_a4_person_tracking"))
    diff = {k for k in set(off) | set(a4) if off.get(k) != a4.get(k)}
    assert diff == {
        "opt_params.densify_grad_threshold",
        "opt_params.percent_dense",
        "Results.save_dir",
        "inherit_from",
    }, f"非单变量！额外差异: {sorted(diff - {'opt_params.densify_grad_threshold', 'opt_params.percent_dense', 'Results.save_dir', 'inherit_from'})}"
    # 两个剂量键的具体取值（历史 A4 组合）
    assert a4["opt_params.densify_grad_threshold"] == pytest.approx(0.0001)
    assert a4["opt_params.percent_dense"] == pytest.approx(0.02)
    assert off["opt_params.densify_grad_threshold"] == pytest.approx(0.0002)
    assert off["opt_params.percent_dense"] == pytest.approx(0.01)


def test_a4_arm_has_no_mechanism_enabled():
    """A4 臂必须机制全关（否则与 off 基线不同管线，「唯一变量」失效）。"""
    c = _resolved("instrument_dose_a4_person_tracking")
    assert c["SelectiveDensification"]["enabled"] is False
    assert (c.get("Mapping") or {}).get("maskstat_dens_stats", False) is False
    assert (c.get("E2") or {}).get("trace_events", False) is False
    assert (c.get("MissStreak") or {}).get("enabled", False) is False


# ─────────────────────── ② 仪器开关 ───────────────────────
def test_a4_instrument_switches_all_on():
    c = yaml.safe_load((CFG_DIR / "instrument_dose_a4_person_tracking.yaml").read_text())
    assert c["Training"]["single_thread"] is True
    assert c["Dataset"]["single_thread"] is True
    assert c["Rasterizer"]["deterministic_backward"] is True
    # 派生文件本身不得写机制键（机制只能通过 inherit_from 继承）
    assert set(c) <= {"inherit_from", "Training", "Dataset", "Rasterizer", "Results"}, set(c)


# ─────────────────────── ③ 判据常数 ───────────────────────
def test_judge_constants_match_prereg():
    txt = JUDGE.read_text()
    assert f"CLAIM_FLOOR_CM = {CLAIM_FLOOR_CM}" in txt
    assert f"GAUSS_RATIO_CAP = {GAUSS_RATIO_CAP}" in txt
    assert "N_FRAMES_EXPECTED = 580" in txt


# ─────────────────────── ④ 四条出口 ───────────────────────
def _run(base, seed, ate, gauss, psnr=28.5, refined=None, rc0="yes"):
    d = base / f"seed_{seed}" / f"2026-01-01-00-00-{seed:02d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tracking_raw.csv").write_text(
        "method,run_id,status,ate_rmse_cm\n"
        f"X,{d.name},OK,{ate}\n")
    (d / "efficiency_raw.csv").write_text(
        "method,run_id,online_num_gaussians,refined_num_gaussians\n"
        f"X,{d.name},{gauss},{refined if refined is not None else gauss}\n")
    (d / "mapping_raw.csv").write_text(
        "method,run_id,psnr,depth_l1_cm\n"
        f"X,{d.name},{psnr},23.5\n")
    with (d / "per_frame_ape.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_id", "ape_cm"])
        for i in range(N):
            w.writerow([i, 1.0])
    (d / "instrument_run1_seed0.done").write_text(
        f"arm=x\nrc={0 if rc0 == 'yes' else 1}\nfinished_rc0={rc0}\n")
    return d


def _judge(off, a4, extra=()):
    out = subprocess.run(
        [sys.executable, str(JUDGE), "--off-root", str(off), "--a4-root", str(a4),
         "--seeds", "0", "1", "2", *extra],
        capture_output=True, text=True)
    return out


def _parse(out):
    """从 stdout 取 VERDICT 行。"""
    for line in out.stdout.splitlines():
        if line.startswith("VERDICT: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(f"无 VERDICT 行:\n{out.stdout}\n{out.stderr}")


def _seed_three(off, a4, triples):
    """triples = [(off_ate, a4_ate, off_g, a4_g), ...] 逐 seed。"""
    for s, (oa, aa, og, ag) in enumerate(triples):
        _run(off, s, oa, og)
        _run(a4, s, aa, ag)


def test_exit_positive_ate_dose_ok(tmp_path):
    """ATE 改善 ≥0.5cm 且高斯数受控 ⇒ POSITIVE_ATE_DOSE_OK。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 11.0, 50000, 60000),   # ratio 1.20
                          (13.9, 11.5, 46000, 55000),   # 1.196
                          (13.7, 11.2, 51000, 62000)])  # 1.216
    r = _judge(off, a4)
    assert r.returncode == 0, r.stderr
    assert _parse(r) == "POSITIVE_ATE_DOSE_OK"


def test_exit_below_claim_floor(tmp_path):
    """三 seed 同号但 |median Δ| < 0.5cm ⇒ BELOW_CLAIM_FLOOR。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 13.3, 50000, 50000),
                          (13.9, 13.6, 46000, 46000),
                          (13.7, 13.5, 51000, 51000)])
    assert _parse(_judge(off, a4)) == "BELOW_CLAIM_FLOOR"


def test_exit_dose_confound_is_the_core_defense(tmp_path):
    """**核心防守**：ATE 改善但高斯数膨胀 > 1.5× ⇒ DOSE_CONFOUND，不判正面。

    这条守护的是「更多 vs 更对」不可区分这件历史教训（prereg §3.3 出口 2）。
    历史 A4 的 2.1×~6.5× 就是落在这个出口。
    """
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 9.0, 50000, 150000),    # 3.0×
                          (13.9, 9.5, 46000, 120000),    # 2.6×
                          (13.7, 9.2, 51000, 180000)])   # 3.5×
    r = _judge(off, a4)
    assert _parse(r) == "DOSE_CONFOUND"
    assert "不可区分" in r.stdout, "出口理由须写明混杂不可区分"


def test_exit_ratio_exactly_at_cap_is_ok(tmp_path):
    """ratio 恰等于 1.5 ⇒ 边界归正面（≤ 是闭区间，prereg §3.3 字面）。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 11.0, 50000, 75000),
                          (13.9, 11.5, 46000, 69000),
                          (13.7, 11.2, 51000, 76500)])
    assert _parse(_judge(off, a4)) == "POSITIVE_ATE_DOSE_OK"


def test_exit_negative_closed(tmp_path):
    """A4 更差（median ≥ +0.5cm）⇒ CLOSED_NEGATIVE_OR_UNSTABLE。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 15.0, 50000, 52000),
                          (13.9, 15.5, 46000, 48000),
                          (13.7, 15.2, 51000, 53000)])
    assert _parse(_judge(off, a4)) == "CLOSED_NEGATIVE_OR_UNSTABLE"


def test_exit_seed_unstable(tmp_path):
    """三 seed 异号 ⇒ CLOSED_NEGATIVE_OR_UNSTABLE（不主张效应）。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 10.0, 50000, 52000),
                          (13.9, 15.0, 46000, 48000),
                          (13.7, 12.0, 51000, 53000)])
    assert _parse(_judge(off, a4)) == "CLOSED_NEGATIVE_OR_UNSTABLE"


def test_exit_missing_rc_anchor_is_invalid(tmp_path):
    """无 .done 锚点 ⇒ INSTRUMENT_INVALID（fail-closed，不得默认放行）。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 11.0, 50000, 51000),
                          (13.9, 11.5, 46000, 47000),
                          (13.7, 11.2, 51000, 52000)])
    # 删掉 seed1 的锚点
    for p in (a4 / "seed_1").rglob("instrument_*.done"):
        p.unlink()
    assert _parse(_judge(off, a4)) == "INSTRUMENT_INVALID"


def test_exit_rc_not_zero_is_invalid(tmp_path):
    """finished_rc0=no（OOM 半程）⇒ 排除该 run ⇒ INSTRUMENT_INVALID。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 11.0, 50000, 51000),
                          (13.9, 11.5, 46000, 47000),
                          (13.7, 11.2, 51000, 52000)])
    for d in sorted((a4 / "seed_1").iterdir()):
        for p in d.glob("instrument_*.done"):
            p.write_text("arm=x\nrc=1\nfinished_rc0=no\n")
    assert _parse(_judge(off, a4)) == "INSTRUMENT_INVALID"


def test_wrong_frame_count_is_invalid(tmp_path):
    """帧数不是 580 ⇒ INSTRUMENT_INVALID（截断 run 不得冒充全长）。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 11.0, 50000, 51000),
                          (13.9, 11.5, 46000, 47000),
                          (13.7, 11.2, 51000, 52000)])
    # 把 a4 seed2 的 per_frame_ape 截成 40 帧
    d = sorted((a4 / "seed_2").iterdir())[0]
    with (d / "per_frame_ape.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_id", "ape_cm"])
        for i in range(40):
            w.writerow([i, 1.0])
    assert _parse(_judge(off, a4)) == "INSTRUMENT_INVALID"


def test_json_report_keys(tmp_path):
    """prereg §6 声明的机械键必须真出现在 JSON 里（呈现层与判据不得脱钩）。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 11.0, 50000, 60000),
                          (13.9, 11.5, 46000, 55000),
                          (13.7, 11.2, 51000, 62000)])
    out = tmp_path / "r.json"
    r = _judge(off, a4, ("--out", str(out)))
    assert r.returncode == 0, r.stderr
    rep = json.loads(out.read_text())
    for key in ("verdict", "median_delta_ate_cm", "deltas", "gauss_ratios",
                "max_gauss_ratio", "same_sign", "claim_floor_cm", "gauss_ratio_cap",
                "n_frames_expected", "reasons"):
        assert key in rep, f"缺机械键 {key}"
    assert rep["gauss_ratio_cap"] == GAUSS_RATIO_CAP
    assert rep["claim_floor_cm"] == CLAIM_FLOOR_CM
    for s in ("0", "1", "2"):
        assert "delta_ate_cm" in rep["per_seed"][s]
        assert "gauss_ratio" in rep["per_seed"][s]


# ─────────── 2026-11-06 G3 审查 F1/F2 回归（致命项）───────────
def test_nan_ate_is_invalid_not_positive(tmp_path):
    """**F1 回归**：ATE 为 nan 时不得判正面。

    事件：旧版没有 isfinite 守卫，`median([nan,nan,nan])` = nan，而 `nan >= 0.5`
    与 `nan < 0.5` 同时为 False ⇒ 一路落到最后 else 判 POSITIVE_ATE_DOSE_OK。
    这不是理论风险——`mapping_raw.csv` 的 `full` 行在本管线三族恒为 nan。
    """
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, float("nan"), 50000, 50000),
                          (13.9, float("nan"), 46000, 46000),
                          (13.7, float("nan"), 51000, 51000)])
    r = _judge(off, a4)
    assert _parse(r) == "INSTRUMENT_INVALID"
    assert r.returncode == 2, "INVALID 必须 rc=2（fail-closed）"
    assert "非有限" in r.stdout


def test_single_seed_is_invalid(tmp_path):
    """**F2 回归**：prereg §3.3 固定三 seed，判据机不得按 1/2 seed 判出口。

    事件：旧版只查「有效数 < 请求数」，传 `--seeds 0` 就按单 seed 判正面。
    """
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 10.0, 50000, 51000),
                          (13.9, 10.0, 46000, 47000),
                          (13.7, 10.0, 51000, 52000)])
    for seeds in (["0"], ["0", "1"]):
        r = _judge(off, a4, ("--seeds", *seeds))
        assert _parse(r) == "INSTRUMENT_INVALID", f"seeds={seeds} 竟被判出口"
        assert r.returncode == 2
        assert "seed 集" in r.stdout


def test_gaussians_nonpositive_is_invalid(tmp_path):
    """高斯数 0/负 ⇒ 读数不存在，不得当 ratio 分母。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 10.0, 0, 51000),
                          (13.9, 10.0, 0, 47000),
                          (13.7, 10.0, 0, 52000)])
    r = _judge(off, a4)
    assert _parse(r) == "INSTRUMENT_INVALID"


def test_psnr_selected_by_mask_type(tmp_path):
    """**M5 回归**：渲染代价按 `mask_type` 选行，不是「取末行」。

    真实 `mapping_raw.csv` 同时写 `full`（全图，仪器口径下恒 nan）与 `static`
    （P-A 静态背景）两行。旧版取末行恰好吃到 static 却叫 "psnr"，与历史 A4 的
    full 口径混引。现在必须分开记：`full_psnr_db` 与 `static_psnr_db`。
    """
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 10.0, 50000, 51000),
                          (13.9, 10.0, 46000, 47000),
                          (13.7, 10.0, 51000, 52000)])
    # 把 a4 seed0 的 mapping 改成真实两行格式（full=nan, static=28.9）
    d = sorted((a4 / "seed_0").iterdir())[0]
    (d / "mapping_raw.csv").write_text(
        "method,run_id,mask_type,psnr,depth_l1_cm\n"
        f"X,{d.name},full,nan,MISSING\n"
        f"X,{d.name},static,28.9,23.5\n")
    out = tmp_path / "r.json"
    _judge(off, a4, ("--out", str(out)))
    rep = json.loads(out.read_text())
    a = rep["per_seed"]["0"]["a4"]
    assert a["static_psnr_db"] == pytest.approx(28.9)
    assert a["full_psnr_db"] is None, "full 行是 nan ⇒ 必须记 None，不得填 static 的值"
    assert a["psnr"] is None, "兼容键 psnr = full 口径 ⇒ 也必须是 None"


# ─────────── 2026-11-06 G3 审查 M3 回归：run 选择规则必须冻结且可钉死 ───────────
def test_run_selection_is_latest_and_reported(tmp_path):
    """选择规则 = 「最新时间戳的合格 run」，且判据机必须打印所用 run。

    没有这条规则时，同一命令在本地（run 集不同）与远程会选出不同 run，判决不可复算
    （G3 审查 M3 实测：本地出 INSTRUMENT_INVALID、远程出有效判决）。
    """
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 10.0, 50000, 51000)] * 3)
    # 在 a4/seed_0 下再加一个**更新的**合格 run（ATE 不同）⇒ 必须被选中
    newer = _run(a4, 0, 9.0, 50000)
    newer2 = newer.parent / "2026-02-02-00-00-00"
    newer.rename(newer2)
    r = _judge(off, a4)
    assert "a4=2026-02-02-00-00-00" in r.stdout, "应选最新时间戳 run"
    assert "used: off=" in r.stdout and "a4=" in r.stdout, "必须打印所用 run"


def test_pinned_run_overrides_selection(tmp_path):
    """`--a4-run SEED=RUNDIR` 钉死后必须只认它，不得回落最新 run。"""
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 10.0, 50000, 51000)] * 3)
    older = _run(a4, 0, 12.0, 50000)          # 2026-01-01-00-00-00
    newer = older.parent / "2026-03-03-00-00-00"
    older.rename(newer)
    r = _judge(off, a4, ("--a4-run", "0=2026-01-01-00-00-00"))
    assert _parse(r) == "INSTRUMENT_INVALID", "钉住的 run 不存在时必须 INVALID，不得回落"
    assert "指定的 run 不存在" in r.stdout


def test_pinned_run_used_when_present(tmp_path):
    """钉住的 run 存在时，读数必须来自它（不是最新那个）。

    构造：a4/seed_0 下有旧 run（ATE=10 ⇒ 判正面）与新 run（ATE=20 ⇒ 判更差）。
    默认规则会选最新的 05-05（判负）；钉到旧 run 则判正面 —— 两者可区分。
    """
    off, a4 = tmp_path / "off", tmp_path / "a4"
    _seed_three(off, a4, [(13.6, 10.0, 50000, 51000)] * 3)
    # 在 a4/seed_0 下再造一个更新、更差的 run
    d = sorted((a4 / "seed_0").iterdir())[0]
    import shutil
    nd = d.parent / "2026-05-05-00-00-00"
    shutil.copytree(d, nd)
    (nd / "tracking_raw.csv").write_text(
        "method,run_id,status,ate_rmse_cm\n"
        f"X,{nd.name},OK,20.0\n")
    assert _parse(_judge(off, a4)) == "CLOSED_NEGATIVE_OR_UNSTABLE", "默认应选最新（更差）"
    r = _judge(off, a4, ("--a4-run", "0=2026-01-01-00-00-00",
                         "--off-run", "0=2026-01-01-00-00-00"))
    assert _parse(r) == "POSITIVE_ATE_DOSE_OK", "钉住旧 run 后应判正面"
    assert "a4=2026-01-01-00-00-00" in r.stdout, "必须用钉住的 run，不是最新的 05-05"
