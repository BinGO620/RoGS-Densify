#!/bin/bash
# run_dose_a4_batch.sh — 剂量轴 A4 仪器批派发（prereg_dose_a4_instrument_2026-11-06 §1.4）。
#
# 布局（5 run，两卡）：
#   卡0: A4 seed0 ×2（R-valid 前置）→ A4 seed1 → A4 seed2
#   卡1: off seed0 桥接（§2.2 批次等价性门）
#
# **同臂不跨卡并发**：arm 根的 tables/*.csv 是共享文件，同臂两 run 并发会交错追加，
# 污染聚合表（判读用 run 内副本，但聚合表是判据工件，不得被写坏）。
# 跨臂并发安全（不同 arm root ⇒ 不同 tables）。
#
# 用法（后台派发唯一形态）：
#   setsid env bash scripts/paper3_bpw/run_dose_a4_batch.sh >> paper3/results/evidence/dose_a4_batch.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
PY=${MONOGS_PY:-${CONDA_PREFIX:-}/bin/python}
if [ ! -x "$PY" ]; then
    echo "set MONOGS_PY, or activate the conda env first (CONDA_PREFIX unset)" >&2
    exit 2
fi
ARM_A4=instrument_dose_a4_person_tracking
ARM_OFF=instrument_maskstat_off
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"

export MONOGS_REPO="$REPO" MONOGS_PY="$PY"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# --- 前置：机器必须空闲（每卡允许 2 并发，但本批机内串行；有他人任务则停）---
n=$(ps -eo cmd | grep -c "[s]lam.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个 slam.py 在跑，本批要求空机（避免并发污染仪器口径）"
  exit 1
fi

log "=== A4 仪器批 开始 ==="
log "REPO=$REPO"
log "PY=$PY"
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

# --- 卡0 链：A4 seed0 ×2 → seed1 → seed2 ---
(
  export CUDA_VISIBLE_DEVICES=0
  log "[gpu0] A4 seed0 ×2（R-valid）"
  bash "$RUNNER" "$ARM_A4" 0 0 2 || { log "[gpu0] seed0 失败"; exit 1; }
  log "[gpu0] A4 seed1"
  bash "$RUNNER" "$ARM_A4" 1 0 1 || { log "[gpu0] seed1 失败"; exit 1; }
  log "[gpu0] A4 seed2"
  bash "$RUNNER" "$ARM_A4" 2 0 1 || { log "[gpu0] seed2 失败"; exit 1; }
  log "[gpu0] 链完成"
) &
P0=$!

# --- 卡1 链：off seed0 桥接（批次等价性门）---
(
  export CUDA_VISIBLE_DEVICES=1
  log "[gpu1] off seed0 桥接（§2.2 等价门）"
  bash "$RUNNER" "$ARM_OFF" 0 0 1 || { log "[gpu1] off 桥接失败"; exit 1; }
  log "[gpu1] 链完成"
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== A4 仪器批 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
