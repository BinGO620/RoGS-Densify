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


def _read_one(path: Path, column: str, expect_run_id=None, expect_frames=None):
    """Read one column, refusing ambiguity instead of silently taking the last row.

    ``tables/*.csv`` are **appended** to (`eval_utils._write_csv_row` opens "a"),
    so a re-run of the same seed leaves several rows in the same file. Taking
    ``rows[-1]`` would silently pick one of them — the same failure family as
    ``latest_run()`` picking the wrong directory (M7). Rules:
      * 0 rows                     -> None
      * >1 distinct ``run_id``     -> raise (ambiguous file, must be split)
      * ``expect_run_id`` mismatch -> raise
      * >1 row with the same run_id-> raise (duplicated append)
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

    frames = {k: v["num_frames"] for k, v in arms.items()}
    if len({int(f) for f in frames.values() if f is not None}) != 1:
        print("ERROR: 三臂帧数不一致 %s —— 跨帧数比较无效" % frames, file=sys.stderr)
        return 2

    d_S_G = arms["S"]["ate_cm"] - arms["G"]["ate_cm"]
    d_G_k0 = arms["G"]["ate_cm"] - arms["k0"]["ate_cm"]
    d_S_k0 = arms["S"]["ate_cm"] - arms["k0"]["ate_cm"]

    seed_deltas = None
    per_seed = None
    if args.runs:
        spec = json.loads(Path(args.runs).read_text())
        per_seed = {}
        for seed_key in sorted(spec, key=lambda v: int(v)):
            arms_s = {k: read_arm(Path(v)) for k, v in spec[seed_key].items()}
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
            per_seed[seed_key] = arms_s
        if per_seed:
            seed_deltas = [per_seed[s]["S"]["ate_cm"] - per_seed[s]["G"]["ate_cm"]
                           for s in per_seed]
    sd_used = SD_SOURCES["A_paired_on_off"]["sd"]
    n_seed = len(seed_deltas) if seed_deltas else 1
    mde_used = mde(sd_used, n_seed) if n_seed >= 2 else None

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
        "per_seed_arms": ({s: {a: v["run_dir"] for a, v in arms_s.items()}
                           for s, arms_s in per_seed.items()} if per_seed else None),
        "mde": {"sd_used": sd_used, "sd_sources": SD_SOURCES,
                "n_seed": n_seed, "mde_cm": mde_used},
        "rule_applied": rule,
        "verdict": verdict,
        "caveats": [
            "本地 2060 产物（远程 3090 2026-10-31 仍 Connection refused）⇒ 按 G-算力条"
            "标「非权威」，不得进论文表。",
            "F1 是计划侧恒等式，不证明两臂候选集相同（prereg §0/§4.1）。",
            "`G−k0`/`S−k0` 是报告项：两臂与 k0 的注入形态不同，不参与 PASS/FAIL（§6 规则 6）。",
        ],
    }

    md = []
    A = md.append
    A("# FDose 出口判定（机械应用 prereg §6）（%s, seed %d）\n" % (args.seq, args.seed))
    A("**判据**：`prereg_fdose_2026-10-31.md` §5/§6；逐序列地板 **%.2f cm**（n=3 口径）\n" % floor)
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
    A("**功效核算（§5）**：sd = %.3f（来源 %s）⇒ n=%d 的 MDE(95%%) = %s"
      % (sd_used, SD_SOURCES["A_paired_on_off"]["src"], n_seed,
         "不可算（n<2）" if mde_used is None else "**%.2f cm**" % mde_used))
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
