#!/bin/bash
# run_cgb_l1.sh — CGB L1：两臂（g1 机制 / g0 等剂量控位对照）串行跑 person_tracking。
#
# 用法：
#   bash scripts/paper3_bpw/run_cgb_l1.sh                 # 全长 580 帧（≈45min+45min/臂）
#   MAX_FRAMES=80 bash scripts/paper3_bpw/run_cgb_l1.sh   # 截断冒烟（先验机制门）
#
# 为什么串行：本地 2060 只有一张卡（6GB），并发会互相抢显存。
# 为什么两臂分开跑而不是复用 off：off 臂已有 run（bpw_off_person_tracking），
#   本脚本不重跑它；判读时用同 seed 的既有 off run 作基线 + 同批 g0 作控位对照。
set -u

REPO=/data/monogs-ours
PY=/data/conda_envs/monogs-ours/bin/python
ARMS="g1 g0"
SEQ=${SEQ:-person_tracking}
MAX_FRAMES=${MAX_FRAMES:-0}
SEED=${SEED:-0}
TAG=${TAG:-cgb}

cd "$REPO" || exit 1

for arm in $ARMS; do
  cfg="configs/experiments/paper3_bpw/cgb_${arm}_${SEQ}.yaml"
  if [ ! -f "$cfg" ]; then
    echo "ERROR: 缺配置 $cfg" >&2
    exit 1
  fi
done

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/${TAG}_l1_${SEQ}_${STAMP}.log"
mkdir -p "$(dirname "$LOG")"

{
  echo "=== CGB L1 — $SEQ ==="
  echo "  repo:       $REPO"
  echo "  HEAD:       $(git rev-parse --short HEAD)  branch=$(git branch --show-current)"
  echo "  arms:       $ARMS  (g1 = 机制 / g0 = 等剂量控位)"
  echo "  max_frames: $MAX_FRAMES (0 = 全长)"
  echo "  seed:       $SEED"
  echo "  log:        $LOG"
} | tee "$LOG"

EXTRA=()
if [ "$MAX_FRAMES" -gt 0 ]; then
  EXTRA=(--max-frames "$MAX_FRAMES")
fi

for arm in $ARMS; do
  cfg="configs/experiments/paper3_bpw/cgb_${arm}_${SEQ}.yaml"
  {
    echo ""
    echo "=== [$(date +%H:%M:%S)] arm=$arm ==="
  } | tee -a "$LOG"
  start=$(date +%s)
  "$PY" slam.py --config "$cfg" --eval --seed "$SEED" "${EXTRA[@]}" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] arm=$arm done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  if [ "$rc" -ne 0 ]; then
    echo "ERROR: arm=$arm 非零退出（rc=$rc）；另一臂继续跑以便对照" | tee -a "$LOG"
  fi
done

echo "" | tee -a "$LOG"
echo "=== ALL ARMS DONE $(date +'%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG"
