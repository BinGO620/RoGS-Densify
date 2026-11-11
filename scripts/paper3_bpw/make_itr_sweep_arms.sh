#!/bin/bash
# make_itr_sweep_arms.sh — 生成 mapping_itr_num 扫描臂（P3-D2-032 §4 丙）。
#
# 目的：量化工况依赖——单线程下「每关键帧优化量」从 150 改成 50/100/300 时，
# ATE 如何变化。若斜率大 ⇒ 仪器口径的绝对值强烈依赖该参数 ⇒ 外推到 async
# （平均每次仅 2.0 迭代）不可靠；若斜率小 ⇒ 外推风险低。
#
# 全部派生自 instrument_maskstat_off（off 臂，无机制），只改 mapping_itr_num。
set -eu
REPO=${MONOGS_REPO:-/data/monogs-ours}
CFGDIR="$REPO/configs/experiments/paper3_bpw"
BASE="instrument_maskstat_off"

for n in 50 100 300; do
  OUT="$CFGDIR/itrsweep${n}_maskstat_off.yaml"
  [ -e "$OUT" ] && { echo "skip（已存在）: $OUT"; continue; }
  cat > "$OUT" <<YAML
# mapping_itr_num 扫描臂（P3-D2-032 §4 丙）：base = ${BASE}，唯一改动 = Training.mapping_itr_num
#
# 用途：量化「每关键帧优化量」对 ATE 的敏感度 ⇒ 判断仪器口径外推到 async 的风险。
# 仪器三项开关全部继承自 base（不在此重复，防漂移）。
inherit_from: "configs/experiments/paper3_bpw/${BASE}.yaml"

Training:
  mapping_itr_num: ${n}

Results:
  save_dir: "results/paper3_bpw/itrsweep${n}_maskstat_off"
YAML
  echo "created: $OUT"
done
