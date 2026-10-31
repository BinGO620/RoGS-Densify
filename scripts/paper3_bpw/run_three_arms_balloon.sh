#!/bin/bash
# run_three_arms_balloon.sh — Phase 0 三臂全长跑（串行）
#
# 用途：随机流对齐（rng_sequence pin "balloon"）之后，跑 off / on / negctl
# 全长 439 帧，验证首事件 k 相等在长跑中保持，并产出逐事件 k 序列供
# P0-A′ 判定（paper3/PREREGISTRATION.md §3.1）。
#
# 用法：
#   bash scripts/paper3_bpw/run_three_arms_balloon.sh            # 全长
#   MAX_FRAMES=80 bash scripts/paper3_bpw/run_three_arms_balloon.sh   # 截断冒烟
#
# 注意：串行。本地 2060 只有一张卡，并发会互相抢显存。
set -u

REPO=/data/monogs-ours
PY=/data/conda_envs/monogs-ours/bin/python
ARMS="off on negctl"
MAX_FRAMES=${MAX_FRAMES:-0}

cd "$REPO" || exit 1

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/three_arms_balloon_${STAMP}.log"
mkdir -p "$(dirname "$LOG")"

echo "=== Phase 0 三臂全长跑 ===" | tee "$LOG"
echo "  repo:       $REPO" | tee -a "$LOG"
echo "  HEAD:       $(git rev-parse --short HEAD)  branch=$(git branch --show-current)" | tee -a "$LOG"
echo "  arms:       $ARMS" | tee -a "$LOG"
echo "  max_frames: $MAX_FRAMES (0 = 全长)" | tee -a "$LOG"
echo "  log:        $LOG" | tee -a "$LOG"

EXTRA=()
if [ "$MAX_FRAMES" -gt 0 ]; then
  EXTRA=(--max-frames "$MAX_FRAMES")
fi

for arm in $ARMS; do
  cfg="configs/experiments/paper3_bpw/bpw_${arm}_balloon.yaml"
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] arm=$arm ===" | tee -a "$LOG"
  start=$(date +%s)
  "$PY" slam.py --config "$cfg" --eval --seed 0 "${EXTRA[@]}" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] arm=$arm done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  if [ "$rc" -ne 0 ]; then
    echo "ERROR: arm=$arm 非零退出（rc=$rc），后续臂继续跑以便对照" | tee -a "$LOG"
  fi
done

echo "" | tee -a "$LOG"
echo "=== ALL ARMS DONE $(date +%Y-%m-%d\ %H:%M:%S) ===" | tee -a "$LOG"
