#!/bin/bash
# run_three_arms.sh — Phase 0 三臂跑（串行，任意序列）
#
# 用法：
#   bash scripts/paper3_bpw/run_three_arms.sh balloon              # 全长 439 帧
#   bash scripts/paper3_bpw/run_three_arms.sh person_tracking      # 全长 582 帧
#   MAX_FRAMES=80 bash scripts/paper3_bpw/run_three_arms.sh balloon   # 截断冒烟
#
# 注意：串行。本地 2060 只有一张卡，并发会互相抢显存。
# 配置须已存在：configs/experiments/paper3_bpw/bpw_{arm}_{SEQ}.yaml
set -u

REPO=/data/monogs-ours
PY=/data/conda_envs/monogs-ours/bin/python
ARMS="off on negctl"
SEQ=${1:?"用法: run_three_arms.sh <sequence>  例如 balloon / person_tracking"}
MAX_FRAMES=${MAX_FRAMES:-0}
SEED=${SEED:-0}

cd "$REPO" || exit 1

for arm in $ARMS; do
  cfg="configs/experiments/paper3_bpw/bpw_${arm}_${SEQ}.yaml"
  if [ ! -f "$cfg" ]; then
    echo "ERROR: 缺配置 $cfg" >&2
    exit 1
  fi
done

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/three_arms_${SEQ}_${STAMP}.log"
mkdir -p "$(dirname "$LOG")"

echo "=== Phase 0 三臂跑 — $SEQ ===" | tee "$LOG"
echo "  repo:       $REPO" | tee -a "$LOG"
echo "  HEAD:       $(git rev-parse --short HEAD)  branch=$(git branch --show-current)" | tee -a "$LOG"
echo "  arms:       $ARMS" | tee -a "$LOG"
echo "  max_frames: $MAX_FRAMES (0 = 全长)" | tee -a "$LOG"
echo "  seed:       $SEED" | tee -a "$LOG"
echo "  log:        $LOG" | tee -a "$LOG"

EXTRA=()
if [ "$MAX_FRAMES" -gt 0 ]; then
  EXTRA=(--max-frames "$MAX_FRAMES")
fi

for arm in $ARMS; do
  cfg="configs/experiments/paper3_bpw/bpw_${arm}_${SEQ}.yaml"
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] arm=$arm ===" | tee -a "$LOG"
  start=$(date +%s)
  "$PY" slam.py --config "$cfg" --eval --seed "$SEED" "${EXTRA[@]}" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] arm=$arm done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  if [ "$rc" -ne 0 ]; then
    echo "ERROR: arm=$arm 非零退出（rc=$rc），后续臂继续跑以便对照" | tee -a "$LOG"
  fi
done

echo "" | tee -a "$LOG"
echo "=== ALL ARMS DONE $(date +%Y-%m-%d\ %H:%M:%S) ===" | tee -a "$LOG"
