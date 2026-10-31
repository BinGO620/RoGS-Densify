#!/bin/bash
# run_p0_sweep.sh — BPW p0 敏感性扫描（串行，等 GPU 空闲后启动）
#
# 目的：检验「持久性收缩先验是否有害」这一假设。
#   现有 p0=8.0 是拍脑袋的先验锁定值。若 p0→0（即按平均梯度排序）显著更好，
#   说明收缩把该补的点压掉了。
#
# 设计要点：p0=0 时 e_i = accum/denom = 平均梯度，top-k 的选择集本应逐位等于
#   off 的 P0（池放宽到 τ_lo 后仍然如此，因为平均梯度最高的 budget 个点
#   恰好就是 P0）。因此 p0=0 是一条内建的正确性对照线,不是普通扫描点。
#
# 用法：
#   bash scripts/paper3_bpw/run_p0_sweep.sh            # 等 GPU 空闲后跑全部
#   WAIT_GPU=0 bash scripts/paper3_bpw/run_p0_sweep.sh # 立刻跑（确认 GPU 空闲时）
set -u

REPO=/data/monogs-ours
PY=/data/conda_envs/monogs-ours/bin/python
SEQ=person_tracking
WAIT_GPU=${WAIT_GPU:-1}
P0S="0 2 32 128"

cd "$REPO" || exit 1

LOG="$REPO/paper3/results/evidence/p0_sweep_${SEQ}_$(date +%Y%m%d-%H%M%S).log"

# 等 GPU 显存降到阈值以下（默认 1500 MiB），避免与前一个 run 抢显存
if [ "$WAIT_GPU" = "1" ]; then
  echo "=== 等待 GPU 空闲（阈值 1500 MiB）===" | tee "$LOG"
  while :; do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' ')
    if [ "${used:-99999}" -lt 1500 ]; then
      echo "GPU 空闲 (used=${used} MiB)，开始" | tee -a "$LOG"
      break
    fi
    sleep 60
  done
fi

echo "=== BPW p0 扫描 — $SEQ ===" | tee -a "$LOG"
echo "  repo:  $REPO" | tee -a "$LOG"
echo "  HEAD:  $(git rev-parse --short HEAD)  branch=$(git branch --show-current)" | tee -a "$LOG"
echo "  p0 值: $P0S" | tee -a "$LOG"
echo "  log:   $LOG" | tee -a "$LOG"

for p in $P0S; do
  cfg="configs/experiments/paper3_bpw/sweep/bpw_on_pt_p0${p}.yaml"
  if [ "$SEQ" != "person_tracking" ]; then
    cfg="configs/experiments/paper3_bpw/sweep/bpw_on_${SEQ}_p0${p}.yaml"
  fi
  if [ ! -f "$cfg" ]; then
    echo "ERROR: 缺配置 $cfg" >&2
    exit 1
  fi
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] p0=$p ===" | tee -a "$LOG"
  start=$(date +%s)
  "$PY" slam.py --config "$cfg" --eval --seed 0 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] p0=$p done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "=== P0 SWEEP DONE $(date +%Y-%m-%d\ %H:%M:%S) ===" | tee -a "$LOG"
