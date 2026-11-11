#!/usr/bin/env python3
"""「生长浪费账本」提取器（P3-D2-036 口径的泛化版，P3-D2-040）。

对若干 run 目录提取 P3-D2-036 定义的账本指标：
  initial_gaussians   首个 densify 事件前的高斯数（trace 首行 n_gauss）
  final_gaussians     末态高斯数（efficiency_raw online_num_gaussians）
  sum_n_added         Σ n_added（trace 逐事件净变化，含事件内 prune）
  sum_console_removed Σ console.log「... removed N Gaussians」（P3-D2-036 同口径，
                      含 lineage prune；与 trace n_added 的口径差 = 事件外插入/删除，
                      两口径差如实并陈，不作缝合成单一"真值"）
  waste_ratio         sum_console_removed / sum_n_added（P3-D2-036 的 16.7% 同款比率）
  n_events            densify 事件数
  obs_saturation      denom 饱和度（n_gt1..n_gt30 逐阈值占比的中位事件值）——
                      MinObsGate 式干预强度在其它序列上的泛化读数

判读基准（P3-D2-036 锁定）：waste_ratio < 20% ⇒ 「刚长出来就被删」不成立。

用法:
  python scripts/paper3_bpw/selfreg_ledger.py \
    --run pt=results/paper3_bpw/e2_miss_streak_on/datasets_bonn/e2_miss_streak_on/seed_0/2026-11-06-13-22-52 \
    --run balloon=results/paper3_bpw/e2_base_balloon/datasets_bonn/e2_base_balloon/seed_0/<ts> \
    --out paper3/results/evidence/selfreg_ledger_2026-11-07.json
"""
import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

WASTE_RATIO_LINE = 0.20  # P3-D2-036 判据线


def sum_n_added(e2_csv: Path):
    """Σ n_added + 事件数 + 首事件 n_gauss + denom 饱和度分位。"""
    with e2_csv.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return None
    added = [int(r["n_added"]) for r in rows if r["n_added"] != ""]
    sat = {}
    for thr in ("1", "3", "5", "10", "20", "30"):
        vals = []
        for r in rows:
            v = r.get(f"n_gt{thr}", "")
            if v != "" and int(r["n_gauss"]) > 0:
                vals.append(int(v) / int(r["n_gauss"]))
        sat[thr] = round(statistics.median(vals), 4) if vals else None
    return {
        "n_events": len(rows),
        "initial_gaussians": int(rows[0]["n_gauss"]),
        "last_event_gaussians": int(rows[-1]["n_gauss"]),  # P3-D2-036 文档「最终高斯」口径
        "sum_n_added": sum(added),
        "obs_saturation_median": sat,
    }


def sum_console_removed(console: Path):
    """Σ「removed N Gaussians」（P3-D2-036 口径：全部 Pruned 行，含 lineage prune）。"""
    pat = re.compile(r"removed (\d+) Gaussians")
    total = 0
    n_lines = 0
    with console.open(errors="ignore") as fh:
        for line in fh:
            m = pat.search(line)
            if m:
                total += int(m.group(1))
                n_lines += 1
    return total, n_lines


def final_gaussians(run: Path):
    eff = run / "efficiency_raw.csv"
    if not eff.is_file():
        return None
    rows = list(csv.DictReader(open(eff, newline="")))
    return int(float(rows[0]["online_num_gaussians"])) if rows else None


def extract(run: Path):
    e2 = run / "e2_events.csv"
    con = run / "console.log"
    if not e2.is_file():
        return None, f"缺 e2_events.csv：{run}"
    if not con.is_file():
        return None, f"缺 console.log：{run}"
    base = sum_n_added(e2)
    if base is None:
        return None, f"e2_events.csv 为空：{run}"
    removed, n_prune_lines = sum_console_removed(con)
    final = final_gaussians(run)
    out = {
        **base,
        "sum_console_removed": removed,
        "n_prune_console_lines": n_prune_lines,
        "final_gaussians": final,
    }
    if base["sum_n_added"] > 0:
        out["waste_ratio"] = round(removed / base["sum_n_added"], 4)
        out["waste_ratio_below_line"] = out["waste_ratio"] < WASTE_RATIO_LINE
    else:
        out["waste_ratio"] = None
        out["waste_ratio_below_line"] = None
    return out, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="append", required=True,
                    help="name=run_dir，可重复")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    report = {
        "tool": "selfreg_ledger (P3-D2-040)",
        "waste_ratio_line": WASTE_RATIO_LINE,
        "ledger": {},
        "all_below_line": None,
        "errors": [],
    }
    for spec in args.run:
        name, _, path = spec.partition("=")
        if not name or not path:
            ap.error(f"--run 需要 name=run_dir 形式，收到 {spec!r}")
        rec, err = extract(Path(path))
        if err:
            report["errors"].append(f"{name}: {err}")
            report["ledger"][name] = {"error": err}
            continue
        report["ledger"][name] = rec

    ratios = [v.get("waste_ratio") for v in report["ledger"].values()
              if isinstance(v, dict) and v.get("waste_ratio") is not None]
    report["all_below_line"] = all(r < WASTE_RATIO_LINE for r in ratios) if ratios else None

    print(f"{'seq':>12} {'events':>7} {'init_g':>8} {'final_g':>8} {'Σn_added':>9} "
          f"{'Σrmvd':>8} {'ratio':>7} {'<20%':>5}")
    for name, v in report["ledger"].items():
        if "error" in v:
            print(f"{name:>12}  ERROR: {v['error']}")
            continue
        print(f"{name:>12} {v['n_events']:>7} {v['initial_gaussians']:>8} "
              f"{(v['final_gaussians'] or 0):>8} {v['sum_n_added']:>9} "
              f"{v['sum_console_removed']:>8} "
              f"{(v['waste_ratio'] if v['waste_ratio'] is not None else float('nan')):>7.4f} "
              f"{str(v['waste_ratio_below_line']):>5}")
    print(f"\nALL_BELOW_LINE(自调节泛化): {report['all_below_line']}")
    for e in report["errors"]:
        print(f"  ! {e}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
