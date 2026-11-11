"""async 迁移检查契约与判读测试（prereg_dose_async_migration_2026-11-08）。

守护：① async off 臂与 tau4x/zero 臂的解析后配置 diff 恰为
{opt_params.densify_grad_threshold, Results.save_dir}（单变量，同 inherit 链）；
② async 臂无任何仪器开关键（口径永不混引的配置侧防线）+ 机制全关 +
dose_zero 纯整数阈值（PyYAML 科学计数坑回归锚）；
③ 判读器路由走**真实 main() 路径**（subprocess 调用，PITFALLS #1198：fixture
不得手写与实现不一致的 payload 形状）。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "configs/experiments/paper3_bpw"
JUDGE = ROOT / "scripts/paper3_bpw/judge_dose_async_migration.py"

ALLOWED = {"opt_params.densify_grad_threshold", "Results.save_dir"}


def _resolved(name):
    sys.path.insert(0, str(ROOT))
    from utils.config_utils import load_config

    return load_config(str(CFG / f"{name}.yaml"))


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat(v, key))
        else:
            out[key] = v
    return out


@pytest.mark.parametrize("base,arm", [
    ("async_off_crowd", "dose_tau4x_crowd"),
    ("async_off_moving_nonobstructing_box", "dose_tau4x_moving_nonobstructing_box"),
    ("maskstat_off_person_tracking", "dose_tau4x_person_tracking"),
    ("maskstat_off_person_tracking", "dose_zero_person_tracking"),
])
def test_arm_is_single_variable(base, arm):
    b, a = _flat(_resolved(base)), _flat(_resolved(arm))
    diff = {k for k in set(b) | set(a) if b.get(k) != a.get(k)}
    assert diff == ALLOWED, f"{arm} vs {base}: diff = {diff}"


@pytest.mark.parametrize("arm", [
    "async_off_crowd", "async_off_moving_nonobstructing_box",
    "dose_tau4x_crowd", "dose_tau4x_moving_nonobstructing_box",
    "maskstat_off_person_tracking", "dose_tau4x_person_tracking", "dose_zero_person_tracking",
])
def test_async_arms_have_no_instrument_keys(arm):
    """口径红线（prereg §1）的配置侧防线：async 臂不得携带任何仪器开关。"""
    c = _resolved(arm)
    assert c["Training"].get("single_thread") is not True, arm
    assert c["Dataset"].get("single_thread") is not True, arm
    # async 基座解析后可能无 Rasterizer 段（缺段 = 默认关，同样满足口径红线）
    assert c.get("Rasterizer", {}).get("deterministic_backward") is not True, arm
    assert c["SelectiveDensification"]["enabled"] is False, arm


def test_dose_zero_grad_threshold_is_plain_int():
    c = _resolved("dose_zero_person_tracking")
    v = c["opt_params"]["densify_grad_threshold"]
    assert isinstance(v, int) and v == 1000000000, (type(v), v)


# ---------------- 判读器路由（subprocess = 真实 main() 产出路径） ----------------

def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)] + [",".join(map(str, r)) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_run(root, arm, seed, frames, ate, gauss, psnr, caliber="async_deploy",
              head="000000000", ts="20261108-000000"):
    """构造一个 rc0 全长 run 目录（.done + 四件判据件，字段名与真实产出一致）。"""
    d = root / arm / f"seed_{seed}" / ts
    d.mkdir(parents=True, exist_ok=True)
    (d / "async_run_seed0.done").write_text(
        f"arm={arm}\nstage=async\nrc=0\nfinished_rc0=yes\nhead={head}\ncaliber={caliber}\n",
        encoding="utf-8")
    _write_csv(d / "per_frame_ape.csv", ["frame", "ape_cm"],
               [[i, 1.0] for i in range(frames)])
    _write_csv(d / "tracking_raw.csv", ["ate_rmse_cm"], [[ate]])
    _write_csv(d / "efficiency_raw.csv", ["online_num_gaussians"], [[gauss]])
    _write_csv(d / "mapping_raw.csv", ["mask_type", "psnr"], [["static", psnr]])
    return d


def _make_pair_tree(root, name, seeds, off_vals, arm_vals, frames):
    for s in seeds:
        o_ate, o_g, o_p = off_vals[s]
        a_ate, a_g, a_p = arm_vals[s]
        _make_run(root, f"off_{name}", s, frames, o_ate, o_g, o_p)
        _make_run(root, f"arm_{name}", s, frames, a_ate, a_g, a_p)


def _run_judge(tmp_path, pairs, envelope="2.14", extra=()):
    out = tmp_path / "judge.json"
    argv = [sys.executable, str(JUDGE)]
    for p in pairs:
        argv += ["--pair", p]
    argv += ["--envelope-cm", envelope, "--require-head", "000000000"]
    argv += list(extra)
    argv += ["--out", str(out)]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return proc.returncode, report, proc.stdout


def _standard_tree(tmp_path, pt_zero_deltas=(0.5, 0.6, 0.55), crowd_deltas=(-0.3, -0.4),
                   mnobox_deltas=(0.4, 0.3), pt_tau4x_deltas=(-0.5, -0.6, -0.55),
                   crowd_ratio=0.22, zero_ratio=0.15):
    seeds3 = [0, 1, 2]
    seeds2 = [0, 1]
    # pt off: ate 13.6, gauss 50000, psnr 28.5；zero: gauss 7500, psnr 22.0
    pt_off = {s: (13.6, 50000, 28.5) for s in seeds3}
    pt_zero = {s: (13.6 + pt_zero_deltas[i], int(50000 * zero_ratio), 28.5 - 6.5)
               for i, s in enumerate(seeds3)}
    pt_tau4x = {s: (13.6 + pt_tau4x_deltas[i], int(50000 * 0.22), 27.5)
                for i, s in enumerate(seeds3)}
    # crowd off: ate 3.4, gauss 100000；tau4x: ratio 0.22
    crowd_off = {s: (3.4, 100000, 30.0) for s in seeds2}
    crowd_tau = {s: (3.4 + crowd_deltas[i], int(100000 * crowd_ratio), 29.2)
                 for i, s in enumerate(seeds2)}
    mnobox_off = {s: (2.0, 80000, 29.0) for s in seeds2}
    mnobox_tau = {s: (2.0 + mnobox_deltas[i], int(80000 * 0.22), 28.2)
                  for i, s in enumerate(seeds2)}
    _make_pair_tree(tmp_path, "pt_zero", seeds3, pt_off, pt_zero, 580)
    _make_pair_tree(tmp_path, "pt_tau4x", seeds3, pt_off, pt_tau4x, 580)
    _make_pair_tree(tmp_path, "crowd", seeds2, crowd_off, crowd_tau, 928)
    _make_pair_tree(tmp_path, "mnobox", seeds2, mnobox_off, mnobox_tau, 778)
    return [
        f"pt_zero:{tmp_path}/off_pt_zero:{tmp_path}/arm_pt_zero:580:zero:0,1,2",
        f"pt_tau4x:{tmp_path}/off_pt_tau4x:{tmp_path}/arm_pt_tau4x:580:tau4x:0,1,2",
        f"crowd:{tmp_path}/off_crowd:{tmp_path}/arm_crowd:928:tau4x:0,1",
        f"mnobox:{tmp_path}/off_mnobox:{tmp_path}/arm_mnobox:778:tau4x:0,1",
    ]


def test_expected_route_map_psnr_transferred(tmp_path):
    """预期出口（prereg §3.2）：比例/PSNR 迁移成立、ATE 全部包络内不可判。"""
    pairs = _standard_tree(tmp_path)
    rc, report, _ = _run_judge(tmp_path, pairs)
    assert rc == 0, report
    assert report["verdict"] == "MAP_PSNR_TRANSFERRED_ATE_ENVELOPE"
    assert all(p["ratio_status"] == "TRANSFERRED" for p in report["pairs"].values())
    assert report["pairs"]["pt_zero"]["psnr_status"] == "TRANSFERRED"
    assert all(p["ate_status"] in ("ENVELOPE_UNJUDGEABLE", "SIGN_UNSTABLE")
               for p in report["pairs"].values())


def test_full_transfer_when_ate_direction_judged_same_sign(tmp_path):
    """pt_zero 超包络且与仪器口径同号（+）⇒ FULL_TRANSFER。"""
    pairs = _standard_tree(tmp_path, pt_zero_deltas=(4.0, 4.2, 3.8))
    rc, report, _ = _run_judge(tmp_path, pairs)
    assert rc == 0
    assert report["verdict"] == "FULL_TRANSFER"
    assert report["pairs"]["pt_zero"]["ate_status"] == "DIRECTION_JUDGED"
    assert report["pairs"]["pt_zero"]["direction_vs_instrument"] == "SAME"


def test_contradicted_when_direction_opposite(tmp_path):
    """mnobox Δ 翻负（仪器参照 +）且超包络。mnobox 属 C4（包络外推），
    不得单独触发 CONTRADICTED（G3-C4）——总出口仍为预期出口，方向作报告项。"""
    pairs = _standard_tree(tmp_path, mnobox_deltas=(-3.0, -3.2))
    rc, report, _ = _run_judge(tmp_path, pairs)
    assert rc == 0
    assert report["verdict"] == "MAP_PSNR_TRANSFERRED_ATE_ENVELOPE"
    assert report["pairs"]["mnobox"]["ate_status"] == "DIRECTION_JUDGED"
    assert report["pairs"]["mnobox"]["direction_vs_instrument"] == "OPPOSITE"
    assert report["pairs"]["mnobox"]["envelope_provenance"] == "pt_config_extrapolated_provisional"


def test_contradicted_when_pt_direction_opposite(tmp_path):
    """pt_tau4x Δ 翻正（仪器参照 −）且超包络 ⇒ CONTRADICTED（pt 对消费进合成，G3-C4）。"""
    pairs = _standard_tree(tmp_path, pt_tau4x_deltas=(3.0, 3.2, 3.1))
    rc, report, _ = _run_judge(tmp_path, pairs)
    assert rc == 0
    assert report["verdict"] == "CONTRADICTED"
    assert report["pairs"]["pt_tau4x"]["direction_vs_instrument"] == "OPPOSITE"
    assert report["pairs"]["pt_tau4x"]["envelope_provenance"] == "pt_config_measured"


def test_contradicted_when_ratio_not_transferred(tmp_path):
    pairs = _standard_tree(tmp_path, crowd_ratio=0.8)
    rc, report, _ = _run_judge(tmp_path, pairs)
    assert rc == 0
    assert report["verdict"] == "CONTRADICTED"
    assert report["pairs"]["crowd"]["ratio_status"] == "NOT_TRANSFERRED"


def test_sign_unstable_counts_as_unjudged(tmp_path):
    """crowd 两 seed 异号 ⇒ SIGN_UNSTABLE（不取中位判方向），出口仍是 MAP_PSNR_…。"""
    pairs = _standard_tree(tmp_path, crowd_deltas=(1.0, -1.0))
    rc, report, _ = _run_judge(tmp_path, pairs)
    assert rc == 0
    assert report["verdict"] == "MAP_PSNR_TRANSFERRED_ATE_ENVELOPE"
    assert report["pairs"]["crowd"]["ate_status"] == "SIGN_UNSTABLE"


def test_fail_closed_when_done_missing(tmp_path):
    """前置门 fail-closed：缺 .done ⇒ RUN_INVALID 且 rc=2。"""
    pairs = _standard_tree(tmp_path)
    # 删掉 crowd off seed0 的 .done（连同目录里其他判据件保留）
    victim = tmp_path / "off_crowd" / "seed_0" / "20261108-000000"
    for f in victim.glob("*.done"):
        f.unlink()
    rc, report, stdout = _run_judge(tmp_path, pairs)
    assert rc == 2
    assert report["verdict"] == "RUN_INVALID"


def test_stale_instrument_run_cannot_substitute(tmp_path):
    """G3-C1：判读根目录里的历史 rc0 全长 run（instrument 口径 .done，无 async
    caliber）不得顶替本批 run——本批 run .done 损坏时总出口必须 RUN_INVALID，
    而不是静默消费旧 run（2060 provisional / 旧批混入 = 跨设备污染）。"""
    pairs = _standard_tree(tmp_path)
    # 同 seed 放一个排序更靠后的旧口径 rc0 全长 run（无 caliber=async_deploy）
    _make_run(tmp_path, "off_crowd", 0, 928, 3.4, 100000, 30.0,
              caliber="instrument_deploy", ts="20261108-999999")
    # 本批 run 的 .done 删除 ⇒ 若无 caliber 过滤，judge 会取旧 run 报 ok
    victim = tmp_path / "off_crowd" / "seed_0" / "20261108-000000"
    for f in victim.glob("*.done"):
        f.unlink()
    rc, report, stdout = _run_judge(tmp_path, pairs)
    assert rc == 2, stdout
    assert report["verdict"] == "RUN_INVALID"
    assert report["pairs"]["crowd"]["status"] == "invalid"


def test_reference_signs_delta_convention_pinned():
    """G2 异议处置（2026-11-08）：REFERENCE_SIGNS 是 **Δ(tau4x/zero − off) 符号**约定，
    不是 gain 符号。母件 n=3 判决（dose_oversupply_seed3_verdict_2026-11-08.md）：
    crowd gain +1.220 ⇒ Δ 中位 −1.220 ⇒ crowd=−1；mnobox gain −0.472 ⇒ Δ 中位 +0.472
    ⇒ mnobox=+1。本测试把约定钉死，防止未来按 gain 符号"更正"造成真反号。"""
    import sys
    sys.path.insert(0, str(ROOT / "scripts/paper3_bpw"))
    from judge_dose_async_migration import REFERENCE_SIGNS
    assert REFERENCE_SIGNS["crowd"] == -1   # tau4x 改善 ⇒ Δ 负
    assert REFERENCE_SIGNS["mnobox"] == +1  # tau4x 变差 ⇒ Δ 正
    assert REFERENCE_SIGNS["pt_tau4x"] == -1
    assert REFERENCE_SIGNS["pt_zero"] == +1
