#!/bin/bash
# run_instrument.sh — 仪器模式 runner（P3-D2-030 / prereg_instrument_mode_2026-11-05）。
#
# 仪器模式 = 单线程（前端+后端）+ det-raster ON + 确定性套件全开。
# 它的唯一职责：让同 config 同 seed 的两次 run **逐位可复现**，
# 从而使臂级 / 逐事件比较有判力（见 detraster_L2_2x2_2026-11-05.md）。
#
# **这不是部署配置**。读数与主线 async 不同源（ATE 1.168 vs 1.177；
# 高斯 19771 vs 25976），必须分开登记、永不混引。
#
# 用法（后台派发唯一形态）：
#   setsid env bash scripts/paper3_bpw/run_instrument.sh <arm> <seed> <max_frames> <n_runs> \
#       >> paper3/results/evidence/instrument_<arm>_<stamp>.log 2>&1 &
#   <arm>       = 配置名（configs/experiments/paper3_bpw/<arm>.yaml 必须存在，
#                 且必须是仪器模式的派生物，见 make_instrument_arm.sh）
#   <max_frames>= 0 表示全长
#   <n_runs>    = run 数（复现性检查用 2；臂级配对 >=3）
set -u

REPO=${MONOGS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
PY=${MONOGS_PY:-${CONDA_PREFIX:-}/bin/python}
if [ ! -x "$PY" ]; then
    echo "set MONOGS_PY, or activate the conda env first (CONDA_PREFIX unset)" >&2
    exit 2
fi
ARM=${1:-}
SEED=${2:-0}
MAXF=${3:-40}
NRUNS=${4:-2}

[ -n "$ARM" ] || { echo "用法: $0 <arm> <seed> <max_frames> <n_runs>" >&2; exit 2; }
CFG="configs/experiments/paper3_bpw/${ARM}.yaml"
[ -f "$REPO/$CFG" ] || { echo "ERROR: 缺配置 $REPO/$CFG" >&2; exit 2; }

# --- 仪器前置（三项，缺一不可；见 configs/experiments/paper3_bpw/instrument_person_tracking.yaml）---
export PYTHONPATH="$REPO/scripts/paper3_bpw/deterministic_probe${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONHASHSEED=0          # 必须在解释器启动前（sitecustomize 里设太早/太晚都无效）
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

cd "$REPO" || exit 1
mkdir -p paper3/results/evidence
STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/instrument_${ARM}_${STAMP}.log"
ARMROOT="results/paper3_bpw/${ARM}"
BASE="$ARMROOT/datasets_bonn/"*"/seed_${SEED}"

{
  echo "=== 仪器模式 $ARM — seed=$SEED max_frames=$MAXF n_runs=$NRUNS — $STAMP ==="
  echo "  HEAD: $(git rev-parse --short HEAD)  branch=$(git branch --show-current)"
  echo "  cfg: $CFG"
  echo "  PYTHONHASHSEED=$PYTHONHASHSEED  CUBLAS_WORKSPACE_CONFIG=$CUBLAS_WORKSPACE_CONFIG"
} | tee "$LOG"

# --- 显存预检（fail-closed）：单线程模式峰值约 4.8 GiB，剩余 < 5.2 GiB 即拒绝 ---
# 设备选取必须跟随 CUDA_VISIBLE_DEVICES：旧实现 `nvidia-smi | head -1` 恒读**物理卡 0**，
# 在 CUDA_VISIBLE_DEVICES=1 时检查的是另一张卡的空闲量 ⇒ 双卡并行派发会失去保护。
if command -v nvidia-smi >/dev/null 2>&1; then
  _dev="${CUDA_VISIBLE_DEVICES%%,*}"     # 只取第一项（本 runner 一进程一卡）
  if [ -n "${_dev:-}" ]; then
    _free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i "$_dev" 2>/dev/null | tr -d ' ')
  else
    _free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
  fi
  if [ -n "${_free_mib:-}" ] && [ "$_free_mib" -lt 5200 ] 2>/dev/null; then
    echo "ERROR: 显存不足（卡 ${_dev:-0} 空闲 ${_free_mib} MiB < 5200 MiB）——仪器模式峰值 ~4.8 GiB，拒绝启动。" \
         "先查 nvidia-smi 有无遗留进程。" | tee -a "$LOG"
    exit 4
  fi
  echo "  gpu free: ${_free_mib} MiB (device ${_dev:-0})" | tee -a "$LOG"
fi

# --- 自检（fail-closed）：任何一项不满足即停，不得带病跑 ---
if ! "$PY" -c "
import os, sys, torch
assert os.environ.get('PYTHONHASHSEED') == '0', 'PYTHONHASHSEED not fixed before start'
assert torch.are_deterministic_algorithms_enabled(), 'deterministic algorithms NOT active'
sys.path.insert(0, '.')
# 必须读**解析后的**配置（派生文件只有 inherit_from，裸 yaml.safe_load 看不到继承键）
from utils.config_utils import load_config
c = load_config('$CFG')
assert c['Training']['single_thread'] is True, 'Training.single_thread must be true'
assert c['Dataset'].get('single_thread') is True, 'Dataset.single_thread must be true'
assert c['Rasterizer']['deterministic_backward'] is True, \
    'Rasterizer.deterministic_backward must be true'
