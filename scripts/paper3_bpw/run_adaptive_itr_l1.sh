#!/bin/bash
# run_adaptive_itr_l1.sh — E 轴 L1 派发（prereg_adaptive_itr_schedule_2026-11-08 §2
# + amendment A1 / A2）。
#
# 布局（**4 个新 run，单卡串行**）：
#   C 臂 `adaptive_itr_person_tracking` seed0 全长 ×2（第 2 个作 R-valid 锚对）
#   A 臂 `instrument_person_tracking`（fixed itr=150）seed0 全长 ×1
#   B 臂 `itrsweep50_maskstat_off`（fixed itr=50）seed0 全长 ×1
#
# **为什么 A/B 也新跑**（G3 致命B 后的处置，amendment A2 §1）：
# 原计划复用 A=`instrument_maskstat_off` s0 / B=`itrsweep50_maskstat_off` s0。
# 实测 B 臂 `efficiency_raw.csv` 的 `mapping_iterations` 是字面 `N/A`（backend_timing
# 里有 6915）、无 `.done`、console 无 `MonoGS: Done.`（止于 offline eval 中途）
# ⇒ 复用臂 provenance 站不住。四臂同 HEAD 同批 ⇒ 批次等价性由构造保证。
#
# **单卡串行是硬要求**：C 两 run 要做逐位比对（compare_three_way），
# 逐位比对批禁并发（DISCIPLINE「测量口径」#5 同源精神 + 仪器模式定义）。
# 四 run 全排一张卡 ⇒ 无并发污染。
#
# 用法（后台派发唯一形态，**远程必须显式覆盖 REPO/PY**）：
#   setsid env MONOGS_REPO=/home/jiangwenheng/cron/monogs-ours \
#     MONOGS_PY=/home/jiangwenheng/anaconda3/envs/monogs-ours-3090/bin/python \
#     bash scripts/paper3_bpw/run_adaptive_itr_l1.sh <seed> \
#     >> paper3/results/evidence/adaptive_itr_l1_batch_$(date +%Y%m%d).log 2>&1 &
set -u

log() { echo "[$(date +%H:%M:%S)] $*"; }

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
# 派发机器（G3-致命A 整改）：远程路径 = /home/jiangwenheng/cron/monogs-ours +
# anaconda3/envs/monogs-ours-3090/bin/python；默认值指向本地 cb 路径，
# 远程未覆盖时下面的前置检查会 fail-closed 退出（不会静默跑成 fixed-150）。
ARM_C=adaptive_itr_person_tracking
ARM_A=instrument_person_tracking
ARM_B=itrsweep50_maskstat_off
SEED=${1:-0}
RUNNER="$REPO/scripts/paper3_bpw/run_instrument.sh"

# --- 前置 ①：路径与机制代码必须在位（fail-closed，G3-致命A/B）---
if [ ! -d "$REPO" ] || [ ! -f "$RUNNER" ] || [ ! -x "$PY" ]; then
  log "ERROR: 路径不存在 ⇒ REPO=$REPO PY=$PY RUNNER=$RUNNER"
  log "        远程派发必须显式设 MONOGS_REPO / MONOGS_PY（见头注）"
  exit 2
fi
if [ ! -f "$REPO/utils/adaptive_itr.py" ] \
   || [ ! -f "$REPO/configs/experiments/paper3_bpw/${ARM_C}.yaml" ]; then
  log "ERROR: 机制代码或 C 臂配置不在位 ⇒ 远程 HEAD 是旧代码（跑了只会是 fixed-150）"
  log "        HEAD=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
  exit 2
