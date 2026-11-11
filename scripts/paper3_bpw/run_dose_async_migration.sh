#!/bin/bash
# run_dose_async_migration.sh — 剂量前沿 async 迁移检查派发（P3-D2-043）。
#
# 依据：prereg_dose_async_migration_2026-11-08.md（判据先行，本脚本随件入库）。
# 口径 = **async 部署口径**（无仪器开关、无确定性套件环境）——与仪器口径永不混引。
# 范围：17 run 全长（pt 3 臂 × 3 seeds = 9；crowd/mnobox 2 臂 × 2 seeds = 8）。
#   GPU0: pt off s0,s1,s2 → tau4x s0,s1,s2 → zero s0,s1,s2
#   GPU1: crowd off s0,s1 → crowd tau4x s0,s1 → mnobox off s0,s1 → mnobox tau4x s0,s1
# 同臂禁并发。派发唯一形态（后台）：
#   setsid env bash scripts/paper3_bpw/run_dose_async_migration.sh \
#       >> paper3/results/evidence/dose_async_migration_batch.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
export MONOGS_REPO="$REPO" MONOGS_PY="$PY"

log() { echo "[$(date +%H:%M:%S)] $*"; }

n=$(ps -eo cmd | grep -c "[s]lam.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个 slam.py 在跑，本批要求空机"
  exit 1
fi

log "=== 剂量前沿 async 迁移批 开始（async 部署口径）==="
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD)"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

run_one() {  # $1=arm $2=seed $3=gpu_tag
  local arm=$1 seed=$2 tag=$3 start end rc before after n_new run
  local cfg="configs/experiments/paper3_bpw/${arm}.yaml"
  [ -f "$REPO/$cfg" ] || { log "[$tag] ERROR: 缺配置 $cfg"; return 1; }
  # per-run 显存预检（G3 次要整改：与 run_instrument.sh 同防线，async 峰值较低取 4000MiB 线）
  if command -v nvidia-smi >/dev/null 2>&1; then
    local _free_mib
    _free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits \
                -i "${CUDA_VISIBLE_DEVICES%%,*}" 2>/dev/null | tr -d ' ')
    if [ -n "${_free_mib:-}" ] && [ "$_free_mib" -lt 4000 ] 2>/dev/null; then
      log "[$tag] ERROR: 显存不足（卡 ${CUDA_VISIBLE_DEVICES%%,*} 空闲 ${_free_mib} MiB < 4000 MiB），拒绝启动"
      return 4
    fi
  fi
  echo "" | tee -a "$BATCH_LOG"
  log "[$tag] $arm seed=$seed 开始"
  start=$(date +%s)
  before=$(ls -d "$REPO"/results/paper3_bpw/"$arm"/datasets_bonn/*/seed_"$seed"/*/ 2>/dev/null | sort)
  (
    cd "$REPO" && "$PY" slam.py --config "$cfg" --eval --seed "$seed"
  ) >>"$BATCH_LOG" 2>&1
  rc=$?
  end=$(date +%s)
  log "[$tag] $arm seed=$seed done rc=$rc elapsed=$((end-start))s"
  after=$(ls -d "$REPO"/results/paper3_bpw/"$arm"/datasets_bonn/*/seed_"$seed"/*/ 2>/dev/null | sort)
  n_new=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -c .)
  run=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1)
  if [ "$n_new" -eq 1 ] && [ -n "$run" ]; then
    # 锚点字段与 run_instrument.sh 同款（finished_rc0 语义），口径标记 = async。
    printf 'arm=%s\nstage=async\nrun=%s\nseed=%s\nrc=%s\nelapsed_s=%s\nmax_frames=0\nhead=%s\ncaliber=async_deploy\nfinished_rc0=%s\n' \
      "$arm" "$(basename "$run")" "$seed" "$rc" "$((end-start))" \
      "$(git -C "$REPO" rev-parse --short HEAD)" \
      "$([ "$rc" -eq 0 ] && echo yes || echo no)" \
      > "${run}async_run_seed${seed}.done"
    return $rc
  fi
  log "[$tag] ERROR: $arm seed=$seed 产生 $n_new 个新 run 目录，不写 .done（歧义）"
  return 1
}

BATCH_LOG="$REPO/paper3/results/evidence/dose_async_migration_batch.log"

(
  export CUDA_VISIBLE_DEVICES=0
  for arm in maskstat_off_person_tracking dose_tau4x_person_tracking dose_zero_person_tracking; do
    for s in 0 1 2; do
      run_one "$arm" "$s" gpu0 || { log "[gpu0] $arm s$s 失败"; exit 1; }
    done
  done
  log "[gpu0] 链完成"
) &
P0=$!

(
  export CUDA_VISIBLE_DEVICES=1
  for arm in async_off_crowd dose_tau4x_crowd async_off_moving_nonobstructing_box dose_tau4x_moving_nonobstructing_box; do
    for s in 0 1; do
      run_one "$arm" "$s" gpu1 || { log "[gpu1] $arm s$s 失败"; exit 1; }
    done
  done
  log "[gpu1] 链完成"
) &
P1=$!

wait "$P0"; RC0=$?
wait "$P1"; RC1=$?
log "=== async 迁移批 结束: gpu0 rc=$RC0  gpu1 rc=$RC1 ==="
[ "$RC0" -eq 0 ] && [ "$RC1" -eq 0 ] || exit 1