" 2>"$LOG.selfcheck"; then
  echo "ERROR: 仪器前置不满足（fail-closed）——" | tee -a "$LOG"
  grep -v "^\[detprobe\]" "$LOG.selfcheck" | tail -5 | tee -a "$LOG"
  exit 3
fi
echo "  selfcheck: hashseed + det-algorithms + both single_thread keys + det_backward ✔" | tee -a "$LOG"
rm -f "$LOG.selfcheck"

run_one() {  # $1 = run 序号
  local idx=$1 start end rc before after n_new run
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] run$idx ===" | tee -a "$LOG"
  start=$(date +%s)
  before=$(ls -d ${BASE}/*/ 2>/dev/null | sort)
  if [ "$MAXF" -gt 0 ]; then
    "$PY" slam.py --config "$CFG" --eval --seed "$SEED" --max-frames "$MAXF" 2>&1 | tee -a "$LOG"
  else
    "$PY" slam.py --config "$CFG" --eval --seed "$SEED" 2>&1 | tee -a "$LOG"
  fi
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] run$idx done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  after=$(ls -d ${BASE}/*/ 2>/dev/null | sort)
  n_new=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -c .)
  run=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1)
  if [ "$n_new" -eq 1 ] && [ -n "$run" ]; then
    # finished_rc0 是项目 .done 的既有字段（run_maskstat_l1.sh / run_fdose_l1.sh 同款）。
    # 本轮 OOM 暴露了它的必要性：on/seed0 在 KF430 因显存耗尽退出（rc=1），
    # 却照样写了 .done，判读器只能靠帧数猜它没跑完。帧数闸对
    # 「跑到一半但 per_frame_ape.csv 恰好非空」的情形不够用，故显式落 rc 语义。
    printf 'arm=%s\nstage=instrument\nrun=%s\nseed=%s\nrc=%s\nelapsed_s=%s\nmax_frames=%s\nhashseed=%s\ncublas=%s\nhead=%s\ndeterministic=on\nsingle_thread=on\ndet_backward=on\nfinished_rc0=%s\n' \
      "$ARM" "$idx" "$SEED" "$rc" "$((end-start))" "$MAXF" \
      "$PYTHONHASHSEED" "$CUBLAS_WORKSPACE_CONFIG" "$(git rev-parse --short HEAD)" \
      "$([ "$rc" -eq 0 ] && echo yes || echo no)" \
      > "${run}instrument_run${idx}_seed${SEED}.done"
    echo "  done 锚点: ${run}instrument_run${idx}_seed${SEED}.done" | tee -a "$LOG"
    eval "INSTR_RUN${idx}=\"\$run\""
    return $rc
  fi
  echo "ERROR: run$idx 产生 $n_new 个新 run 目录，不写 .done（歧义）" | tee -a "$LOG"
  return 1
}

for i in $(seq 1 "$NRUNS"); do
  run_one "$i" || { echo "=== INSTRUMENT RUN FAIL @ run$i (rc!=0) ===" | tee -a "$LOG"; exit 1; }
done

# --- 复现性比对（n_runs >= 2 时）---
if [ "$NRUNS" -ge 2 ]; then
  # 必须用本次两 run 的实际目录（run_one 里由 before/after 差集捕获）。
  # 曾用 `ls -dt | head -1 / tail -1`，结果比的是**全部历史目录**的最早与最新，
  # 于是把上一会话留下的旧 run 当成本次 run1，产生 R2_divergent 假阳性。
  R1="${INSTR_RUN1}"
  R2="${INSTR_RUN2}"
  if [ -z "$R1" ] || [ -z "$R2" ]; then
    echo "ERROR: 未捕获到本次两 run 的目录（INSTR_RUN1='$R1' INSTR_RUN2='$R2'）" | tee -a "$LOG"
    exit 5
  fi
  echo "" | tee -a "$LOG"
  echo "=== 逐位比对（易变列剔除口径）: $(basename $R1) vs $(basename $R2) ===" | tee -a "$LOG"
  "$PY" scripts/paper3_bpw/deterministic_probe/compare_three_way.py \
      --base "$(dirname "$R1")" --samples "$(basename "$R1")" "$(basename "$R2")" 2>&1 | tee -a "$LOG"
  V=$(grep -o 'R1_bitwise_identical\|R2_divergent' "$LOG" | tail -1)
  if [ "$V" = "R1_bitwise_identical" ]; then
    echo "=== INSTRUMENT OK: 逐位一致 ⇒ 该臂可用于臂级判读 ===" | tee -a "$LOG"
  else
    # **fail-closed（2026-11-06 G3 审查 M6）**：旧版这里只打印措辞、末尾恒 exit 0
    # ⇒ R2_divergent 时批次仍报成功，仪器坏了却无人察觉。现在非零退出。
    echo "=== INSTRUMENT BROKEN: 仍分叉 ⇒ 不得用于臂级判读（查 single_thread/det 是否真生效）===" | tee -a "$LOG"
    exit 6
  fi
fi
exit 0
