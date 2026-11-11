#!/bin/bash
# run_selfreg_probe.sh — 戊泛化探针派发（P3-D2-040）：三类序列 × 2 run 40 帧仪器口径 E2 trace。
#
# 序列 = balloon（单物体）/ crowd（人群）/ moving_nonobstructing_box（移动物体）
# 配置 = e2_base_<seq>（instr_off_<seq> + E2.trace_events，纯日志开关，机制零改动）
# 每序列 2 run ⇒ 同 config 同 seed 可比对（trace 应逐位一致，仪器口径）。
#
# 用法：setsid env bash scripts/paper3_bpw/run_selfreg_probe.sh >> paper3/results/evidence/selfreg_probe.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"
export MONOGS_REPO="$REPO" MONOGS_PY="$PY"

log() { echo "[$(date +%H:%M:%S)] $*"; }

n=$(ps -eo cmd | grep -c "[s]lam.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个 slam.py 在跑，探针要求空机"
  exit 1
fi

log "=== 自调节泛化探针 开始 ==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"

(
  export CUDA_VISIBLE_DEVICES=0
  for s in balloon crowd; do
    log "[gpu0] e2_base_$s ×2"
    bash "$RUNNER" "e2_base_$s" 0 40 2 || { log "[gpu0] $s 失败"; exit 1; }
  done
  log "[gpu0] 链完成"
) &
P0=$!

(
  export CUDA_VISIBLE_DEVICES=1
  log "[gpu1] e2_base_moving_nonobstructing_box ×2"
  bash "$RUNNER" "e2_base_moving_nonobstructing_box" 0 40 2 || { log "[gpu1] mnobox 失败"; exit 1; }
  log "[gpu1] 链完成"
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== 自调节泛化探针 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
