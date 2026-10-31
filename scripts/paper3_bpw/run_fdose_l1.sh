#!/bin/bash
# run_fdose_l1.sh — FDose L1：三臂（k0 计划源 / G 控位 / S 机制）串行跑 person_tracking。
#
# 预注册：paper3/results/evidence/prereg_fdose_2026-10-31.md
#
# 三段式（顺序是判据的一部分，不得调换）：
#   stage1  s0,s1,s2 的 k0（自计划）—— 计划源
#   freeze  从每个 seed 的 k0 trace 冻结 dose_plan（sha256 入库，N_plan 截断）
#   stage2  s0,s1,s2 的 G 与 S，消费**各自 seed** 的冻结计划
#
# 为什么按 seed 各冻结一份：计划是「这一条随机轨迹上该注入多少」的外生固定值；
# 跨 seed 复用会把 seed 效应混进剂量（prereg §2）。
#
# 用法：
#   bash scripts/paper3_bpw/run_fdose_l1.sh stage1
#   bash scripts/paper3_bpw/run_fdose_l1.sh freeze
#   bash scripts/paper3_bpw/run_fdose_l1.sh stage2
#   MAX_FRAMES=40 bash scripts/paper3_bpw/run_fdose_l1.sh stage1   # 冒烟
#
# **后台派发（唯一许可形态；本脚本前台阻塞，必须这样起）**：
#   setsid env SEEDS="0" bash /data/monogs-ours/scripts/paper3_bpw/run_fdose_l1.sh stage1 \
#       >> /data/monogs-ours/paper3/results/evidence/fdose_l1_stage1_manual.log 2>&1 &
# 起完必须回读确认真的起来了（三个工件都要看）：
#   pgrep -af "[s]lam.py"                     # 进程在
#   ls -dt results/paper3_bpw/fdose_k0_*/datasets_bonn/*/seed_0/*/ | head -1   # run 目录出现
#   tail -3 <最新 run>/console.log             # 有 iter 行
# 禁止 `cd X && … &` 链式启动（`&` 优先级低于 `&&` ⇒ 后续命令在未 cd 的 shell 里跑、
# 相对路径全失效而静默不启）。
set -u

REPO=/data/monogs-ours
PY=/data/conda_envs/monogs-ours/bin/python
SEQ=${SEQ:-person_tracking}
SEEDS=${SEEDS:-"0 1 2"}
MAX_FRAMES=${MAX_FRAMES:-0}
N_PLAN=${N_PLAN:-57}
STAGE=${1:-}
TAG=fdose
PLAN_DIR=$REPO/results/paper3_bpw/dose_plan
GEN_DIR=/tmp/fdose_cfg

cd "$REPO" || exit 1
mkdir -p "$PLAN_DIR" "$GEN_DIR"

STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$REPO/paper3/results/evidence/${TAG}_l1_${SEQ}_${STAGE}_${STAMP}.log"

{
  echo "=== FDose L1 $STAGE — $SEQ seeds=[$SEEDS] ==="
  echo "  HEAD: $(git rev-parse --short HEAD)  branch=$(git branch --show-current)"
  echo "  max_frames: $MAX_FRAMES (0 = 全长)   n_plan: $N_PLAN"
  echo "  log: $LOG"
} | tee "$LOG"

EXTRA=()
[ "$MAX_FRAMES" -gt 0 ] && EXTRA=(--max-frames "$MAX_FRAMES")

# 为某臂某 seed 生成配置：把 plan 路径覆写进去。
#
# **文件名必须与臂名一致**（放在按 seed 分的子目录里）：slam.py 在
# `Results.save_results` 时用 `Dataset.sequence`，而该字段会被 config 的 **basename**
# 覆写（`get_sequence_id`）⇒ 文件名带 seed 会让 sequence 也带 seed，run 目录层级
# 与 tables 的 sequence 列一起漂。按 seed 分目录 + 同名文件两头都对。
gen_cfg() {  # $1=arm $2=seed $3=plan_path(可空)
  local arm=$1 seed=$2 plan=$3 src out
  src="configs/experiments/paper3_bpw/fdose_${arm}_${SEQ}.yaml"
  out="$GEN_DIR/seed${seed}/fdose_${arm}_${SEQ}.yaml"
  [ -f "$src" ] || { echo "ERROR: 缺配置 $src" >&2; return 1; }
  mkdir -p "$(dirname "$out")"
  sed -e "s|^  dose_plan_path:.*|  dose_plan_path: ${plan}|" "$src" > "$out"
  echo "$out"
}

