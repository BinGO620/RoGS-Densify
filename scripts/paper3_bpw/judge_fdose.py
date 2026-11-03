#!/usr/bin/env python
"""judge_fdose.py — FDose 出口判定（机械应用 prereg §6 六条规则），零 GPU。

输入 = 三臂 run 目录（**显式路径**，不用 latest_run 隐式查找）。
输出 = markdown + JSON —— **判决书由本脚本生成**，不手写
（CGB 审查 S2 的教训：手写判决与判据机两套梯度并存）。

判据来源（不得在此改）：`paper3/results/evidence/prereg_fdose_2026-10-31.md` §5/§6

口径（`DISCIPLINE.md`「测量口径」#12）：
  ATE  = `tracking_raw.csv` 的 `ate_rmse_cm`（全帧口径；不是 console 的 RMSE ATE）
  高斯 = `efficiency_raw.csv` 的 `online_num_gaussians` / `refined_num_gaussians`
         **两列并陈**（CGB 教训：8 臂中 2 臂两列差 +5,000 = 末端 KF 竞态）
  地板 = `paper3/results/evidence/seq_floors_2026-10-30.json` 的逐序列值
  R6/R7 = 两臂 run 目录里 `fdose_selection_trace.csv` 的池规模/iter（prereg §4.2
         「必须报」的残余混杂量化；**报告项**，缺 trace 显式声明 missing）

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/judge_fdose.py --seed 0 \
      --k0 results/paper3_bpw/fdose_k0_person_tracking/datasets_bonn/.../seed_0/<ts> \
      --g  results/paper3_bpw/fdose_G_person_tracking/datasets_bonn/.../seed_0/<ts> \
      --s  results/paper3_bpw/fdose_S_person_tracking/datasets_bonn/.../seed_0/<ts> \
      --seq person_tracking --out-md ... --out-json ...
  # 多 seed（推荐）：显式 run 目录清单，不手填 Δ
  $PY scripts/paper3_bpw/judge_fdose.py --seed 0 --runs runs.json ...
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLOORS = REPO / "paper3/results/evidence/seq_floors_2026-10-30.json"
# prereg §5：sd 取两个来源里保守者。A = bpw on−off 逐 seed 配对差 sd（n=3, pt）；
# B = off vs off_trace 同 config 零对比差（单对，当 sd 用偏乐观）。
SD_SOURCES = {
    "A_paired_on_off": {"sd": 1.491, "n_seed": 3,
                        "diffs_cm": [0.2219, 0.4995, 2.9327],
                        "src": "bpw_on vs bpw_off, person_tracking, 3 seeds"},
    "B_same_config_null": {"sd": 0.951, "n_seed": 1,
                           "diff_cm": 0.9514,
                           "src": "off vs off_trace, same config/seed, 580 frames"},
}
MDE_T = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365}


def _read_one(path: Path, column: str, expect_run_id=None):
    """Read one column, refusing ambiguity instead of silently taking the last row.

    ``tables/*.csv`` are **appended** to (`eval_utils._write_csv_row` opens "a"),
    so a re-run of the same seed leaves several rows in the same file. Taking
    ``rows[-1]`` would silently pick one of them — the same failure family as
    ``latest_run()`` picking the wrong directory (M7). Rules:
      * 0 rows                     -> None
      * >1 distinct ``run_id``     -> raise (ambiguous file, must be split)
      * ``expect_run_id`` mismatch -> raise
      * >1 row with the same run_id-> raise (duplicated append)

    （A6：删掉声明后从未使用的 ``expect_frames`` 形参 —— 帧数闸的真实现是
    ``--expect-frames`` CLI 绝对闸，见 main；死参数会让人误以为闸已生效。）
    """
    if not path.is_file():
        return None
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return None
    run_ids = {r.get("run_id") for r in rows if r.get("run_id")}
    if len(run_ids) > 1:
        raise ValueError(
            "%s 内含 %d 个不同 run_id %s —— 同 seed 重跑被追加进同一张表，"
            "不能静默取末行（M7）。请按 run 目录分别读，或先拆分该表。"
            % (path, len(run_ids), sorted(run_ids))
        )
    if len(rows) > 1:
        raise ValueError(
            "%s 有 %d 行且 run_id 相同 —— 重复追加，读数不可判（M7）。" % (path, len(rows))
        )
    if expect_run_id and run_ids and expect_run_id not in run_ids:
        raise ValueError(
            "%s 的 run_id=%s 与 run 目录名 %s 不一致" % (path, sorted(run_ids), expect_run_id)
        )
    try:
        return float(rows[-1][column])
    except (KeyError, TypeError, ValueError):
        return None


def read_arm(run_dir: Path):
    """Read one arm from an **explicit** run directory.

    本 run 目录里的表可能不在目录内而在 `<arm>/tables/`（MonoGS 的表格是臂级、
    不在时间戳目录里）。先看 run 目录，再回落到臂级 tables —— 但回落的表**必须**
    按 run 目录名核 run_id（见 `_read_one`），否则同臂两个时间戳会混。
    """
    run_dir = Path(run_dir)
    rid = run_dir.name

    def _pick(name):
        local = run_dir / name
        if local.is_file():
            return local
        # <save_dir>/datasets_bonn/<run>/seed_<n>/<ts>/  ->  <save_dir>/tables/<name>
        # <save>/datasets_bonn/<run>/seed_<n>/<ts> -> parents[0..3] 是 seed/run/datasets_bonn/<save>
        cand = run_dir.parents[3] / "tables" / name if len(run_dir.parents) > 3 else None
        return cand if cand is not None and cand.is_file() else local

    tr = _pick("tracking_raw.csv")
    ef = _pick("efficiency_raw.csv")
    return {
        "run_dir": str(run_dir),
        "ate_cm": _read_one(tr, "ate_rmse_cm", expect_run_id=rid),
        "num_gaussians": _read_one(ef, "online_num_gaussians", expect_run_id=rid),
        "refined_gaussians": _read_one(ef, "refined_num_gaussians", expect_run_id=rid),
        "num_frames": _read_one(ef, "num_frames", expect_run_id=rid),
    }


def mde(sd: float, n: int):
    if n < 2 or n not in MDE_T:
        return None
    return MDE_T[n] * sd / (n ** 0.5)


# A4 阈值（与 check_fdose_gate.py 的常量同源；此处只做 provenance 声明，不重复判定）。
A4_THRESHOLDS = {"mean_min": 1.15, "event_ratio_min": 1.10, "event_share_min": 0.60}
A4_PROVENANCE = {
    "amendment": "P3-D2-014",
    "amendment_file": "paper3/results/evidence/prereg_fdose_amendment_a4_2026-11-02.md",
    "approved": "2026-11-02",
    "landing_commits": {"amendment": "3dd1fa093", "implementation": "54c33e07e",
                        "validation": "62371430f"},
    "post_data_instrument_correction": True,
    "thresholds": A4_THRESHOLDS,
    "thresholds_changed": False,       # 1.15/1.10/60% 沿用 Amendment A1，未因 ATE 放宽
    "ATE_not_used_to_choose_threshold": True,
    "anchor_seed": 0,
    # confirmation_seeds 不再硬编码（G2 2026-11-03 重大#3）：由 manifest 的
    # selected_role 动态生成，避免 n 变化时 provenance 与被证事实脱节。
}


def _norm(p):
    """路径归一（相对/绝对都收成 as_posix 字符串，去掉末尾斜杠）。"""
    return str(Path(p).as_posix()).rstrip("/") if p is not None else None


def validate_gate_artifact(gate_path: Path, seed_key: str, arms_s, plan_sha=None):
    """校验某 seed 的 A4 gate 工件与 manifest 选定 run **一致**，并返回其 A4 读数。

    G2 教训（2026-11-02 Reject 重大#2/#3）：判决不得跳过 gate。这里的规则是
    **只消费、不重算**——gate JSON 缺失/损坏/`verdict=FAIL`/source 与 manifest 选定
    run 不一致/plan sha 不一致 ⇒ 直接 raise（main 转 rc=2），禁止从 raw trace"自救"。
    """
    gp = Path(gate_path)
    if not gp.is_file():
        raise ValueError("%s: gate JSON 不存在（%s）—— 判决必须消费 gate 工件，"
                         "不得从 raw trace 重算（G2 重大#2）" % (seed_key, gp))
    g = json.loads(gp.read_text())
    if g.get("verdict") != "PASS":
        raise ValueError("%s: gate verdict=%s ≠ PASS —— 装置门未过，不得出判决"
                         % (seed_key, g.get("verdict")))
    if not g.get("f3a_prime_ok"):
        raise ValueError("%s: gate f3a_prime_ok 非 True —— F3a′ 未过" % seed_key)
    src = g.get("source", {})
    # gate 的 source 给的是 trace 路径；manifest 给的是 run 目录 ⇒ 比对父目录。
    for arm in ("G", "S", "k0"):
        want = _norm(arms_s[arm]["run_dir"])
        got = _norm(src.get(arm.lower()))
        if got is None or Path(got).parent.as_posix().rstrip("/") != want:
            raise ValueError("%s: gate source.%s=%s 与 manifest 选定 run=%s 不一致"
                             % (seed_key, arm, got, want))
    # done 锚点硬校验（G2 2026-11-03 次要#9）：gate 自己算过 done_ok，判决必须复核，
    # 否则「无 .done 的 run」只要 gate 的 F3a′ 过就能出判决。
    if g.get("done_ok") is not True:
        raise ValueError("%s: gate done_ok=%r ≠ True —— 正式批判读必须 --require-done"
                         % (seed_key, g.get("done_ok")))
    # plan sha：**必须在计划文件实体上重算**（G2 2026-11-03 重大#1）。
    # plan_sha_for 取不到（gate 无 source.plan / 计划文件缺失）⇒ fail-closed。
    if plan_sha is None:
        raise ValueError("%s: 无法从 gate 记录的 plan 路径重算 sha（source.plan 缺失或"
                         "计划文件不存在）—— 计划一致性不可证，不得出判决" % seed_key)
    got_sha = (g.get("plan") or {}).get("sha256")
    if got_sha != plan_sha:
        raise ValueError("%s: gate plan sha=%s ≠ 计划文件实算 sha=%s（门与计划不配套）"
                         % (seed_key, got_sha, plan_sha))
    fp = g.get("f3a_prime") or {}
    cb = g.get("f3a_cross_arm") or {}
    pbl = g.get("pool_baseline_ratio") or {}
    return {
        "gate_path": _norm(gp),
        "gate_verdict": g.get("verdict"),
        "plan_sha256": (g.get("plan") or {}).get("sha256"),
        "f3a_prime_mean": fp.get("f3a_prime_mean"),
        "f3a_prime_share_above": fp.get("f3a_prime_share_above"),
        "f3a_prime_events": fp.get("n_events"),
        "f3a_prime_reason": fp.get("reason"),
        "f3a_cross_arm_mean": cb.get("ratio_mean"),
        "pool_baseline_median": pbl.get("ratio_median"),
    }


def arms_snapshot(arms_s):
    """每 seed 原始读数快照（G2 次要#3：判决 JSON 必须自带 ATE，不让人跳九个 CSV）。"""
    return {a: {k: v[k] for k in ("run_dir", "ate_cm", "num_gaussians",
                                  "refined_gaussians", "num_frames")}
            for a, v in arms_s.items()}


def read_fdose_trace(run_dir: Path):
    """读 run 目录里的 `fdose_selection_trace.csv`（R6/R7 的数据源）。

    → {event: {"n_sel", "n_pool_only", "pool_idx": set, "iter"}}；文件缺失 → None
    （R6/R7 是报告项，缺源时必须显式声明 missing，不得静默略过 —— M3 类教训）。
    """
    p = Path(run_dir) / "fdose_selection_trace.csv"
    if not p.is_file():
        return None
    per = {}
    with open(p) as fh:
        for r in csv.DictReader(fh):
            e = int(r["event"])
            d = per.setdefault(e, {"n_sel": 0, "n_pool_only": 0,
                                   "pool_idx": set(), "iter": int(r["iter"])})
            d["pool_idx"].add(int(r["gauss_idx"]))
            if r["kind"] == "sel":
                d["n_sel"] += 1
            else:
                d["n_pool_only"] += 1
    return per


def _iqr(values):
    """→ (q25, q75)；样本 < 2 时给 None（statistics.quantiles 需要 ≥2 个点）。"""
    if len(values) < 2:
        return None, None
    q = st.quantiles(values, n=4)
    return q[0], q[2]


def r6_pool_drift(tr_g, tr_s):
    """R6 候选集漂移（prereg §4.2，**报告项**）：本设计的主要残余混杂。

    同序数事件上两臂 |pool|（sel + pool_only）的相对差 中位 + IQR；以及池的
    gauss_idx 交集占比（Jaccard）。⚠ 后者与 F3b 同源：两臂各自在线长地图 ⇒
    索引空间不可比，这个数量化的是**地图分叉**，不是「候选集重合度」——
    报告里必须带这条口径说明（prereg §0：未切断「候选集仍各自长」）。
    """
    common = sorted(set(tr_g) & set(tr_s))
    rel, jac = [], []
    for e in common:
        pg = tr_g[e]["n_sel"] + tr_g[e]["n_pool_only"]
        ps = tr_s[e]["n_sel"] + tr_s[e]["n_pool_only"]
        if pg > 0:
            rel.append((ps - pg) / pg)
        union = tr_g[e]["pool_idx"] | tr_s[e]["pool_idx"]
        if union:
            jac.append(len(tr_g[e]["pool_idx"] & tr_s[e]["pool_idx"]) / len(union))
    q1, q3 = _iqr(rel)
    q1j, q3j = _iqr(jac)
    return {
        "n_common_events": len(common),
        "pool_rel_diff_median": st.median(rel) if rel else None,
        "pool_rel_diff_iqr": [q1, q3],
        "pool_rel_diff_min": min(rel) if rel else None,
        "pool_rel_diff_max": max(rel) if rel else None,
        "pool_jaccard_mean": (sum(jac) / len(jac)) if jac else None,
        "pool_jaccard_median": st.median(jac) if jac else None,
        "pool_jaccard_iqr": [q1j, q3j],
        "caveat": "池 Jaccard 跨索引空间不可比，量化的是地图分叉（prereg §0）",
    }


def r7_ordinal_time_shift(tr_g, tr_s):
    """R7 序数—时间错位（prereg §4.2，**报告项**）：§0 第三条未切断项的量化。

    同序数事件 `iter_S − iter_G` 的中位 + p90 + 极值；两臂事件总数差。
    「一个事件间隔」= 两臂各自相邻事件 iter 差中位的较大者（保守界）。
    触发条件（prereg 原文）：事件数差 > 2 或 |偏移| p90 > 一个事件间隔 ⇒
    判决必须明写「剂量按数量相等，不按地图时刻相等」。
    """
    common = sorted(set(tr_g) & set(tr_s))
    diffs = [tr_s[e]["iter"] - tr_g[e]["iter"] for e in common]
    abs_sorted = sorted(abs(d) for d in diffs)
    p90 = (abs_sorted[min(len(abs_sorted) - 1, int(round(0.9 * (len(abs_sorted) - 1))))]
           if abs_sorted else None)

    def _gap(tr):
        its = sorted(tr[e]["iter"] for e in tr)
        g = [b - a for a, b in zip(its, its[1:]) if b > a]
        return st.median(g) if g else None

    gaps = [g for g in (_gap(tr_g), _gap(tr_s)) if g is not None]
    gap_ref = max(gaps) if gaps else None
    n_diff = len(tr_s) - len(tr_g)
    warn = ((abs(n_diff) > 2)
            or (p90 is not None and gap_ref is not None and p90 > gap_ref))
    return {
        "n_common_events": len(common),
        "n_events_G": len(tr_g), "n_events_S": len(tr_s),
        "n_events_diff": n_diff,
        "iter_diff_median": st.median(diffs) if diffs else None,
        "abs_iter_diff_p90": p90,
        "abs_iter_diff_min": min(abs_sorted) if abs_sorted else None,
        "abs_iter_diff_max": max(abs_sorted) if abs_sorted else None,
        "event_gap_median_ref": gap_ref,
        "warn_dose_by_count_not_time": warn,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--k0", required=True)
    ap.add_argument("--g", required=True, help="γ=0 臂 run 目录")
    ap.add_argument("--s", required=True, help="γ=1 臂 run 目录")
    ap.add_argument("--seed", type=int, required=True, help="本判定对应的 seed（单 seed 判定用）")
    ap.add_argument("--runs", default=None,
                    help="多 seed 判定：JSON 文件，形如 "
                         '{"0": {"k0": "...", "G": "...", "S": "..."}, "1": {...}, ...}'
                         "（每项是该 seed 三个臂的**显式 run 目录**）。给出才走 §6 规则 2–5。"
                         "不接受手填的 Δ 值 —— 汇总这一步最容易出错，必须由 run 目录机算。")
    ap.add_argument("--seq", default="person_tracking")
    ap.add_argument("--expect-frames", type=int, default=580,
                    help="帧数绝对闸（A6）：三臂帧数必须彼此一致**且**等于本值 —— 旧的"
                         "相对闸只查一致性，三臂同为 40 帧的冒烟也能过，「冒烟混进全长"
                         "判定」无闸可挡。冒烟判定须显式传 --expect-frames 40。")
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args(argv)

    arms = {
        "k0": read_arm(Path(args.k0)),
        "G": read_arm(Path(args.g)),
        "S": read_arm(Path(args.s)),
    }
    missing = [k for k, v in arms.items()
               if v["ate_cm"] is None or v["num_gaussians"] is None]
    if missing:
        print("ERROR: 缺读数 %s —— 检查路径与 status" % missing, file=sys.stderr)
        return 2

    floors = json.loads(FLOORS.read_text())["per_sequence"]
    floor = float(floors[args.seq]["floor_cm_conservative"])

    # R6/R7（prereg §4.2，报告项，不入 PASS/FAIL）：数据源 = 两臂 run 目录里的
    # fdose_selection_trace.csv。缺 trace 时显式报 missing（M3 类：声明了的证据
    # 通道必须有产出或显式缺源声明，不许静默消失）。
    def _r6r7(g_dir, s_dir):
        trg, trs = read_fdose_trace(Path(g_dir)), read_fdose_trace(Path(s_dir))
        if trg is None or trs is None:
            miss = "/".join(n for n, t in (("G", trg), ("S", trs)) if t is None)
            return None, "缺 %s 臂的 fdose_selection_trace.csv" % miss
        return (r6_pool_drift(trg, trs), r7_ordinal_time_shift(trg, trs)), None

    r6r7, r6r7_missing = _r6r7(args.g, args.s)

    frames = {k: v["num_frames"] for k, v in arms.items()}
    frame_vals = {int(f) for f in frames.values() if f is not None}
    if len(frame_vals) != 1:
        print("ERROR: 三臂帧数不一致 %s —— 跨帧数比较无效" % frames, file=sys.stderr)
        return 2
    # A6 帧数绝对闸：三臂一致还不够 —— 三臂同为 40 帧的冒烟也能过相对闸；
    # 「冒烟混进全长判定」必须由绝对值挡住（prereg 装置陷阱：40 帧 ATE ≈1.2cm vs
    # 580 帧 ≈11.5cm，混比即假判决）。
    if frame_vals != {args.expect_frames}:
        print("ERROR: 三臂帧数 %s ≠ --expect-frames %d —— 冒烟与全长混比无闸（A6）；"
              "若本判定确实是冒烟，请显式传 --expect-frames 40"
              % (sorted(frame_vals), args.expect_frames), file=sys.stderr)
        return 2

    d_S_G = arms["S"]["ate_cm"] - arms["G"]["ate_cm"]
    d_G_k0 = arms["G"]["ate_cm"] - arms["k0"]["ate_cm"]
    d_S_k0 = arms["S"]["ate_cm"] - arms["k0"]["ate_cm"]

    seed_deltas = None
    per_seed = None
    per_seed_meta = {}
    per_seed_gate = {}

    def plan_sha_for(seed_key):
        """**独立**读取冻结计划文件并算 sha（G2 2026-11-03 重大#1 修复）。

        旧实现从 gate JSON 自己读 sha 再与 gate 自己比 ⇒ 恒真、校验空转。
        现改为：按 gate 记录的 plan **路径**打开计划文件，重算 sha256；
        文件缺失/不可读 ⇒ 返回 None ⇒ 校验分支报错（fail-closed），
        禁止以 gate 自述值代替文件实体。
        """
        try:
            gp = json.loads(Path(spec[seed_key]["gate_json"]).read_text())
            plan_rel = (gp.get("source") or {}).get("plan") or (gp.get("plan") or {}).get("path")
            if not plan_rel:
                return None
            import hashlib
            pf = Path(plan_rel)
            if not pf.is_file():
                return None
            return hashlib.sha256(pf.read_bytes()).hexdigest()
        except Exception:
            return None

    if args.runs:
        spec = json.loads(Path(args.runs).read_text())
        # A6 schema 校验：键必须是数字 seed 字符串、每项必须含 k0/G/S 三个显式路径 ——
        # 缺键原样走到取 Δ 时抛未捕获 KeyError（不清晰）；这里改成 rc=2 的可读报错。
        if not isinstance(spec, dict) or not spec:
            print("ERROR: --runs 必须是非空 JSON 对象 {\"<seed>\": {\"k0\":…, \"G\":…, \"S\":…}}",
                  file=sys.stderr)
            return 2
        bad_keys = [k for k in spec if not str(k).isdigit()]
        if bad_keys:
            print("ERROR: --runs 的 seed 键必须是数字字符串，坏键 %s" % bad_keys,
                  file=sys.stderr)
            return 2
        for seed_key in sorted(spec, key=lambda v: int(v)):
            entry = spec[seed_key]
            if (not isinstance(entry, dict)
                    or not {"k0", "G", "S"} <= set(entry)
                    or not all(isinstance(entry.get(a), str) and entry[a]
                               for a in ("k0", "G", "S"))):
                print("ERROR: --runs seed %s 缺 k0/G/S 键或值不是非空路径字符串 —— "
                      "schema：{\"<seed>\": {\"k0\":…, \"G\":…, \"S\":…}}" % seed_key,
                      file=sys.stderr)
                return 2
        if str(args.seed) not in spec:
            print("ERROR: --runs 的 seed 集合 %s 不含 --seed %d —— 锚定 seed 必须"
                  "在多 seed 清单里（A6 一致性校验）" % (sorted(spec), args.seed),
                  file=sys.stderr)
            return 2
        # A4 元数据键（gate/role/first_run 等）不得被当成 arm 路径读入。
        ARM_KEYS = ("k0", "G", "S")
        META_KEYS = ("gate_json", "selected_role", "selection_reason",
                     "first_run", "first_run_gate_json")
        per_seed = {}
        for seed_key in sorted(spec, key=lambda v: int(v)):
            entry = spec[seed_key]
            bad = sorted(set(entry) - set(ARM_KEYS) - set(META_KEYS))
            if bad:
                print("ERROR: seed %s 的 --runs 条目含未知键 %s（允许 arm %s + 元数据 %s）"
                      % (seed_key, bad, list(ARM_KEYS), list(META_KEYS)), file=sys.stderr)
                return 2
            arms_s = {k: read_arm(Path(entry[k])) for k in ARM_KEYS}
            missing_s = [k for k, v in arms_s.items()
                         if v["ate_cm"] is None or v["num_gaussians"] is None]
            if missing_s:
                print("ERROR: seed %s 缺读数 %s" % (seed_key, missing_s), file=sys.stderr)
                return 2
            frames_s = {int(v["num_frames"]) for v in arms_s.values()
                        if v["num_frames"] is not None}
            if len(frames_s) != 1:
                print("ERROR: seed %s 三臂帧数不一致 %s" % (seed_key, frames_s),
                      file=sys.stderr)
                return 2
            if frames_s != {args.expect_frames}:
                print("ERROR: seed %s 三臂帧数 %s ≠ --expect-frames %d（A6 绝对闸；"
                      "冒烟判定须显式传 --expect-frames 40）"
                      % (seed_key, sorted(frames_s), args.expect_frames),
                      file=sys.stderr)
                return 2
            per_seed[seed_key] = arms_s
            per_seed_meta[seed_key] = {k: entry.get(k) for k in META_KEYS if k in entry}
            # gate 工件校验（只消费、不重算）：缺失/FAIL/source 不符/plan sha 不符 ⇒ rc=2
            if not per_seed_meta[seed_key].get("gate_json"):
                print("ERROR: seed %s 缺 gate_json 元数据 —— 多 seed 判决必须绑定每 seed 的 "
                      "gate 工件（A4/G2 重大#2）；旧式 {k0,G,S} 清单只用于装置门之前的诊断"
                      % seed_key, file=sys.stderr)
                return 2
            try:
                per_seed_gate[seed_key] = validate_gate_artifact(
                    Path(per_seed_meta[seed_key]["gate_json"]), seed_key, arms_s,
                    plan_sha=plan_sha_for(seed_key))
            except ValueError as exc:
                print("ERROR: %s" % exc, file=sys.stderr)
                return 2
        if per_seed:
            seed_deltas = [per_seed[s]["S"]["ate_cm"] - per_seed[s]["G"]["ate_cm"]
                           for s in per_seed]
    # 首跑 vs 诊断重跑并陈（G2 致命项）：seed0 若在 manifest 里标了 first_run，
    # 就把首跑的三臂 ATE 与 Δ 一并机算出来——**不许静默替换**。
    first_vs_rerun = None
    meta0 = per_seed_meta.get(str(args.seed)) if per_seed_meta else None
    if meta0 and meta0.get("first_run"):
        try:
            fr = {a: read_arm(Path(meta0["first_run"][a])) for a in ("k0", "G", "S")}
            fr_delta = fr["S"]["ate_cm"] - fr["G"]["ate_cm"]
            re_delta = (per_seed[str(args.seed)]["S"]["ate_cm"]
                        - per_seed[str(args.seed)]["G"]["ate_cm"])
            first_vs_rerun = {
                "selected_role": meta0.get("selected_role"),
                "selection_reason": meta0.get("selection_reason"),
                "first_run": arms_snapshot(fr),
                "first_run_deltas_cm": {
                    "S_minus_G": fr_delta,
                    "G_minus_k0": fr["G"]["ate_cm"] - fr["k0"]["ate_cm"],
                    "S_minus_k0": fr["S"]["ate_cm"] - fr["k0"]["ate_cm"],
                },
                "rerun": arms_snapshot(per_seed[str(args.seed)]),
                "rerun_deltas_cm": {"S_minus_G": re_delta},
                "direction_flip_cm": {"from": fr_delta, "to": re_delta,
                                      "flipped": (fr_delta > 0) != (re_delta > 0)},
                "l2_ate_drift_pct": {
                    a: (100.0 * (per_seed[str(args.seed)][a]["ate_cm"] - fr[a]["ate_cm"])
                        / fr[a]["ate_cm"]) for a in ("G", "S")},
            }
        except (KeyError, TypeError, ZeroDivisionError):
            first_vs_rerun = {"status": "unreadable", "detail": "first_run 路径不可读"}

    sd_used = SD_SOURCES["A_paired_on_off"]["sd"]
    n_seed = len(seed_deltas) if seed_deltas else 1
    mde_used = mde(sd_used, n_seed) if n_seed >= 2 else None

    # 多 seed 的 R6/R7：逐 seed 各算一份（同一份 trace 只属一个 run 目录）。
    per_seed_r6r7 = None
    r7_warn_seeds = []
    if per_seed:
        per_seed_r6r7 = {}
        for s, arms_s in per_seed.items():
            pair, miss = _r6r7(arms_s["G"]["run_dir"], arms_s["S"]["run_dir"])
            if pair is None:
                per_seed_r6r7[s] = {"status": "missing_trace", "detail": miss}
            else:
                per_seed_r6r7[s] = {"R6_pool_drift": pair[0],
                                    "R7_ordinal_time_shift": pair[1]}
                if pair[1]["warn_dose_by_count_not_time"]:
                    r7_warn_seeds.append(s)
    if r6r7 is not None and r6r7[1]["warn_dose_by_count_not_time"]:
        r7_warn_seeds.append("anchor(seed %d)" % args.seed)

    # --- §6 机械应用 -------------------------------------------------------
    if seed_deltas is None:
        verdict = ("SINGLE_SEED — §6 的规则 2/3/4/5 需要跨 seed 读数；"
                   "单 seed 只报方向（prereg §5：n=1 一律不可判）")
        rule = None
    else:
        mean_d = sum(seed_deltas) / len(seed_deltas)
        signs = {(1 if v > 0 else -1 if v < 0 else 0) for v in seed_deltas}
        consistent = len(signs) == 1 and 0 not in signs
        if abs(mean_d) >= (mde_used or float("inf")):
            if mean_d < 0:
                verdict = "PLACEMENT_POSITIVE — 进 L2（§6 规则 2）"
                rule = 2
            else:
                verdict = "PLACEMENT_NEGATIVE — 本族止损（§6 规则 3）"
                rule = 3
        elif consistent and n_seed < 6:
            verdict = "EXTEND — 方向一致但未过 MDE，允许扩到 n=6（§6 规则 4）"
            rule = 4
        else:
            verdict = "INCONCLUSIVE — 不可判，记「已排除方向」（§6 规则 5）"
            rule = 5

    report = {
        "prereg": ["paper3/results/evidence/prereg_fdose_2026-10-31.md §5/§6"],
        "sequence": args.seq,
        "seed": args.seed,
        "floor_cm": floor,
        "arms": arms,
        "deltas_cm": {"S_minus_G": d_S_G, "G_minus_k0": d_G_k0, "S_minus_k0": d_S_k0},
        "seed_deltas_cm": seed_deltas,
        "per_seed_arms": ({s: arms_snapshot(arms_s)
                           for s, arms_s in per_seed.items()} if per_seed else None),
        "per_seed_gate": per_seed_gate if per_seed else None,
        "per_seed_meta": per_seed_meta if per_seed else None,
        "a4_provenance": dict(
            A4_PROVENANCE,
            # 动态派生（G2 2026-11-03 重大#3）：与本次判定消费的 manifest 一致。
            confirmation_seeds=[int(s) for s in sorted(per_seed, key=int)
                                if (per_seed_meta.get(s) or {}).get("selected_role") == "confirmation"]
            if per_seed else [],
            seeds_in_judgment=[int(s) for s in sorted(per_seed, key=int)] if per_seed else [],
        ),
        "first_run_vs_diagnostic_rerun": first_vs_rerun,
        "mde": {"sd_used": sd_used, "sd_sources": SD_SOURCES,
                "n_seed": n_seed, "mde_cm": mde_used},
        "R6_pool_drift": (r6r7[0] if r6r7 else None),
        "R7_ordinal_time_shift": (r6r7[1] if r6r7 else None),
        "R6R7_status": ("ok" if r6r7 else "missing_trace"),
        "R6R7_missing_detail": r6r7_missing,
        "per_seed_R6R7": per_seed_r6r7,
        "rule_applied": rule,
        "verdict": verdict,
        "caveats": [
            "本地产物（非远程 3090 正式批）⇒ 按 G-算力条标「非权威」，"
            "不得进论文表；本判决为 provisional（远程不可达的具体原因以当日现场为准，"
            "本文件不做硬编码断言）。",
            "F1 是计划侧恒等式，不证明两臂候选集相同（prereg §0/§4.1）。",
            "`G−k0`/`S−k0` 是报告项：两臂与 k0 的注入形态不同，不参与 PASS/FAIL（§6 规则 6）。",
            ("n=%d 按 §6 规则判定出口，**不构成方向或效果结论**（prereg §5：n=1 一律不可判；"
             "n=3 方向一致性只决定 EXTEND）——本轮 seed 数 = %d，规则 %d 出口见判定行。"
             % (len(per_seed), len(per_seed), rule)) if per_seed else
            "n=1 只报方向，不可判（prereg §5）。",
            "A4 是 **post-data 仪器修正**（写于 seed0 全长数据后、seeds 1/2 前）：形态由仪器"
            "可判性决定，阈值 1.15/1.10/60% 沿用 Amendment A1 未放宽，ATE 未用于选门；"
            "seed0 首跑/重跑方向翻转已如实并陈（n=1 抖动，任何方向不得作结论）。",
            "负结果、评测协议与「不退化」均**不得**作论文贡献或 headline（DISCIPLINE"
            "「论文叙事纪律」；prereg §8）。",
        ],
    }
    if r7_warn_seeds:
        report["caveats"].append(
            "剂量按数量相等，不按地图时刻相等（prereg §4.2 R7 触发：%s）——"
            "两臂同序数事件的地图时刻不同步。" % ", ".join(r7_warn_seeds))

    md = []
    A = md.append
    if per_seed:
        A("# FDose %d-seed 出口判定（anchor seed%d，n=%d；机械应用 prereg §6）\n"
          % (len(per_seed), args.seed, len(per_seed)))
    else:
        A("# FDose 单 seed 诊断判定（%s, seed %d；prereg §6 需跨 seed，本件只报方向）\n"
          % (args.seq, args.seed))
    A("**判据**：`prereg_fdose_2026-10-31.md` §5/§6 + **Amendment A4（`P3-D2-014`，"
      "post-data 仪器修正，阈值沿用 A1）**；逐序列地板 **%.2f cm**（固定口径 = prereg §5 的 "
      "n=3 估计值，不随本判定 seed 数变化）\n" % floor)
    if per_seed_gate:
        A("## 每 seed 装置门与 A4 读数（只消费 gate 工件，不在此重算）\n")
        A("| seed | role | gate | F3a′ 均值 | F3a′ ≥1.10 事件 | 跨臂比 | 池基线 C/A | gate 路径 |")
        A("|---|---|---|---:|---:|---:|---:|---|")
        for s in sorted(per_seed_gate):
            gd = per_seed_gate[s]
            role = (per_seed_meta.get(s) or {}).get("selected_role", "—")
            A("| %s | %s | %s | %s | %s | %s | %s | `%s` |" % (
                s, role, gd["gate_verdict"],
                "n/a" if gd["f3a_prime_mean"] is None else "**%.4f×**" % gd["f3a_prime_mean"],
                "n/a" if gd["f3a_prime_share_above"] is None
                else "%.0f%%" % (100 * gd["f3a_prime_share_above"]),
                "n/a" if gd["f3a_cross_arm_mean"] is None
                else "%.4f×" % gd["f3a_cross_arm_mean"],
                "n/a" if gd["pool_baseline_median"] is None
                else "%.3f×" % gd["pool_baseline_median"],
                gd["gate_path"]))
        A("")
    if first_vs_rerun and first_vs_rerun.get("status") != "unreadable":
        frr = first_vs_rerun
        A("## seed0 首跑 vs 诊断重跑（G2 致命项：必须并陈，不得静默替换）\n")
        A("| 口径 | k0 ATE | G ATE | S ATE | S−G | G−k0 | S−k0 |")
        A("|---|---:|---:|---:|---:|---:|---:|")
        fr, fq = frr["first_run"], frr["rerun"]
        fd, rd = frr["first_run_deltas_cm"], frr["rerun_deltas_cm"]
        A("| 首跑（first_run） | %.4f | %.4f | %.4f | %+.4f | %+.4f | %+.4f |"
          % (fr["k0"]["ate_cm"], fr["G"]["ate_cm"], fr["S"]["ate_cm"],
             fd["S_minus_G"], fd["G_minus_k0"], fd["S_minus_k0"]))
        A("| 诊断重跑（selected） | %.4f | %.4f | %.4f | %+.4f | %+.4f | %+.4f |"
          % (fq["k0"]["ate_cm"], fq["G"]["ate_cm"], fq["S"]["ate_cm"],
             rd["S_minus_G"],
             fq["G"]["ate_cm"] - fq["k0"]["ate_cm"],
             fq["S"]["ate_cm"] - fq["k0"]["ate_cm"]))
        A("")
        A("- **方向翻转**：S−G %+.4f → %+.4f cm（%s）⇒ n=1 装置抖动，任何方向不得作结论。"
          % (frr["direction_flip_cm"]["from"], frr["direction_flip_cm"]["to"],
             "已翻转" if frr["direction_flip_cm"]["flipped"] else "未翻转"))
        A("- L2 ATE 漂移：G %+.1f%% / S %+.1f%%（同 config 同 seed 重跑；"
          "**「<20%% 带内」的出处 = `results/evidence/fdose_f3a_achievable_diagrerun_2026-11-01.md` "
          "的自述，prereg/A1–A4/DECISIONS 正文均无该阈值**——G2 2026-11-03 重大#4："
          "按自述口径引用，不作为判据条文）。"
          % (frr["l2_ate_drift_pct"]["G"], frr["l2_ate_drift_pct"]["S"]))
        A("- 选用诊断重跑的理由：%s"
          % (frr.get("selection_reason") or "—"))
        A("")
    A("| 臂 | ATE (cm) | online 高斯 | refined 高斯 | 帧数 |")
    A("|---|---:|---:|---:|---:|")
    for k in ("k0", "G", "S"):
        a = arms[k]
        A("| %s | %.4f | %s | %s | %s |" % (
            k, a["ate_cm"],
            "—" if a["num_gaussians"] is None else "%d" % a["num_gaussians"],
            "—" if a["refined_gaussians"] is None else "%d" % a["refined_gaussians"],
            "—" if a["num_frames"] is None else "%d" % a["num_frames"]))
    A("")
    A("| Δ | 值 (cm) |")
    A("|---|---:|")
    A("| S − G（主判据） | %+.4f |" % d_S_G)
    A("| G − k0（报告项） | %+.4f |" % d_G_k0)
    A("| S − k0（报告项） | %+.4f |" % d_S_k0)
    A("")
    if per_seed:
        A("## 每 seed 原始读数（机读，不手填）\n")
        A("| seed | 臂 | ATE (cm) | online 高斯 | refined 高斯 | 帧数 | run 目录 |")
        A("|---|---|---:|---:|---:|---:|---|")
        for s in sorted(per_seed, key=lambda v: int(v)):
            for a in ("k0", "G", "S"):
                v = per_seed[s][a]
                A("| %s | %s | %.4f | %s | %s | %s | `%s` |" % (
                    s, a, v["ate_cm"],
                    "—" if v["num_gaussians"] is None else "%d" % v["num_gaussians"],
                    "—" if v["refined_gaussians"] is None else "%d" % v["refined_gaussians"],
                    "—" if v["num_frames"] is None else "%d" % v["num_frames"],
                    v["run_dir"]))
        A("")
        A("## 每 seed R6/R7（报告项；缺 trace 显式 missing）\n")
        A("| seed | R6 池相对差中位 | R6 池 Jaccard 均值 | R7 事件数差 | R7 \\|偏移\\| p90 | R7 触发 |")
        A("|---|---:|---:|---:|---:|---|")
        for s in sorted(per_seed_r6r7 or {}, key=lambda v: int(v)):
            v = per_seed_r6r7[s]
            if v.get("status") == "missing_trace":
                A("| %s | missing_trace | — | — | — | — |" % s)
            else:
                A("| %s | %.4f | %.3f | %+d | %s | %s |" % (
                    s, v["R6_pool_drift"]["pool_rel_diff_median"],
                    v["R6_pool_drift"]["pool_jaccard_mean"],
                    v["R7_ordinal_time_shift"]["n_events_diff"],
                    "n/a" if v["R7_ordinal_time_shift"]["abs_iter_diff_p90"] is None
                    else "%d" % v["R7_ordinal_time_shift"]["abs_iter_diff_p90"],
                    "是 ⚠" if v["R7_ordinal_time_shift"]["warn_dose_by_count_not_time"] else "否"))
        A("")
    # R6/R7：报告项小节（prereg §4.2「必须报」的机械落点；不入 PASS/FAIL）
    # 口径（G2 2026-11-03 重大#2）：顶层 r6r7 只由 --g/--s（anchor seed 的 run）算出，
    # 不是多 seed 聚合。必须显式标注，否则读者会把 anchor 读数误读为全体。
    A("## R6/R7 残余混杂量化（prereg §4.2 报告项；**本小节 = anchor seed %d 单 seed 口径**）\n"
      % args.seed)
    if r6r7 is None:
        A("> ⚠ **R6/R7 不可算**：%s —— 报告项缺源必须显式声明，不得静默消失（M3 类）。"
          % r6r7_missing)
    else:
        r6d, r7d = r6r7

        def _f(v, pat="%+.4f"):
            return "n/a" if v is None else (pat % v)

        A("| 项 | 读数 |")
        A("|---|---|")
        A("| R6 候选集漂移：\\|pool\\| 相对差（中位；IQR；范围） | %s；[%s, %s]；[%s, %s]"
          "（%d 共同事件） |"
          % (_f(r6d["pool_rel_diff_median"]),
             _f(r6d["pool_rel_diff_iqr"][0]), _f(r6d["pool_rel_diff_iqr"][1]),
             _f(r6d["pool_rel_diff_min"]), _f(r6d["pool_rel_diff_max"]),
             r6d["n_common_events"]))
        A("| R6 池 gauss_idx Jaccard（**跨索引不可比**，量化地图分叉） | 均值 %s / 中位 %s |"
          % (_f(r6d["pool_jaccard_mean"], "%.3f"), _f(r6d["pool_jaccard_median"], "%.3f")))
        A("| R7 序数—时间错位：iter_S−iter_G（中位；\\|偏移\\| p90；极值） | %s；%s；[%s, %s] |"
          % (_f(r7d["iter_diff_median"]), _f(r7d["abs_iter_diff_p90"]),
             _f(r7d["abs_iter_diff_min"]), _f(r7d["abs_iter_diff_max"])))
        A("| R7 两臂事件总数差 | S−G = %+d（G %d / S %d） |"
          % (r7d["n_events_diff"], r7d["n_events_G"], r7d["n_events_S"]))
        A("| R7 触发「剂量按数量相等，不按地图时刻相等」 | %s |"
          % ("**是 ⚠**（\\|偏移\\| p90 %s vs 事件间隔中位 %s，或事件数差 > 2）"
             % (_f(r7d["abs_iter_diff_p90"]), _f(r7d["event_gap_median_ref"]))
             if r7d["warn_dose_by_count_not_time"] else "否"))
        # 跨 seed 对照（G2 2026-11-03 重大#2）：anchor 单 seed 读数不得冒充全体。
        if per_seed_r6r7 and len(per_seed_r6r7) > 1:
            rows = []
            for sk in sorted(per_seed_r6r7, key=int):
                e = per_seed_r6r7[sk] or {}
                d6, d7 = e.get("R6_pool_drift") or {}, e.get("R7_ordinal_time_shift") or {}
                rows.append("seed%s: R6 中位 %s / Jaccard %s；R7 事件差 %s、\\|偏移\\| p90 %s"
                            % (sk, _f(d6.get("pool_rel_diff_median")),
                               _f(d6.get("pool_jaccard_mean"), "%.3f"),
                               _f(d7.get("n_events_diff"), "%+d"),
                               _f(d7.get("abs_iter_diff_p90"), "%.0f")))
            A("")
            A("**逐 seed R6/R7（勿把上一小节当全体口径）**：")
            for r in rows:
                A("- " + r)
    A("")
    A("**功效核算（§5）**：sd = %.3f（来源 %s）⇒ n=%d 的 MDE(95%%) = %s"
      % (sd_used, SD_SOURCES["A_paired_on_off"]["src"], n_seed,
         "不可算（n<2）" if mde_used is None else "**%.2f cm**" % mde_used))
    A("")
    if per_seed:
        mde6 = mde(sd_used, 6)
        if len(per_seed) < 6:
            need = (mde6 * 6 - sum(seed_deltas)) / (6 - len(per_seed)) if mde6 is not None else None
            A("**n=6 信息价值（规则 4 的处置依据）**：MDE(6) = %.3f cm；已有 %d seed 合计 "
              "%.3f cm ⇒ 新增 %d seed 平均需 > **%s cm** 才能让 n=6 越过 MDE，否则机械出口为 "
              "INCONCLUSIVE（规则 5）。" % (mde6, len(per_seed), sum(seed_deltas),
                                        6 - len(per_seed),
                                        "n/a" if need is None else "%.3f" % need))
        else:
            A("**n=%d 信息价值**：MDE(%d) = %.3f cm；%d seed 合计 %.3f cm（均值 %.3f cm）⇒ "
              "|mean| %s MDE ⇒ 规则 %d 出口见下。"
              % (len(per_seed), len(per_seed), mde6 if mde6 is not None else float("nan"),
                 len(per_seed), sum(seed_deltas), sum(seed_deltas) / len(per_seed),
                 ">" if mde6 is not None and abs(sum(seed_deltas) / len(per_seed)) > mde6 else "≤",
                 rule))
        A("")
    A("## 判定\n")
    A("> **%s**" % verdict)
    A("")
    for c in report["caveats"]:
        A("- %s" % c)
    md_text = "\n".join(md) + "\n"

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    if args.out_md:
        Path(args.out_md).write_text(md_text, encoding="utf-8")
    if not args.out_md and not args.out_json:
        print(md_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
