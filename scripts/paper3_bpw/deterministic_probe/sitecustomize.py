"""Deterministic-mode injection（P3-D2-024 装置门探针，prereg_device_gate_2026-11-05 Part B）.

经 ``PYTHONPATH`` 注入：Python 启动时自动 import 本模块（sitecustomize 钩子），
对**每一个**解释器进程生效——包括 slam.py 的 mp 子进程（``slam.py:680`` 为
``mp.set_start_method("spawn")``，进程内 torch 标志不跨进程传播，但 spawn 子
解释器继承 PYTHONPATH 并重新执行本文件 ⇒ 全进程树覆盖）。

注入内容（prereg B2 锁定）：
- ``CUBLAS_WORKSPACE_CONFIG=:4096:8``（须在 cuBLAS 句柄创建前进环境）；
- ``torch.use_deterministic_algorithms(True, warn_only=False)``——fail-closed：
  非确定性算子直接 raise（R3 出口），**禁止**静默退化；
- ``cudnn.deterministic=True``、``cudnn.benchmark=False``、TF32 双关
  （``matmul/cudnn allow_tf32=False``，固定归约精度）。

启用失败即 raise（探针失效 ⇒ 后续 run 的读数无判力，不得带病跑）。
本目录只被探针 runner 加进 PYTHONPATH；其余任何用法不受影响。
核心代码（``gaussian_splatting/``、``utils/``、``slam.py``）零改动。
"""

import os
import sys

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
# 设备无关分叉源（2026-11-05 det-raster L1 追加）：CPython 的 str/bytes hash 默认
# 每进程随机化 ⇒ set/dict 迭代顺序随进程变 ⇒ 下游按序消费处产生分叉。
# 注意：PYTHONHASHSEED 必须在**解释器启动前**由环境给定；在 sitecustomize 里赋值
# 已经太晚（哈希随机化已生效）。故此处只做 fail-closed 探测，真正设置由 runner
# export 负责（run_detraster_probe.sh / run_device_gate_probe.sh）。
if os.environ.get("PYTHONHASHSEED") != "0":
    print(
        "[detprobe] FATAL: PYTHONHASHSEED 未在解释器启动前固定为 0"
        f"（当前={os.environ.get('PYTHONHASHSEED')!r}）——set/dict 迭代顺序不定，"
        "探针失效（fail-closed）。请由 runner export PYTHONHASHSEED=0。",
        file=sys.stderr, flush=True,
    )
    raise RuntimeError("PYTHONHASHSEED not fixed before interpreter start")


def _enable_deterministic() -> None:
    import torch

    torch.use_deterministic_algorithms(True, warn_only=False)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


try:
    _enable_deterministic()
    print(
        "[detprobe] deterministic mode ON: use_deterministic_algorithms(True), "
        f"CUBLAS_WORKSPACE_CONFIG={os.environ['CUBLAS_WORKSPACE_CONFIG']}, "
        "cudnn.deterministic=True, benchmark=False, tf32=off",
        file=sys.stderr,
        flush=True,
    )
except Exception as exc:  # pragma: no cover — fail-closed
    print(
        f"[detprobe] FATAL: 无法启用确定性模式（探针失效，fail-closed）: {exc!r}",
        file=sys.stderr,
        flush=True,
    )
    raise
