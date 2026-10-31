#!/usr/bin/env python
"""judge_p0a.py — Phase 0 P0-A′ 剂量判据的机械判定器（数字零手抄）。

判据单一事实源 = `paper3/PREREGISTRATION.md` §3.1（P0-A，2026-10-28 逐事件修订）。
本脚本只做三件事，不做任何解释性判断：

  ① 首事件 k 三臂是否完全相等（含 off-free 的两臂对照：on vs negctl）；
  ② 逐事件 k 序列（按 iteration 索引对齐；报告逐事件相等/不等的计数）；
  ③ 最终高斯数（报告项，不参与 PASS/FAIL）+ ATE（tracking_raw.csv 第 8 列）。

⚠ 已知读法边界（脚本不改判据，只在输出里如实标注）：
  - P0-A′ 的「每个 densify 事件上 on 与 negctl 的 budget 相等」除首事件外**结构性
    依赖两臂地图同构**；两臂一旦选了不同的点致密化，其后地图不同、梯度统计不同，
    k 必然分叉。这与此前被废弃的「最终高斯数差 ≤2%」是同一个内生量问题在更细粒度上
    的重现（见 spec §5.3）。脚本因此把「首事件相等」与「后续事件相等」分成两行报，
    不合并成一个布尔值。
  - 参考臂 off 不打 BPW 日志（`SelectiveDensification.enabled=false` 走标量路径），
    因此「等于参考臂同事件的 |P0|」在 on 臂上的等价形式是 `budget == |{g_i>=τ_base}|`，
    即 `budget` 自身的定义；脚本报 on 臂 budget 序列，供人工与 off 侧对照。
  - `off` 臂没有 `accepted` 字段（不走选择器），格式一致但语义不同。

用法：
  python scripts/paper3_bpw/judge_p0a.py                    # 自动取每臂最新 run
  python scripts/paper3_bpw/judge_p0a.py --run-dir off=... --run-dir on=...
  python scripts/paper3_bpw/judge_p0a.py --json out.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

ARM_ROOT = "results/paper3_bpw/bpw_{arm}_balloon/datasets_bonn/bpw_{arm}_balloon/seed_0"

# console.log 里 rich 把 Log 的 "[bpw]" 前缀当样式标记吃掉了，实际行形如
#   MonoGS:  iter=1 pool=4186 budget=2187 accepted=2187 mean_p=1.00 fallback=0
BPW_RE = re.compile(
    r"iter=(\d+)\s+pool=(\d+)\s+budget=(\d+)\s+accepted=(\d+)"
    r"\s+mean_p=(-?[\d.]+)\s+fallback=(\d+)"
)


def latest_run(arm: str) -> Path | None:
    """最新 run 目录：优先已完成的（有 tracking_raw.csv），否则退到最新有 console 的。"""
    root = REPO / ARM_ROOT.format(arm=arm)
    if not root.is_dir():
        return None

    runs = sorted((d for d in root.iterdir() if d.is_dir() and (d / "console.log").is_file()), key=name)
    if not runs:
        return None
    done = [d for d in runs if (d / "tracking_raw.csv").is_file()]
    return (done or runs)[-1]


def name(p: Path) -> str:
    return p.name


def parse_events(console: Path) -> list[dict]:
    """Extract per-densify-event rows from a console.log, in log order."""
    events = []
    with open(console, "r", errors="replace") as fh:
        for line in fh:
            m = BPW_RE.search(line)
            if not m:
                continue
            it, pool, budget, accepted, mean_p, fallback = m.groups()
            events.append(
                {
                    "iter": int(it),
                    "pool": int(pool),
                    "budget": int(budget),
                    "accepted": int(accepted),
                    "mean_p": float(mean_p),
                    "fallback": int(fallback),
                }
            )
    return events


def read_last_row(csv_path: Path) -> dict | None:
    if not csv_path.is_file():
        return None
    with open(csv_path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[-1] if rows else None


def num_frames(run: Path) -> int | None:
    row = read_last_row(run / "efficiency_raw.csv")
    if not row:
        return None
    try:
        return int(float(row.get("num_frames", "nan")))
    except (TypeError, ValueError):
        return None


def summarize_arm(arm: str, run: Path | None) -> dict:
    if run is None:
        return {"arm": arm, "run": None, "error": "no run directory with console.log"}
    events = parse_events(run / "console.log")
    track = read_last_row(run / "tracking_raw.csv")
    eff = read_last_row(run / "efficiency_raw.csv")
    try:
        rel = str(run.resolve().relative_to(REPO))
    except ValueError:
        rel = str(run)
    return {
        "arm": arm,
        "run": rel,
        "num_frames": num_frames(run),
        "status": (track or {}).get("status") or (eff or {}).get("status"),
        "ate_cm": _f((track or {}).get("ate_rmse_cm")),
        "num_gaussians": _i((eff or {}).get("num_gaussians")),
        "n_events": len(events),
        "events": events,
    }


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def config_diff(a: Path, b: Path) -> list[str]:
    """两个 run 的 config.yml 差异键（排除 save_dir）；空 ⇒ 同 config，L2 合法。"""
    import yaml

    def flat(d, p=""):
        out = {}
        if isinstance(d, dict):
            for k, v in d.items():
                out.update(flat(v, f"{p}.{k}" if p else str(k)))
        else:
            out[p] = d
        return out

    fa_path, fb_path = a / "config.yml", b / "config.yml"
    if not (fa_path.is_file() and fb_path.is_file()):
        return ["<missing config.yml>"]
    fa = flat(yaml.safe_load(fa_path.read_text()))
    fb = flat(yaml.safe_load(fb_path.read_text()))
    ignore = ("Results.save_dir",)
    return [
        k
        for k in sorted(set(fa) | set(fb))
        if fa.get(k, "<missing>") != fb.get(k, "<missing>") and k not in ignore
    ]


def compare(first: dict, second: dict) -> dict:
    """Compare two arms' event series, aligned by position and by iteration index."""
    a, b = first["events"], second["events"]
    a_by_iter = {e["iter"]: e for e in a}
    b_by_iter = {e["iter"]: e for e in b}
    shared = sorted(set(a_by_iter) & set(b_by_iter))
    only_a = sorted(set(a_by_iter) - set(b_by_iter))
    only_b = sorted(set(b_by_iter) - set(a_by_iter))
    diff_rows = [
        {
            "iter": it,
            f"budget_{first['arm']}": a_by_iter[it]["budget"],
            f"budget_{second['arm']}": b_by_iter[it]["budget"],
            "delta": b_by_iter[it]["budget"] - a_by_iter[it]["budget"],
        }
        for it in shared
        if a_by_iter[it]["budget"] != b_by_iter[it]["budget"]
    ]
    return {
        "shared_iters": len(shared),
        "only_in_first": only_a,
        "only_in_second": only_b,
        "n_budget_mismatch": len(diff_rows),
        "mismatch_rows": diff_rows,
    }


