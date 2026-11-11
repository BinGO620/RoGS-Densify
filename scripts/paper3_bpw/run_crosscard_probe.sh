#!/bin/bash
# run_crosscard_probe.sh — 卡间等价性探针（2026-11-06 G3 审查 M2 整改）。
#
# 目的：把「GPU0 与 GPU1 是否逐位等价」变成有据可查的事实。此前 A4 判决里
# A4 三 seed 跑卡0、off 基线出自卡1，跨卡构成未消除的第二变量，而仓内无任何证据。
#
# 设计：同 config（instrument_maskstat_off）同 seed（0），卡0 跑 1 run、卡1 跑 1 run，
# 全长 580 帧，然后 compare_three_way.py 逐位比对。
# 出口：R1_bitwise_identical ⇒ 卡间等价成立（跨卡不构成混杂）；
#       R2_divergent ⇒ 卡间不等价（A4 判决必须标注；后续批一律同臂同卡串行）。
#
# 用法：
#   setsid env bash scripts/paper3_bpw/run_crosscard_probe.sh \
#     >> paper3/results/evidence/crosscard_probe.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
ARM=instrument_maskstat_off
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"
export MONOGS_REPO="$REPO" MONOGS_PY="$PY"

log() { echo "[$(date +%H:%M:%S)] $*"; }

n=$(ps -eo cmd | grep -c "[s]lam.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个 slam.py 在跑，探针要求空机"
  exit 1
fi

log "=== 卡间等价性探针 开始 ==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"

# 同臂并发禁忌：本探针**故意**同臂并发（这是要测的东西），但两 run 写同一 arm 根
# 的 tables/*.csv ⇒ 聚合表会被交错写坏。用 --tables-dir 不行（run_instrument.sh 不透传），
# 故探针在跑完后只信 run 内副本（compare_three_way 读的就是 run 内），聚合表损坏不影响判据。
# 为减少干扰，两 run 错开 60s 启动。
(
  export CUDA_VISIBLE_DEVICES=0
  log "[gpu0] 探针 run"
  bash "$RUNNER" "$ARM" 0 0 1
) &
P0=$!
sleep 60
(
  export CUDA_VISIBLE_DEVICES=1
  log "[gpu1] 探针 run"
  bash "$RUNNER" "$ARM" 0 0 1
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "两 run 完成: gpu0 rc=$RC0  gpu1 rc=$RC1"

# 取本次两个 run（都写在 seed_0 下，按 mtime 取最新两个）
BASE="$REPO/results/paper3_bpw/${ARM}/datasets_bonn/${ARM}/seed_0"
RUNS=$(ls -dt "$BASE"/*/ 2>/dev/null | head -2 | xargs -n1 basename)
set -- $RUNS
if [ $# -ne 2 ]; then
  log "ERROR: 未捕获到两个新 run（拿到: $RUNS）"
  exit 5
fi
log "比对: $1 vs $2"
OUT=$("$PY" "$REPO/scripts/paper3_bpw/deterministic_probe/compare_three_way.py" \
    --base "$BASE" --samples "$1" "$2" 2>&1)
echo "$OUT"
V=$(echo "$OUT" | grep -o 'R1_bitwise_identical\|R2_divergent' | tail -1)
if [ "$V" = "R1_bitwise_identical" ]; then
  log "=== CROSSCARD OK: 卡0 与卡1 逐位等价 ⇒ 跨卡不构成混杂 ==="
else
  log "=== CROSSCARD BROKEN: 卡间不等价（$V）⇒ A4 判决必须标注跨卡；新批一律同卡 ==="
  exit 6
fi
