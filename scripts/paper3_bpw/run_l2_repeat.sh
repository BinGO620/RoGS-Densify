#!/bin/bash
# run_l2_repeat.sh — 同 config 同 seed 重复跑（L2 确定性门 / 逐事件 k 的噪声地板）
#
# 为什么需要这一支：
#   三臂全长跑显示「首事件之后 on 与 negctl 的 budget 逐事件分叉」。两种可能：
#     (a) 机制内生量（两臂地图不同 ⇒ 梯度统计不同 ⇒ k 必然分叉，见 spec §5.3）；
#     (b) 同一臂重复跑本身就不逐位可复现（GPU 非确定性 / 调度差异）。
#   二者对 P0-A′ 的处置完全不同：(a) 说明「逐事件 k 相等」结构性不可达；
#   (b) 说明连「同臂可复现」都没有，任何逐事件判据都不能用。
#   判别手段 = 同 config 同 seed 跑两次，比较 k 序列（DISCIPLINE「测量口径」先量地板）。
#
# 用法：
#   bash scripts/paper3_bpw/run_l2_repeat.sh [MAX_FRAMES]
#   默认 MAX_FRAMES=120（够覆盖 12 个 densify 事件，单 run 约 4–5 分钟）
#
# 注意：串行；两次 run 的 config 除保存目录时间戳外逐字节相同。
set -u

REPO=/data/monogs-ours
PY=/data/conda_envs/monogs-ours/bin/python
CFG=${CFG:-configs/experiments/paper3_bpw/bpw_on_balloon.yaml}
MAX_FRAMES=${1:-120}

cd "$REPO" || exit 1

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/l2_repeat_${STAMP}.log"
mkdir -p "$(dirname "$LOG")"

echo "=== L2 重复跑（同 config 同 seed）===" | tee "$LOG"
echo "  config:     $CFG" | tee -a "$LOG"
echo "  HEAD:       $(git rev-parse --short HEAD)  branch=$(git branch --show-current)" | tee -a "$LOG"
echo "  max_frames: $MAX_FRAMES" | tee -a "$LOG"
echo "  log:        $LOG" | tee -a "$LOG"

for i in 1 2; do
  echo "" | tee -a "$LOG"
  echo "=== [$i/2][$(date +%H:%M:%S)] repeat ===" | tee -a "$LOG"
  start=$(date +%s)
  "$PY" slam.py --config "$CFG" --eval --seed 0 --max-frames "$MAX_FRAMES" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$i/2][$(date +%H:%M:%S)] done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "=== L2 REPEAT DONE $(date +%Y-%m-%d\ %H:%M:%S) ===" | tee -a "$LOG"
