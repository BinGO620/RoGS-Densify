#!/bin/bash
# run_adaptive_itr_l2.sh — E 轴 L2 三 seed 确认批派发（Amd A3 §1/§4，P3-D2-047 提名）。
#
# 布局（**4 个新 run，单卡串行**）：
#   C 臂 `adaptive_itr_person_tracking` seed1 → seed2（各 1 run）
#   B 臂 `itrsweep50_maskstat_off`      seed1 → seed2（各 1 run）
# （C/B 的 seed0 已在 L1 批产出；A 臂复用 instrument_maskstat_off 三 seed 读数，不跑。）
#
# 判据（Amd A3 §2，锁定先于本批）：四出口 L2_CONFIRMED / L2_CONFIRMED_TRADEOFF /
# L2_DIRECTION_ONLY / L2_SIGN_UNSTABLE（止损）/ L2_INSTRUMENT_INVALID（rc=2）。
#
# 用法（后台派发唯一形态，远程必须显式覆盖 REPO/PY）：
#   setsid env MONOGS_REPO=/home/jiangwenheng/cron/monogs-ours \
#     MONOGS_PY=/home/jiangwenheng/anaconda3/envs/monogs-ours-3090/bin/python \
#     bash scripts/paper3_bpw/run_adaptive_itr_l2.sh \
#     >> paper3/results/evidence/adaptive_itr_l2_batch_20261110.log 2>&1 &
set -u

log() { echo "[$(date +%H:%M:%S)] $*"; }

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
ARM_C=adaptive_itr_person_tracking
ARM_B=itrsweep50_maskstat_off
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"

# --- 前置 fail-closed（G3-致命A 同款三查）---
if [ ! -d "$REPO" ] || [ ! -f "$RUNNER" ] || [ ! -x "$PY" ]; then
  log "ERROR: 路径不存在 ⇒ REPO=$REPO PY=$PY RUNNER=$RUNNER"
  exit 2
fi
for f in utils/adaptive_itr.py \
         configs/experiments/paper3_bpw/${ARM_C}.yaml \
         configs/experiments/paper3_bpw/${ARM_B}.yaml; do
  [ -f "$REPO/$f" ] || { log "ERROR: 缺 $REPO/$f（旧代码/缺配置 ⇒ 跑了也无效）"; exit 2; }
done
n=$(ps -eo cmd | grep -c "[s]lam.py")
[ "$n" -ne 0 ] && { log "ERROR: 已有 $n 个 slam.py 在跑；本批单卡串行，拒绝启动"; exit 1; }

export MONOGS_REPO="$REPO" MONOGS_PY="$PY"
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

log "=== E 轴 L2 三 seed 确认批 开始 ==="
log "REPO=$REPO  PY=$PY"
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD) branch=$(git -C "$REPO" branch --show-current)"
log "4 run 全长串行（C s1 → C s2 → B s1 → B s2）卡 $CUDA_VISIBLE_DEVICES"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

bash "$RUNNER" "$ARM_C" 1 0 1 || { log "ERROR: C s1 失败"; exit 1; }
bash "$RUNNER" "$ARM_C" 2 0 1 || { log "ERROR: C s2 失败"; exit 1; }
bash "$RUNNER" "$ARM_B" 1 0 1 || { log "ERROR: B s1 失败"; exit 1; }
bash "$RUNNER" "$ARM_B" 2 0 1 || { log "ERROR: B s2 失败"; exit 1; }

log "=== E 轴 L2 批 结束: 4 run 全 rc=0 ==="

# --- 实测 pins 落纸（L1 批同款，G2 重大-2 整改口径）---
pin() { ls -1 "$REPO/results/paper3_bpw/$1/datasets_bonn/$1/seed_$2" 2>/dev/null \
          | grep '^2026-' | sort | tail -1; }
log "本批新 run："
log "  C s1 = $(pin "$ARM_C" 1)"
log "  C s2 = $(pin "$ARM_C" 2)"
log "  B s1 = $(pin "$ARM_B" 1)"
log "  B s2 = $(pin "$ARM_B" 2)"
log ""
log "判读（在派发机执行；seed0 pins 固定为 L1 批读数 run）："
log "  $PY scripts/paper3_bpw/judge_adaptive_itr_l2.py \\"
log "    --b-root results/paper3_bpw/${ARM_B}/datasets_bonn/${ARM_B} \\"
log "    --c-root results/paper3_bpw/${ARM_C}/datasets_bonn/${ARM_C} \\"
log "    --seeds 0 1 2 \\"
log "    --b-pin 0=2026-11-09-21-03-01 \\"
log "    --c-pin 0=2026-11-09-19-17-31 \\"
log "    --out paper3/results/evidence/adaptive_itr_l2_judge_$(date +%Y-%m-%d).json"
exit 0
