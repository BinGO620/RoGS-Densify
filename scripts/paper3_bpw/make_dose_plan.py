#!/usr/bin/env python
"""make_dose_plan.py — 从 k0（参考剂量臂）的 trace 冻结出 FDose 的剂量计划。

规格：`paper3/results/evidence/prereg_fdose_2026-10-31.md` §2。计划 = 逐事件
源点注入数 K_i 的列表，**按事件序号**（0,1,2,…）索引；不含任何来自被处理臂的量。

为什么按事件序号而不是 raw iteration：densify 事件由
`iteration_count % gaussian_update_every` 触发，而这个计数器按 mapping 调用推进，
前后端队列时序会改变它 —— 同一 config 的两臂实测分别触发 63 与 61 个事件
（`verdict_cgb_l1_2026-10-30.md` §4.2）。按 iteration 做键会让同序号的事件在
两臂上拿到不同剂量。

输入 trace 里的 `k_plan` 列就是 k0 自计划模式算出的 K_i（= 该事件的 `|ref_sel|`）。

**N_plan**：计划会被截断到 ``--n-plan``（缺省 = 全部事件）。截断后事件序号 >= N_plan
的位置在两臂上**注入 0**（`utils.densification_selection.compute_frozen_dose_knobs`），
这样总注入量 = 计划前缀和，与各臂实际触发的事件数无关 —— 而事件数本来就不同
（同一 config 家族实测 61 / 63 / 64）。

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/make_dose_plan.py \
      --trace results/paper3_bpw/fdose_k0_person_tracking/datasets_bonn/\
fdose_k0_person_tracking/seed_0/<ts>/fdose_selection_trace.csv \
      --out results/paper3_bpw/dose_plan/person_tracking_seed0.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

PROTOCOL = "fdose-plan-v1"


def read_plan(trace: Path):
    """→ (k_list, per_event_rows)，k_list 按事件序号升序。"""
    per_event = {}
    with open(trace) as fh:
        for r in csv.DictReader(fh):
            ev, kind = int(r["event"]), r["kind"]
            row = per_event.setdefault(
                ev,
                {"event": ev, "iter": int(r["iter"]), "k_plan": int(r["k_plan"]),
                 "overflow": int(r["plan_overflow"]), "n_sel": 0, "n_pool_only": 0},
            )
            if int(r["k_plan"]) != row["k_plan"] or int(r["plan_overflow"]) != row["overflow"]:
                raise ValueError(
                    "trace 内同一事件的 k_plan/overflow 不一致：event=%d (%d,%d) vs (%d,%d)"
                    % (ev, row["k_plan"], row["overflow"],
                       int(r["k_plan"]), int(r["plan_overflow"]))
                )
            if kind == "sel":
                row["n_sel"] += 1
            else:
                row["n_pool_only"] += 1
    events = sorted(per_event)
    if events != list(range(len(events))):
        raise ValueError(
            "事件序号不连续（%s...）：trace 可能被截断或拼接，拒绝冻结计划"
            % events[:5]
        )
    rows = [per_event[e] for e in events]
    for row in rows:
        if row["overflow"]:
            raise ValueError(
                "k0 trace 出现 plan_overflow=1（event=%d）——自计划模式不可能越界，"
                "说明该 trace 不是 k0，不能当计划源" % row["event"]
            )
        if row["n_sel"] != row["k_plan"]:
            raise ValueError(
                "event=%d: 实际选 %d != k_plan %d（F1 在计划源上就不成立）"
                % (row["event"], row["n_sel"], row["k_plan"])
            )
    return [row["k_plan"] for row in rows], rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-arm", default="fdose_k0")
    ap.add_argument("--sequence", default="person_tracking")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-plan", type=int, default=None,
                    help="截断到前 N 个事件（缺省=全部）。越界事件注入 0。")
    ap.add_argument("--n-init", type=int, default=None,
                    help="前多少个事件属于 initialize_map 站点（A4 契约：必须显式给出并"
                         "写进计划；判据机默认从计划读。580 帧 person_tracking 实测 11，"
                         "由 init_itr_num/init_gaussian_update 决定，见 NEXT_SESSION 陷阱表）。")
    args = ap.parse_args(argv)

    if args.n_init is None:
        raise ValueError(
            "--n-init 必填（A4 契约 2026-11-01）：站点切分是装置参数，必须显式声明并"
            "冻进计划 —— 判据机的 F1_init/F1_map、gross 界都从它推，不允许静默默认"
        )
    trace = Path(args.trace)
    k, rows = read_plan(trace)
    n_events_in_trace = len(k)
    n_plan = n_events_in_trace if args.n_plan is None else int(args.n_plan)
    if not 1 <= n_plan <= len(k):
        raise ValueError(
            "n_plan=%d 越界（可用 1..%d）——截断只能变短，不能凭空变长" % (n_plan, len(k))
        )
    if not 0 <= args.n_init <= n_plan:
        raise ValueError(
            "n_init=%d 越界（可用 0..%d）：init 站点事件数必须落在计划长度内"
            % (args.n_init, n_plan)
        )
    if n_plan < len(k):
        print("截断计划 %d -> %d 个事件；其后两臂注入 0（总剂量 = 前缀和）"
              % (len(k), n_plan))
        k = k[:n_plan]
        rows = rows[:n_plan]

    plan = {
        "protocol": PROTOCOL,
        "source": {
            "arm": args.source_arm,
            "trace": str(trace),
            "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
            "n_events_in_trace": n_events_in_trace,
        },
        "n_plan": n_plan,
        "n_init": int(args.n_init),
        "overflow_dose": 0,
        "sequence": args.sequence,
        "seed": args.seed,
        "k": k,
        "sum_k": int(sum(k)),
        "k_min": int(min(k)),
        "k_max": int(max(k)),
        "k_median": sorted(k)[len(k) // 2],
        "per_event": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    body = out.read_bytes()
    print(
        "wrote %s (%d events, sum_k=%d, K range [%d,%d], median %d, n_init=%d)\n  sha256(plan)=%s"
        % (out, len(k), sum(k), min(k), max(k), plan["k_median"], plan["n_init"],
           hashlib.sha256(body).hexdigest())
    )


if __name__ == "__main__":
    main()
