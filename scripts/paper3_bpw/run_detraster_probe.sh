#!/bin/bash
# run_detraster_probe.sh — det-raster L1 探针（P3-D2-027 / prereg_det_raster_2026-11-05）。
#
# 臂 = detraster_on_person_tracking.yaml（maskstat_off 同链 + Rasterizer.deterministic_backward=true）。
# 两 run 同 config 同 seed，比对目标：若 det-raster 生效则逐位一致。
#
# 阶段：
#   smoke  seed0 40 帧 × 1 run —— 防 config/kernel 边界崩（R-crash）
#   full   seed0 40 帧 × 2 run 单卡串行 + compare_three_way.py 逐位比对
#
# 判读映射：R1_bitwise_identical ⇒ R-feasible（进 L2）；R2_divergent ⇒ R-infeasible。
#
# 用法（后台派发唯一形态）：
#   setsid env bash scripts/paper3_bpw/run_divsrc_bisect.sh smoke \
#       >> paper3/results/evidence/divsrc_manual.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
PY=${MONOGS_PY:-${CONDA_PREFIX:-}/bin/python}
if [ ! -x "$PY" ]; then
    echo "set MONOGS_PY, or activate the conda env first (CONDA_PREFIX unset)" >&2
    exit 2
fi
SEQ=${SEQ:-person_tracking}
SEED=${SEED:-0}
STAGE=${1:-}
CFG="configs/experiments/paper3_bpw/detraster_on_person_tracking.yaml"
ARMROOT="results/paper3_bpw/detraster_on_${SEQ}"
TAG=detraster

[ -n "$STAGE" ] || { echo "用法: $0 smoke|full" >&2; exit 2; }
[ -f "$REPO/$CFG" ] || { echo "ERROR: 缺配置 $REPO/$CFG" >&2; exit 2; }

# --- 确定性注入（prereg §1；与 run_device_gate_probe.sh 同仪器） ---
export PYTHONPATH="$REPO/scripts/paper3_bpw/deterministic_probe${PYTHONPATH:+:$PYTHONPATH}"
export CUBLAS_WORKSPACE_CONFIG=:4096:8
# 设备无关分叉源：str hash 随机化 ⇒ set/dict 迭代顺序随进程变。
# 必须在解释器启动前固定（sitecustomize 里赋值太晚）。
export PYTHONHASHSEED=0
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

cd "$REPO" || exit 1
mkdir -p "paper3/results/evidence"
STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/${TAG}_${STAGE}_${STAMP}.log"

{
  echo "=== 确定性栅格探针 40 帧×2 $STAGE — $SEQ seed=$SEED ==="
  echo "  HEAD: $(git rev-parse --short HEAD)  branch=$(git branch --show-current)"
  echo "  cfg: $CFG   CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
  echo "  CUBLAS_WORKSPACE_CONFIG=$CUBLAS_WORKSPACE_CONFIG"
} | tee "$LOG"

# 自检（fail-closed）：确定性标志 + hash 种子都必须已生效，否则探针无判力。
# 注：sitecustomize 里 raise 会被 CPython 吞掉（仅打印一行），故闸门必须在此显式断言。
if ! "$PY" -c "
import os, sys, torch
assert os.environ.get('PYTHONHASHSEED') == '0', f'PYTHONHASHSEED={os.environ.get(\"PYTHONHASHSEED\")!r} (须在解释器启动前固定为 0)'
assert torch.are_deterministic_algorithms_enabled(), 'deterministic algorithms NOT active'
import random
assert random.getstate() is not None
" 2>"$LOG.selfcheck"; then
  echo "ERROR: 探针前置条件未满足（fail-closed）—— $(cat "$LOG.selfcheck")" | tee -a "$LOG"
  exit 3
fi
echo "  selfcheck: deterministic flags + PYTHONHASHSEED=0 active ✔" | tee -a "$LOG"
rm -f "$LOG.selfcheck"

