#!/bin/bash
# run_device_gate_probe.sh — 决定性模式探针（P3-D2-024 / prereg_device_gate_2026-11-05 Part B）
#
# 问题：3090 同 config 同 seed 分叉是否可被 PyTorch 确定性套件消除？
# R1 全长两 run 逐位一致 ⇒ 甲复活；R2 任一判据件不同（或 R3 确定性算子 raise）⇒ 丙坐实。
#
# 阶段：
#   smoke  seed0 40 帧 × 1 run（确定性模式 ON）——崩 = R3 级证据，不得 warn_only 续跑
#   full   seed0 全长 580 帧 × 2 run 单卡串行 + 逐位比对（md5）→ detprobe_compare.json
#
# 确定性注入 = 环境级零核心代码改动：PYTHONPATH 前置 deterministic_probe/，
# sitecustomize.py 在每个解释器（含 spawn 子进程）启动时开 torch 确定性套件。
#
# 用法（后台派发唯一形态）：
#   setsid env bash scripts/paper3_bpw/run_device_gate_probe.sh smoke \
#       >> paper3/results/evidence/detprobe_manual.log 2>&1 &
set -u

REPO=${MONOGS_REPO:-/data/monogs-ours}
PY=${MONOGS_PY:-/data/conda_envs/monogs-ours/bin/python}
SEQ=${SEQ:-person_tracking}
SEED=${SEED:-0}
MAX_FRAMES=${MAX_FRAMES:-0}
STAGE=${1:-}
CFG="configs/experiments/paper3_bpw/maskstat_off_${SEQ}.yaml"
TAG=detprobe

[ -n "$STAGE" ] || { echo "用法: $0 smoke|full" >&2; exit 2; }
[ -f "$REPO/$CFG" ] || { echo "ERROR: 缺配置 $REPO/$CFG" >&2; exit 2; }

# --- 确定性注入（prereg B2；必须在启动 slam.py 前导出） ---
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
  echo "=== 装置门决定性探针 $STAGE — $SEQ seed=$SEED ==="
  echo "  HEAD: $(git rev-parse --short HEAD)  branch=$(git branch --show-current)"
  echo "  cfg: $CFG   max_frames: $MAX_FRAMES (0=全长580)   CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
  echo "  CUBLAS_WORKSPACE_CONFIG=$CUBLAS_WORKSPACE_CONFIG"
  echo "  log: $LOG"
} | tee "$LOG"

# 自检：探针解释器里确定性标志必须已开（fail-closed；不开即整批停）
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

# 比对集（prereg B3）：run 内逐位件 + 共享 tables 末行快照
BITWISE_FILES="tracking_raw.csv per_frame_ape.csv plot/summary.json plot/trj_final.json plot/trj_full_final.json plot/stats_final.json"

snapshot_tables_lastrow() {  # $1 = run 目录
  local run=$1 t
  for t in efficiency_raw mapping_raw; do
    if [ -f "results/paper3_bpw/maskstat_off_${SEQ}/tables/${t}.csv" ]; then
      tail -1 "results/paper3_bpw/maskstat_off_${SEQ}/tables/${t}.csv" > "${run}detprobe_${t}_lastrow.txt"
    else
      echo "MISSING" > "${run}detprobe_${t}_lastrow.txt"
    fi
  done
}

run_one() {  # $1 = run 序号
  local idx=$1 start end rc base before after n_new run
  echo "" | tee -a "$LOG"
  echo "=== [$(date +%H:%M:%S)] run$idx  cfg=$CFG  seed=$SEED ===" | tee -a "$LOG"
  start=$(date +%s)
  # 定位 run 目录用「跑前记录目录集合、跑后取新增者」（A6 同款，禁 ls -dt 隐式取目录）。
  base="results/paper3_bpw/maskstat_off_${SEQ}/datasets_bonn/"*/seed_"$SEED"
  before=$(ls -d ${base}/*/ 2>/dev/null | sort)
  "$PY" slam.py --config "$CFG" --eval --seed "$SEED" \
    $( [ "$MAX_FRAMES" -gt 0 ] && echo --max-frames "$MAX_FRAMES" ) 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  end=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] run$idx done rc=$rc elapsed=$((end-start))s ===" | tee -a "$LOG"
  after=$(ls -d ${base}/*/ 2>/dev/null | sort)
  n_new=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -c .)
  run=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | head -1)
  if [ "$n_new" -eq 1 ] && [ -n "$run" ]; then
    snapshot_tables_lastrow "$run"
    printf 'stage=%s\nrun=%s\nseed=%s\nrc=%s\nelapsed_s=%s\nmax_frames=%s\ncublas=%s\nhead=%s\ndeterministic=on\n' \
      "$STAGE" "$idx" "$SEED" "$rc" "$((end-start))" "$MAX_FRAMES" \
      "$CUBLAS_WORKSPACE_CONFIG" "$(git rev-parse --short HEAD)" > "${run}${TAG}_run${idx}_seed${SEED}.done"
    echo "  done 锚点: ${run}${TAG}_run${idx}_seed${SEED}.done" | tee -a "$LOG"
    # 动态赋值必须走 eval：`DETPROBE_RUN${idx}="$run"` 在 bash 里展开前含 `$` 不构成
    # 合法标识符 ⇒ 被当命令执行（rc=127、变量恒空）⇒ compare 段空对空假阳性
    # （2026-11-05 实测：3/3 假 R1 已作废，改由判据侧重比对）。
    eval "DETPROBE_RUN${idx}=\"\$run\""
    return $rc
  fi
  echo "ERROR: run$idx 产生 $n_new 个新 run 目录，不写 .done（歧义）" | tee -a "$LOG"
  return 1
}

