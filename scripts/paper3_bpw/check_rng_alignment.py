#!/usr/bin/env python
"""check_rng_alignment.py — 验证 BPW 三臂是否共享同一随机流。

审计 2026-10-28：slam.py:736 在运行期把 Dataset.sequence 覆写为 config
文件 basename，而 base_rng_key 正是从该字段取键。三份 config 文件名不同
⇒ 三臂的初始点云下采样与随机 KF 顺序都不同 ⇒ 因果孪生前提不成立。

本脚本复现该覆写，并断言三臂的 base_rng_key 一致。

用法: python scripts/paper3_bpw/check_rng_alignment.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from utils.causal_twin import base_rng_key  # noqa: E402
from utils.config_utils import load_config  # noqa: E402

ARMS = ("off", "on", "negctl")
CFG = "configs/experiments/paper3_bpw/bpw_{arm}_balloon.yaml"


def keys_by_arm():
    """Base RNG key per arm, with slam.py:736's runtime overwrite reproduced."""
    out = {}
    for arm in ARMS:
        cfg = load_config(os.path.join(REPO, CFG.format(arm=arm)))
        cfg.setdefault("Dataset", {})["sequence"] = f"bpw_{arm}_balloon"
        cfg["seed"] = 0
        out[arm] = base_rng_key(cfg)
    return out


def main():
    keys = keys_by_arm()
    for arm, key in keys.items():
        print(f"  {arm:7s} -> {key}")

    distinct = {k for k in keys.values()}
    if len(distinct) == 1:
        only = next(iter(keys.values()))
        print(f"\nPASS: 三臂共享同一随机流，key={only}")
        return 0
    print("\nFAIL: 三臂随机流不一致 —— 因果孪生前提不成立")
    return 1


if __name__ == "__main__":
    sys.exit(main())
