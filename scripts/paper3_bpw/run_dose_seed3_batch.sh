#!/bin/bash
# run_dose_seed3_batch.sh — 剂量过供给批 Amendment A1（第三 seed 补批）派发。
#
# 依据：prereg_dose_oversupply_amendment_a1_seed3_2026-11-08.md（判据先行，本脚本随件入库）。
# 范围：6 臂 × seed 2 = 7 run（仪器口径，全长）；R-valid 锚对 = crowd tau4x s2 ×2。
#   GPU0: crowd tau4x s2 ×2(R-valid) → balloon tau4x s2 → balloon off s2
#   GPU1: crowd off s2 → mnobox tau4x s2 → mnobox off s2
# pt 侧三臂已各 3 seed，不在本批。同臂禁并发（arm 根 tables 共享）。
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

log "=== 剂量过供给 A1 第三 seed 补批 开始 ==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

# G3-C1 同源防线（2026-11-08）：判读 collect() 取"排序后最后一个 rc0 全长 run"，
# 若 seed_2 目录已有历史 run，新 run 失败时会被旧 run 静默顶替。六个臂的 seed_2
# 必须是空的（本批首跑）；发现既有 run 即拒绝派发。
for arm in instrument_dose_tau4x_crowd instr_off_crowd instrument_dose_tau4x_balloon \
           instr_off_balloon instrument_dose_tau4x_moving_nonobstructing_box \
           instr_off_moving_nonobstructing_box; do
  existing=$(ls -d "$REPO"/results/paper3_bpw/"$arm"/datasets_bonn/*/seed_2/*/ 2>/dev/null | grep -c .)
  if [ "$existing" -ne 0 ]; then
    log "ERROR: $arm seed_2 已有 $existing 个 run 目录（预期为空）——判读会被旧 run 污染，拒绝派发"
    exit 1
  fi
done
log "seed_2 预检通过：六臂均无既有 run"

(
  export CUDA_VISIBLE_DEVICES=0
  log "[gpu0] crowd tau4x s2 ×2（R-valid 锚对）"
  bash "$RUNNER" instrument_dose_tau4x_crowd 2 0 2 || { log "[gpu0] crowd tau4x s2 失败"; exit 1; }
  log "[gpu0] balloon tau4x s2"
  bash "$RUNNER" instrument_dose_tau4x_balloon 2 0 1 || { log "[gpu0] balloon tau4x s2 失败"; exit 1; }
  log "[gpu0] balloon off s2"
  bash "$RUNNER" instr_off_balloon 2 0 1 || { log "[gpu0] balloon off s2 失败"; exit 1; }
  log "[gpu0] 链完成"
) &
P0=$!

(
  export CUDA_VISIBLE_DEVICES=1
  log "[gpu1] crowd off s2"
  bash "$RUNNER" instr_off_crowd 2 0 1 || { log "[gpu1] crowd off s2 失败"; exit 1; }
  log "[gpu1] mnobox tau4x s2"
  bash "$RUNNER" instrument_dose_tau4x_moving_nonobstructing_box 2 0 1 || { log "[gpu1] mnobox tau4x s2 失败"; exit 1; }
  log "[gpu1] mnobox off s2"
  bash "$RUNNER" instr_off_moving_nonobstructing_box 2 0 1 || { log "[gpu1] mnobox off s2 失败"; exit 1; }
  log "[gpu1] 链完成"
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== A1 第三 seed 补批 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
