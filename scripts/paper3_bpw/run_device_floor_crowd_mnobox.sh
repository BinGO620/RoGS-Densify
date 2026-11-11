#!/bin/bash
# run_device_floor_crowd_mnobox.sh — crowd/mnobox 仪器口径自差包络补测（测量口径 #6 扩展）。
#
# 依据：prereg_device_floor_crowd_mnobox_2026-11-08.md（判据先行，本脚本随件入库）。
# 范围：4 run（两序列 off seed_3 ×2，全长；seed_3 取空目录——seed_0/1/2 已被既有判决批消费）；
# 每序列内置 R-valid（run_instrument.sh）。
#   GPU0: crowd off s3 ×2
#   GPU1: mnobox off s3 ×2
# 派发唯一形态（后台，路径用绝对值，命令行禁含 "slam.py" 字面量——PITFALLS 自匹配第三形态）：
#   setsid env MONOGS_REPO=<repo> MONOGS_PY=<py> bash <abs>/run_device_floor_crowd_mnobox.sh >> <abs>/device_floor_cm_batch.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"
export MONOGS_REPO="$REPO" MONOGS_PY="$PY"

log() { echo "[$(date +%H:%M:%S)] $*"; }

n=$(ps -eo cmd | grep -c "[s]lam\.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个相关进程在跑，本批要求空机"
  exit 1
fi

# 包络批预检：seed_0 下不允许已有 run（防 R-valid 比对挑错历史目录）
for arm in instr_off_crowd instr_off_moving_nonobstructing_box; do
  base=$(ls -d "$REPO"/results/paper3_bpw/"$arm"/datasets_bonn/*/seed_3/ 2>/dev/null | head -1)
  if [ -n "$base" ]; then
    existing=$(ls -d "$base"*/ 2>/dev/null | grep -c .)
    if [ "$existing" -ne 0 ]; then
      log "ERROR: $arm seed_3 已有 $existing 个 run——本批要求该臂 seed_3 为空"
      exit 1
    fi
  fi
done

log "=== crowd/mnobox 自差包络补测 开始 ==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

(
  export CUDA_VISIBLE_DEVICES=0
  log "[gpu0] crowd off s3 ×2（R-valid）"
  bash "$RUNNER" instr_off_crowd 3 0 2 || { log "[gpu0] crowd 失败"; exit 1; }
  log "[gpu0] 链完成"
) &
P0=$!

(
  export CUDA_VISIBLE_DEVICES=1
  log "[gpu1] mnobox off s3 ×2（R-valid）"
  bash "$RUNNER" instr_off_moving_nonobstructing_box 3 0 2 || { log "[gpu1] mnobox 失败"; exit 1; }
  log "[gpu1] 链完成"
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== 自差包络批 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
