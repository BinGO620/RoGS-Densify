#!/usr/bin/env python3
"""E 轴 L1 判读器：Adaptive itr 调度 vs 固定 itr=50（prereg §3 机械执行）。

预注册：`paper3/results/evidence/prereg_adaptive_itr_schedule_2026-11-08.md`
（判据链：amendment A1 精度化 + A2 G3 整改（A/B 改新跑）——
  `prereg_adaptive_itr_amendment_{a1,a2}_2026-11-09.md`）。

三条判据（prereg §3）：
  M1 机制门   C 臂 console 的逐调用日志必须真调度：序数 2..8 全 itr_early，
              序数 ≥9 全 itr_late（初始化关键帧不调度、也无日志行）；计数与
              backend_timing.json 一致；A/B 两臂必须**零调度行**（单变量）。
              任一不符 ⇒ MECH_INVALID（rc=2，fail-closed）。
  M2 等价门   |ATE_C − ATE_B| ≤ 0.5cm（0.5cm 判读地板）。
  M3 省算力门 mapping_iterations(C) < mapping_iterations(B)。

四条互斥出口（按序机械路由）：
  INSTRUMENT_INVALID  前置门失败（.done rc0 / 帧数 / C 臂 R-valid 锚对 / 读数非有限）
  MECH_INVALID        M1 失败
  L1_ATE_GAIN         M1 ∧ ATE_C < ATE_B − 0.5cm（H-B 成立信号，优先级最高）
  L1_PASS             M1 ∧ M2 ∧ M3
  L1_NO_VALUE         M1 ∧ (¬M2 ∨ 无算力节省) —— 止损

R-valid 锚对：C 臂（承载机制的臂）必须有两个**同 seed 全长** run 且逐位一致
（复用 `deterministic_probe/compare_three_way.py` 的比对集与口径）；仪器口径的
自差包络 = 0.0cm 由该逐位一致性直接确立（装置门核算见 amendment A1 §三）。

用法（L1 批实测命令，2026-11-09，在派发机 3090 执行；G2 条件⑥ 更新）:
  python scripts/paper3_bpw/judge_adaptive_itr_l1.py \
    --a-root results/paper3_bpw/instrument_person_tracking/datasets_bonn/instrument_person_tracking \
    --a-run 2026-11-09-20-15-37 \
    --b-root results/paper3_bpw/itrsweep50_maskstat_off/datasets_bonn/itrsweep50_maskstat_off \
    --b-run 2026-11-09-21-03-01 \
    --c-root results/paper3_bpw/adaptive_itr_person_tracking/datasets_bonn/adaptive_itr_person_tracking \
    --c-runs 2026-11-09-19-17-31 2026-11-09-19-46-32 \
    --seed 0 --frames 580 \
    --out paper3/results/evidence/adaptive_itr_l1_judge_2026-11-09.json
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts/paper3_bpw/deterministic_probe"))

CLAIM_FLOOR_CM = 0.5
N_FRAMES_EXPECTED = 580
# R-valid 锚对的最少可比对件数（G3-重大3 空转防线）：正常 run 至少贡献
# tracking/efficiency/mapping CSV + per_frame_ape + plot 终态 json + config.yml ≈ 8+。
MIN_COMPARED_FILES = 6
# 预注册预期节省（报告项）：按本仓实测 KF 密度（115 KF / 580 帧）算出的 −2.02%，
# 而非 prereg 括注的 −5%（后者按 58 KF 推算）。见 amendment A1 §二。
EXPECTED_SAVING_PCT = -2.02


def _finite(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(float(x))


def read_frames(path):
    with path.open(newline="") as fh:
        return len(list(csv.DictReader(fh)))


def read_done(run):
    hits = sorted(run.glob("instrument_*.done"))
    if not hits:
        return None
    kv = {}
    for line in hits[-1].read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def collect(root, seed, pin, prefer_frames=N_FRAMES_EXPECTED, require_done=True):
    """取该臂该 seed 的合格 run。pin 给了就只认它（不回落，防「显式指定却悄悄换 run」）。

    ``require_done``：**三臂一律要求** `instrument_*.done` 且 `finished_rc0=yes`
    （fail-closed，防 OOM 半程 run 混入）。
    历史：A1 §5.1 曾对 B 臂豁免（P3-D2-032 批早于 `.done` 惯例）；A2 §1 把 B 改为
    **新跑**后豁免失去对象——本批 B run 带 `.done`，豁免若沿用，将来恢复 stash 的
    旧 B run 会被静默采纳（G2 重大-1）。故自本版起删除该豁免。
    """
    base = Path(root) / f"seed_{seed}"
    if not base.is_dir():
        return None, f"缺 seed_{seed} 目录：{base}"
    if pin:
        d = base / pin
        if not d.is_dir():
            return None, f"seed_{seed} 指定的 run 不存在：{pin}"
        runs = [d]
    else:
        runs = sorted([dd for dd in base.iterdir() if dd.is_dir()], key=lambda dd: dd.name)
    if not runs:
        return None, f"seed_{seed} 无 run 目录"

    candidates, chosen, failed = [], None, []
    for d in runs:
        pf = d / "per_frame_ape.csv"
        nf = read_frames(pf) if pf.is_file() else None
        candidates.append(f"{d.name}(frames={nf})")
        if require_done:
            kv = read_done(d)
            if kv is None:
                failed.append(f"{d.name}(无 .done 锚点)")
                continue
            if kv.get("finished_rc0") != "yes":
                failed.append(f"{d.name}(rc={kv.get('rc')})")
                continue
        if nf == prefer_frames and (d / "tracking_raw.csv").is_file():
            chosen = d
    suffix = f"；不合格 run: {', '.join(failed)}" if failed else ""
    if chosen is None:
        return None, (f"seed_{seed} 无 {prefer_frames} 帧 rc0 run{suffix}；"
                      f"候选: {', '.join(candidates[-4:])}")

    tr = list(csv.DictReader(open(chosen / "tracking_raw.csv")))[0]
    er = list(csv.DictReader(open(chosen / "efficiency_raw.csv")))[0]
    try:
        ate = float(tr["ate_rmse_cm"])
        gauss = int(float(er["online_num_gaussians"]))
    except (TypeError, ValueError, KeyError) as exc:
        return None, f"{chosen.name} 读数不可解析：{exc}"
    if not (_finite(ate) and gauss > 0):
        return None, f"{chosen.name} ATE/高斯数非有限或非正"

    # 迭代数来源：**优先 backend_timing.json**（后端自己写的权威值）。
    # 2026-11-09 G3 致命B 实测：`itrsweep50_maskstat_off` s0 的 efficiency_raw.csv
    # 里 `mapping_iterations`/`mapping_calls` 是字面 `N/A`（该 run 早于
    # `_wait_for_backend_timing` 收口），而 backend_timing.json 有 6915 ——
    # 旧代码读 efficiency 会 `int(float('N/A'))` 抛错，把可用臂判成 INSTRUMENT_INVALID。
    bt = chosen / "backend_timing.json"
    timing = json.loads(bt.read_text()) if bt.is_file() else {}
    iters_src = er.get("mapping_iterations")
    if timing.get("mapping_iterations") is not None:
        iters_src = timing["mapping_iterations"]
    calls_src = er.get("mapping_calls")
    if timing.get("mapping_calls") is not None:
        calls_src = timing["mapping_calls"]
    try:
        iters = int(float(iters_src))
        calls = int(float(calls_src))
    except (TypeError, ValueError):
        return None, (f"{chosen.name} 迭代数不可解析（efficiency={iters_src!r}，"
                      f"backend_timing={timing.get('mapping_iterations')!r}）")
    if iters <= 0:
        return None, f"{chosen.name} mapping_iterations={iters} 非正"
    out = {
        "run": chosen.name, "dir": str(chosen),
        "ate_cm": ate, "gaussians": gauss,
        "mapping_iterations": iters, "mapping_calls": calls,
        "iterations_source": ("backend_timing" if timing.get("mapping_iterations") is not None
                              else "efficiency_raw"),
        "frames": prefer_frames,
    }
    if timing:
        out["backend_early_calls"] = timing.get("adaptive_itr_early_calls", None)
        out["backend_late_calls"] = timing.get("adaptive_itr_late_calls", None)
        out["backend_mapping_iterations"] = timing.get("mapping_iterations", None)
        # efficiency 与 backend_timing 都给出数值时必须一致（两边都在 ⇒ 互印证）
        try:
            eff_iters = int(float(er.get("mapping_iterations")))
        except (TypeError, ValueError):
            eff_iters = None
        if eff_iters is not None:
            out["iterations_consistent"] = (eff_iters == iters)
    return out, None


def parse_schedule_log(run_dir):
    """解析 `adaptive_itr KF#<ord> (frame <f>) itr=<i>` 行（稳定子串，不用 `[...]`）。

    rich 会把方括号当 markup 静默吞掉（PITFALLS 同类踩坑），故日志与解析都只认
    `adaptive_itr KF#` 这个不带方括号的形状。
    """
    import re

    log = Path(run_dir) / "console.log"
    if not log.is_file():
        return None, "缺 console.log"
    rows = []
    pattern = re.compile(r"adaptive_itr KF#(\d+) \(frame (\d+)\) itr=(\d+)")
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pattern.search(line)
        if m:
            rows.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return rows, None


def run_params(run_dir):
    """从**被审 run 自己的** config.yml 读调度参数（判据可复现，不读当前仓 config）。

    G3-重大10：M1 曾读 repo 里的 C 臂 config，若 config 被后续改动，历史 run 的判据
    就不可复算。run 内 config.yml 是运行期的完整合并配置（含 Mapping.adaptive_itr）。
    """
    cfg_path = Path(run_dir) / "config.yml"
    if not cfg_path.is_file():
        return None, f"{Path(run_dir).name} 缺 config.yml"
    import yaml

    with cfg_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    block = (cfg.get("Mapping", {}) or {}).get("adaptive_itr", {}) or {}
    if not block.get("enabled", False):
        return None, f"{Path(run_dir).name} 的 config.yml 未启用 Mapping.adaptive_itr"
    try:
        params = {
            "itr_early": int(block["itr_early"]),
            "itr_late": int(block["itr_late"]),
            "kf_threshold": int(block["kf_threshold"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"{Path(run_dir).name} 的 adaptive_itr 参数不可解析：{exc}"
    return params, None


def check_m1(c_run, a_run, b_run):
    """M1 机制门。返回 (ok, detail, reason)。

    参数一律取自 **C 臂 run 自己的 config.yml**（run 级可复现）。
    """
    params, perr = run_params(c_run["dir"])
    if params is None:
        return False, {}, f"C 臂 {perr}"
    early_itr = params["itr_early"]
    late_itr = params["itr_late"]
    threshold = params["kf_threshold"]

    rows, err = parse_schedule_log(c_run["dir"])
    if rows is None:
        return False, {}, f"C 臂 {err}"
    if not rows:
        return False, {"n_lines": 0}, "C 臂 console 无任何调度行 ⇒ 机制未触发"

    # ① 序数必须从 2 起逐一递增（1 = 初始化关键帧，不调度、无日志行）
    ordinals = [r[0] for r in rows]
    expected = list(range(2, 2 + len(rows)))
    if ordinals != expected:
        return False, {"ordinals": ordinals[:6]}, (
            f"C 臂调度序数不连续：期望 {expected[0]}..{expected[-1]}，"
            f"实得 {ordinals[0]}..{ordinals[-1]}（共 {len(ordinals)} 行）")

    # ② 每行 itr 必须与两段式一致
    bad = [r for r in rows
           if r[2] != (early_itr if r[0] <= threshold else late_itr)]
    if bad:
        return False, {"first_bad": bad[0]}, (
            f"C 臂调度值不符两段式（阈值 {threshold}）：首个违例行 {bad[0]}，"
            f"共 {len(bad)} 行违例")

    n_early = sum(1 for r in rows if r[0] <= threshold)
    n_late = len(rows) - n_early
    detail = {
        "n_lines": len(rows), "early_calls": n_early, "late_calls": n_late,
        "itr_early": early_itr, "itr_late": late_itr, "kf_threshold": threshold,
        "first_late_frame": next((r[1] for r in rows if r[0] > threshold), None),
    }

    # ③ 落盘计数必须与日志一致（静默组件纪律：两处互相印证）。
    # G3-重大2 整改：旧版 `is not None` / `is False` 守卫 ⇒ 缺键时静默跳过（fail-open）。
    # 现在缺键即失败：C 臂必须带双计数与 iterations_consistent；A/B 必须带 0/0。
    if c_run.get("backend_early_calls") is None or c_run.get("backend_late_calls") is None:
        return False, detail, (
            "C 臂 backend_timing.json 缺 adaptive_itr_early_calls/late_calls"
            "（机制无落盘证据 ⇒ 不得判 M1 通过）")
    if (c_run["backend_early_calls"] != n_early
            or c_run["backend_late_calls"] != n_late):
        return False, detail, (
            f"C 臂 backend_timing 计数 ({c_run['backend_early_calls']}/"
            f"{c_run['backend_late_calls']}) 与日志 ({n_early}/{n_late}) 不一致")
    if c_run.get("iterations_consistent") is not True:
        return False, detail, (
            "C 臂 efficiency_raw 与 backend_timing 的 mapping_iterations 不一致或缺失"
            "（两表互印证不成立）")

    # ④ 控制臂必须零调度行（单变量：机制只在 C 臂）
    for tag, run in (("A", a_run), ("B", b_run)):
        other_rows, other_err = parse_schedule_log(run["dir"])
        if other_rows is None:
            return False, detail, f"{tag} 臂 {other_err}"
        if other_rows:
            return False, detail, f"{tag} 臂出现 {len(other_rows)} 条调度行 ⇒ 非单变量"
        if (run.get("backend_early_calls") is None
                or run.get("backend_late_calls") is None):
            return False, detail, (
                f"{tag} 臂 backend_timing.json 缺 adaptive_itr 计数键"
                "（无法证明机制未触发）")
        if run["backend_early_calls"] != 0 or run["backend_late_calls"] != 0:
            return False, detail, f"{tag} 臂 backend_timing 计数非零 ⇒ 非单变量"

    return True, detail, ""


def check_r_valid(root, seed, pins):
    """C 臂两 run 逐位比对（R-valid 锚对）。返回 (ok, detail, reason)。

    G3-重大3 整改（2026-11-09）：旧版在三个缺口上会**空转通过**——
    ① 两个 pin 指向不存在的目录（`collect()` 两侧全 None ⇒ 无 diff ⇒ 假绿）；
    ② 同一个 pin 传两次（自己与自己比）；③ 比对集不足（缺件被当 N/A 跳过）。
    现在三条都是硬门：pin 去重、两目录必须存在且有读数值、比对件数须 ≥ MIN。
    """
    import compare_three_way as C

    if not pins or len(pins) < 2:
        return False, {}, "C 臂需两个 run 作 R-valid 锚对（prereg §3 前置门）"
    if len(set(pins)) != len(pins):
        return False, {"pins": pins}, "C 臂 R-valid 锚对的两个 pin 重复（必须两个不同 run）"

    base = Path(root) / f"seed_{seed}"
    missing = [p for p in pins if not (base / p).is_dir()]
    if missing:
        return False, {"missing": missing}, f"C 臂锚对目录不存在：{missing}"

    samples = {chr(ord("A") + i): ts for i, ts in enumerate(pins)}
    _, md5s = C.collect(base, samples)
    # 空转防线：任一件在**两侧都**缺失 ⇒ 该比对集不覆盖判据面（不得记 R1）
    compared = [f for f, m in md5s.items()
                if not all(m.get(t) is None for t in samples)]
    if len(compared) < MIN_COMPARED_FILES:
        return False, {"files_compared": len(compared), "min_required": MIN_COMPARED_FILES}, (
            f"C 臂锚对可比对件仅 {len(compared)} 件 < {MIN_COMPARED_FILES}"
            "（空目录/缺件不得记 R1）")

    diffs = []
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            a, b = chr(ord("A") + i), chr(ord("A") + j)
            for f, m in md5s.items():
                if not (m[a] is None and m[b] is None) and m[a] != m[b]:
                    diffs.append(f"{f}: {m[a]} vs {m[b]}")
    if diffs:
        return False, {"diffs": diffs[:8], "files_compared": len(compared)}, (
            f"C 臂两 run 分叉（{len(diffs)} 件）⇒ 仪器失效")
    return True, {"files_compared": len(compared), "diffs": 0}, ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--a-root", required=True, help="A 臂（fixed itr=150，参考）seed_N 的父目录")
    ap.add_argument("--b-root", required=True, help="B 臂（fixed itr=50）seed_N 的父目录")
    ap.add_argument("--c-root", required=True, help="C 臂（调度）seed_N 的父目录")
    ap.add_argument("--a-run", default=None, help="钉住 A 臂 run 目录名（不钉则取最新合格 run）")
    ap.add_argument("--b-run", default=None, help="钉住 B 臂 run 目录名")
    ap.add_argument("--c-runs", nargs="+", default=None,
                    help="钉住 C 臂两个 run 目录名（R-valid 锚对；第一个用作读数）")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--frames", type=int, default=N_FRAMES_EXPECTED)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    report = {
        "prereg": "paper3/results/evidence/prereg_adaptive_itr_schedule_2026-11-08.md",
        "amendments": [
            "paper3/results/evidence/prereg_adaptive_itr_amendment_a1_2026-11-09.md",
            "paper3/results/evidence/prereg_adaptive_itr_amendment_a2_2026-11-09.md"],
        "seed": args.seed,
        "frames_expected": args.frames,
        "claim_floor_cm": CLAIM_FLOOR_CM,
        "expected_saving_pct": EXPECTED_SAVING_PCT,
        "arms": {}, "m1": None, "m2": None, "m3": None, "r_valid": None,
        "verdict": None, "reasons": [],
    }

    a, ea = collect(args.a_root, args.seed, args.a_run, args.frames)
    b, eb = collect(args.b_root, args.seed, args.b_run, args.frames)
    c_pins = args.c_runs or []
    c, ec = collect(args.c_root, args.seed, c_pins[0] if c_pins else None, args.frames)
    report["arms"] = {"A": a, "B": b, "C": c}
    report["arm_errors"] = {k: v for k, v in
                            (("A", ea), ("B", eb), ("C", ec)) if v}

    invalid = [f"{k}: {v}" for k, v in report["arm_errors"].items()]
    if invalid:
        report["verdict"] = "INSTRUMENT_INVALID"
        report["reasons"] = invalid
        return _emit(report, args.out, rc=2)

    r_ok, r_detail, r_reason = check_r_valid(args.c_root, args.seed, c_pins)
    report["r_valid"] = {"ok": r_ok, **r_detail}
    if not r_ok:
        report["verdict"] = "INSTRUMENT_INVALID"
        report["reasons"] = [r_reason]
        return _emit(report, args.out, rc=2)

    m1_ok, m1_detail, m1_reason = check_m1(c, a, b)
    report["m1"] = {"ok": m1_ok, **m1_detail}
    if not m1_ok:
        report["verdict"] = "MECH_INVALID"
        report["reasons"] = [m1_reason]
        return _emit(report, args.out, rc=2)

    delta_cb = round(c["ate_cm"] - b["ate_cm"], 4)
    m2_ok = abs(delta_cb) <= CLAIM_FLOOR_CM
    report["m2"] = {"ok": m2_ok, "delta_ate_cm": delta_cb,
                    "gate_cm": CLAIM_FLOOR_CM}
    m3_ok = c["mapping_iterations"] < b["mapping_iterations"]
    saving = b["mapping_iterations"] - c["mapping_iterations"]
    report["m3"] = {
        "ok": m3_ok,
        "b_iterations": b["mapping_iterations"],
        "c_iterations": c["mapping_iterations"],
        "saving_iterations": saving,
        "saving_pct": round(100.0 * saving / b["mapping_iterations"], 3),
        "expected_pct_prereg": -5.0,
        "expected_pct_measured_density": EXPECTED_SAVING_PCT,
        # 符号约定：saving_pct 为「节省幅度」（正值 = C 迭代更少）；
        # 两个 expected_* 以负号表示「预算应下降」。两者同向（正节省 ↔ 负预期）。
        "sign_convention": "saving_pct positive = fewer iterations in C",
    }
    report["report_only"] = {
        "a_ate_cm": a["ate_cm"], "a_iterations": a["mapping_iterations"],
        "delta_ca_cm": round(c["ate_cm"] - a["ate_cm"], 4),
        "delta_ba_cm": round(b["ate_cm"] - a["ate_cm"], 4),
    }

    if c["ate_cm"] < b["ate_cm"] - CLAIM_FLOOR_CM:
        report["verdict"] = "L1_ATE_GAIN"
        report["reasons"] = [f"ATE_C={c['ate_cm']:.4f} < ATE_B−0.5={b['ate_cm'] - CLAIM_FLOOR_CM:.4f}"]
    elif m2_ok and m3_ok:
        report["verdict"] = "L1_PASS"
        report["reasons"] = [f"|ΔATE|={abs(delta_cb):.4f} ≤ 0.5 且节省 "
                             f"{saving} 迭代（{report['m3']['saving_pct']:+.2f}%）"]
    else:
        report["verdict"] = "L1_NO_VALUE"
        if not m2_ok:
            report["reasons"].append(f"|ΔATE|={abs(delta_cb):.4f} > 0.5cm（等价门不过）")
        if not m3_ok:
            report["reasons"].append(
                f"C 迭代 {c['mapping_iterations']} 未少于 B {b['mapping_iterations']}")
    return _emit(report, args.out, rc=0)


def _emit(report, out, rc):
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(payload)
    print(payload)
    return rc


if __name__ == "__main__":
    sys.exit(main())
