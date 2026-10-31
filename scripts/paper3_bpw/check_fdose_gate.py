#!/usr/bin/env python
"""check_fdose_gate.py — FDose 机制门（F1–F5）判定器，零 GPU。

对应 `paper3/results/evidence/prereg_fdose_2026-10-31.md` §4.1。判的是**装置**，
不是效果。任一子门不成立 ⇒ 冻结读数、修装置、不得解释机制。

  F1 剂量恒等：每个事件 |sel| == K_i 逐事件严格相等（分站点再报一次：F1_init / F1_map）
  F2 计划忠实：两臂实际 K 序列与 dose_plan.json 逐事件逐位相等（含顺序与长度）
  F3a γ 活性（硬门）：臂内稀疏度剖面分开（S/G 比均值 ≥1.15 且 ≥60% 事件 >1.10）
  F3b 索引 Jaccard：**报告项**（两臂索引空间不可比，只反映地图分叉）
  F4 池约束：选中点全部 mean_grad >= τ_lo（两臂各自）
  F5 组件生效：两臂 Σsel == 计划 ΣK 且 > 0；给 --k0 时另报 k0 的 Σsel
  done 锚点（M6）：加 `--require-done` 时，两臂都须有 finished_rc0=yes 的 .done

⚠ F1 的适用域（CGB 审查 M7 同源）：F1 是**计划侧**恒等式，证明「两臂拿到的剂量指令
相同且被正确执行」。它**不**证明两臂候选集相同——本设计做不到（prereg §0）。
F1 打 ✅ 不得被读成「两臂地图一致」。

用法：
  PY=/data/conda_envs/monogs-ours/bin/python
  $PY scripts/paper3_bpw/check_fdose_gate.py \
      --plan results/paper3_bpw/dose_plan/person_tracking_seed0.json \
      --g  results/paper3_bpw/fdose_G_person_tracking/datasets_bonn/\
fdose_G_person_tracking/seed_0/<ts>/fdose_selection_trace.csv \
      --s  results/paper3_bpw/fdose_S_person_tracking/datasets_bonn/\
fdose_S_person_tracking/seed_0/<ts>/fdose_selection_trace.csv \
      [--k0 results/.../fdose_k0_.../fdose_selection_trace.csv] \
      --out-md ... --out-json ...
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

TAU_LO = 1e-4
# F3 原阈值（0.80 / 0.75）已于 2026-10-31 由 Amendment A1 废止，常量一并删除：
# 按 gauss_idx 的 Jaccard 在两臂各自在线长地图时恒 ~0.15（索引空间不可比），是恒为真的门。
# A1 的 F3a：臂内稀疏度剖面必须分开（index-free，可判「γ 有没有把点放得更疏」）。
F3A_RATIO_MEAN_MIN = 1.15
F3A_RATIO_EVENT_MIN = 1.10
F3A_EVENT_SHARE_MIN = 0.60


def read_trace(path: Path):
    """→ ({event: {"sel": [...], "pool_only": [...]}}, {event: {"k_plan":…, "iter":…, "overflow":…}})"""
    ev = defaultdict(lambda: defaultdict(list))
    meta = {}
    n_sentinel = 0
    with open(path) as fh:
        for r in csv.DictReader(fh):
            e = int(r["event"])
            if r["kind"] == "overflow_zero":
                # 越界哨兵行：只用来让「计划用完了」可审计（默认 trace 只写 sel，
                # 越界事件本来一行都不写）。不计入选择集合。
                n_sentinel += 1
            ev[e][r["kind"]].append(
                {
                    "idx": int(r["gauss_idx"]),
                    "g": float(r["mean_grad"]),
                    "s": float(r["sparsity"]),
                    "key": float(r["key"]),
                    # max_scale 是 clone/split 判据的输入（A2 的 gross 口径要用它）。
                    # 缺列时给 None，下游显式跳过，不静默当 0。
                    "max_scale": (float(r["max_scale"])
                                  if r.get("max_scale") not in (None, "") else None),
                }
            )
            m = meta.setdefault(
                e,
                {"k_plan": int(r["k_plan"]), "iter": int(r["iter"]),
                 "overflow": int(r["plan_overflow"])},
            )
            if m["k_plan"] != int(r["k_plan"]) or m["overflow"] != int(r["plan_overflow"]):
                raise ValueError("trace 内同一事件的 k_plan 不一致 (event=%d)" % e)
    if meta:
        meta["__n_sentinel__"] = n_sentinel
    return dict(ev), meta


def _check_arm(ev, meta, plan_k, label):
    n_events = len(ev)
    ev_ids = [e for e in meta if isinstance(e, int)]   # meta 里还有哨兵计数等非事件键
    k_err = []
    overflow_err = []
    below_pool = 0
    trim = []
    for e in sorted(ev_ids):
        sel = ev[e]["sel"]
        # 事件序号 >= N_plan 之后，规格要求注入 0（prereg §2 末段）：沿用末位剂量会让
        # 总剂量随事件数分叉。所以期望值必须跟着这个规则，不能写成 plan_k[-1]。
        want = plan_k[e] if e < len(plan_k) else 0
        k_err.append((e, len(sel), want, meta[e]["k_plan"]))
        expect_overflow = 1 if e >= len(plan_k) else 0
        overflow_err.append((e, meta[e]["overflow"], expect_overflow))
        if sel:
            below_pool += sum(1 for p in sel if p["g"] < TAU_LO - 1e-12)
        # 该臂本事件的「参考规模」= 池内 g >= τ_base 的点数，trace 未直接记录 τ_base，
        # 因此用计划侧 K_i 与 sel 的差作为修剪幅度的下界指标；绝对值由判决书另从
        # `[fdose] trim=` 日志取。这里只报 sel − K_plan。
        trim.append(len(sel) - want)
    return {
        "label": label,
        "n_events": n_events,
        "events_with_wrong_k": [
            {"event": e, "n_sel": n, "plan_k": want, "trace_k_plan": tk}
            for (e, n, want, tk) in k_err if n != want or tk != want
        ],
        "log_overflow_events": [e for e in sorted(ev_ids) if meta[e]["overflow"]],
        "n_overflow_events": sum(1 for e in ev_ids if meta[e]["overflow"]),
        "n_sentinel_rows": int(meta.get("__n_sentinel__", 0)),
        "overflow_flag_wrong": [
            {"event": e, "flag": flag, "expected": exp}
            for (e, flag, exp) in overflow_err if flag != exp
        ],
        "below_pool_total": below_pool,
        "sel_minus_plan": trim,
    }


def sparsity_profile(ev_g, ev_s):
    """F3a：逐事件比较两臂**各自**选中集的平均稀疏度（不跨索引空间）。

    为什么不用跨臂 Jaccard：两臂各自在线长地图 ⇒ `gauss_idx` 从事件 1 起就不可比
    （冒烟实测同索引位置重合率 0.000），Jaccard 恒 ~0.15，与 γ 是否生效无关
    （Amendment A1 §1）。稀疏度剖面是臂内量，可判。
    """
    rows = []
    for e in sorted(set(ev_g) & set(ev_s)):
        a = [p["s"] for p in ev_g[e]["sel"]]
        b = [p["s"] for p in ev_s[e]["sel"]]
        if not a or not b:
            continue
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        if ma <= 0:
            continue
        rows.append({"event": e, "s_G": ma, "s_S": mb, "ratio": mb / ma})
    ratios = [r["ratio"] for r in rows]
    n = len(ratios)
    # 点数加权（pooled）口径：把两臂在共同事件上的所有选中点合起来比均值。
    # 审查 M2 的次要项：事件均值与点数加权在冒烟上分别是 1.206 与 1.181，
    # 门 1.15 对后者的余量只有 0.03 —— 必须两个都报，不能只报有利的那个。
    sum_g = sum(r["s_G"] * len([p for p in ev_g[r["event"]]["sel"]]) for r in rows) if rows else 0.0
    n_g = sum(len(ev_g[r["event"]]["sel"]) for r in rows) if rows else 0
    sum_s = sum(r["s_S"] * len([p for p in ev_s[r["event"]]["sel"]]) for r in rows) if rows else 0.0
    n_s = sum(len(ev_s[r["event"]]["sel"]) for r in rows) if rows else 0
    pooled = ((sum_s / n_s) / (sum_g / n_g)) if (n_s and n_g and sum_g > 0) else float("nan")
    return {
        "ratio_pooled": pooled,
        "rows": rows,
        "n_events": n,
        "ratio_mean": (sum(ratios) / n) if n else float("nan"),
        "ratio_median": sorted(ratios)[n // 2] if n else float("nan"),
        "ratio_min": min(ratios) if ratios else float("nan"),
        "ratio_max": max(ratios) if ratios else float("nan"),
        "share_above": (sum(1 for r in ratios if r > F3A_RATIO_EVENT_MIN) / n) if n else 0.0,
    }


def f1_by_site(ev, meta, plan_k, n_init):
    """M8：把 F1 的剂量恒等按**站点**分列报（prereg §2 站点表要求的 `F1_init`/`F1_map`）。

    两个 densify 站点共用同一个事件序数且 clone/split 界不同（1.80 m / 0.06 m），
    所以「F1 全绿」必须能回答「init 段与 map 段各自是否也全绿」—— 合并计数会把
    某一整段失效藏在另一段的正常里（`per_site_dose` 报的是剂量占比，不是误差归属）。
    """
    out = {}
    for site, lo, hi in (("init", 0, n_init), ("map", n_init, None)):
        wrong = []
        n_ev = 0
        for e in sorted(k for k in meta if isinstance(k, int)):
            if e < lo or (hi is not None and e >= hi):
                continue
            n_ev += 1
            want = plan_k[e] if e < len(plan_k) else 0
            got = len(ev[e]["sel"])
            if got != want or meta[e]["k_plan"] != want:
                wrong.append({"event": e, "n_sel": got, "plan_k": want,
                              "trace_k_plan": meta[e]["k_plan"]})
        out[site] = {"n_events": n_ev, "ok": not wrong, "events_with_wrong_k": wrong}
    out["ok"] = out["init"]["ok"] and out["map"]["ok"]
    return out


def done_anchor(trace_path: Path, arm: str):
    """M6：读同一 run 目录里的 `.done` 锚点（runner 在每臂结束时写）。

    项目判决纪律只认「done 里 `finished_rc0=yes` 之后 consolelog 的末行 eval」。
    没有锚点时，runner 的 `|| true` 会让失败的臂照样进入下一段，而 trace 也可能
    半截可读 —— 判据机必须先问「这一臂跑完了吗」，再判装置。
    `--require-done` 下缺锚点 ⇒ FAIL；未加该开关时仍报状态（不阻塞合成夹具测试）。
    """
    d = trace_path.parent
    cands = sorted(d.glob("fdose_*_seed*.done")) + sorted(d.glob("fdose_*.done"))
    if not cands:
        return {"found": False, "arm": arm, "finished_rc0": None,
                "path": None, "detail": "run 目录内无 .done 锚点"}
    p = cands[0]
    kv = {}
    for line in p.read_text(errors="ignore").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    ok = kv.get("finished_rc0") == "yes"
    return {"found": True, "arm": arm, "finished_rc0": ok, "path": str(p),
            "rc": kv.get("rc"), "num_frames": kv.get("max_frames"),
            "detail": "" if ok else "锚点存在但 finished_rc0=%s（rc=%s）"
                                    % (kv.get("finished_rc0"), kv.get("rc"))}


def per_site_dose(ev, n_init):
    """M8：按站点分列报剂量（init 站点与 map 站点的 clone/split 界不同）。

    init 站点 = `initialize_map`（`mapping_iteration % init_gaussian_update`），
    map 站点 = `map()`（`iteration_count % gaussian_update_every`）。判据机不需要
    自己判断站点，只需知道前 `n_init` 个事件属于 init 站点（计划文件里也可记）。
    """
    init_n = sum(len(ev[e]["sel"]) for e in ev if e < n_init)
    map_n = sum(len(ev[e]["sel"]) for e in ev if e >= n_init)
    return {"n_init_events": n_init, "dose_init": init_n, "dose_map": map_n,
            "share_init": (init_n / (init_n + map_n)) if (init_n + map_n) else float("nan")}


def gross_primitives(ev, n_init, cameras_extent=6.0, percent_dense=0.01,
                     init_extent_factor=30.0, map_extent_factor=1.0):
    """M8/A2：按**站点正确界**估 gross 原语数（clone +1 / split +2）。

    界 = `percent_dense · cameras_extent · extent_factor`：
      init 站点 0.01·6·30 = **1.80 m**；map 站点 0.01·6·1 = **0.06 m**。
    （slam-critic G3 的原报漏了 `cameras_extent`，用 0.30/0.01 ⇒ 把 init 站点的
     点大量误判成 split，量级错约 7 倍；见 critic_verify_fdose_g3 §一。）
    """
    b_init = percent_dense * cameras_extent * init_extent_factor
    b_map = percent_dense * cameras_extent * map_extent_factor
    n_sel = n_split = 0
    for e in sorted(ev):
        b = b_init if e < n_init else b_map
        ms = [p["max_scale"] for p in ev[e]["sel"] if p.get("max_scale") is not None]
        if not ms:
            continue
        sp = sum(1 for v in ms if v > b)
        n_sel += len(ms)
        n_split += sp
    gross = (n_sel - n_split) * 1 + n_split * 2
    return {"sel": n_sel, "split": n_split, "gross": gross,
            "split_share": (n_split / n_sel) if n_sel else float("nan"),
            "bounds_m": [b_init, b_map]}


def jaccard_by_event(ev_a, ev_b):
    out = []
    for e in sorted(set(ev_a) & set(ev_b)):
        a = {p["idx"] for p in ev_a[e]["sel"]}
        b = {p["idx"] for p in ev_b[e]["sel"]}
        if not a and not b:
            continue
        out.append({"event": e, "jaccard": len(a & b) / len(a | b),
                    "n_a": len(a), "n_b": len(b)})
    return out


def _md(res, src):
    L = []
    A = L.append
    A("# FDose 机制门 F1–F5（prereg `prereg_fdose_2026-10-31.md` §4.1）\n")
    A("**输入**：")
    for k, v in src.items():
        A("- `%s`: `%s`" % (k, v))
    A("")
    plan = res["plan"]
    A("**计划**：%d 事件，ΣK = %d，K ∈ [%d, %d]，中位 %d；sha256 = `%s`\n"
      % (plan["n_events"], plan["sum_k"], plan["k_min"], plan["k_max"],
         plan["k_median"], plan["sha256"]))
    A("| 子门 | G 臂 | S 臂 | 判 |")
    A("|---|---|---|---|")
    g, s = res["arms"]["G"], res["arms"]["S"]
    f1 = (not g["events_with_wrong_k"]) and (not s["events_with_wrong_k"])
    A("| F1 剂量恒等 | %d 事件，错 %d | %d 事件，错 %d | %s |"
      % (g["n_events"], len(g["events_with_wrong_k"]),
         s["n_events"], len(s["events_with_wrong_k"]), "✅" if f1 else "❌"))
    f2 = res["f2_plan_faithful"]
    A("| F2 计划忠实 | 越界事件 %d（规格=注入 0） | 计划 N_plan %d | %s |"
      % (g["n_overflow_events"] + s["n_overflow_events"],
         res["f2_plan_events"], "✅" if f2 else "❌"))
    prof = res["f3a_sparsity"]
    f3a = (prof["ratio_mean"] >= F3A_RATIO_MEAN_MIN
           and prof["share_above"] >= F3A_EVENT_SHARE_MIN)
    # 表内两个「mean(s)」必须是**臂级均值**（先前误取 events[0] 的值，标签写 mean(s)）。
    mean_s_g = (sum(r["s_G"] for r in prof["rows"]) / len(prof["rows"])
                if prof["rows"] else float("nan"))
    mean_s_s = (sum(r["s_S"] for r in prof["rows"]) / len(prof["rows"])
                if prof["rows"] else float("nan"))
    A("| F3a γ 活性（硬门） | 臂均 mean(s) %.3f | 臂均 mean(s) %.3f | %s（S/G 比 均值 **%.2f×**、"
      "中位 %.2f、范围 [%.2f, %.2f]、> %.2f 的事件 %.0f%%，共 %d 事件；"
      "点数加权口径见 JSON `ratio_pooled`） |"
      % (mean_s_g, mean_s_s, "✅" if f3a else "❌",
         prof["ratio_mean"], prof["ratio_median"], prof["ratio_min"],
         prof["ratio_max"], F3A_RATIO_EVENT_MIN, 100 * prof["share_above"],
         prof["n_events"]))
    jac = res["f3b_index_jaccard"]
    A("| F3b 索引 Jaccard（**报告项**） | — | — | 均值 %.3f，中位 %.3f，最大 %.3f（两臂索引"
      "空间不可比，此值反映地图分叉，并入 R6 报告） |"
      % (jac["mean"], jac["median"], jac["max"]))
    A("")
    A("## F3a 逐事件稀疏度比（前 8 / 后 4）\n")
    A("| 事件 | mean(s) G | mean(s) S | 比 |")
    A("|---:|---:|---:|---:|")
    prows = prof["rows"]
    ppick = prows[:8] + (prows[-4:] if len(prows) > 8 else [])
    for r in ppick:
        A("| %d | %.3f | %.3f | %.2f× |" % (r["event"], r["s_G"], r["s_S"], r["ratio"]))
    A("")
    f4 = g["below_pool_total"] == 0 and s["below_pool_total"] == 0
    A("| F4 池约束 | 池外 %d | 池外 %d | %s |"
      % (g["below_pool_total"], s["below_pool_total"], "✅" if f4 else "❌"))
    f5 = res["f5_activity"]
    A("| F5 组件生效 | Σsel %d | Σsel %d | %s（计划 ΣK %d；%s） |"
      % (f5["sum_sel_G"], f5["sum_sel_S"], "✅" if f5["ok"] else "❌",
         plan["sum_k"], f5["note"]))
    A("")
    fs = res["f1_by_site"]
    A("**F1 分站点**（M8：两个 densify 站点共用一个事件序数、clone/split 界不同）：")
    A("")
    A("| 臂 | init 段（ord < %d） | map 段 |" % res["per_site"]["G"]["n_init_events"])
    A("|---|---|---|")
    for label in ("G", "S"):
        r = fs[label]
        A("| %s | %d 事件，错 %d | %d 事件，错 %d |"
          % (label, r["init"]["n_events"], len(r["init"]["events_with_wrong_k"]),
             r["map"]["n_events"], len(r["map"]["events_with_wrong_k"])))
    A("")
    dn = res["done"]
    A("**done 锚点**（M6；%s）：G `%s`；S `%s`"
      % ("必需" if dn["required"] else "非必需（合成夹具/冒烟）",
         (dn["G"]["path"] or "-") + ("（finished_rc0=yes）" if dn["G"]["finished_rc0"]
                                     else "（%s）" % dn["G"]["detail"]),
         (dn["S"]["path"] or "-") + ("（finished_rc0=yes）" if dn["S"]["finished_rc0"]
                                     else "（%s）" % dn["S"]["detail"])))
    A("")
    A("## 剂量差读数（两臂 sel 之差，逐事件；本设计的剂量外生 ⇒ 应为恒 0）\n")
    for label, arm in (("G", g), ("S", s)):
        v = arm["sel_minus_plan"]
        if not v:
            continue
        A("- %s 臂的 sel − K_plan：中位 %+d，范围 [%+d, %+d]（≡0 才算合规；F1 已逐事件判过）"
          % (label, int(st.median(v)), min(v), max(v)))
    A("")
    A("## 逐事件 Jaccard（前 8 / 后 4）\n")
    A("| 事件 | Jaccard | |sel_G| | |sel_S| |")
    A("|---:|---:|---:|---:|")
    rows = jac["rows"]
    pick = rows[:8] + (rows[-4:] if len(rows) > 8 else [])
    for r in pick:
        A("| %d | %.3f | %d | %d |" % (r["event"], r["jaccard"], r["n_a"], r["n_b"]))
    A("")
    A("")
    A("## 剂量三口径（A2：源点数 / gross 原语 / 分站点）\n")
    A("| 口径 | G | S | 比 |")
    A("|---|---:|---:|---:|")
    A("| 源点数 Σsel（F1 已强制相等） | %d | %d | %.4f |"
      % (f5["sum_sel_G"], f5["sum_sel_S"], f5["sum_sel_S"] / max(1, f5["sum_sel_G"])))
    gp = res["gross_primitives"]
    A("| gross 原语（clone+1 / split+2） | %d | %d | **%.4f** |"
      % (gp["G"]["gross"], gp["S"]["gross"],
         gp["S"]["gross"] / max(1, gp["G"]["gross"])))
    A("| ├ split 占比 | %.2f%% | %.2f%% | — |"
      % (100 * gp["G"]["split_share"], 100 * gp["S"]["split_share"]))
    A("| ├ 站点界 (init / map) | %.2f m / %.2f m | 同 | — |"
      % (gp["G"]["bounds_m"][0], gp["G"]["bounds_m"][1]))
    ps = res["per_site"]
    A("| 分站点剂量 init / map | %d / %d（init 占 %.1f%%） | %d / %d | — |"
      % (ps["G"]["dose_init"], ps["G"]["dose_map"], 100 * ps["G"]["share_init"],
         ps["S"]["dose_init"], ps["S"]["dose_map"]))
    A("")
    A("> ⚠ F1 是**计划侧**恒等式，对「两臂候选集是否相同」完全盲（prereg §4.1 注）；")
    A("> gross 原语不是 F1 的子门，它是 A2 要求并陈的第二口径（源点数相等 ≠ 净高斯数相等）。")
    A("")
    A("**结论**：%s" % ("机制门全过（装置干净）" if all([f1, f2, f3a, f4, f5["ok"]])
                        else "机制门未全过 ⇒ 装置失效，冻结读数、先修装置（不得解释机制）"))
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--g", required=True, help="γ=0 臂 trace")
    ap.add_argument("--s", required=True, help="γ=1 臂 trace")
    ap.add_argument("--k0", default=None, help="参考剂量臂 trace（可缺省）")
    ap.add_argument("--n-init", type=int, default=11,
                    help="前多少个事件来自 initialize_map 站点（默认 11；冒烟实测 0..10）。"
                         "两个站点的 scene_extent 不同 ⇒ clone/split 界不同（prereg §2）。")
    ap.add_argument("--require-done", action="store_true",
                    help="要求两臂 run 目录各有 `finished_rc0=yes` 的 .done 锚点（M6）。"
                         "正式批判读**必须**加；合成夹具/冒烟可不加。")
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args(argv)

    import hashlib

    plan_raw = Path(args.plan).read_bytes()
    plan = json.loads(plan_raw)
    plan_k = [int(v) for v in plan["k"]]

    evG, metaG = read_trace(Path(args.g))
    evS, metaS = read_trace(Path(args.s))

    arms = {"G": _check_arm(evG, metaG, plan_k, "G"),
            "S": _check_arm(evS, metaS, plan_k, "S")}

    jac_rows = jaccard_by_event(evG, evS)
    jacs = [r["jaccard"] for r in jac_rows]
    f3b = {
        "n_events": len(jacs),
        "mean": float(sum(jacs) / len(jacs)) if jacs else float("nan"),
        "median": float(st.median(jacs)) if jacs else float("nan"),
        "max": float(max(jacs)) if jacs else float("nan"),
        "rows": jac_rows,
    }
    f3a = sparsity_profile(evG, evS)

    covered = min(len(evG), len(evS))
    # 越界事件本身是**规格要求的**（注入 0），不构成失败；失败的是标记/剂量不符：
    #   ord <  N_plan 时 flag 必须 0；ord >= N_plan 时 flag 必须 1 且 sel == 0。
    flag_violations = (len(arms["G"]["overflow_flag_wrong"])
                       + len(arms["S"]["overflow_flag_wrong"]))
    # 原 `covered >= min(len(plan_k), 1)` 形同虚设（只要有 1 个事件就过）。改为
    # 两臂都必须真的覆盖到计划长度：短触发的臂只在 F5 上兜底，而 F5 只比总量。
    f2 = (flag_violations == 0) and covered >= len(plan_k)

    sum_sel_G = sum(len(evG[e]["sel"]) for e in evG)
    sum_sel_S = sum(len(evS[e]["sel"]) for e in evS)
    sum_plan = int(sum(plan_k))
    # F5：S 臂与 G 臂的注入总量都必须等于计划总量（各事件相等已在 F1 里判过；
    # 这里判「总和层面」以及「非零」，让一个全程零注入的臂无法靠空集过 F1）。
    f5_ok = (sum_sel_G == sum_plan) and (sum_sel_S == sum_plan) and sum_plan > 0
    note = "两臂 Σsel 均等于计划 ΣK" if f5_ok else "Σsel 与计划 ΣK 不等或为零 ⇒ 组件可能未生效"
    if args.k0:
        evK, metaK = read_trace(Path(args.k0))
        arms["k0"] = _check_arm(evK, metaK, plan_k, "k0")
        sum_sel_k0 = sum(len(evK[e]["sel"]) for e in evK)
        note += "；k0 Σsel %d" % sum_sel_k0

    res = {
        "generated_by": "scripts/paper3_bpw/check_fdose_gate.py",
        "source": {"plan": args.plan, "g": args.g, "s": args.s, "k0": args.k0},
        "done": {"G": done_anchor(Path(args.g), "G"),
                 "S": done_anchor(Path(args.s), "S"),
                 "required": bool(args.require_done)},
        "plan": {
            "n_events": len(plan_k),
            "sum_k": sum_plan,
            "k_min": int(min(plan_k)),
            "k_max": int(max(plan_k)),
            "k_median": int(sorted(plan_k)[len(plan_k) // 2]),
            "sha256": hashlib.sha256(plan_raw).hexdigest(),
            "trace_sha256": plan.get("source", {}).get("trace_sha256"),
        },
        "arms": arms,
        "f2_covered_events": covered,
        "f2_plan_events": len(plan_k),
        "f2_plan_faithful": f2,
        "f2_overflow_flag_violations": flag_violations,
        "f3a_sparsity": f3a,
        "f3b_index_jaccard": f3b,
        "f5_activity": {"sum_sel_G": sum_sel_G, "sum_sel_S": sum_sel_S,
                        "sum_plan": sum_plan, "ok": f5_ok, "note": note},
        "per_site": {"G": per_site_dose(evG, args.n_init),
                     "S": per_site_dose(evS, args.n_init)},
        "f1_by_site": {"G": f1_by_site(evG, metaG, plan_k, args.n_init),
                       "S": f1_by_site(evS, metaS, plan_k, args.n_init)},
        "gross_primitives": {"G": gross_primitives(evG, args.n_init),
                             "S": gross_primitives(evS, args.n_init)},
    }
    f3a_pass = (f3a["ratio_mean"] >= F3A_RATIO_MEAN_MIN
                and f3a["share_above"] >= F3A_EVENT_SHARE_MIN)
    # M6：加 `--require-done` 时，任一臂缺锚点或 finished_rc0 != yes ⇒ 装置判废。
    # 默认不加（合成夹具与冒烟没有 .done），但状态一律写进 JSON，便于判决书引用。
    done_ok = (not args.require_done) or all(
        res["done"][a]["found"] and res["done"][a]["finished_rc0"] for a in ("G", "S"))
    res["done_ok"] = done_ok
    res["verdict"] = "PASS" if all([
        not arms["G"]["events_with_wrong_k"],
        not arms["S"]["events_with_wrong_k"],
        f2, f3a_pass,
        arms["G"]["below_pool_total"] == 0, arms["S"]["below_pool_total"] == 0, f5_ok,
        done_ok,
    ]) else "FAIL"

    md = _md(res, res["source"])
    Path(args.out_md).write_text(md, encoding="utf-8")
    Path(args.out_json).write_text(json.dumps(res, indent=1, ensure_ascii=False),
                                   encoding="utf-8")
    print(md)
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
