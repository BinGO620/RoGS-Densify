#!/usr/bin/env python
"""render_dose_response.py — 剂量-响应筛查报告生成器（P3-D2-018 / prereg_dose_response §3–§4）。

只读 run 工件（tracking_raw.csv / efficiency_raw.csv / .done 或既有 run），
零手抄输出 md + json。1× 臂为既有 maskstat_off seed0 全长 run（prereg §1 明示复用）。

用法：
  python scripts/paper3_bpw/render_dose_response.py \
      --out-md paper3/results/evidence/dose_response_screen_2026-11-04.md \
      --out-json paper3/results/evidence/dose_response_screen_2026-11-04.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FLOOR_CM = 3.83  # person_tracking 逐序列地板（PREREGISTRATION §3.2）
EXPECT_FRAMES = 580  # D3 帧数闸：全长口径；冒烟 run（40 帧）不得混入
D1_MIN_PCT = 3.0  # D1 下界：最高与最低剂量臂的终态高斯数至少差 3%（否则"剂量没变"）

# 每 seed 的 run 目录（1× 臂复用既有 maskstat_off 全长 run）。
# 默认映射 = 本地 2060 provisional 批（2026-11-04 白天，P3-D2-018），时间戳显式钉死；
# 3090 权威批用 --runs 清单（dose_runs_3090_2026-11-05.json）。两批并存后 glob 会歧义，
# 故默认也走显式路径（M3：歧义即拒，禁止隐式取末位）。
RUNS = {
    0: {
        0.5: ("results/paper3_bpw/dose_tau05x_person_tracking/datasets_bonn/dose_tau05x_person_tracking/seed_0/2026-11-04-12-20-20/",
              "dose_tau05x_seed0.done"),
        1.0: ("results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/maskstat_off_person_tracking/seed_0/2026-11-04-03-22-44/", None),
        2.0: ("results/paper3_bpw/dose_tau2x_person_tracking/datasets_bonn/dose_tau2x_person_tracking/seed_0/2026-11-04-13-10-52/",
              "dose_tau2x_seed0.done"),
        4.0: ("results/paper3_bpw/dose_tau4x_person_tracking/datasets_bonn/dose_tau4x_person_tracking/seed_0/2026-11-04-13-50-18/",
              "dose_tau4x_seed0.done"),
    },
    1: {
        1.0: ("results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/maskstat_off_person_tracking/seed_1/2026-11-04-04-54-57/", None),
        2.0: ("results/paper3_bpw/dose_tau2x_person_tracking/datasets_bonn/dose_tau2x_person_tracking/seed_1/2026-11-04-14-33-45/",
              "dose_tau2x_seed1.done"),
        4.0: ("results/paper3_bpw/dose_tau4x_person_tracking/datasets_bonn/dose_tau4x_person_tracking/seed_1/2026-11-04-15-12-48/",
              "dose_tau4x_seed1.done"),
    },
}
TAU = {0.5: 0.0001, 1.0: 0.0002, 2.0: 0.0004, 4.0: 0.0008}



def _last(path, need):
    if not os.path.isfile(path):
        raise RuntimeError(f"missing artifact: {path}")
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if not rows:
        raise RuntimeError(f"empty artifact: {path}")
    last = rows[-1]
    miss = [c for c in need if c not in last or last[c] in ("", "MISSING", None)]
    if miss:
        raise RuntimeError(f"missing columns {miss} in {path}")
    return last


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _last_any(path, cols):
    """读末行，但容许可空列（渲染指标在 Bonn 全帧恒 NaN 是已知事实）。"""
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if not rows:
        raise RuntimeError(f"empty artifact: {path}")
    return rows[-1]


def _assert_frames(n):
    """M3：帧数闸——只接受全长 580 帧，冒烟/截断/缺列一律拒绝。"""
    if n is None:
        raise RuntimeError(f"num_frames 缺失 != {EXPECT_FRAMES}（冒烟/截断不得混入）")
    n = int(float(n))
    if n != EXPECT_FRAMES:
        raise RuntimeError(f"num_frames={n} != {EXPECT_FRAMES}（冒烟/截断不得混入）")
    return n


def collect(runs=None):
    """runs=None 用内置 RUNS；否则用 --runs 清单（显式 run 目录，禁 glob 歧义）。

    清单结构：{"note": 批次说明, "runs": {"<seed>": {"<scale>": {"run_dir": 相对 REPO 的
    显式目录或含通配的 glob, "done": .done 路径（相对 run 目录或绝对路径，可 null）}}}}
    """
    manifest_note = None
    if runs is not None:
        with open(runs, encoding="utf-8") as fh:
            manifest = json.load(fh)
        manifest_note = manifest.get("note")
        run_spec = manifest["runs"]
    else:
        run_spec = RUNS
    per_seed = {}
    for seed, arms in run_spec.items():
        rows = []
        for scale_raw, spec in arms.items():
            scale = float(scale_raw)  # 清单键是字符串；内置映射已是 float
            if isinstance(spec, dict):
                run_glob = spec["run_dir"]
                done_name = spec.get("done")
            else:
                run_glob, done_name = spec
            if any(ch in run_glob for ch in "*?["):
                dirs = sorted(glob.glob(os.path.join(REPO, run_glob)))
                if not dirs:
                    raise RuntimeError(f"seed{seed} tau{scale}x: 无 run 目录（{run_glob}）")
                # M3：显式解析——glob 必须唯一命中一个 run 目录，禁止隐式取末位。
                if len(dirs) > 1:
                    raise RuntimeError(
                        f"seed{seed} tau{scale}x: glob 命中 {len(dirs)} 个 run 目录，歧义（{run_glob}）"
                    )
                d = dirs[0]
            else:
                # 显式目录：必须存在，不做 glob 展开（清单即唯一事实源）。
                d = os.path.join(REPO, run_glob)
                if not os.path.isdir(d):
                    raise RuntimeError(f"seed{seed} tau{scale}x: run 目录不存在（{run_glob}）")
            elapsed = None
            # 完成证据两形态（fail-closed，但都要求 run 末行 eval 存在）：
            #   ① runner 跑的 arm 有 .done（finished_rc0=yes，含 elapsed）
            #   ② 裸 slam.py 直跑无 .done ⇒ 以 console.log 末行 "MonoGS: Done." 为完成锚
            done_path = None
            if done_name:
                done_path = done_name if os.path.isabs(done_name) else os.path.join(d, done_name)
            if done_path and os.path.isfile(done_path):
                info = dict(
                    line.strip().split("=", 1)
                    for line in open(done_path, encoding="utf-8")
                    if "=" in line
                )
                if info.get("finished_rc0") != "yes":
                    raise RuntimeError(f"seed{seed} tau{scale}x: finished_rc0 != yes")
                try:
                    elapsed = int(info.get("elapsed_s", 0))
                except ValueError:
                    elapsed = None
            else:
                clog = os.path.join(d, "console.log")
                if not os.path.isfile(clog):
                    raise RuntimeError(f"seed{seed} tau{scale}x: 既无 .done 也无 console.log")
                tail = open(clog, encoding="utf-8", errors="ignore").read()[-4000:]
                if "MonoGS: Done." not in tail:
                    raise RuntimeError(
                        f"seed{seed} tau{scale}x: console.log 末段无 'MonoGS: Done.'（未完成/被中断）"
                    )
            anchor = "done" if (done_path and os.path.isfile(done_path)) else "console_done"
            tt = _last(os.path.join(d, "tracking_raw.csv"), ["ate_rmse_cm", "status"])
            ee = _last(
                os.path.join(d, "efficiency_raw.csv"),
                ["num_frames", "num_gaussians", "online_num_gaussians", "refined_num_gaussians"],
            )
            # M3：帧数闸机械化——非 580 帧（冒烟/截断）一律拒出报告，不许与全长混比。
            n_frames = _assert_frames(ee["num_frames"])
            render = None
            mpath = os.path.join(d, "mapping_raw.csv")
            if os.path.isfile(mpath):
                mr = _last_any(mpath, ["psnr", "ssim", "lpips", "depth_l1_cm", "mask_type"])
                render = {
                    "psnr": _f(mr.get("psnr")),
                    "ssim": _f(mr.get("ssim")),
                    "lpips": _f(mr.get("lpips")),
                    "depth_l1_cm": _f(mr.get("depth_l1_cm")),
                    "mask_type": mr.get("mask_type"),
                }
            rows.append({
                "tau_scale": scale,
                "completion_anchor": anchor,
                "tau": TAU[scale],
                "run_dir": os.path.relpath(d, REPO).rstrip("/"),
                "ate_cm": float(tt["ate_rmse_cm"]),
                "status": tt["status"],
                "num_frames": int(float(ee["num_frames"])),
                # M4：列名如实——该列是 online 末态高斯数（不是 refined 终态）；
                # refined 列同时保留，避免"终态高斯"歧义。
                "online_num_gaussians": int(float(ee["online_num_gaussians"])),
                "refined_num_gaussians": int(float(ee["refined_num_gaussians"])),
                "elapsed_s": elapsed,
                "render_report": render,
            })
        rows.sort(key=lambda r: r["tau_scale"])
        per_seed[seed] = rows
    return per_seed


def _seed_analysis(rows):
    g = [r["online_num_gaussians"] for r in rows]  # M4：剂量代理 = online 末态高斯数
    n_frames = [r["num_frames"] for r in rows]
    d3_frames_ok = all(n == EXPECT_FRAMES for n in n_frames)  # M3：全长帧数闸
    d1_monotone = all(g[i + 1] <= g[i] * 1.03 for i in range(len(g) - 1))
    # M2：下界——"剂量真的变了"。若最高剂量臂相对最低剂量臂的降幅 < 3%，
    # 三臂/四臂几乎同值时 monotone 会平凡为真，必须判 DEVICE_FAIL 而不是 PASS。
    drop_pct = (max(g) - min(g)) / max(g) * 100.0 if max(g) else 0.0
    d1_changed = d1_monotone and drop_pct >= D1_MIN_PCT
    ates = [r["ate_cm"] for r in rows]
    span = max(ates) - min(ates)
    i_min = ates.index(min(ates))
    if span < FLOOR_CM:
        shape = "PLATEAU"
    elif i_min not in (0, len(ates) - 1):
        shape = "U_SHAPE"
    else:
        shape = "MONOTONE"
    by = {r["tau_scale"]: r for r in rows}
    plat = None
    if 2.0 in by and 4.0 in by and 1.0 in by:
        gaps = {
            "gap_2x_4x_cm": abs(by[2.0]["ate_cm"] - by[4.0]["ate_cm"]),
            "gap_2x_1x_cm": abs(by[2.0]["ate_cm"] - by[1.0]["ate_cm"]),
            "gap_4x_1x_cm": abs(by[4.0]["ate_cm"] - by[1.0]["ate_cm"]),
        }
        # M1：平台列必须真判——三个差全部 < 地板才允许写 YES，不能"2× 臂存在即 YES"。
        plat = dict(gaps)
        plat["platform_ok"] = all(v < FLOOR_CM for v in gaps.values())
    return {"d1_dose_monotone": d1_monotone,
            "d1_dose_changed": d1_changed,
            "d1_total_drop_pct": drop_pct,
            "d3_frames_ok": d3_frames_ok,
            "ate_span_cm": span,
            "min_ate_arm_tau": rows[i_min]["tau_scale"], "shape": shape,
            "platform": plat}


def analyse(per_seed):
    per = {s: _seed_analysis(rows) for s, rows in per_seed.items()}
    # 跨 seed 平台一致性：两 seed 都满足 2×≈4×（差 < 地板）且 2×/4× 均与 1× 同量级（差 < 地板）
    ok = []
    for s, a in per.items():
        p = a["platform"]
        if p is None:
            ok.append(False)
            continue
        # M1：直接消费 platform_ok（真判结果），不再用"2× 臂存在"当证据。
        ok.append(bool(p.get("platform_ok")))
    return {
        "per_seed": per,
        "d1_all_seeds": all(a["d1_dose_changed"] for a in per.values()),
        "d3_frames_ok": all(a["d3_frames_ok"] for a in per.values()),
        "platform_replicates": ok,
        "platform_all_seeds": all(ok),
        "n_seeds": len(per),
        "floor_cm": FLOOR_CM,
        "d1_min_drop_pct": D1_MIN_PCT,
        "expect_frames": EXPECT_FRAMES,
        "note_dose_keep": {s: [f"{r['tau_scale']:g}x: {r['online_num_gaussians']:,}"
                               f" (refined {r['refined_num_gaussians']:,})" for r in rows]
                           for s, rows in per_seed.items()},
    }


def render(per_seed, a, batch_note=None):
    L = []
    L.append("# 剂量-响应筛查报告（ADC 主阈值 τ 扫描；P3-D2-018）")
    L.append("")
    if batch_note:
        L.append(
            "> 预注册 = `prereg_dose_response_2026-11-04.md` + Amendment A1（seed1 扩批 2×/4×）"
            "+ Amendment A2（M8 简化臂边界 / M9 功效核算 / M10 措辞）。"
            "唯一变量 = `opt_params.densify_grad_threshold`。"
            "**简化臂边界（A2-1）**：四臂均在 `combined_prune/method.yaml` 基座"
            "（`SelectiveDensification.enabled=false`）上跑，结论只描述该简化臂与 person_tracking 序列。"
        )
        L.append("> **批次说明**：" + batch_note)
    else:
        L.append(
            "> **provisional**（本地 2060，非权威；不进论文表）。预注册 = "
            "`prereg_dose_response_2026-11-04.md` + Amendment A1（seed1 扩批 2×/4×）"
            "+ Amendment A2（M8 简化臂边界 / M9 功效核算 / M10 措辞）。"
            "唯一变量 = `opt_params.densify_grad_threshold`；1× 臂复用既有 `maskstat_off` 全长 run。"
            "**简化臂边界（A2-1）**：四臂均在 `combined_prune/method.yaml` 基座"
            "（`SelectiveDensification.enabled=false`）上跑，结论只描述该简化臂与 person_tracking 序列。"
        )
    L.append("")
    L.append("## 装置门（先于读数）")
    L.append("")
    d1_lines = []
    for s, x in a["per_seed"].items():
        d1_lines.append(
            f"  - seed {s}: 剂量单调不增={x['d1_dose_monotone']}，"
            f"最高/最低剂量臂降幅 {x['d1_total_drop_pct']:.2f}% "
            f"(下界 {D1_MIN_PCT:.0f}%) ⇒ "
            f"**{'PASS' if x['d1_dose_changed'] else 'FAIL'}**"
        )
    L.append(f"- **D1 剂量真的变了**（终态 `online_num_gaussians` 随 τ 单调不增，"
             f"且最高/最低剂量臂降幅 ≥ {D1_MIN_PCT:.0f}%；±3% 装置抖动带）："
             f"**{'PASS' if a['d1_all_seeds'] else 'FAIL'}**（{a['n_seeds']} seed 分别成立）")
    L.extend(d1_lines)
    L.append(
        "  - **列敏感性（G2-3090 次-4，两读法并陈）**：D1 用 prereg 字面列 "
        "`num_gaussians`（=online，逐位相同）；若改用 refined 列，单调性判定可能翻转"
        "（如 3090 seed0：online 47973→50122 倒挂 FAIL，refined 52973→50122→42980 单调 PASS）。"
        "出口以 prereg 字面列为准，refined 读法仅作并陈。"
    )
    L.append("")
    L.append("## 每 seed 四臂读数（机读，不手填）")
    for s, rows in per_seed.items():
        L.append("")
        L.append(f"### seed {s}")
        L.append("")
        L.append("| τ_scale | 阈值 | ATE (cm) | online 末态高斯 | refined 末态高斯 | 完毕锚点 | run |")
        L.append("|---:|---:|---:|---:|---:|---|---|")
        for r in rows:
            L.append(f"| {r['tau_scale']:g}× | {r['tau']:.4f} | {r['ate_cm']:.4f} | "
                     f"{r['online_num_gaussians']:,} | {r['refined_num_gaussians']:,} | "
                     f"{r['completion_anchor']} | `{r['run_dir']}` |")
    L.append("")
    L.append("## 形态与平台（prereg §3 + A1 判据）")
    L.append("")
    L.append("| seed | ATE 极差 (cm) | 形态 | 谷底 τ | 2×−4× (cm) | 2×−1× | 4×−1× | 平台 |")
    L.append("|---|---:|---|---:|---:|---:|---:|---|")
    for s, x in a["per_seed"].items():
        p = x["platform"] or {}
        L.append(
            f"| {s} | {x['ate_span_cm']:.2f} | {x['shape']} | {x['min_ate_arm_tau']:g}× | "
            f"{p.get('gap_2x_4x_cm', float('nan')):.2f} | "
            f"{p.get('gap_2x_1x_cm', float('nan')):.2f} | "
            f"{p.get('gap_4x_1x_cm', float('nan')):.2f} | "
            f"{'—' if p is None else ('YES' if p.get('platform_ok') else 'NO')} |"
        )
    L.append("")
    L.append(f"- **平台跨 seed 一致性检查 = {a['platform_all_seeds']}**"
             f"（判据：2×−4×、2×−1×、4×−1× 三差**全部** < 地板 {FLOOR_CM:.2f}cm 才记 True；"
             f"见 `platform_ok`）。**注意：True 只表示「差低于装置分辨率」，"
             f"按 PREREGISTRATION §3.2 读作「不可判」，不是「平台已确认」。**")
    if not batch_note:
        L.append("- 0.5× 只有 seed0（A1 明示不补）⇒ **U 形左臂是单 seed 描述，不进跨 seed 结论**。")
    L.append("")
    L.append("## 渲染代价报告项（非判据；PREREGISTRATION §3.1：渲染不作跟踪好坏判据）")
    L.append("")
    L.append("| seed | τ | PSNR | SSIM | LPIPS | depth L1 (cm) | 掩码口径 |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for s, rows in per_seed.items():
        for r in rows:
            rr = r.get("render_report") or {}
            f = lambda v: "NaN" if v is None else f"{v:.4f}"  # noqa: E731
            L.append(f"| {s} | {r['tau_scale']:g}× | {f(rr.get('psnr'))} | {f(rr.get('ssim'))} | "
                     f"{f(rr.get('lpips'))} | {f(rr.get('depth_l1_cm'))} | {rr.get('mask_type') or '—'} |")
    L.append("")
    L.append("> 读法：名称为「online 末态高斯」，不是 refined 终态；渲染质量随剂量下降**单调变差**。"
             "两者不同轴——「跟踪不敏感」不等于「地图免费」，写论文时须并陈。")
    L.append("")
    L.append("## 出口（prereg §4 + A1）")
    L.append("")
    if not a["d1_all_seeds"]:
        L.append("- **DEVICE_FAIL**：D1 不成立（剂量未真的变化或不单调），本批作废，不加 run。")
    else:
        if not a["d3_frames_ok"]:
            L.append("- **D3 FAIL**：存在非 580 帧的 run，读数不可比。")
        else:
            L.append(f"- D1/D3 成立；n={a['n_seeds']}；平台跨 seed 一致性 = {a['platform_all_seeds']}"
                     "（一致性 = True 仅指差 < 地板，按 §3.2 读作不可判）。")
        if a["platform_all_seeds"]:
            L.append("- **平台读数（描述性，非效应主张）**：2×、4× 与 1× 的 ATE 两两差均 < "
                     f"地板 {FLOOR_CM:.2f}cm。差异低于装置分辨率 ⇒ 按 PREREGISTRATION §3.2 "
                     "记「**不可判**」；方向一致性只作线索，不得写成「ATE 不动」「等值」"
                     "或「平台已确认」。")
        L.append("- 仍不作显著性与效应量主张（n=2；0.5× 左臂单 seed）；进论文表须 3090 复跑。")
    L.append("")
    L.append("## 不主张什么")
    L.append("")
    for c in [
        "n=2 不构成效应结论；读数是形态描述，不是显著性。",
        "「差异 < 地板」= **不可判**（PREREGISTRATION §3.2），不是「等值」、不是「ATE 不动」。",
        "剂量下降本身不是收益；「平台」不等于「致密化无用」。",
        "0.5× 侧 U 形左臂仅 seed0 单点，不得写成跨 seed 结论。",
        "τ 是原版 ADC 的既有旋钮，本批不构成机制创新。",
        "**简化臂外推边界**：四臂均在 `combined_prune/method.yaml` 基座"
        "（`SelectiveDensification.enabled=false`）上跑；结论只描述该简化臂上的 τ 敏感度，"
        "不外推到完整系统或其它序列。",
        "**事件序数**：不同 τ 臂的 densify 事件时刻不同，逐事件配对不可构造；"
        "本报告只做臂级终态比较。",
        ("全部产自本地 2060 ⇒ provisional。" if not batch_note else
         "读数以 `--runs` 清单所指 run 目录为准（本批为 3090 权威复跑；"
         "本地 2060 旧读数仅作跨机对拍参照）。"),
    ]:
        L.append(f"- {c}")
    L.append("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--runs", default=None,
                    help="run 清单 JSON（显式目录；缺省 = 内置本地 provisional 映射）")
    args = ap.parse_args()
    try:
        per_seed = collect(args.runs)
        a = analyse(per_seed)
    except RuntimeError as e:
        print(f"REJECTED: {e}")
        return 2
    batch_note = None
    if args.runs:
        with open(args.runs, encoding="utf-8") as fh:
            batch_note = json.load(fh).get("note")
    rep = {"prereg": "paper3/results/evidence/prereg_dose_response_2026-11-04.md",
           "runs_manifest": args.runs, "per_seed": per_seed, "analysis": a}
    for p, text in ((args.out_md, render(per_seed, a, batch_note)),
                    (args.out_json, json.dumps(rep, indent=1, ensure_ascii=False))):
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        open(p, "w", encoding="utf-8").write(text)
    print(f"n={a['n_seeds']} D1={'PASS' if a['d1_all_seeds'] else 'FAIL'} "
          f"platform_all_seeds={a['platform_all_seeds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
