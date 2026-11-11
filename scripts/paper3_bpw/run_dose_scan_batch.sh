#!/bin/bash
# run_dose_scan_batch.sh — 剂量轴反向扫派发（prereg_dose_reverse_2026-11-06 §1.2）。
#
# 布局（7 run，两卡）：
#   卡0: tau2x seed0 ×2（R-valid）→ tau2x seed1
#   卡1: tau2x seed2 → tau4x seed0 → seed1 → seed2
#
# 卡1 多一个 run，但 tau4x 三 seed 全长同形，时间可控（~80min/run）。
# **同臂不跨卡并发**（arm 根 tables/*.csv 是共享文件）。
#
# 用法：
#   setsid env bash scripts/paper3_bpw/run_dose_scan_batch.sh >> paper3/results/evidence/dose_scan_batch.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
ARM2=instrument_dose_tau2x_person_tracking
ARM4=instrument_dose_tau4x_person_tracking
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"

export MONOGS_REPO="$REPO" MONOGS_PY="$PY"

log() { echo "[$(date +%H:%M:%S)] $*"; }

n=$(ps -eo cmd | grep -c "[s]lam.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个 slam.py 在跑，本批要求空机（避免并发污染仪器口径）"
  exit 1
fi

log "=== 剂量反向扫 开始 ==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

(
  export CUDA_VISIBLE_DEVICES=0
  log "[gpu0] tau2x seed0 ×2（R-valid）"
  bash "$RUNNER" "$ARM2" 0 0 2 || { log "[gpu0] tau2x seed0 失败"; exit 1; }
  log "[gpu0] tau2x seed1"
  bash "$RUNNER" "$ARM2" 1 0 1 || { log "[gpu0] tau2x seed1 失败"; exit 1; }
  log "[gpu0] 链完成"
) &
P0=$!

(
  export CUDA_VISIBLE_DEVICES=1
  log "[gpu1] tau2x seed2"
  bash "$RUNNER" "$ARM2" 2 0 1 || { log "[gpu1] tau2x seed2 失败"; exit 1; }
  for s in 0 1 2; do
    log "[gpu1] tau4x seed$s"
    bash "$RUNNER" "$ARM4" "$s" 0 1 || { log "[gpu1] tau4x seed$s 失败"; exit 1; }
  done
  log "[gpu1] 链完成"
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== 剂量反向扫 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
