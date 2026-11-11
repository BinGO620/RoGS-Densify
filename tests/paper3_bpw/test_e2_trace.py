"""E2 逐事件落盘单测（prereg_e2_event_pairing_2026-11-06 P1）。

守护两条硬纪律：
  ① 默认关（E2.trace_events 缺省/false）⇒ 不写文件（零开销 = 逐位不变的前提）；
  ② 开启后列口径正确（机制输入量分位数 + 机制作用量计数），且 n_gated 只在有门时非空。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import csv

import torch

from utils.e2_trace import e2_enabled, log_event, snapshot_inputs


class _G:
    def __init__(self, denom, accum):
        self.denom = torch.tensor(denom, dtype=torch.float32).reshape(-1, 1)
        self.xyz_gradient_accum = torch.tensor(accum, dtype=torch.float32).reshape(-1, 1)


def _cfg(tmp_path, on):
    return {
        "E2": {"trace_events": on},
        "Results": {"save_dir": str(tmp_path)},
    }


def test_default_off_writes_nothing(tmp_path):
    cfg = _cfg(tmp_path, False)
    assert e2_enabled(cfg) is False
    g = _G([1.0, 2.0], [0.1, 0.2])
    log_event(cfg, snapshot_inputs(g), 100, 0, n_gated=0, n_added=5)
    assert not (tmp_path / "e2_events.csv").exists()


def test_absent_key_is_off(tmp_path):
    cfg = {"Results": {"save_dir": str(tmp_path)}}
    assert e2_enabled(cfg) is False


def test_on_writes_header_and_row(tmp_path):
    cfg = _cfg(tmp_path, True)
    g = _G([1.0, 4.0, 8.0, 16.0], [0.0, 0.4, 0.8, 1.6])
    log_event(cfg, snapshot_inputs(g), 150, 0, n_gated=2, n_added=7)
    p = tmp_path / "e2_events.csv"
    assert p.exists()
    rows = list(csv.DictReader(open(p)))
    assert len(rows) == 1
    r = rows[0]
    assert r["event"] == "0" and r["iteration"] == "150"
    assert r["n_gauss"] == "4"
    assert float(r["denom_p50"]) > 0
    assert r["n_gated"] == "2" and r["n_added"] == "7"


def test_no_gate_leaves_gated_blank(tmp_path):
    cfg = _cfg(tmp_path, True)
    g = _G([1.0, 2.0], [0.1, 0.2])
    log_event(cfg, snapshot_inputs(g), 100, 0, n_gated=None, n_added=3)
    r = list(csv.DictReader(open(tmp_path / "e2_events.csv")))[0]
    assert r["n_gated"] == ""
    assert r["n_added"] == "3"


def test_two_events_append(tmp_path):
    cfg = _cfg(tmp_path, True)
    g = _G([1.0], [0.1])
    log_event(cfg, snapshot_inputs(g), 100, 0, n_gated=0, n_added=1)
    log_event(cfg, snapshot_inputs(g), 250, 1, n_gated=0, n_added=2)
    rows = list(csv.DictReader(open(tmp_path / "e2_events.csv")))
    assert [r["event"] for r in rows] == ["0", "1"]


def test_snapshot_reads_nonzero_quantiles(tmp_path):
    """回归（2026-11-06 冒烟踩坑）：分位数必须非零。

    第一版把分位数读在 densify_and_prune **之后**，而该函数末尾会重置
    denom/accum ⇒ 冒烟里 p10/p50/p90/grad_p50 全 0。现改为事前 snapshot。
    """
    cfg = _cfg(tmp_path, True)
    g = _G([2.0, 5.0, 9.0, 20.0], [0.4, 1.0, 1.8, 4.0])
    snap = snapshot_inputs(g)
    assert snap["denom_p50"] > 0
    assert snap["grad_p50"] > 0
    assert snap["n_gauss"] == 4
