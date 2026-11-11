#!/bin/bash
# remote_build_detraster.sh — 在远程 3090 机上构建并安装 det-raster 版栅格化器。
#
# 前置：本地已把 submodules/diff-gaussian-rasterization 的工作树（含 det 补丁）rsync 到
#       $R/submodules/diff-gaussian-rasterization（含 .git 指向主仓对象库，或裸工作树）。
#
# 幂等：① 首次运行备份原 site-packages 两件到 .orig_backup；② 已存在备份则不覆盖。
# 回滚：cp 回 .orig_backup 两件即可。
set -eu
R=${MONOGS_REPO:-/home/jiangwenheng/cron/monogs-ours}
PY=${MONOGS_PY:-/home/jiangwenheng/anaconda3/envs/monogs-ours-3090/bin/python}
SRC="$R/submodules/diff-gaussian-rasterization"
SP=$("$PY" -c "import site;print(site.getsitepackages()[0])")/diff_gaussian_rasterization

echo "=== remote_build_detraster ==="
echo "  R=$R"
echo "  SP=$SP"
[ -f "$SRC/setup.py" ] || { echo "ERROR: $SRC 无 setup.py（未 rsync 源码）" >&2; exit 2; }
grep -q "quantize_det" "$SRC/cuda_rasterizer/backward.cu" || { echo "ERROR: 源码无 det 补丁" >&2; exit 3; }

# 1) 备份（仅首次）
mkdir -p "$SP/.orig_backup"
if [ ! -f "$SP/.orig_backup/_C.so" ]; then
  cp "$SP"/_C*.so "$SP/.orig_backup/_C.so"
  cp "$SP/__init__.py" "$SP/.orig_backup/__init__.py"
  echo "  backup: $(md5sum "$SP/.orig_backup/"* | tr '\n' ' ')"
else
  echo "  backup: 已存在，保留（$(md5sum "$SP/.orig_backup/_C.so" | cut -c1-12)）"
fi

# 2) 构建（3090 = sm_86；保留 sm_75 以便与本地一致）
cd "$SRC"
# 远程默认 CUDA 12.8，但 torch 是 cu118 ⇒ 必须显式指定 11.8 工具链（否则 CUDA_MISMATCH）
export CUDA_HOME=${CUDA_HOME:-/usr/local/cuda-11.8}
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TORCH_CUDA_ARCH_LIST="7.5;8.6"
echo "  nvcc: $(which nvcc) -> $(nvcc --version | tail -1)"
"$PY" setup.py build_ext --inplace 2>&1 | tail -5

# 3) 安装
cp "$SRC/diff_gaussian_rasterization/_C.cpython-310-x86_64-linux-gnu.so" "$SP/"
cp "$SRC/diff_gaussian_rasterization/__init__.py" "$SP/"
rm -rf "$SP/__pycache__"
echo "  installed: $(md5sum "$SP"/_C*.so "$SP/__init__.py" | tr '\n' ' ')"
echo "=== remote_build_detraster OK ==="
