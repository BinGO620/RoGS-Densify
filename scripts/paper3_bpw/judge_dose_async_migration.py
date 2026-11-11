#!/usr/bin/env python3
"""剂量前沿 async 迁移检查判读器（prereg_dose_async_migration_2026-11-08 §4，机械执行）。

口径 = **async 部署口径**（与仪器口径永不混引；本判读器的全部读数只与本批 async run 对应）。

出口路由（互斥，优先级 = 判读顺序）：
  RUN_INVALID                            任一对前置门不过（rc0/帧数/解析）⇒ rc=2
  CONTRADICTED                           任一比例对 NOT_TRANSFERRED，或任一 ATE 方向判出且与仪器口径反号
  FULL_TRANSFER                          C1 全过 + C2 过 + 至少一个 ATE 对判出方向且与仪器同号
  MAP_PSNR_TRANSFERRED_ATE_ENVELOPE      C1 全过 + C2 过 + 无任何 ATE 对判出方向（预期出口）
  MIXED                                  其余

ATE 三档（per 对）：DIRECTION_JUDGED（|median| > 包络）/ ENVELOPE_UNJUDGEABLE（≤ 包络）/
SIGN_UNSTABLE（seeds 异号，不取中位假装有值）。

用法:
  python scripts/paper3_bpw/judge_dose_async_migration.py \
    --pair pt_zero:OFF_ROOT:ZERO_ROOT:580:zero:0,1,2 \
    --pair pt_tau4x:OFF_ROOT:TAU_ROOT:580:tau4x:0,1,2 \
    --pair crowd:OFF_ROOT:TAU_ROOT:928:tau4x:0,1 \
    --pair mnobox:OFF_ROOT:TAU_ROOT:778:tau4x:0,1 \
    --envelope-cm 2.14 --out paper3/results/evidence/dose_async_migration_judge_2026-11-08.json
"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

# 仪器口径参照符号（Δ = tau4x/zero − off；来自母件判决 dose_oversupply_verdict_2026-11-08）：
#   crowd tau4x 改善 ⇒ Δ 负；mnobox tau4x 变差 ⇒ Δ 正；pt tau4x 改善 ⇒ Δ 负；pt zero 变差 ⇒ Δ 正。
REFERENCE_SIGNS = {"crowd": -1, "mnobox": +1, "pt_tau4x": -1, "pt_zero": +1}
# 比例门（prereg §4.1）：ARM_TAG → (TRANSFERRED 上限, NOT_TRANSFERRED 下限)
RATIO_GATES = {"tau4x": (0.40, 0.70), "zero": (0.30, 0.60)}
# C2 门（prereg §4.2）：static PSNR 差 (TRANSFERRED ≤, NOT_TRANSFERRED ≥)
PSNR_GATES = (-4.0, -1.0)


def _finite(x):
    return x is not None and isinstance(x, (int, float)) and x == x and abs(x) != float("inf")


def read_frames(path):
    with path.open(newline="") as fh:
        return len(list(csv.DictReader(fh)))


def read_done(run):
    hits = sorted(run.glob("*.done"))
    if not hits:
        return None
    kv = {}
    for line in hits[-1].read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def collect(root, seed, prefer_frames, require_caliber="async_deploy", require_head=""):
    """G3-C1/C3 整改（2026-11-08）：本批过滤。

    判读根目录里可能存在历史 rc0 全长 run（2060 provisional / 旧批）——collect
    原实现"取排序后最后一个 rc0 run"会在新 run 失败/止损时被旧 run 静默顶替，
    且 2060 旧 run 混入 = 跨设备污染。现在要求 .done 锚含
    caliber==require_caliber（仪器 .done 无此键即拒）且（若 --require-head 给出）
    head==批 HEAD。"""
    base = root / f"seed_{seed}"
    if not base.is_dir():
        return None, f"缺 seed_{seed} 目录"
    runs = sorted([d for d in base.iterdir() if d.is_dir()], key=lambda d: d.name)
    if not runs:
        return None, f"seed_{seed} 无 run 目录"
    candidates, chosen, failed = [], None, []
    for d in runs:
        pf = d / "per_frame_ape.csv"
        nf = read_frames(pf) if pf.is_file() else None
        kv = read_done(d)
        cal = kv.get("caliber") if kv else None
        candidates.append(f"{d.name}(frames={nf},caliber={cal})")
        if kv is None:
            failed.append(f"{d.name}(无 .done 锚点)")
            continue
        if kv.get("finished_rc0") != "yes":
            failed.append(f"{d.name}(rc={kv.get('rc')})")
            continue
        if kv.get("caliber") != require_caliber:
            failed.append(f"{d.name}(caliber={kv.get('caliber')!r}≠{require_caliber})")
            continue
        if require_head and kv.get("head") != require_head:
            failed.append(f"{d.name}(head={kv.get('head')!r}≠{require_head})")
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
        return None, f"{chosen.name} 读数不可解析: {exc}"
    if not (_finite(ate) and gauss > 0):
        return None, f"{chosen.name} ATE/高斯数非有限或非正"
    out = {"run": chosen.name, "ate_cm": ate, "gaussians": gauss, "frames": prefer_frames}
    mp = chosen / "mapping_raw.csv"
    if mp.is_file():
        rows = list(csv.DictReader(open(mp)))
        by_mask = {r.get("mask_type"): r for r in rows}
        r = by_mask.get("static")
        if r is not None:
            try:
                out["static_psnr_db"] = float(r.get("psnr"))
            except (TypeError, ValueError):
                out["static_psnr_db"] = None
            if out["static_psnr_db"] is not None and not _finite(out["static_psnr_db"]):
                out["static_psnr_db"] = None
    return out, None


def judge_pair(off_root, arm_root, frames, seeds, arm_tag,
               require_caliber="async_deploy", require_head=""):
    """返回 (status, payload)。status ∈ {ok, invalid}。"""
    per, errs = {}, []
    for s in seeds:
        o, eo = collect(off_root, s, frames, require_caliber, require_head)
        a, ea = collect(arm_root, s, frames, require_caliber, require_head)
        if o is None or a is None:
            errs.append(f"seed{s}: {eo or ea}")
            continue
        rec = {"off": o, "arm": a,
               "delta_ate_cm": round(a["ate_cm"] - o["ate_cm"], 4),
               "gauss_ratio": round(a["gaussians"] / o["gaussians"], 4) if o["gaussians"] else None}
        if a.get("static_psnr_db") is not None and o.get("static_psnr_db") is not None:
            rec["static_psnr_delta_db"] = round(a["static_psnr_db"] - o["static_psnr_db"], 4)
        per[s] = rec
    if errs or len(per) < len(seeds):
        return "invalid", {"per_seed": per, "reasons": errs or ["有效 seed 不足"]}
    deltas = [v["delta_ate_cm"] for v in per.values()]
    ratios = [v["gauss_ratio"] for v in per.values()]
    if not all(_finite(x) for x in deltas) or not all(_finite(x) for x in ratios) \
            or any(v["gauss_ratio"] is None for v in per.values()):
        return "invalid", {"per_seed": per, "reasons": ["Δ 或 ratio 非有限"]}
    payload = {"per_seed": per, "deltas": deltas, "gauss_ratios": ratios,
               "arm_tag": arm_tag, "reasons": []}
    payload["median_delta_ate_cm"] = round(statistics.median(deltas), 4)
    payload["median_gauss_ratio"] = round(statistics.median(ratios), 4)
    signs = {d > 0 for d in deltas}
    if len(signs) > 1:
        payload["ate_status"] = "SIGN_UNSTABLE"
        payload["reasons"].append(f"seeds 异号（不取中位判方向）：{deltas}")
    else:
        payload["ate_status"] = None  # 由主流程按包络判
    # 比例档（机械）
    lo, hi = RATIO_GATES[arm_tag]
    if payload["median_gauss_ratio"] <= lo:
        payload["ratio_status"] = "TRANSFERRED"
    elif payload["median_gauss_ratio"] >= hi:
        payload["ratio_status"] = "NOT_TRANSFERRED"
    else:
        payload["ratio_status"] = "UNJUDGEABLE_BAND"
    # PSNR 档（仅 zero 对主判；tau4x 对为报告项）
    psnr_deltas = [v["static_psnr_delta_db"] for v in per.values()
                   if v.get("static_psnr_delta_db") is not None]
    if arm_tag == "zero":
        if len(psnr_deltas) < len(seeds):
            return "invalid", {"per_seed": per,
                               "reasons": errs + ["zero 对 static PSNR 缺失（C2 主判不可缺）"]}
        med_psnr = round(statistics.median(psnr_deltas), 4)
        payload["median_static_psnr_delta_db"] = med_psnr
        if med_psnr <= PSNR_GATES[0]:
            payload["psnr_status"] = "TRANSFERRED"
        elif med_psnr >= PSNR_GATES[1]:
            payload["psnr_status"] = "NOT_TRANSFERRED"
        else:
            payload["psnr_status"] = "UNJUDGEABLE_BAND"
    else:
        payload["psnr_status"] = None
    return "ok", payload


def finalize_ate(pair, envelope_cm):
    """按包络三档补齐 ate_status（SIGN_UNSTABLE 已在 judge_pair 判过）。

    G3-C4 整改（2026-11-08）：装置自差包络 2.14cm 只在 pt 系 config 上实测
    （device_floor_3090_2026-11-05.md），crowd/mnobox 的自差未测——其
    DIRECTION_JUDGED 一律记 **provisional（诊断级）**，不参与总出口合成
    （合成只消费 pt 对，见 route()）。
    P 批 amendment（2026-11-09）：crowd/mnobox 可给实测 async 包络
    （--envelope-crowd/--envelope-mnobox），provenance 升级 measured_async；
    合成仍只消费 pt 对（prereg amendment §2.3 不变）。"""
    env = pair.get("envelope_cm_pair", envelope_cm)
    prov_default = ("pt_config_measured"
                    if pair["name"] in ("pt_tau4x", "pt_zero")
                    else pair.get("envelope_provenance_pair", "pt_config_extrapolated_provisional"))
    if pair["ate_status"] is not None:
        return
    med = pair["median_delta_ate_cm"]
    if abs(med) > env:
        pair["ate_status"] = "DIRECTION_JUDGED"
        pair["direction_sign"] = 1 if med > 0 else -1
        pair["direction_vs_instrument"] = (
            "SAME" if pair["direction_sign"] == REFERENCE_SIGNS[pair["name"]] else "OPPOSITE")
        pair["envelope_provenance"] = prov_default
    else:
        pair["ate_status"] = "ENVELOPE_UNJUDGEABLE"
        pair["envelope_provenance"] = prov_default


def route(pairs, envelope_cm):
    """机械总出口（优先级 = prereg §4.5：RUN_INVALID → CONTRADICTED → FULL_TRANSFER
    → MAP_PSNR_TRANSFERRED_ATE_ENVELOPE → MIXED）。

    G3-C4 整改：ATE 方向合成**只消费 pt 对**（pt_tau4x/pt_zero，包络实测宿主）；
    crowd/mnobox 的 DIRECTION_JUDGED 为诊断级报告项，不触发 CONTRADICTED/
    FULL_TRANSFER（prereg §4.4/§4.5 同 commit 更正）。"""
    reasons = []
    invalid = [n for n, p in pairs.items() if p["status"] == "invalid"]
    if invalid:
        return "RUN_INVALID", [f"对 {invalid} 前置门不过 ⇒ rc=2（fail-closed）"]
    for n, p in pairs.items():
        finalize_ate(p, envelope_cm)
    # CONTRADICTED（ATE 反号条件只消费 pt 对）
    not_ratio = [n for n, p in pairs.items() if p["ratio_status"] == "NOT_TRANSFERRED"]
    not_psnr = [n for n, p in pairs.items() if p.get("psnr_status") == "NOT_TRANSFERRED"]
    opposite = [n for n, p in pairs.items()
                if n in ("pt_tau4x", "pt_zero")
                and p["ate_status"] == "DIRECTION_JUDGED"
                and p["direction_vs_instrument"] == "OPPOSITE"]
    if not_ratio or not_psnr or opposite:
        return "CONTRADICTED", [
            f"比例 NOT_TRANSFERRED: {not_ratio}；PSNR NOT_TRANSFERRED: {not_psnr}；"
            f"ATE 方向与仪器口径反号（pt 对）: {opposite}"]
    ratio_ok = all(p["ratio_status"] == "TRANSFERRED" for p in pairs.values())
    zero_pairs = [p for p in pairs.values() if p["arm_tag"] == "zero"]
    psnr_ok = all(p.get("psnr_status") == "TRANSFERRED" for p in zero_pairs) and bool(zero_pairs)
    judged = [(n, p) for n, p in pairs.items()
              if n in ("pt_tau4x", "pt_zero") and p["ate_status"] == "DIRECTION_JUDGED"]
    same_sign = [n for n, p in judged if p["direction_vs_instrument"] == "SAME"]
    if ratio_ok and psnr_ok and same_sign:
        return "FULL_TRANSFER", [
            f"比例全迁移 + PSNR 迁移 + ATE 方向同号可判（pt 对）: {same_sign} "
            f"(median Δ = {[(n, pairs[n]['median_delta_ate_cm']) for n in same_sign]})"]
    if ratio_ok and psnr_ok:
        return "MAP_PSNR_TRANSFERRED_ATE_ENVELOPE", [
            "比例与 PSNR 迁移成立；ATE 方向全部包络内不可判或异号"
            f"（包络 {envelope_cm}cm，pt 实测宿主）——预期出口"]
    return "MIXED", [f"比例档: {[(n, pairs[n]['ratio_status']) for n in pairs]}；"
                     f"PSNR 档: {[(n, pairs[n].get('psnr_status')) for n in pairs if pairs[n]['arm_tag'] == 'zero']}"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pair", action="append", required=True,
                    help="NAME:OFF_ROOT:ARM_ROOT:FRAMES:ARM_TAG:SEEDS "
                         "（NAME ∈ crowd/mnobox/pt_tau4x/pt_zero；ARM_TAG ∈ tau4x/zero；SEEDS 逗号分隔）")
    ap.add_argument("--envelope-cm", type=float, default=2.14,
                    help="装置自差包络（device_floor_3090_2026-11-05 实测，pt 系 config 宿主，prereg §2）")
    ap.add_argument("--require-head", default="",
                    help="批 HEAD 短哈希——给出则 .done head 不匹配的 run 一律拒（G3-C1 本批过滤）")
    ap.add_argument("--envelope-crowd", type=float, default=None,
                    help="crowd 对实测 async 包络（prereg_device_floor_async_cm 2026-11-09）——"
                         "给出则该对 envelope_provenance 升级为 measured_async")
    ap.add_argument("--envelope-mnobox", type=float, default=None,
                    help="mnobox 对实测 async 包络——语义同 --envelope-crowd")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    report = {
        "prereg": "paper3/results/evidence/prereg_dose_async_migration_2026-11-08.md",
        "caliber": "async_deploy",
        "envelope_cm": args.envelope_cm,
        "reference_signs": REFERENCE_SIGNS,
        "pairs": {},
        "verdict": None,
        "reasons": [],
    }
    pairs = {}
    for spec in args.pair:
        name, off_root, arm_root, frames, arm_tag, seeds_s = spec.split(":")
        if name not in REFERENCE_SIGNS:
            print(f"ERROR: 未知对名 {name}（须 ∈ {sorted(REFERENCE_SIGNS)}）", file=sys.stderr)
            return 2
        if arm_tag not in RATIO_GATES:
            print(f"ERROR: 未知 arm_tag {arm_tag}", file=sys.stderr)
            return 2
        seeds = [int(x) for x in seeds_s.split(",")]
        status, payload = judge_pair(Path(off_root), Path(arm_root), int(frames), seeds, arm_tag,
                                     require_head=args.require_head)
        payload["name"] = name
        # 按对包络（P 批 amendment 2026-11-09）：crowd/mnobox 用实测 async 包络并升级 provenance
        env = {"crowd": args.envelope_crowd, "mnobox": args.envelope_mnobox}.get(name)
        if env is not None:
            payload["envelope_cm_pair"] = env
            payload["envelope_provenance_pair"] = "measured_async"
        pairs[name] = {"status": status, **payload}
    report["pairs"] = pairs

    verdict, reasons = route(pairs, args.envelope_cm)
    report["verdict"] = verdict
    report["reasons"] = reasons

    print(f"{'pair':>10} {'status':>8} {'ratio':>8} {'ratio_st':>16} {'Δ median':>10} {'ate_st':>20} {'psnr_st':>16}")
    for name, v in pairs.items():
        if v["status"] == "invalid":
            print(f"{name:>10} {'INVALID':>8} - - - -  {v.get('reasons')}")
            continue
        # route() 在 RUN_INVALID 时提前返回、finalize_ate 未跑 ⇒ ate_status 等可为 None，
        # 打印必须 None 安全（否则判读器以 rc=1 崩溃而非机械 rc=2，2026-11-08 自测抓出）。
        print(f"{name:>10} {v['status']:>8} {str(v['median_gauss_ratio']):>8} {v['ratio_status']:>16} "
              f"{str(v['median_delta_ate_cm']):>10} {str(v['ate_status']):>20} {str(v.get('psnr_status')):>16}")
    print(f"\nASYNC MIGRATION VERDICT: {verdict}")
    for r in reasons:
        print(f"  - {r}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if verdict == "RUN_INVALID" else 0


if __name__ == "__main__":
    sys.exit(main())