run_one() {  # $1 = run 序号  $2 = max_frames（0=全长）
  local idx=$1 mf=$2 start end rc base before after n_new run
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] run$idx  cfg=$CFG  seed=$SEED  max_frames=$mf ===" | tee -a "$LOG"
  start=$(date +%s)
  base="$ARMROOT/datasets_bonn/"*/seed_"$SEED"
  before=$(ls -d ${base}/*/ 2>/dev/null | sort)
  # MAX_FRAMES 显式传参（PITFALLS P40：禁 ${VAR:-} 二次默认）
  if [ "$mf" -gt 0 ]; then
    "$PY" slam.py --config "$CFG" --eval --seed "$SEED" --max-frames "$mf" 2>&1 | tee -a "$LOG"
  else
    "$PY" slam.py --config "$CFG" --eval --seed "$SEED" 2>&1 | tee -a "$LOG"
  fi
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] run$idx done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  after=$(ls -d ${base}/*/ 2>/dev/null | sort)
  n_new=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -c .)
  run=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1)
  if [ "$n_new" -eq 1 ] && [ -n "$run" ]; then
    for t in efficiency_raw mapping_raw; do
      if [ -f "$ARMROOT/tables/${t}.csv" ]; then
        tail -1 "$ARMROOT/tables/${t}.csv" > "${run}detprobe_${t}_lastrow.txt"
      else
        echo "MISSING" > "${run}detprobe_${t}_lastrow.txt"
      fi
    done
    printf 'stage=%s\nrun=%s\nseed=%s\nrc=%s\nelapsed_s=%s\nmax_frames=%s\ncublas=%s\nhead=%s\ndeterministic=on\narm=detraster_on\n' \
      "$STAGE" "$idx" "$SEED" "$rc" "$((end-start))" "$mf" \
      "$CUBLAS_WORKSPACE_CONFIG" "$(git rev-parse --short HEAD)" > "${run}${TAG}_run${idx}_seed${SEED}.done"
    echo "  done 锚点: ${run}${TAG}_run${idx}_seed${SEED}.done" | tee -a "$LOG"
    eval "DET_RASTER_RUN${idx}=\"\$run\""
    return $rc
  fi
  echo "ERROR: run$idx 产生 $n_new 个新 run 目录，不写 .done（歧义）" | tee -a "$LOG"
  return 1
}

if [ "$STAGE" = "smoke" ]; then
  if run_one 1 40; then
    echo "=== DET-RASTER PROBE OK — 决策关停臂 40 帧无崩；可放全长 ===" | tee -a "$LOG"
    exit 0
  fi
  echo "=== DET-RASTER PROBE FAIL — config 边界崩，按 prereg §2 R-crash 处置 ===" | tee -a "$LOG"
  exit 1
fi

if [ "$STAGE" = "full" ]; then
  run_one 1 40 || { echo "=== DET-RASTER PROBE FAIL @ run1（R-crash 出口，停）===" | tee -a "$LOG"; exit 1; }
  run_one 2 40 || { echo "=== DET-RASTER PROBE FAIL @ run2（R-crash 出口，停）===" | tee -a "$LOG"; exit 1; }
  R1="$DET_RASTER_RUN1"; R2="$DET_RASTER_RUN2"
  echo "" | tee -a "$LOG"
  echo "=== 逐位比对（compare_three_way.py；比对集同 prereg B3 口径）===" | tee -a "$LOG"
  "$PY" scripts/paper3_bpw/deterministic_probe/compare_three_way.py \
      --base "$(dirname "$R1")" --samples "$(basename "$R1")" "$(basename "$R2")" \
      --out-dir "$(dirname "$R1")" 2>&1 | tee -a "$LOG"
  VERDICT=$(grep -o 'R1_bitwise_identical\|R2_divergent' "$LOG" | tail -1)
  if [ "$VERDICT" = "R1_bitwise_identical" ]; then
    echo "=== DET-RASTER PROBE R-feasible: det-ON 两 run 逐位一致 ⇒ 定点化 backward 消除分叉，进 L2 ===" | tee -a "$LOG"
  elif [ "$VERDICT" = "R2_divergent" ]; then
    echo "=== DET-RASTER PROBE R-infeasible: det-ON 两 run 仍分叉 ⇒ 除 rasterizer backward 之外尚有至少一个分叉源（按 prereg §2 停损，待定位后再定 L2 去留）===" | tee -a "$LOG"
  else
    echo "=== DET-RASTER PROBE: 判读行缺失（比对异常），人工复核 ===" | tee -a "$LOG"
    exit 1
  fi
  exit 0
fi

echo "用法: $0 smoke|full" >&2
exit 2
