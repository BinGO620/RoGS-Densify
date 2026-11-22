#!/bin/bash
# run_dose_oversupply_batch.sh — 剂量过供给验证批派发（prereg_dose_oversupply_2026-11-07 §3）。
#
# 布局（16 run，两卡，全长）：
#   GPU0: dose_zero s0×2(R-valid) → s1 → s2 → balloon off s0,s1 → balloon tau4x s0×2(R-valid) → s1
#   GPU1: crowd tau4x s0×2(R-valid) → s1 → mnobox off s0,s1 → mnobox tau4x s0×2(R-valid) → s1
# crowd off 复用 MaskStat L2 批已有 run（不重跑）。
# 同臂不跨卡并发（arm 根 tables 共享）。
set -u

REPO=${MONOGS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
PY=${MONOGS_PY:-${CONDA_PREFIX:-}/bin/python}
if [ ! -x "$PY" ]; then
    echo "set MONOGS_PY, or activate the conda env first (CONDA_PREFIX unset)" >&2
    exit 2
fi
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"
export MONOGS_REPO="$REPO" MONOGS_PY="$PY"

log() { echo "[$(date +%H:%M:%S)] $*"; }

n=$(ps -eo cmd | grep -c "[s]lam.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个 slam.py 在跑，本批要求空机"
  exit 1
fi

log "=== 剂量过供给验证批 开始 ==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

(
  export CUDA_VISIBLE_DEVICES=0
  log "[gpu0] dose_zero s0 ×2（R-valid）"
  bash "$RUNNER" instrument_dose_zero_person_tracking 0 0 2 || { log "[gpu0] zero s0 失败"; exit 1; }
  for s in 1 2; do
    log "[gpu0] dose_zero s$s"
    bash "$RUNNER" instrument_dose_zero_person_tracking $s 0 1 || { log "[gpu0] zero s$s 失败"; exit 1; }
  done
  log "[gpu0] balloon off s0,s1"
  bash "$RUNNER" instr_off_balloon 0 0 1 && bash "$RUNNER" instr_off_balloon 1 0 1 || { log "[gpu0] balloon off 失败"; exit 1; }
  log "[gpu0] balloon tau4x s0 ×2（R-valid）"
  bash "$RUNNER" instrument_dose_tau4x_balloon 0 0 2 || { log "[gpu0] balloon tau4x s0 失败"; exit 1; }
  log "[gpu0] balloon tau4x s1"
  bash "$RUNNER" instrument_dose_tau4x_balloon 1 0 1 || { log "[gpu0] balloon tau4x s1 失败"; exit 1; }
  log "[gpu0] 链完成"
) &
P0=$!

(
  export CUDA_VISIBLE_DEVICES=1
  log "[gpu1] crowd tau4x s0 ×2（R-valid）"
  bash "$RUNNER" instrument_dose_tau4x_crowd 0 0 2 || { log "[gpu1] crowd tau4x s0 失败"; exit 1; }
  log "[gpu1] crowd tau4x s1"
  bash "$RUNNER" instrument_dose_tau4x_crowd 1 0 1 || { log "[gpu1] crowd tau4x s1 失败"; exit 1; }
  log "[gpu1] mnobox off s0,s1"
  bash "$RUNNER" instr_off_moving_nonobstructing_box 0 0 1 && bash "$RUNNER" instr_off_moving_nonobstructing_box 1 0 1 || { log "[gpu1] mnobox off 失败"; exit 1; }
  log "[gpu1] mnobox tau4x s0 ×2（R-valid）"
  bash "$RUNNER" instrument_dose_tau4x_moving_nonobstructing_box 0 0 2 || { log "[gpu1] mnobox tau4x s0 失败"; exit 1; }
  log "[gpu1] mnobox tau4x s1"
  bash "$RUNNER" instrument_dose_tau4x_moving_nonobstructing_box 1 0 1 || { log "[gpu1] mnobox tau4x s1 失败"; exit 1; }
  log "[gpu1] 链完成"
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== 剂量过供给验证批 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
