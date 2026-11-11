#!/bin/bash
# run_maskstat_l1.sh — MaskStat L1：双臂（off 基线 / on 机制）串行跑 person_tracking。
#
# 预注册：paper3/results/evidence/prereg_maskstat_2026-11-04.md；账本 P3-D2-016。
#
# 阶段（顺序是判据的一部分）：
#   smoke   seed0 双臂 40 帧（MAX_FRAMES=40）—— 装置验证，非权威
#   stage1  seed0 双臂全长（580 帧）
#   stage2  seed1 双臂全长
#
# 用法：
#   bash scripts/paper3_bpw/run_maskstat_l1.sh smoke
#   bash scripts/paper3_bpw/run_maskstat_l1.sh stage1
#   bash scripts/paper3_bpw/run_maskstat_l1.sh stage2
#
# **后台派发（唯一许可形态；本脚本前台阻塞，必须这样起）**：
#   setsid env bash /data/monogs-ours/scripts/paper3_bpw/run_maskstat_l1.sh stage1 \
#       >> /data/monogs-ours/paper3/results/evidence/maskstat_l1_stage1_manual.log 2>&1 &
# 起完回读三件：run 目录出现 / console.log 有 iter 行 / maskstat_on 臂 trace 文件出现。
# 判活以工件 mtime + 后台退出通知为准（pgrep 会误命中嵌 "slam.py" 字样的无关进程）。
set -u

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
SEQ=${SEQ:-person_tracking}
SEEDS=${SEEDS:-"0"}
MAX_FRAMES=${MAX_FRAMES:-0}
STAGE=${1:-}
TAG=maskstat

cd "$REPO" || exit 1
mkdir -p "paper3/results/evidence"

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/${TAG}_l1_${SEQ}_${STAGE}_${STAMP}.log"

{
  echo "=== MaskStat L1 $STAGE — $SEQ seeds=[$SEEDS] ==="
  echo "  HEAD: $(git rev-parse --short HEAD)  branch=$(git branch --show-current)"
  echo "  max_frames: $MAX_FRAMES (0 = 全长 580)"
  echo "  log: $LOG"
} | tee "$LOG"

EXTRA=()
[ "$MAX_FRAMES" -gt 0 ] && EXTRA=(--max-frames "$MAX_FRAMES")

run_arm() {  # $1=arm $2=seed
  local arm=$1 seed=$2 start end rc run before after n_new
  local cfg="configs/experiments/paper3_bpw/maskstat_${arm}_${SEQ}.yaml"
  [ -f "$cfg" ] || { echo "ERROR: 缺配置 $cfg" >&2; return 1; }
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] $arm seed=$seed  cfg=$cfg ===" | tee -a "$LOG"
  start=$(date +%s)
  # 定位 run 目录用「跑前记录目录集合、跑后取新增者」（A6 同款，禁 ls -dt 隐式取目录）。
  local base="results/paper3_bpw/maskstat_${arm}_${SEQ}/datasets_bonn/"*/seed_"${seed}"
  before=$(ls -d ${base}/*/ 2>/dev/null | sort)
  "$PY" slam.py --config "$cfg" --eval --seed "$seed" "${EXTRA[@]}" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] $arm seed=$seed done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  after=$(ls -d ${base}/*/ 2>/dev/null | sort)
  n_new=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -c .)
  run=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1)
  if [ "$n_new" -eq 1 ] && [ -n "$run" ]; then
    printf 'arm=%s\nseed=%s\nrc=%s\nelapsed_s=%s\nmax_frames=%s\nlog=%s\nfinished_rc0=%s\n' \
      "$arm" "$seed" "$rc" "$((end-start))" "$MAX_FRAMES" "$LOG" \
      "$([ "$rc" -eq 0 ] && echo yes || echo no)" > "${run}maskstat_${arm}_seed${seed}.done"
    echo "  done 锚点: ${run}maskstat_${arm}_seed${seed}.done" | tee -a "$LOG"
  elif [ "$n_new" -gt 1 ]; then
    echo "ERROR: $arm seed=$seed 产生了 $n_new 个新 run 目录，不写 .done（歧义）" | tee -a "$LOG"
  else
    echo "WARN: $arm seed=$seed 没有新 run 目录，不写 .done —— 请人工核对" | tee -a "$LOG"
  fi
  return $rc
}

case "$STAGE" in
  smoke)
    MAX_FRAMES=40
    EXTRA=(--max-frames 40)
    for s in $SEEDS; do
      run_arm off "$s" || true
      run_arm on  "$s" || true
    done
    ;;
  stage1|stage2)
    for s in $SEEDS; do
      run_arm off "$s" || true
      run_arm on  "$s" || true
    done
    ;;
  *) echo "用法: $0 {smoke|stage1|stage2}" >&2; exit 1 ;;
esac

echo "" | tee -a "$LOG"
echo "=== STAGE $STAGE DONE $(date +'%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG"
