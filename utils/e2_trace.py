"""E2 逐事件落盘（prereg_e2_event_pairing_2026-11-06 P1）。

框架 §E2 要求「两臂都有逐事件机制输入量落盘」。本模块提供最小实现：

  - 门 = config `E2.trace_events`（**默认 false ⇒ 不实例化、逐位不变**）
  - 输出 = `<run save_dir>/e2_events.csv`，每次 densify 事件一行
  - 指标（框架 §E2 指定）：机制输入量分位数 + 机制作用量计数

设计纪律：
  - 只在 densify 事件处写（不每 iteration 写）⇒ 文件小、可比对
  - 任何异常不得杀死 mapping（同 bpw/cgb trace 的既有纪律）
  - 不改变任何计算路径（只读张量、只写文件）
"""
import os

import torch

DEFAULTS = {"trace_events": False}


def e2_enabled(config):
    return bool((config.get("E2") or {}).get("trace_events", DEFAULTS["trace_events"]))


def _run_scoped_save_dir(config):
    """与 densification_selection._selection_trace_dir 同款：优先 run-scoped。"""
    res = config.get("Results", {}) or {}
    for key in ("save_dir_run", "current_run_dir"):
        p = res.get(key) or config.get(key)
        if p:
            return p
    base = res.get("save_dir")
    if not base:
        return None
    try:
        import glob

        hits = sorted(d for d in glob.glob(os.path.join(base, "datasets_bonn", "*", "seed_*", "*"))
                      if os.path.isdir(d))
        if hits:
            return hits[-1]
    except Exception:
        pass
    return base


def _quantiles(t, qs=(0.1, 0.5, 0.9)):
    if t.numel() == 0:
        return tuple(float("nan") for _ in qs)
    try:
        vals = torch.quantile(t.float(), torch.tensor(qs, device=t.device))
        return tuple(float(v) for v in vals)
    except Exception:
        return tuple(float("nan") for _ in qs)


def snapshot_inputs(gaussians):
    """在 densify_and_prune **之前**抓取机制输入量。

    必须前置：`densify_and_prune` 末尾会重置 `denom` / `xyz_gradient_accum`，
    之后读到的分位数全是 0（2026-11-06 冒烟实测踩到，第一版写成事后读）。
    返回可直接传给 log_event 的 dict；关闭时返回 None（零开销）。
    """
    denom = gaussians.denom.detach().squeeze(-1).clamp_min(0.0)
    accum = torch.nan_to_num(
        gaussians.xyz_gradient_accum.detach().squeeze(-1), nan=0.0, posinf=0.0, neginf=0.0
    )
    grad = accum / denom.clamp_min(1.0)
    d10, d50, d90 = _quantiles(denom)
    g50 = _quantiles(grad, (0.5,))[0]
    # MissStreak 信号分布（prereg_miss_streak 前置闸）：字段不存在时为 nan
    ms = getattr(gaussians, "miss_streak", None)
    if ms is not None and ms.numel() == denom.numel():
        m = ms.detach().squeeze(-1).float()
        m10, m50, m90, m99 = _quantiles(m, (0.1, 0.5, 0.9, 0.99))
        # 多阈值截断量（M 扫描用：一次 trace 就能选出合适 M，不必反复改 config 重跑）
        stale_counts = {thr: int((m > thr).sum().item()) for thr in (1, 3, 5, 10, 20, 30)}
    else:
        m10 = m50 = m90 = m99 = float("nan")
        stale_counts = None
    return {"denom_p10": d10, "denom_p50": d50, "denom_p90": d90,
            "grad_p50": g50, "n_gauss": int(denom.numel()),
            "ms_p10": m10, "ms_p50": m50, "ms_p90": m90, "ms_p99": m99,
            "stale_counts": stale_counts}


def log_event(config, inputs, iteration_count, event_idx,
              n_gated=None, n_added=None, log_fn=None):
    """写一行逐事件记录。任何异常都吞掉（诊断不得杀死 mapping）。

    `inputs` 必须来自 `snapshot_inputs()`（densify 之前），否则分位数恒 0。
    指标（框架 §E2）：
      denom_p10/p50/p90  观测计数分位数（机制输入量）
      grad_p50           平均梯度中位数（机制输入量）
      n_gauss            事件前高斯数
      n_gated            被门槛排除的数量（机制作用量；无门则为空）
      n_added            事件后新增数（机制作用量）
    """
    if not e2_enabled(config):
        return
    try:
        path = os.path.join(_run_scoped_save_dir(config), "e2_events.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new_file = not os.path.exists(path)
        d10 = inputs["denom_p10"]; d50 = inputs["denom_p50"]; d90 = inputs["denom_p90"]
        g50 = inputs["grad_p50"]; n_gauss = inputs["n_gauss"]
        with open(path, "a", encoding="utf-8") as fh:
            if new_file:
                fh.write("event,iteration,n_gauss,denom_p10,denom_p50,denom_p90,"
                         "grad_p50,ms_p50,ms_p90,ms_p99,"
                         "n_gt1,n_gt3,n_gt5,n_gt10,n_gt20,n_gt30,n_gated,n_added\n")
            _sc = inputs["stale_counts"]
            def _sc_get(thr):
                return "" if _sc is None else int(_sc[thr])
            fh.write("%d,%d,%d,%.6f,%.6f,%.6f,%.10f,%.2f,%.2f,%.2f,"
                     "%s,%s,%s,%s,%s,%s,%s,%s\n" % (
                int(event_idx), int(iteration_count), n_gauss, d10, d50, d90, g50,
                inputs["ms_p50"], inputs["ms_p90"], inputs["ms_p99"],
                _sc_get(1), _sc_get(3), _sc_get(5), _sc_get(10), _sc_get(20), _sc_get(30),
                "" if n_gated is None else int(n_gated),
                "" if n_added is None else int(n_added),
            ))
    except Exception as exc:  # noqa: BLE001
        if log_fn is not None:
            log_fn(f"[e2] trace failed at iter {int(iteration_count)}: {exc}")