# ---------- smoke ----------
if [ "$STAGE" = "smoke" ]; then
  # 显式覆盖而非 ${MAX_FRAMES:-40}：MAX_FRAMES 已在头部默认成 0（已设非空，:- 不触发），
  # 否则"冒烟"会全长跑（2026-11-05 实测踩坑；先修正该默认，再走 40 帧门）。
  MAX_FRAMES=40
  if run_one 1; then
    echo "" | tee -a "$LOG"
    echo "=== DETPROBE SMOKE OK — 确定性模式下 40 帧无 raise；可放全长（full）===" | tee -a "$LOG"
    exit 0
  else
    echo "" | tee -a "$LOG"
    echo "=== DETPROBE SMOKE FAIL — 见上方 raise 算子名。按 prereg B3-R3：不得 warn_only 续跑；" \
         "raise 算子本身即 R2/R3 级证据 ===" | tee -a "$LOG"
    exit 1
  fi
fi

# ---------- full ----------
if [ "$STAGE" = "full" ]; then
  DETPROBE_RUN1=""; DETPROBE_RUN2=""
  run_one 1 || { echo "=== DETPROBE FULL FAIL @ run1（R3 出口，停）===" | tee -a "$LOG"; exit 1; }
  run_one 2 || { echo "=== DETPROBE FULL FAIL @ run2（R3 出口，停）===" | tee -a "$LOG"; exit 1; }

  R1="$DETPROBE_RUN1"; R2="$DETPROBE_RUN2"
  echo "" | tee -a "$LOG"
  echo "=== 逐位比对（md5）===" | tee -a "$LOG"
  DIFFS=(); SAME=0; CHECKED=0
  for f in $BITWISE_FILES; do
    for side in "$R1" "$R2"; do [ -f "${side}${f}" ] || { echo "WARN: 缺 ${side}${f}" | tee -a "$LOG"; }; done
    [ -f "${R1}${f}" ] && [ -f "${R2}${f}" ] || continue
    CHECKED=$((CHECKED+1))
    m1=$(md5sum "${R1}${f}" | cut -d' ' -f1)
    m2=$(md5sum "${R2}${f}" | cut -d' ' -f1)
    if [ "$m1" = "$m2" ]; then SAME=$((SAME+1)); echo "  same  $f  $m1" | tee -a "$LOG"
    else DIFFS+=("$f"); echo "  DIFF  $f  $m1 vs $m2" | tee -a "$LOG"; fi
  done
  # config.yml：掩蔽 save_dir 行（含时间戳，非行为变量）后比对
  c1=$(sed 's|^  save_dir:.*|  save_dir: <MASKED>|' "$R1/config.yml" | md5sum | cut -d' ' -f1)
  c2=$(sed 's|^  save_dir:.*|  save_dir: <MASKED>|' "$R2/config.yml" | md5sum | cut -d' ' -f1)
  CHECKED=$((CHECKED+1))
  if [ "$c1" = "$c2" ]; then SAME=$((SAME+1)); echo "  same  config.yml(save_dir掩蔽)  $c1" | tee -a "$LOG"
  else DIFFS+=("config.yml(masked)"); echo "  DIFF  config.yml(save_dir掩蔽)  $c1 vs $c2" | tee -a "$LOG"; fi
  # 共享 tables 末行快照
  for t in efficiency_raw mapping_raw; do
    CHECKED=$((CHECKED+1))
    m1=$(md5sum "${R1}detprobe_${t}_lastrow.txt" | cut -d' ' -f1)
    m2=$(md5sum "${R2}detprobe_${t}_lastrow.txt" | cut -d' ' -f1)
    if [ "$m1" = "$m2" ]; then SAME=$((SAME+1)); echo "  same  tables/${t}.csv 末行快照  $m1" | tee -a "$LOG"
    else DIFFS+=("tables/${t}_lastrow"); echo "  DIFF  tables/${t}.csv 末行快照  $m1 vs $m2" | tee -a "$LOG"; fi
  done

  VERDICT=R1; [ "$SAME" -eq "$CHECKED" ] || VERDICT=R2
  "$PY" - "$R1" "$R2" "$VERDICT" "$CHECKED" "$SAME" "$LOG" <<'PYEOF'
import json, sys
r1, r2, verdict, checked, same, log = sys.argv[1:7]
out = {
    "probe": "device_gate_deterministic_P3-D2-024",
    "prereg": "paper3/results/evidence/prereg_device_gate_2026-11-05.md#part-b",
    "verdict": verdict,          # R1 = 逐位一致(甲复活)；R2 = 有件不同(丙坐实)
    "checked": int(checked), "same": int(same),
    "run1": r1, "run2": r2, "log": log,
}
for d in (r1, r2):
    with open(f"{d}detprobe_compare.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False))
PYEOF
  echo "" | tee -a "$LOG"
  if [ "$VERDICT" = "R1" ]; then
    echo "=== DETPROBE FULL R1: ${SAME}/${CHECKED} 件逐位一致 ⇒ 甲复活（确定性模式下门带宽可按机重标定；地板须重测）===" | tee -a "$LOG"
  else
    echo "=== DETPROBE FULL R2: ${SAME}/${CHECKED} 中 ${#DIFFS[@]} 件不同（${DIFFS[*]}）⇒ 丙坐实（臂级读数维持乙降级）===" | tee -a "$LOG"
  fi
  exit 0
fi

echo "用法: $0 smoke|full" >&2
exit 2