fi
for arm in "$ARM_A" "$ARM_B" "$ARM_C"; do
  [ -f "$REPO/configs/experiments/paper3_bpw/${arm}.yaml" ] || {
    log "ERROR: 缺配置 configs/experiments/paper3_bpw/${arm}.yaml"; exit 2; }
  # 既存产物预检：本批要求新 run 目录（同臂既有全长 run 会被判读器 pin 绕过，
  # 但本批按「同批同 HEAD」语义，发现既有 dir 即停，交给人工确认——沿用 G3-C1 精神）
  if [ -n "$(find "$REPO/results/paper3_bpw/${arm}" -maxdepth 4 -type d -name '20*' 2>/dev/null | head -1)" ]; then
    log "WARN: ${arm} 已有既有 run 目录（本批仍会新建独立时间戳目录，不覆盖）"
  fi
done

export MONOGS_REPO="$REPO" MONOGS_PY="$PY"
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

# --- 前置 ②：机内无并发 slam.py（逐位比对批禁并发）---
n=$(ps -eo cmd | grep -c "[s]lam.py")
if [ "$n" -ne 0 ]; then
  log "ERROR: 已有 $n 个 slam.py 在跑；本批须单卡串行，拒绝启动"
  exit 1
fi

log "=== E 轴 L1 派发 开始 ==="
log "REPO=$REPO"
log "PY=$PY"
log "HEAD=$(git -C "$REPO" rev-parse --short HEAD) branch=$(git -C "$REPO" branch --show-current)"
log "SEED=$SEED  卡 $CUDA_VISIBLE_DEVICES  4 run 全长串行（C×2 → A → B）"
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader

# --- 四 run 串行（任何一环 rc!=0 即停，不带着坏数据往下跑）---
log "[1/4] C 臂 run1（R-valid 锚对之一）"
bash "$RUNNER" "$ARM_C" "$SEED" 0 1 || { log "ERROR: C run1 失败"; exit 1; }
log "[2/4] C 臂 run2（R-valid 锚对之二）"
bash "$RUNNER" "$ARM_C" "$SEED" 0 1 || { log "ERROR: C run2 失败"; exit 1; }
log "[3/4] A 臂（fixed itr=150）"
bash "$RUNNER" "$ARM_A" "$SEED" 0 1 || { log "ERROR: A 臂失败"; exit 1; }
log "[4/4] B 臂（fixed itr=50）"
bash "$RUNNER" "$ARM_B" "$SEED" 0 1 || { log "ERROR: B 臂失败"; exit 1; }

log "=== E 轴 L1 派发 结束: 4 run 全 rc=0 ==="

# --- 实际 pins 落纸（G2 重大-2 整改：不再留占位符）---
# 本批四个 run 是各臂根下最新的时间戳目录（批次内单调递增），
# C 取最新两个（时间升序 = 先锚对读数后锚对），A/B 各取最新一个。
pin() { # $1=arm根  $2=取几个(1或2)
  ls -1 "$REPO/results/paper3_bpw/$1/datasets_bonn/$1/seed_${SEED}" 2>/dev/null \
    | grep '^2026-' | sort | tail -"$2" | tr '\n' ' '
}
C_PINS=$(pin "$ARM_C" 2)
A_PIN=$(pin "$ARM_A" 1)
B_PIN=$(pin "$ARM_B" 1)
log "本批 pins: C=[$C_PINS] A=[$A_PIN] B=[$B_PIN]"

# --- 判读命令落纸（G3-C5 同款；pins 为实测值）---
log ""
log "判读（在派发机执行；pins 为上面方括号内的实测目录名）："
log "  $PY scripts/paper3_bpw/judge_adaptive_itr_l1.py \\"
log "    --a-root results/paper3_bpw/${ARM_A}/datasets_bonn/${ARM_A} --a-run ${A_PIN} \\"
log "    --b-root results/paper3_bpw/${ARM_B}/datasets_bonn/${ARM_B} --b-run ${B_PIN} \\"
log "    --c-root results/paper3_bpw/${ARM_C}/datasets_bonn/${ARM_C} --c-runs ${C_PINS} \\"
log "    --seed ${SEED} --frames 580 \\"
log "    --out paper3/results/evidence/adaptive_itr_l1_judge_$(date +%Y-%m-%d).json"
exit 0
