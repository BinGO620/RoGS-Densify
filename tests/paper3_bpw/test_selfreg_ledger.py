"""戊泛化探针门禁（P3-D2-040）：
① 三个 e2_base 配置 = instr_off_<seq> 的单变量派生（只差 E2.trace_events + save_dir）；
② 仪器开关与机制关断全部在位；
③ selfreg_ledger 提取器的账本口径（以 P3-D2-036 的 pt 参照数为回归锚）。
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "configs/experiments/paper3_bpw"
LEDGER = ROOT / "scripts/paper3_bpw/selfreg_ledger.py"

SEQS = ("balloon", "crowd", "moving_nonobstructing_box")


def _resolved(name):
    sys.path.insert(0, str(ROOT))
    from utils.config_utils import load_config

    return load_config(str(CFG / f"{name}.yaml"))


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat(v, key))
        else:
            out[key] = v
    return out


@pytest.mark.parametrize("seq", SEQS)
def test_e2_base_is_single_variable_derivation(seq):
    """e2_base_<seq> vs instr_off_<seq>：差异恰为 E2 开关 + 两条路径键。"""
    base = _flat(_resolved(f"instr_off_{seq}"))
    e2 = _flat(_resolved(f"e2_base_{seq}"))
    diff = {k for k in set(base) | set(e2) if base.get(k) != e2.get(k)}
    assert diff == {"E2.trace_events", "Results.save_dir", "inherit_from"}, sorted(diff)


@pytest.mark.parametrize("seq", SEQS)
def test_e2_base_gates(seq):
    """E2 开、仪器三开关全 on、机制全关（纯日志探针，不得带任何机制）。"""
    c = _resolved(f"e2_base_{seq}")
    assert c["E2"]["trace_events"] is True
    assert c["Training"]["single_thread"] is True
    assert c["Dataset"]["single_thread"] is True
    assert c["Rasterizer"]["deterministic_backward"] is True
    assert c["SelectiveDensification"]["enabled"] is False
    assert (c.get("Mapping") or {}).get("maskstat_dens_stats", False) is False
    assert (c.get("MissStreak") or {}).get("enabled", False) is False


# ─────────────── ③ 提取器口径（pt 参照回归锚） ───────────────
def _mk_run(tmp_path, events, removed_lines, online_gauss):
    d = tmp_path / "run"
    d.mkdir(parents=True)
    with (d / "e2_events.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow("event,iteration,n_gauss,denom_p10,denom_p50,denom_p90,"
                   "grad_p50,ms_p50,ms_p90,ms_p99,"
                   "n_gt1,n_gt3,n_gt5,n_gt10,n_gt20,n_gt30,n_gated,n_added".split(","))
        for i, (ng, na) in enumerate(events):
            w.writerow([i, 100 * (i + 1), ng, 1, 2, 3, 0.1, 0, 0, 0,
                        ng // 2, ng // 4, ng // 8, ng // 16, ng // 32, ng // 64,
                        "", na])
    (d / "console.log").write_text(
        "".join(f"MonoGS: Pruned {i} lineage(s): removed {n} Gaussians\n"
                for i, n in enumerate(removed_lines)))
    (d / "efficiency_raw.csv").write_text(
        "method,run_id,online_num_gaussians\n"
        f"X,r,{online_gauss}\n")
    return d


def test_ledger_matches_pt_reference_numbers(tmp_path):
    """P3-D2-036 的 pt 参照数必须被逐位复现（账本口径的回归锚）。

    参照（growth_waste_balance_2026-11-06.md）：Σn_added=11842、Σremoved=1975、
    ratio=16.68%（文档四舍五入为 16.7%）。这里用同一组数字的合成 fixture。
    """
    # 构造：11 个事件、Σn_added=11842；console removed 合计 1975
    per = [1077, 1077, 1077, 1077, 1077, 1077, 1077, 1077, 1077, 1077, 1072]
    assert sum(per) == 11842
    d = _mk_run(tmp_path, [(7188 + i * 1000, per[i]) for i in range(11)],
                [1, 1, 1042, 931], 19771)
    out = tmp_path / "j.json"
    r = subprocess.run([sys.executable, str(LEDGER), f"--run=pt={d}",
                        f"--out={out}"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rep = json.loads(out.read_text())
    pt = rep["ledger"]["pt"]
    assert pt["sum_n_added"] == 11842
    assert pt["sum_console_removed"] == 1975
    assert pt["waste_ratio"] == pytest.approx(0.1668, abs=1e-4)
    assert pt["waste_ratio_below_line"] is True
    assert rep["all_below_line"] is True


def test_ledger_above_line_detected(tmp_path):
    """浪费比率超 20% ⇒ below_line=False（判据线可反向触发，防恒真）。"""
    d = _mk_run(tmp_path, [(1000, 1000)], [500], 1500)   # 500/1000 = 50%
    out = tmp_path / "j.json"
    subprocess.run([sys.executable, str(LEDGER), f"--run=x={d}",
                    f"--out={out}"], capture_output=True, text=True)
    rep = json.loads(out.read_text())
    assert rep["ledger"]["x"]["waste_ratio_below_line"] is False
    assert rep["all_below_line"] is False


def test_ledger_missing_artifacts_fail_closed(tmp_path):
    """缺 e2_events.csv / console.log ⇒ 报错且 rc=1，不得静默跳过。"""
    d = tmp_path / "empty"
    d.mkdir()
    r = subprocess.run([sys.executable, str(LEDGER), f"--run=x={d}"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "缺" in r.stdout