def relative_delta_stats(first: dict, second: dict) -> dict:
    """逐事件 |Δk|/k_first 的中位与分位。

    分母口径 = 首次处理的臂（`first`）的 budget，与已归档地板证据
    （phase0_event_k_floor_2026-10-28 的 2.83%）一致；换分母会得到不同
    数字（max 分母 2.80%、second 分母 2.87%），故分母必须显式固定并回报。
    """
    a = {e["iter"]: e["budget"] for e in first["events"]}
    b = {e["iter"]: e["budget"] for e in second["events"]}
    shared = sorted(set(a) & set(b))
    rels = sorted(
        abs(a[i] - b[i]) / a[i] for i in shared if a[i] > 0
    )
    if not rels:
        return {"shared_iters": len(shared), "n": 0, "denominator": "first-arm budget"}
    return {
        "denominator": "first-arm budget",
        "shared_iters": len(shared),
        "n": len(rels),
        "sum_k_a": sum(a[i] for i in shared),
        "sum_k_b": sum(b[i] for i in shared),
        "rel_median_pct": 100 * statistics.median(rels),
        "rel_p90_pct": 100 * rels[min(len(rels) - 1, int(0.9 * (len(rels) - 1)))],
        "rel_max_pct": 100 * rels[-1],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-dir",
        action="append",
        default=[],
        metavar="ARM=PATH",
        help="显式指定 run 目录（可多次）；缺省则每臂自动取最新",
    )
    ap.add_argument("--json", default="", help="把完整结果写到该 JSON 路径")
    ap.add_argument(
        "--floor-run",
        action="append",
        default=[],
        metavar="ARM=PATH",
        help="同臂同 config 同 seed 的两次重跑（两个 ARM=PATH，ARM 名可重复），"
        "用其逐事件相对差中位作为装置地板；P0-A-2 已降为报告项（P3-D2-006 甲案）",
    )
    args = ap.parse_args()

    explicit = {}
    for spec in args.run_dir:
        if "=" not in spec:
            ap.error(f"--run-dir 需要 ARM=PATH 形式，收到 {spec!r}")
        arm, path = spec.split("=", 1)
        explicit[arm] = Path(path) if Path(path).is_absolute() else REPO / path

    arms = [a for a in ("off", "on", "negctl") if a in explicit or latest_run(a)]
    arms = sorted(arms, key=lambda a: ("off", "on", "negctl").index(a))

    results = {}
    for arm in arms:
        run = explicit.get(arm) or latest_run(arm)
        results[arm] = summarize_arm(arm, run)

    print("=" * 74)
    print("P0-A′ 剂量判据（paper3/PREREGISTRATION.md §3.1，逐事件口径）")
    print("=" * 74)
    for arm in arms:
        r = results[arm]
        if r.get("error"):
            print(f"\n[{arm}] {r['error']}")
            continue
        print(f"\n[{arm}] run={r['run']}")
        print(
            f"      frames={r['num_frames']} status={r['status']} "
            f"ATE={r['ate_cm']} cm  gauss={r['num_gaussians']}  events={r['n_events']}"
        )
        if r["events"]:
            e = r["events"][0]
            print(
                f"      first event: iter={e['iter']} pool={e['pool']} "
                f"budget={e['budget']} accepted={e['accepted']}"
            )

    # ① 首事件相等
    print("\n" + "-" * 74)
    print("① 首事件 k 相等（on vs negctl）")
    print("-" * 74)
    first_ok = None
    if all(results.get(a, {}).get("events") for a in ("on", "negctl")):
        e_on, e_nc = results["on"]["events"][0], results["negctl"]["events"][0]
        same = e_on["budget"] == e_nc["budget"]
        first_ok = same
        print(
            f"  on     iter={e_on['iter']} pool={e_on['pool']} budget={e_on['budget']}"
        )
        print(
            f"  negctl iter={e_nc['iter']} pool={e_nc['pool']} budget={e_nc['budget']}"
        )
        print(f"  ⇒ budget {'相等' if same else '不等'}；pool {'相等' if e_on['pool'] == e_nc['pool'] else '不等'}")
    else:
        print("  (缺 on / negctl 事件日志，无法判定)")

    # ② 逐事件 k 序列
    print("\n" + "-" * 74)
    print("② 逐事件 k 序列")
    print("-" * 74)
    cmp = None
    if all(results.get(a, {}).get("events") for a in ("on", "negctl")):
        cmp = compare(results["on"], results["negctl"])
        print(
            f"  共同 iteration 事件数={cmp['shared_iters']}  "
            f"budget 不等事件数={cmp['n_budget_mismatch']}"
        )
        if cmp["only_in_first"]:
            print(f"  仅 on 有的事件 iter={cmp['only_in_first']}")
        if cmp["only_in_second"]:
            print(f"  仅 negctl 有的事件 iter={cmp['only_in_second']}")
        if cmp["mismatch_rows"]:
            print("  首个不等事件：", cmp["mismatch_rows"][0])
    else:
        print("  (缺 on / negctl 事件日志，无法判定)")

    # ②b 装置地板（甲案：P0-A-2 降为报告项，须与跨臂差并列）
    floor = None
    if args.floor_run:
        if len(args.floor_run) != 2:
            ap.error("--floor-run 需要恰好两个 ARM=PATH（同臂同 config 同 seed 的两次重跑）")
        runs = []
        for spec in args.floor_run:
            if "=" not in spec:
                ap.error(f"--floor-run 需要 ARM=PATH 形式，收到 {spec!r}")
            arm, path = spec.split("=", 1)
            p = Path(path)
            runs.append((arm, p if p.is_absolute() else REPO / p))
        cfg_diff = config_diff(runs[0][1], runs[1][1])
        ra = summarize_arm(runs[0][0], runs[0][1])
        rb = summarize_arm(runs[1][0], runs[1][1])
        st = relative_delta_stats(ra, rb)
        floor = {
            "arm": runs[0][0],
            "runs": [str(r[1]) for r in runs],
            "config_diff": cfg_diff,
            "stats": st,
            "restats": {
                "num_gaussians": [ra["num_gaussians"], rb["num_gaussians"]],
                "ate_cm": [ra["ate_cm"], rb["ate_cm"]],
            },
        }
        print("\n" + "-" * 74)
        print("②b 装置地板（同臂同 config 同 seed 重跑；甲案：报告项，非 PASS/FAIL）")
        print("-" * 74)
        print(f"  arm={runs[0][0]}  配置差异键: {cfg_diff if cfg_diff else '无 ⇒ 同 config'}")
        if cfg_diff:
            print("  ⚠ 配置不同 ⇒ 本比较不是合法 L2 地板，只能作诊断读数")
        print(
            f"  共同事件={st.get('shared_iters')}  "
            f"k 相对差中位={st.get('rel_median_pct', float('nan')):.2f}%  "
            f"p90={st.get('rel_p90_pct', float('nan')):.2f}%  "
            f"max={st.get('rel_max_pct', float('nan')):.2f}%"
        )
        print(
            f"ΔATE = {rb['ate_cm'] - ra['ate_cm']:+.4f} cm  "
            f"Δgauss = {rb['num_gaussians'] - ra['num_gaussians']:+d}"
        )


    print("\n" + "-" * 74)
    print("③ 选择器自洽 accepted == min(budget, pool)（on / negctl）")
    print("-" * 74)
    for arm in ("on", "negctl"):
        evs = results.get(arm, {}).get("events") or []
        if not evs:
            continue
        bad = [e for e in evs if e["accepted"] != min(e["budget"], e["pool"])]
        print(f"  {arm}: {len(evs) - len(bad)}/{len(evs)} 事件自洽" + ("" if not bad else f"；不自洽示例 {bad[0]}"))

    # ④ 报告项：最终高斯数与两两差
    print("\n" + "-" * 74)
    print("④ 报告项（不参与 PASS/FAIL）：最终高斯数 / ATE")
    print("-" * 74)
    for arm in arms:
        r = results[arm]
        if r.get("error"):
            continue
        gauss = "N/A" if r["num_gaussians"] is None else f"{r['num_gaussians']:>7}"
        ate = "N/A" if r["ate_cm"] is None else f"{r['ate_cm']}"
        print(f"  {arm:7s} gauss={gauss}  ATE={ate} cm")
    g = {a: results[a].get("num_gaussians") for a in arms if not results[a].get("error")}
    if g.get("on") and g.get("negctl"):
        pct = 100.0 * (g["on"] - g["negctl"]) / g["negctl"]
        print(f"  on vs negctl 高斯数差 = {pct:+.2f}%")
    a_on, a_nc = results.get("on", {}).get("ate_cm"), results.get("negctl", {}).get("ate_cm")
    if a_on is not None and a_nc is not None:
        print(f"  ΔATE(on − negctl) = {a_on - a_nc:+.4f} cm（噪声地板 0.62 cm）")

    payload = {
        "criterion": "P0-A' per-event dose (PREREGISTRATION.md §3.1, 2026-10-28)",
        "arms": results,
        "first_event_budget_equal": first_ok,
        "per_event_comparison_on_vs_negctl": cmp,
        "device_floor": floor,
    }
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\nJSON → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
