#!/usr/bin/env python3
"""装置门探针三方逐位比对生成器（P3-D2-024；prereg_device_gate_2026-11-05 B3 口径）.

对同 config 同 seed 的 N 个确定性样本 run 目录做两两 md5 逐位比对：
- 逐位件：tracking_raw.csv / per_frame_ape.csv / efficiency_raw.csv /
  mapping_raw.csv / plot/{stats_final,trj_final,trj_full_final}.json /
  detprobe_*_lastrow.txt（共享 tables 末行快照）
- config.yml：掩蔽 ``save_dir`` 行后比对（行含时间戳路径，非行为变量）
- 出口：全部件两两全同 ⇒ R1_bitwise_identical；任一件不同 ⇒ R2_divergent

用法（判定 2026-11-05 探针批）：
  python3 -I scripts/paper3_bpw/deterministic_probe/compare_three_way.py \
      --base results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/\
maskstat_off_person_tracking/seed_0 \
      --samples 2026-11-05-03-23-38 2026-11-05-03-49-26 2026-11-05-04-13-35 \
      --out-dir <run 目录根>   # 在每个样本 run 目录写 detprobe_compare.json

消费方：P3-D2-024 判决（G2-C3 整改——生成器必须入库可复跑）。
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

# 逐位比对集。CSV 类走「易变列剔除」变体（见 CSV_FILES / VOLATILE_COLUMNS），
# 不在此列表里重复登记——否则同一份文件会被以原始字节再比一次而误报。
BITWISE = [
    "per_frame_ape.csv",
    "plot/stats_final.json",
    "plot/trj_final.json",
    "plot/trj_full_final.json",
]
LASTROW = ["detprobe_efficiency_raw_lastrow.txt", "detprobe_mapping_raw_lastrow.txt"]
MASKED = ["config.yml"]

# 易变列（每次 run 必然不同，不构成行为差异）：时间戳 / 路径 / 墙上时钟 / 显存峰值。
# 2026-11-05 加入（det-raster 2×2）：不排除它们会把「逐位一致」误报成 R2，
# 因为这些列的语义是「这次跑在哪、跑了多久」，不是「模型算出了什么」。
VOLATILE_COLUMNS = {
    "run_id", "source_dir", "notes",
    "online_fps", "online_time_s", "online_peak_gpu_memory_gb",
    "refinement_wall_time_s", "refinement_backend_time_s", "refinement_peak_gpu_memory_gb",
    "fps_end_to_end", "tracking_fps", "mapping_fps",
    "tracking_time_ms", "mapping_time_ms", "total_time_s",
    "tracking_time_s", "mapping_time_s", "color_refinement_time_s",
    "semantic_time_ms", "gpu_memory_gb", "geometry_eval_time_s",
    "reliability_time_ms", "tri_reliability_time_ms", "reliable_tracking_time_ms",
}
CSV_FILES = {
    "tracking_raw.csv", "efficiency_raw.csv", "mapping_raw.csv",
    "reliability_signal/frames.csv", "deferred_commit_events.csv",
}
NEEDS_MASK = {"tracking_raw.csv", "efficiency_raw.csv", "mapping_raw.csv"}


def masked_csv(path):
    """CSV 内容，去掉 VOLATILE_COLUMNS 列（其余列原样、逐字节）。"""
    import csv as _csv
    import io
    with path.open(newline="") as fh:
        rows = list(_csv.reader(fh))
    if not rows:
        return b""
    hdr = rows[0]
    keep = [i for i, name in enumerate(hdr) if name not in VOLATILE_COLUMNS]
    out = io.StringIO()
    w = _csv.writer(out, lineterminator="\n")
    for r in rows:
        w.writerow([r[i] if i < len(r) else "" for i in keep])
    return out.getvalue().encode()


def md5(data):
    return hashlib.md5(data).hexdigest()


def masked(path):
    """config.yml 内容，save_dir 行替换为占位（时间戳非行为变量）。"""
    out = []
    for line in path.read_bytes().split(b"\n"):
        out.append(b"save_dir: <MASKED>" if line.lstrip().startswith(b"save_dir:") else line)
    return b"\n".join(out)


def collect(base, samples):
    files, md5s = [], {}
    for tag, ts in samples.items():
        d = base / ts
        for f in BITWISE + LASTROW:
            p = d / f
            data = p.read_bytes() if p.is_file() else None
            md5s.setdefault(f, {})[tag] = md5(data) if data is not None else None
        for f in MASKED:
            p = d / f
            data = masked(p) if p.is_file() else None
            md5s.setdefault(f + "(save_dir掩蔽)", {})[tag] = md5(data) if data is not None else None
        for f in CSV_FILES:
            p = d / f
            if not p.is_file():
                continue
            data = masked_csv(p) if f in NEEDS_MASK else p.read_bytes()
            md5s.setdefault(f + "(易变列剔除)", {})[tag] = md5(data)
    return files, md5s


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="seed_N 目录（其下为各 run 时间戳目录）")
    ap.add_argument("--samples", nargs="+", required=True, help="run 目录名（时间戳）；顺序 = 样本号 A,B,C…")
    ap.add_argument("--out-dir", default="", help="若给出，则在每个样本 run 目录写 detprobe_compare.json")
    ap.add_argument("--stdout", default="", help="若给出，另写一份 json 到该路径")
    args = ap.parse_args()

    base = Path(args.base)
    samples = {chr(ord("A") + i): ts for i, ts in enumerate(args.samples)}
    _, md5s = collect(base, samples)

    tags = list(samples)
    report = {"pairs": {}, "files": md5s, "samples": samples, "verdict": None}
    all_same = True
    for i in range(len(tags)):
        for j in range(i + 1, len(tags)):
            a, b = tags[i], tags[j]
            # 两侧都不存在 ⇒ 该件不适用于本批（例如手工派发的 run 不写 lastrow 快照），
            # 记为 N/A 而非 DIFF。只有「一侧有、一侧无」才是真差异。
            diffs = [
                f for f, m in md5s.items()
                if not (m[a] is None and m[b] is None)
                and (m[a] != m[b] or m[a] is None or m[b] is None)
            ]
            report["pairs"][f"{a}-{b}"] = {
                "same": [f for f in md5s if f not in diffs],
                "diff": diffs,
            }
            if diffs:
                all_same = False
            print(f"pair {a}-{b}: same={len(md5s) - len(diffs)} diff={len(diffs)}")
            for f in diffs:
                print(f"  DIFF {f}: {md5s[f][a]} vs {md5s[f][b]}")
    report["verdict"] = "R1_bitwise_identical" if all_same else "R2_divergent"
    print(f"\nVERDICT: {report['verdict']}")

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out_dir:
        for ts in samples.values():
            (base / ts / "detprobe_compare.json").write_text(payload)
    if args.stdout:
        Path(args.stdout).write_text(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
