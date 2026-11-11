#!/bin/bash
# make_instrument_arm.sh — 从一个既有实验配置派生「仪器模式」版本。
#
# 用途：把任意臂（configs/experiments/paper3_bpw/<arm>.yaml）包成仪器模式，
#       使其在相同机制设置下获得逐位可复现性（P3-D2-030）。
#
# 只复制 inherit_from 链、不改任何机制键：仪器模式只加三项——
#   Training.single_thread / Dataset.single_thread / Rasterizer.deterministic_backward
#   （另给独立 save_dir，便于与 async 读数分开登记）
#
# 用法：
#   bash scripts/paper3_bpw/make_instrument_arm.sh <base_arm> [<instrument_name>]
set -eu
REPO=${MONOGS_REPO:-/data/monogs-ours}
BASE_ARM=${1:-}
NAME=${2:-"instrument_${BASE_ARM}"}
[ -n "$BASE_ARM" ] || { echo "用法: $0 <base_arm> [<instrument_name>]" >&2; exit 2; }
SRC="$REPO/configs/experiments/paper3_bpw/${BASE_ARM}.yaml"
[ -f "$SRC" ] || { echo "ERROR: 缺配置 $SRC" >&2; exit 2; }
OUT="$REPO/configs/experiments/paper3_bpw/${NAME}.yaml"
[ -e "$OUT" ] && { echo "ERROR: $OUT 已存在（不覆盖；换名或手工编辑）" >&2; exit 3; }

cat > "$OUT" <<YAML
# 仪器模式派生物（P3-D2-030）：base = ${BASE_ARM}
#
# 与 base 的唯一差别 = 三处仪器开关（机制设置原样继承）+ 独立 save_dir。
# 仪器模式定义与证据见 paper3/results/evidence/detraster_L2_2x2_2026-11-05.md：
# 只有「单线程 × det-ON」这一格达成 40 帧 ×2 逐位一致。
#
# **两个 single_thread key 必须同时设**（前端读 Training、后端读 Dataset）。
# runner 必须 export PYTHONHASHSEED=0 + CUBLAS_WORKSPACE_CONFIG=:4096:8
# + PYTHONPATH=scripts/paper3_bpw/deterministic_probe（见 run_instrument.sh）。
inherit_from: "configs/experiments/paper3_bpw/${BASE_ARM}.yaml"

Training:
  single_thread: true
Dataset:
  single_thread: true

Rasterizer:
  deterministic_backward: true

Results:
  save_dir: "results/paper3_bpw/${NAME}"
YAML
echo "created: $OUT"
python3 - "$OUT" <<'PY'
import sys, yaml
p = sys.argv[1]
c = yaml.safe_load(open(p))
assert c["Training"]["single_thread"] is True
assert c["Dataset"]["single_thread"] is True
assert c["Rasterizer"]["deterministic_backward"] is True
print("verify ok: 三个仪器开关均在")
PY
