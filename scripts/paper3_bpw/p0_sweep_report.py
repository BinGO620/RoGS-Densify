#!/usr/bin/env python
"""p0_sweep_report.py — 生成 p0 扫描的完整汇总（含基准 p0=8），数字零手抄。

`analyze_p0_sweep.py` 只扫 `sweep_p0_*` 目录，会漏掉 p0=8 的基准 run
（它在 `bpw_on_person_tracking` 下）。本脚本补齐基准点 + 输出 JSON，
供 `p0_sweep_result_*.md` 直接引用。

用法：
  python scripts/paper3_bpw/p0_sweep_report.py \
      --baseline-p0 8 \
      --baseline-run results/paper3_bpw/bpw_on_person_tracking/datasets_bonn/bpw_on_person_tracking/seed_0/2026-10-28-21-37-02 \
      --off-run     results/paper3_bpw/bpw_off_person_tracking/datasets_bonn/bpw_off_person_tracking/seed_0/2026-10-28-20-52-14 \
      --json paper3/results/evidence/p0_sweep_result_2026-10-29.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

EVENT_RE = re.compile(r"iter=(\d+)\s+pool=(\d+)\s+budget=(\d+)\s+accepted=(\d+)")


def _last(path: Path) -> dict:
    if not path.is_file():
        return {}
    rows = list(csv.DictReader(open(path)))
    return rows[-1] if rows else {}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_run(d: Path) -> dict:
    t = _last(d / "tracking_raw.csv")
    e = _last(d / "efficiency_raw.csv")
    events = []
    console = d / "console.log"
    if console.is_file():
        for line in console.read_text(errors="replace").splitlines():
            m = EVENT_RE.search(line)
            if m:
                events.append(
                    {
                        "iter": int(m.group(1)),
                        "pool": int(m.group(2)),
                        "budget": int(m.group(3)),
                        "accepted": int(m.group(4)),
                    }
                )
    return {
        "run_dir": str(d),
        "status": t.get("status"),
        "ate_cm": _f(t.get("ate_rmse_cm")),
        "kf_ate_cm": _f(t.get("keyframe_ate_rmse_cm")),
        "num_gaussians": _f(e.get("online_num_gaussians")),
        "n_events": len(events),
        "sum_budget": sum(x["budget"] for x in events),
        "first_budget": events[0]["budget"] if events else None,
        "events": events,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-p0", type=float, default=8.0)
    ap.add_argument("--baseline-run", required=True)
    ap.add_argument("--off-run", required=True)
    ap.add_argument("--sweep-root", default="results/paper3_bpw")
    ap.add_argument("--pattern", default="sweep_p0_*_person_tracking")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    root = Path(args.sweep_root)
    if not root.is_absolute():
        root = REPO / root

    arms = {}
    for g in sorted(glob.glob(str(root / args.pattern / "datasets_bonn" / "*" / "seed_0" / "*"))):
        d = Path(g)
        m = re.search(r"_p0(?:_|)(\d+)(?:_|$)", str(d))
        if not m:
            continue
        arms[float(m.group(1))] = read_run(d)

    for label, p in (("baseline", Path(args.baseline_run)), ("off", Path(args.off_run))):
        if not p.is_absolute():
            p = REPO / p
        r = read_run(p)
        if label == "baseline":
            arms[args.baseline_p0] = r
        else:
            off = r

    if not arms:
        print("未找到任何 p0 run", file=sys.stderr)
        return 1

    print("# p0 扫描汇总（含基准 p0=%g）\n" % args.baseline_p0)
    print("| p0 | ATE (cm) | 相对 p0=%g | 高斯数 | 事件数 | Σbudget | 首事件 budget |"
          % args.baseline_p0)
    print("|---:|---:|---:|---:|---:|---:|---:|")
    ref = arms[args.baseline_p0]["ate_cm"]
    for p in sorted(arms):
        r = arms[p]
        delta = "—" if (r["ate_cm"] is None or ref is None) else "%+.4f" % (r["ate_cm"] - ref)
        print(
            "| %g | %s | %s | %s | %d | %d | %s |"
            % (
                p,
                "—" if r["ate_cm"] is None else "%.4f" % r["ate_cm"],
                delta,
                "—" if r["num_gaussians"] is None else "%d" % r["num_gaussians"],
                r["n_events"],
                r["sum_budget"],
                r["first_budget"],
            )
        )

    print("\n基线 off（无选择器，控制台无逐事件记录）：ATE %s cm，高斯 %s，事件 %d"
          % (off["ate_cm"], off["num_gaussians"], off["n_events"]))

    print("\n## 相邻 p0 差分\n")
    ks = sorted(arms)
    adj = []
    for a, b in zip(ks, ks[1:]):
        if arms[a]["ate_cm"] is None or arms[b]["ate_cm"] is None:
            continue
        dd = arms[b]["ate_cm"] - arms[a]["ate_cm"]
        adj.append({"from": a, "to": b, "delta_cm": dd})
        print("- %g → %g：%+.4f cm" % (a, b, dd))

    vals = [arms[p]["ate_cm"] for p in ks if arms[p]["ate_cm"] is not None]
    summary = {
        "p0_values": ks,
        "ate_cm": {str(p): arms[p]["ate_cm"] for p in ks},
        "num_gaussians": {str(p): arms[p]["num_gaussians"] for p in ks},
        "n_events": {str(p): arms[p]["n_events"] for p in ks},
        "sum_budget": {str(p): arms[p]["sum_budget"] for p in ks},
        "first_budget": {str(p): arms[p]["first_budget"] for p in ks},
        "adjacent_deltas": adj,
        "ate_span_cm": max(vals) - min(vals),
        "ate_median_abs_dev_from_baseline_cm": statistics.median(
            abs(arms[p]["ate_cm"] - ref) for p in ks
        ),
        "off": off,
        "arms": {str(p): arms[p] for p in ks},
    }
    print("\nATE 跨度（max−min）：%.4f cm" % summary["ate_span_cm"])

    if args.json:
        out = Path(args.json)
        if not out.is_absolute():
            out = REPO / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        print("JSON → %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
