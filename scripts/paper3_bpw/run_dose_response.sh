#!/bin/bash
# run_dose_response.sh — 剂量-响应筛查（P3-D2-018 / prereg_dose_response_2026-11-04）
#
# 四臂 τ_scale ∈ {0.5,1,2,4}；1× 臂复用已有 maskstat_off seed0 全长 run（不重跑），
# 本脚本只跑 0.5× / 2× / 4× 三个 run（串行，本地 2060）。
#
# 用法（后台派发唯一形态）：
#   setsid env bash /data/monogs-ours/scripts/paper3_bpw/run_dose_response.sh \
#       >> /data/monogs-ours/paper3/results/evidence/dose_response_manual.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
PY=${MONOGS_PY:-${CONDA_PREFIX:-}/bin/python}
if [ ! -x "$PY" ]; then
    echo "set MONOGS_PY, or activate the conda env first (CONDA_PREFIX unset)" >&2
    exit 2
fi
SEQ=${SEQ:-person_tracking}
SEED=${SEED:-0}
MAX_FRAMES=${MAX_FRAMES:-0}
STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/dose_response_${SEQ}_${STAMP}.log"

cd "$REPO" || exit 1
EXTRA=()
[ "$MAX_FRAMES" -gt 0 ] && EXTRA=(--max-frames "$MAX_FRAMES")

{
  echo "=== 剂量-响应筛查 — $SEQ seed=$SEED ==="
  echo "  HEAD: $(git rev-parse --short HEAD)  branch=$(git branch --show-current)"
  echo "  max_frames: $MAX_FRAMES (0 = 全长 580)   log: $LOG"
} | tee "$LOG"

run_arm() {  # $1=scale_tag $2=cfg
  local tag=$1 cfg=$2 start end rc base before after n_new run
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] tau${tag}x  cfg=$cfg ===" | tee -a "$LOG"
  start=$(date +%s)
  base="results/paper3_bpw/dose_tau${tag}x_${SEQ}/datasets_bonn/"*/seed_"$SEED"
  before=$(ls -d ${base}/*/ 2>/dev/null | sort)
  "$PY" slam.py --config "$cfg" --eval --seed "$SEED" "${EXTRA[@]}" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] tau${tag}x done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  after=$(ls -d ${base}/*/ 2>/dev/null | sort)
  n_new=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -c .)
  run=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1)
  if [ "$n_new" -eq 1 ] && [ -n "$run" ]; then
    printf 'arm=%s\nseed=%s\nrc=%s\nelapsed_s=%s\nmax_frames=%s\nlog=%s\nfinished_rc0=%s\n' \
      "tau${tag}x" "$SEED" "$rc" "$((end-start))" "$MAX_FRAMES" "$LOG" \
      "$([ "$rc" -eq 0 ] && echo yes || echo no)" > "${run}dose_tau${tag}x_seed${SEED}.done"
    echo "  done 锚点: ${run}dose_tau${tag}x_seed${SEED}.done" | tee -a "$LOG"
  elif [ "$n_new" -gt 1 ]; then
    echo "ERROR: tau${tag}x 产生 $n_new 个新 run 目录，不写 .done（歧义）" | tee -a "$LOG"
  else
    echo "WARN: tau${tag}x 没有新 run 目录，不写 .done" | tee -a "$LOG"
  fi
  return $rc
}

FAILED=()
for s in 0p5 2 4; do
  case "$s" in
    0p5) tag=05 ;;
    *)   tag=$s ;;
  esac
  if ! run_arm "$tag" "configs/experiments/paper3_bpw/dose_tau${tag}x_${SEQ}.yaml"; then
    echo "ERROR: tau${tag}x arm FAILED（见上方 rc）—— 记录后继续其余 arm" | tee -a "$LOG"
    FAILED+=("tau${tag}x")
  fi
done

if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "" | tee -a "$LOG"
  echo "=== DOSE RESPONSE ABORTED: 失败 arm = ${FAILED[*]} ===" | tee -a "$LOG"
  exit 1
fi

echo "" | tee -a "$LOG"
echo "=== DOSE RESPONSE DONE $(date +'%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG"
