#!/bin/bash
# run_maskstat_crowd_l2.sh — MaskStat crowd L2 派发（prereg_maskstat_crowd_l2_2026-11-07 §2）。
#
# 布局（6 run，两卡）：GPU0 = off 链（s0×2 R-valid → s1）；GPU1 = on 链（s0×2 R-valid → s1）。
# 同臂不跨卡并发（arm 根 tables 共享）。
set -u

REPO=${MONOGS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
PY=${MONOGS_PY:-${CONDA_PREFIX:-}/bin/python}
if [ ! -x "$PY" ]; then
    echo "set MONOGS_PY, or activate the conda env first (CONDA_PREFIX unset)" >&2
    exit 2
fi
ARM_OFF=instr_off_crowd
ARM_ON=instrument_maskstat_on_crowd
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"
export MONOGS_REPO="$REPO" MONOGS_PY="$PY"

log() { echo "[$(date +%H:%M:%S)] $*"; }

n=$(ps -eo cmd | grep -c "[s]lam.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个 slam.py 在跑，本批要求空机"
  exit 1
fi

log "=== MaskStat crowd L2 开始 ==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

(
  export CUDA_VISIBLE_DEVICES=0
  log "[gpu0] off seed0 ×2（R-valid）"
  bash "$RUNNER" "$ARM_OFF" 0 0 2 || { log "[gpu0] off seed0 失败"; exit 1; }
  log "[gpu0] off seed1"
  bash "$RUNNER" "$ARM_OFF" 1 0 1 || { log "[gpu0] off seed1 失败"; exit 1; }
  log "[gpu0] 链完成"
) &
P0=$!

(
  export CUDA_VISIBLE_DEVICES=1
  log "[gpu1] on seed0 ×2（R-valid）"
  bash "$RUNNER" "$ARM_ON" 0 0 2 || { log "[gpu1] on seed0 失败"; exit 1; }
  log "[gpu1] on seed1"
  bash "$RUNNER" "$ARM_ON" 1 0 1 || { log "[gpu1] on seed1 失败"; exit 1; }
  log "[gpu1] 链完成"
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== MaskStat crowd L2 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
