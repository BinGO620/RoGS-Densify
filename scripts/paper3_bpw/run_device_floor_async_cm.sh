#!/bin/bash
# run_device_floor_async_cm.sh — crowd/mnobox **async 口径**自差包络补测（P 批 amendment）。
#
# 依据：prereg_device_floor_async_cm_2026-11-09.md（判据先行）。
# 范围：4 run（两序列 off seed_2 ×2，全长，async 部署口径——直接 slam.py，无仪器环境）。
#   GPU0: crowd off s2 ×2
#   GPU1: mnobox off s2 ×2
# 派发唯一形态（后台，绝对路径，命令行禁含目标进程名字面量——PITFALLS 自匹配第三形态）。
set -u

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
export MONOGS_REPO="$REPO" MONOGS_PY="$PY"
BATCH_LOG="$REPO/paper3/results/evidence/device_floor_async_cm_batch_20261109.log"

log() { echo "[$(date +%H:%M:%S)] $*"; }

n=$(ps -eo cmd | grep -c "[s]lam\.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个相关进程在跑，本批要求空机"
  exit 1
fi

# 预检：两臂 seed_2 必须为空（G3-C1 同源防线——判读 collect 不被旧 run 顶替）
for arm in async_off_crowd async_off_moving_nonobstructing_box; do
  existing=$(ls -d "$REPO"/results/paper3_bpw/"$arm"/datasets_bonn/*/seed_2/*/ 2>/dev/null | grep -c .)
  if [ "$existing" -ne 0 ]; then
    log "ERROR: $arm seed_2 已有 $existing 个 run——本批要求为空"
    exit 1
  fi
done

log "=== async 口径 crowd/mnobox 自差包络补测 开始 ==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

run_one() {  # $1=arm $2=seed $3=tag
  local arm=$1 seed=$2 tag=$3 start end rc before after n_new run
  local cfg="configs/experiments/paper3_bpw/${arm}.yaml"
  [ -f "$REPO/$cfg" ] || { log "[$tag] ERROR: 缺配置 $cfg"; return 1; }
  if command -v nvidia-smi >/dev/null 2>&1; then
    local _free_mib
    _free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits \
                -i "${CUDA_VISIBLE_DEVICES%%,*}" 2>/dev/null | tr -d ' ')
    if [ -n "${_free_mib:-}" ] && [ "$_free_mib" -lt 4000 ] 2>/dev/null; then
      log "[$tag] ERROR: 显存不足（空闲 ${_free_mib} MiB < 4000 MiB）"
      return 4
    fi
  fi
  echo "" | tee -a "$BATCH_LOG"
  log "[$tag] $arm seed=$seed 开始"
  start=$(date +%s)
  before=$(ls -d "$REPO"/results/paper3_bpw/"$arm"/datasets_bonn/*/seed_"$seed"/*/ 2>/dev/null | sort)
  ( cd "$REPO" && "$PY" slam.py --config "$cfg" --eval --seed "$seed" ) >>"$BATCH_LOG" 2>&1
  rc=$?
  end=$(date +%s)
  log "[$tag] $arm seed=$seed done rc=$rc elapsed=$((end-start))s"
  after=$(ls -d "$REPO"/results/paper3_bpw/"$arm"/datasets_bonn/*/seed_"$seed"/*/ 2>/dev/null | sort)
  n_new=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -c .)
  run=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1)
  if [ "$n_new" -eq 1 ] && [ -n "$run" ]; then
    printf 'arm=%s\nstage=async\nrun=%s\nseed=%s\nrc=%s\nelapsed_s=%s\nmax_frames=0\nhead=%s\ncaliber=async_deploy\nfinished_rc0=%s\n' \
      "$arm" "$(basename "$run")" "$seed" "$rc" "$((end-start))" \
      "$(git -C "$REPO" rev-parse --short HEAD)" \
      "$([ "$rc" -eq 0 ] && echo yes || echo no)" \
      > "${run}async_floor_seed${seed}.done"
    return $rc
  fi
  log "[$tag] ERROR: 新 run 目录数 $n_new ≠ 1，不写 .done（歧义）"
  return 1
}

(
  export CUDA_VISIBLE_DEVICES=0
  for i in 1 2; do run_one async_off_crowd 2 gpu0 || { log "[gpu0] crowd 失败"; exit 1; }; done
  log "[gpu0] 链完成"
) &
P0=$!

(
  export CUDA_VISIBLE_DEVICES=1
  for i in 1 2; do run_one async_off_moving_nonobstructing_box 2 gpu1 || { log "[gpu1] mnobox 失败"; exit 1; }; done
  log "[gpu1] 链完成"
) &
P1=$!
wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== async 自差包络批 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
