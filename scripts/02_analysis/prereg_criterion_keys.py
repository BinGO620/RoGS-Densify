#!/usr/bin/env python
"""prereg_criterion_keys.py — 类登记：**prereg 声明的机械判据键，判据机必须真产出**（可复跑、可变红）。

起因（2026-10-06，DynPort-Offline G1/G4）：
  - G1 重大 M1：prereg 声明 J3 含 `Δfull ≥ −0.25 dB`，但 `judge_dynport.py` 不产出任何 full 键
    ⇒ 该子句**永远不可判**（判据是死的，却写成"第一硬门"）。
  - G1 重大 M2 / 次要：J5/J9 在离线场景构造恒真（失去守门力）、J6 的 `bad_px 中位>0` 无落点
    ⇒ 同族：**判据可判性 = 声明的键必须能在判据链路上找到生产者**。
  - G4 条件 C7：本类必须进类登记表（脚本 + 负对照），否则同类复发即触"两轮连发 ⇒ 致命"。

规则（机械化，非人工清单）：
  1. `KEY_REGISTRY` 逐族登记：prereg 文件 → {判据名: (要求的机械键, 生产者文件清单)}。
  2. `sweep()`：对每个要求的键，在任一生产者文件里搜 `"键名"` 字面出现（粗粒度，防过度解析）；
     全无 ⇒ MISSING（该判据不可判）。
  3. `missing_keys()` 是**纯函数**，供负对照测试（能变红）。
  4. 本脚本**预期在 S3 实装前为红**（键尚未落地）——它正是"S3 必须转绿"的护栏；不属于 pytest 常驻集，
     在 G2/判效前手动跑。

用法：
  python scripts/02_analysis/prereg_criterion_keys.py            # 扫 KEY_REGISTRY（红=有缺键）
  python scripts/02_analysis/prereg_criterion_keys.py --selftest  # 负对照（门可红）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# 生产者文件（判据链路上的实现，判据键须能在此找到）
_JUDGE = "scripts/dynport/judge_dynport.py"
_COLLECT_ONLINE = "scripts/dynport/collect_L1.py"
_COLLECT_OFFLINE = "scripts/dynport_offline/collect_L1.py"
# 论文3 / CGB 的判据机（2026-10-30）
_CGB_GATE = "scripts/paper3_bpw/check_cgb_gate.py"
_CGB_JUDGE = "scripts/paper3_bpw/judge_cgb_l1.py"
_FDOSE_GATE = "scripts/paper3_bpw/check_fdose_gate.py"
_FDOSE_JUDGE = "scripts/paper3_bpw/judge_fdose.py"
# 论文3 / MaskStat 的判据链（2026-11-04，P3-D2-016）
_MASKSTAT_MODEL = "gaussian_splatting/scene/gaussian_model.py"
_MASKSTAT_MOD = "utils/maskstat.py"
_MASKSTAT_JUDGE = "scripts/paper3_bpw/judge_maskstat.py"
# 论文3 / 剂量-响应筛查的报告生成器（P3-D2-018/019）
_DOSE_RENDER = "scripts/paper3_bpw/render_dose_response.py"
# 论文3 / 剂量轴 A4 仪器口径判读（P3-D2-038）
_DOSE_A4_JUDGE = "scripts/paper3_bpw/judge_dose_a4_instrument.py"
# 论文3 / 剂量轴反向扫判读（P3-D2-039）
_DOSE_SCAN_JUDGE = "scripts/paper3_bpw/judge_dose_scan.py"
# 论文3 / MaskStat 仪器口径判读（P3-D2-031 起；2026-11-07 加 --expect-frames）
_MASKSTAT_INSTR_JUDGE = "scripts/paper3_bpw/judge_maskstat_instrument.py"
# 论文3 / 剂量过供给验证批判读（P3-D2-041）
_OVERSUPPLY_JUDGE = "scripts/paper3_bpw/judge_dose_oversupply.py"
_ASYNC_MIGRATION_JUDGE = "scripts/paper3_bpw/judge_dose_async_migration.py"
# 论文3 / E 轴自适应 itr 调度 L1（P3-D2-045）
_ADAPTIVE_ITR_JUDGE = "scripts/paper3_bpw/judge_adaptive_itr_l1.py"
_ADAPTIVE_ITR_L2_JUDGE = "scripts/paper3_bpw/judge_adaptive_itr_l2.py"
_ADAPTIVE_ITR_MODULE = "utils/adaptive_itr.py"

# 族登记表：prereg → {判据: (要求键列表, 允许的生产者文件列表)}
KEY_REGISTRY: dict[str, dict[str, tuple[list[str], list[str]]]] = {
    "results/dynport_offline/evidence/prereg_dynport_offline_L1.md": {
        # §12 v4（2026-10-07）：J1/J2/J3 出口口径 = samepose；旧键（B/final-map、快照位姿 causal）降为诊断。
        "J3_static": (["J3_samepose_static_delta"], [_JUDGE, _COLLECT_OFFLINE]),
        "J1_dynamic": (["J1_samepose_bad_psnr_delta"], [_JUDGE, _COLLECT_OFFLINE]),
        "J2_depth": (["J2_samepose_bad_dl1_ratio"], [_JUDGE, _COLLECT_OFFLINE]),
        # 诊断口径键（须仍可产，供对照；不进出口）
        "J3_diag_finalmap": (["J3_static_delta"], [_JUDGE]),
        # M1：Δfull 子句须有机械落点（生产者须吐该键）**且回接出口**（G2 L3 major#2：
        # 原只产键、`j3_ok` 不消费 ⇒ 现要求 judge 产同帧键 `J3_samepose_full_delta` + collect 消费）。
        "J3_full": (["J3_full_delta", "J3_samepose_full_delta"], [_JUDGE, _COLLECT_OFFLINE]),
        # 次要：J6 的 bad_px 中位 >0 须有落点（且须落帧覆盖 → J6_frame_coverage）
        "J6_judgeable": (["dyn_bad_px", "J6_frame_coverage"], [_JUDGE, _COLLECT_OFFLINE]),
        # M8/J4：离线预算报数键
        "J4_offline_budget": (["repair_wall_s"], [_COLLECT_OFFLINE]),
        # G2 类「prereg 声明 ⊃ 实装（守门弱化）」：以下键证明守门**真按 prereg 实装**（非静默弱化）。
        # J5 三计数 + 峰值非退化（非"跑完即>0"）；J9 batch 级 off≡底图（非 `.get(...,True)` 默认真）；
        # J5 两态差 = **PSNR max|Δ|**（prereg §3 字面；G2 L3 major#1：原用逐位 off≡底图替代，非 PSNR）。
        # 缺任一 ⇒ 该守门不可判（MISSING）。
        "J5_guard": (["J5_counters_ok", "J5_n_dyn_peak", "J5_two_state_full_psnr_maxabs"],
                     [_JUDGE, _COLLECT_OFFLINE]),
        "J9_guard": (["J9_status", "batch_off_state"], [_COLLECT_OFFLINE]),
    },
    # 2026-10-30 新增（slam-critic M6）：论文3 / CGB 族。登记后本门即可检出
    # "预注册声明了机械判据、判据机却不产出该键"这一类（§0.3 要求新族立案即登记）。
    "paper3/results/evidence/prereg_cgb_2026-10-30.md": {
        # R1 机制门的三个子键（check_cgb_gate.py 必须真产出）
        "R1_dose": (["g1_budget_err_max_abs"], [_CGB_GATE]),
        "R1_placement": (["g2_ratio_mean"], [_CGB_GATE]),
        "R1_disjoint": (["g3_ref_extra_overlap"], [_CGB_GATE]),
        # §4 R2 剂量：两列并陈键（2026-10-30 审查 F1 后新增）
        "R2_dose_columns": (["relative_gap_online", "relative_gap_refined",
                             "columns_agree_in_sign"], [_CGB_JUDGE]),
    },
    # 2026-10-31 新增（FDose = ② 的可构造形式；DISCIPLINE「类登记表」要求新族立案即登记）：
    # 机制门 F1–F5 的机械落点。F3 已按 Amendment A1 从「跨臂索引 Jaccard」拆成
    # F3a（臂内稀疏度比，硬门）/ F3b（索引 Jaccard，报告项）。
    # 键名用**判据机源码里的字面名**（本门是 substring 匹配，不解析 JSON 路径）。
    "paper3/results/evidence/prereg_fdose_2026-10-31.md": {
        "F1_dose": (["events_with_wrong_k"], [_FDOSE_GATE]),
        "F2_plan": (["f2_plan_faithful", "f2_overflow_flag_violations",
                     "f2_plan_events"], [_FDOSE_GATE]),
        # A1 把 F3 拆成 F3a（臂内稀疏度比，硬门）/ F3b（索引 Jaccard，报告项）；
        # A4（2026-11-02）把 F3a 硬门换成 F3a′ 同池反事实键对比（trace_pool 数据源），
        # 旧跨臂口径降报告项并与池基线并陈。
        "F3a_prime_gamma_active": (["f3a_prime_mean", "f3a_prime_share_above"], [_FDOSE_GATE]),
        "F3a_cross_arm_report": (["f3a_cross_arm", "pool_baseline_ratio"], [_FDOSE_GATE]),
        "F3b_index_jaccard_report": (["f3b_index_jaccard"], [_FDOSE_GATE]),
        "F4_pool": (["below_pool_total"], [_FDOSE_GATE]),
        "F5_activity": (["f5_activity", "sum_sel_G", "sum_sel_S",
                         # Amendment A3（2026-11-01）：F5② 降为报告项，判据机须产结构化
                         # k0 报告字段（f5_k0_report / sum_sel_k0），不再是硬门键。
                         "f5_k0_report", "sum_sel_k0"], [_FDOSE_GATE]),
        # §6 出口：三 seed 判定键（单 seed 时判据机落 SINGLE_SEED，仍产这些键）
        "R_outcome": (["rule_applied", "mde_cm", "S_minus_G"], [_FDOSE_JUDGE]),
        # §4.2 R6/R7「必须报」的机械落点（2026-11-01 A5；报告项，缺 trace 显式 missing）
        "R6R7_residuals": (["R6_pool_drift", "R7_ordinal_time_shift"], [_FDOSE_JUDGE]),
    },
    # 2026-11-04 新增（MaskStat = 统计输入纯度轴；「类登记表」要求新族立案即登记）。
    "paper3/results/evidence/prereg_maskstat_2026-11-04.md": {
        # §2 G1/G2：加权数学落点（weight=None 逐位一致 / w 缩放 accum 与 denom）
        "G1_G2_weight_math": (["weight * grad_norm", "denom[update_filter] += weight"],
                              [_MASKSTAT_MODEL]),
        # §2 G3：fail-closed（机制开而掩码不可得 ⇒ RuntimeError）
        "G3_fail_closed": (["禁止静默按 w=1 退化"], [_MASKSTAT_MOD]),
        # §2 G4：机制激活证据（run 级 CSV）
        "G4_trace": (["maskstat_trace.csv", "share_w_lt_1", "share_w_eq_0",
                      "mean_mask_ratio"], [_MASKSTAT_MOD]),
        # §4 出口：判据机机械键
        "R_outcome": (["rule_applied", "mde_cm", "on_minus_off"], [_MASKSTAT_JUDGE]),
    },
    # 2026-11-04 新增（P3-D2-019 G2-M7）：剂量-响应筛查族的声明键。
    # 守护「prose 声称的平台判定必须真由机械键产出」，防止呈现层与判据脱钩（M1 的成因）。
    "paper3/results/evidence/prereg_dose_response_2026-11-04.md": {
        # R1：平台列真判（三差全 < 地板才 YES）
        "R1_platform": (["platform_ok", "gap_2x_4x_cm", "gap_2x_1x_cm", "gap_4x_1x_cm"],
                        [_DOSE_RENDER]),
        # R2：D1 必须带下界（"剂量真的变了"，不是平凡单调）
        "R2_d1": (["d1_dose_changed", "d1_total_drop_pct", "d1_dose_monotone"],
                  [_DOSE_RENDER]),
        # R3：帧数闸机械化（580 断言）
        "R3_frames": (["num_frames", "expect_frames", "d3_frames_ok"], [_DOSE_RENDER]),
    },
    # 2026-11-06 新增（P3-D2-038）：剂量轴 A4 仪器口径复验。核心防守 = 高斯数比硬约束
    # （prereg §3.3 出口 2：ATE 改善但 ratio > 1.5 ⇒ DOSE_CONFOUND，防「更多 vs 更对」）。
    "paper3/results/evidence/prereg_dose_a4_instrument_2026-11-06.md": {
        "R1_effect": (["POSITIVE_ATE_DOSE_OK", "median_delta_ate_cm", "same_sign",
                       "claim_floor_cm"], [_DOSE_A4_JUDGE]),
        "R2_dose_cap": (["DOSE_CONFOUND", "max_gauss_ratio", "gauss_ratio_cap"],
                        [_DOSE_A4_JUDGE]),
        "R3_frames_rc": (["n_frames_expected", "finished_rc0", "INSTRUMENT_INVALID"],
                         [_DOSE_A4_JUDGE]),
        "R4_outcome": (["BELOW_CLAIM_FLOOR", "CLOSED_NEGATIVE_OR_UNSTABLE",
                        "CLOSED_NEGATIVE_OR_UNSTABLE"], [_DOSE_A4_JUDGE]),
    },
    # 2026-11-06 新增（P3-D2-039）：剂量轴**反向**扫。核心防守升级为 **ratio 双侧带**
    # [0.5, 1.5]（A4 只有上界；反向会塌高斯数，需下界防「地图退化冒充改善」）
    # + static PSNR 降 ≤0.5dB（只在判正面时卡）。
    "paper3/results/evidence/prereg_dose_reverse_2026-11-06.md": {
        "R1_effect": (["POSITIVE_DEFAULT_OVERDOSED", "median_delta_ate_cm", "same_sign",
                       "claim_floor_cm"], [_DOSE_SCAN_JUDGE]),
        "R2_dose_band": (["DOSE_CONFOUND", "min_gauss_ratio", "max_gauss_ratio",
                          "gauss_ratio_band"], [_DOSE_SCAN_JUDGE]),
        "R3_psnr_gate": (["max_psnr_drop_db", "psnr_drop_cap_db", "static_psnr_db"],
                         [_DOSE_SCAN_JUDGE]),
        "R4_joint": (["BOTH_SIDES_WORSE", "MONOTONE_WORSE_DOWN",
                      "DOWN_SIDE_HAS_EFFECT", "joint_verdict"], [_DOSE_SCAN_JUDGE]),
        "R5_frames_rc": (["n_frames_expected", "finished_rc0", "INSTRUMENT_INVALID"],
                         [_DOSE_SCAN_JUDGE]),
    },
    # 2026-11-07 新增（P3-D2-040 开放区收尾）：MaskStat crowd L2。判据结构沿用
    # prereg_maskstat_instrument（出口/门槛逐字），本件只改序列与 seed 数——
    # 登记目的是让帧数期望随序列变的参数（--expect-frames）有判据锚。
    "paper3/results/evidence/prereg_maskstat_crowd_l2_2026-11-07.md": {
        "R_outcome": (["rule_applied", "maskstat_trace", "mean_w"], [_MASKSTAT_JUDGE]),
        "R_frames": (["n_frames_expected", "expect_frames"], [_MASKSTAT_INSTR_JUDGE]),
    },
    # 2026-11-07 新增（P3-D2-041）：剂量过供给验证批。核心 = H1 可证伪预测
    # （churn→增益同序）的机械路由 + 每序列异号「未判」不取中位。
    "paper3/results/evidence/prereg_dose_oversupply_2026-11-07.md": {
        "H1_routes": (["PREDICTION_CONFIRMED", "GAIN_NO_PREDICTOR",
                       "SEQUENCE_DEPENDENT", "NO_GENERALIZATION"], [_OVERSUPPLY_JUDGE]),
        "H1_gain": (["gain_cm", "median_delta_ate_cm", "claim_floor_cm"], [_OVERSUPPLY_JUDGE]),
        "H2_left": (["median_delta_vs_default_cm"], [_OVERSUPPLY_JUDGE]),
        "R_frames_rc": (["finished_rc0", "INSTRUMENT_INVALID"], [_OVERSUPPLY_JUDGE]),
    },
    # 2026-11-08 新增（过供给 Amendment A1）：第三 seed 补批（论文数字 3-seed 纪律）。
    # 判据/出口/判读器全部沿母件，仅 seed 集 0/1 → 0/1/2 + R-valid 锚对消费规则预声明。
    "paper3/results/evidence/prereg_dose_oversupply_amendment_a1_seed3_2026-11-08.md": {
        "H1_routes": (["PREDICTION_CONFIRMED", "GAIN_NO_PREDICTOR",
                       "SEQUENCE_DEPENDENT", "NO_GENERALIZATION"], [_OVERSUPPLY_JUDGE]),
        "H1_gain": (["gain_cm", "median_delta_ate_cm", "claim_floor_cm"], [_OVERSUPPLY_JUDGE]),
        "R_frames_rc": (["finished_rc0", "INSTRUMENT_INVALID"], [_OVERSUPPLY_JUDGE]),
        "R_valid_anchor": (["R1_bitwise_identical", "R2"], ["scripts/paper3_bpw/run_instrument.sh"]),
    },
    # 2026-11-08 新增（P3-D2-043）：剂量前沿 async 迁移检查（部署口径）。核心 =
    # 装置自差包络三档（DIRECTION_JUDGED / ENVELOPE_UNJUDGEABLE / SIGN_UNSTABLE）
    # + 比例/PSNR 迁移档 + 机械总出口（优先级互斥）。
    "paper3/results/evidence/prereg_dose_async_migration_2026-11-08.md": {
        "Migration_routes": (["RUN_INVALID", "CONTRADICTED", "FULL_TRANSFER",
                              "MAP_PSNR_TRANSFERRED_ATE_ENVELOPE", "MIXED"],
                             [_ASYNC_MIGRATION_JUDGE]),
        "C1_ratio_gates": (["gauss_ratio", "UNJUDGEABLE_BAND"], [_ASYNC_MIGRATION_JUDGE]),
        "C2_psnr": (["static_psnr_delta_db"], [_ASYNC_MIGRATION_JUDGE]),
        "C3_ate_envelope": (["DIRECTION_JUDGED", "ENVELOPE_UNJUDGEABLE", "SIGN_UNSTABLE",
                             "envelope_cm", "direction_vs_instrument"], [_ASYNC_MIGRATION_JUDGE]),
        "R_frames_rc": (["finished_rc0"], [_ASYNC_MIGRATION_JUDGE]),
    },
    # 2026-11-09 新增（P3-D2-045 E 轴）：自适应 itr 调度 L1。核心 = 四出口机械路由
    # （L1_PASS / L1_ATE_GAIN / L1_NO_VALUE / INSTRUMENT_INVALID；MECH_INVALID 为
    # fail-closed 旁路）+ M1 机制门的可执行计数（日志稳定子串 + backend 双计数）。
    "paper3/results/evidence/prereg_adaptive_itr_schedule_2026-11-08.md": {
        "E1_routes": (["L1_PASS", "L1_ATE_GAIN", "L1_NO_VALUE", "INSTRUMENT_INVALID",
                       "MECH_INVALID"], [_ADAPTIVE_ITR_JUDGE]),
        "E2_mech_gate": (["adaptive_itr KF#", "adaptive_itr_early_calls",
                          "adaptive_itr_late_calls"], [_ADAPTIVE_ITR_JUDGE, _ADAPTIVE_ITR_MODULE]),
        "E3_parity_and_saving": (["claim_floor_cm", "saving_iterations", "saving_pct"],
                                 [_ADAPTIVE_ITR_JUDGE]),
        "R_frames_rc": (["finished_rc0"], [_ADAPTIVE_ITR_JUDGE]),
    },
    # 2026-11-10 新增（P3-D2-047 提名的 L2 确认批，Amd A3）：四出口 + 渲染代价闸。
    "paper3/results/evidence/prereg_adaptive_itr_amendment_a3_2026-11-10.md": {
        "L2_routes": (["L2_CONFIRMED", "L2_CONFIRMED_TRADEOFF", "L2_DIRECTION_ONLY",
                       "L2_SIGN_UNSTABLE", "L2_INSTRUMENT_INVALID"], [_ADAPTIVE_ITR_L2_JUDGE]),
        # mech/rc 两键的生产者是 L1 判读器（L2 经 import 复用其 collect/read_done/日志解析）
        "L2_mech_gate": (["adaptive_itr KF#", "schedule_params"],
                         [_ADAPTIVE_ITR_L2_JUDGE, _ADAPTIVE_ITR_JUDGE]),
        "L2_render_gate": (["static_psnr_db", "static_depth_l1_cm", "tradeoff_triggered"],
                           [_ADAPTIVE_ITR_L2_JUDGE]),
        "R_frames_rc": (["finished_rc0"], [_ADAPTIVE_ITR_L2_JUDGE, _ADAPTIVE_ITR_JUDGE]),
    },
}


def missing_keys(declared: dict[str, tuple[list[str], list[str]]],
                 corpus: dict[str, str]) -> dict[str, list[str]]:
    """纯函数：返回 {判据: [缺的键...]}。corpus = {文件路径: 文本内容}。

    要求：每个键须在**该判据允许的任一生产者文件**里字面出现；全无 ⇒ 缺。
    """
    out: dict[str, list[str]] = {}
    for crit, (keys, producers) in declared.items():
        texts = [corpus.get(p, "") for p in producers]
        miss = [k for k in keys if not any(k in t for t in texts)]
        if miss:
            out[crit] = miss
    return out


def _load_corpus(files: set[str]) -> dict[str, str]:
    corpus = {}
    for rel in files:
        f = REPO / rel
        corpus[rel] = f.read_text(errors="ignore") if f.exists() else ""
    return corpus


def sweep() -> int:
    total_missing = 0
    for prereg, declared in KEY_REGISTRY.items():
        files = {p for _k, (_ks, ps) in declared.items() for p in ps}
        corpus = _load_corpus(files)
        miss = missing_keys(declared, corpus)
        print(f"[criterion-keys] {prereg}")
        for crit, (keys, producers) in declared.items():
            bad = miss.get(crit)
            status = "OK" if not bad else f"MISSING {bad}"
            print(f"    {crit}: {keys} via {producers} => {status}")
            total_missing += len(bad or [])
    print(f"MISSING_TOTAL = {total_missing}")
    return 1 if total_missing else 0


def selftest() -> int:
    """负对照：声明键但生产者不含 ⇒ 必红；生产者含 ⇒ 必绿。"""
    declared = {"Jx": (["key_a", "key_b"], ["prod.py"])}
    # 负对照：生产者缺 key_b ⇒ 必须报出 key_b
    red = missing_keys(declared, {"prod.py": 'res["key_a"] = 1'})
    assert red == {"Jx": ["key_b"]}, f"负对照失败：缺键未被抓到 ⇒ 门失效（{red}）"
    # 正对照：生产者含两键 ⇒ 不报
    green = missing_keys(declared, {"prod.py": 'res["key_a"]=1; res["key_b"]=2'})
    assert not green, f"正对照失败：键齐备仍报警 ⇒ 过度报警（{green}）"
    # 生产者文件不存在（空语料）⇒ 视为缺（防"路径写错导致假绿"）
    empty = missing_keys(declared, {})
    assert empty == {"Jx": ["key_a", "key_b"]}, f"空语料未判缺 ⇒ 假绿风险（{empty}）"
    assert KEY_REGISTRY, "族登记表为空 —— 机制被摘除"
    print("selftest OK（缺键变红 / 齐备放行 / 空语料判缺 / 登记表非空）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    return selftest() if args.selftest else sweep()


if __name__ == "__main__":
    sys.exit(main())