run_arm() {  # $1=cfg $2=label $3=seed $4=arm
  local cfg=$1 label=$2 seed=$3 arm=$4 start end rc run newdir
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] $label  cfg=$cfg ===" | tee -a "$LOG"
  start=$(date +%s)
  "$PY" slam.py --config "$cfg" --eval --seed "$seed" "${EXTRA[@]}" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] $label done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  # done 锚点（M6）：项目判决纪律只认「done 里 finished rc=0 之后 consolelog 的末行 eval」。
  # 没有锚点时，`|| true` 吞掉失败后 STAGE DONE 照样出现，只能靠人看日志。
  run=$(ls -dt "results/paper3_bpw/fdose_${arm}_${SEQ}/datasets_bonn/"*/seed_"${seed}"/*/ 2>/dev/null | head -1)
  if [ -n "$run" ]; then
    printf 'arm=%s\nseed=%s\nrc=%s\nelapsed_s=%s\nmax_frames=%s\nlog=%s\nfinished_rc0=%s\n' \
      "$arm" "$seed" "$rc" "$((end-start))" "$MAX_FRAMES" "$LOG" \
      "$([ "$rc" -eq 0 ] && echo yes || echo no)" > "${run}fdose_${arm}_seed${seed}.done"
    echo "  done 锚点: ${run}fdose_${arm}_seed${seed}.done" | tee -a "$LOG"
  fi
  return $rc
}

case "$STAGE" in
  stage1)
    for s in $SEEDS; do
      run_arm "$(gen_cfg k0 "$s" null)" "k0 seed=$s" "$s" k0 || true
    done
    ;;
  freeze)
    # 帧数闸：`ls -dt | head -1` 会静默取到**冒烟 run**（40 帧），把它冻结成计划
    # 就等于用一个 19 事件的短计划跑全长 —— 必须按 num_frames 选，不能按 mtime。
    WANT_FRAMES=$MAX_FRAMES
    [ "$WANT_FRAMES" -eq 0 ] && WANT_FRAMES=580
    for s in $SEEDS; do
      run=""
      for cand in $(ls -dt results/paper3_bpw/fdose_k0_${SEQ}/datasets_bonn/*/seed_${s}/*/ 2>/dev/null); do
        got=$("$PY" - "$cand" <<'EOF'
import csv, pathlib, sys
d = pathlib.Path(sys.argv[1])
p = d / "efficiency_raw.csv"
if not p.is_file():
    print(-1); raise SystemExit
rows = list(csv.DictReader(open(p)))
print(int(float(rows[-1]["num_frames"])) if rows and rows[-1].get("num_frames") not in (None, "", "MISSING") else -1)
EOF
)
        if [ "$got" = "$WANT_FRAMES" ]; then run=$cand; break; fi
        echo "  跳过 $cand（num_frames=$got，需要 $WANT_FRAMES）" | tee -a "$LOG"
      done
      [ -n "$run" ] || { echo "ERROR: seed=$s 找不到 $WANT_FRAMES 帧的 k0 run" | tee -a "$LOG"; continue; }
      trace="${run}fdose_selection_trace.csv"
      [ -f "$trace" ] || { echo "ERROR: seed=$s 缺 k0 trace ($trace)" | tee -a "$LOG"; continue; }
      echo "  freeze seed=$s <- $run" | tee -a "$LOG"
      "$PY" scripts/paper3_bpw/make_dose_plan.py --trace "$trace" \
        --out "$PLAN_DIR/${SEQ}_seed${s}.json" --n-plan "$N_PLAN" \
        --sequence "$SEQ" --seed "$s" 2>&1 | tee -a "$LOG"
    done
    ;;
  stage2)
    for s in $SEEDS; do
      plan="$REPO/results/paper3_bpw/dose_plan/${SEQ}_seed${s}.json"
      [ -f "$plan" ] || { echo "ERROR: seed=$s 缺计划 $plan（先跑 freeze）" | tee -a "$LOG"; continue; }
      run_arm "$(gen_cfg G "$s" "$plan")" "G seed=$s" "$s" G || true
      run_arm "$(gen_cfg S "$s" "$plan")" "S seed=$s" "$s" S || true
    done
    ;;
  *) echo "用法: $0 {stage1|freeze|stage2}" >&2; exit 1 ;;
esac

echo "" | tee -a "$LOG"
echo "=== STAGE $STAGE DONE $(date +'%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG"
