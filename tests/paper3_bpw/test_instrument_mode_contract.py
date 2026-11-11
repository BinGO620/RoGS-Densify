"""仪器模式契约单测（P3-D2-030 / prereg_instrument_mode_2026-11-05）。

守护：仪器配置与 runner 的**契约一致性**——任一处漂移，仪器就静默失效。
  ① 基准仪器配置三项开关齐全（Training/Dataset single_thread + det_backward）；
  ② 派生脚本产出的配置同样齐全，且机制键原样继承（不被仪器开关污染）；
  ③ runner 的 fail-closed 闸门确实检查了这三项（文本级断言，防被删）。
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG_DIR = ROOT / "configs/experiments/paper3_bpw"


def _load(name):
    return yaml.safe_load((CFG_DIR / f"{name}.yaml").read_text())


def _assert_instrument(cfg, name):
    assert cfg["Training"]["single_thread"] is True, f"{name}: Training.single_thread"
    assert cfg["Dataset"]["single_thread"] is True, f"{name}: Dataset.single_thread"
    assert cfg["Rasterizer"]["deterministic_backward"] is True, f"{name}: det_backward"


def test_base_instrument_config_has_all_three_switches():
    """① 基准仪器配置三项齐全。"""
    _assert_instrument(_load("instrument_person_tracking"), "instrument_person_tracking")


def test_make_instrument_arm_inherits_mechanism_keys(tmp_path):
    """② 派生脚本产出的配置：开关齐全 + 机制键未被改写。"""
    import subprocess
    import sys

    out_dir = tmp_path / "cfgs"
    out_dir.mkdir()
    # 复制一份基座配置到临时目录，用 REPO 指向临时树
    src = CFG_DIR / "maskstat_off_person_tracking.yaml"
    (out_dir / "maskstat_off_person_tracking.yaml").write_text(src.read_text())
    fake_repo = tmp_path
    (fake_repo / "configs/experiments/paper3_bpw").mkdir(parents=True)
    (fake_repo / "configs/experiments/paper3_bpw/maskstat_off_person_tracking.yaml").write_text(
        src.read_text())

    r = subprocess.run(
        ["bash", str(ROOT / "scripts/paper3_bpw/make_instrument_arm.sh"),
         "maskstat_off_person_tracking", "instrument_x"],
        env={"MONOGS_REPO": str(fake_repo), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout

    cfg = yaml.safe_load((fake_repo / "configs/experiments/paper3_bpw/instrument_x.yaml").read_text())
    _assert_instrument(cfg, "instrument_x")
    # 机制键 = 只通过 inherit_from 继承，派生文件本身不得再写机制键
    assert set(cfg) <= {"inherit_from", "Training", "Dataset", "Rasterizer", "Results"}, set(cfg)
    assert cfg["inherit_from"].endswith("maskstat_off_person_tracking.yaml")


def test_runner_checks_all_three_switches():
    """③ runner 的 fail-closed 闸门覆盖三项（防被删/被简化）。"""
    txt = (ROOT / "scripts/paper3_bpw/run_instrument.sh").read_text()
    assert "Training.single_thread must be true" in txt
    assert "Dataset.single_thread must be true" in txt
    assert "Rasterizer.deterministic_backward must be true" in txt
    assert "PYTHONHASHSEED" in txt and "CUBLAS_WORKSPACE_CONFIG" in txt
    # 显存预检（本轮 OOM 后加的）
    assert "memory.free" in txt


def test_runner_wordings_match_comparator():
    """仪器判据措辞与比对器出口一致（R1 ⇒ OK）。"""
    txt = (ROOT / "scripts/paper3_bpw/run_instrument.sh").read_text()
    assert "R1_bitwise_identical" in txt
    assert "INSTRUMENT OK" in txt and "INSTRUMENT BROKEN" in txt


def test_runner_writes_finished_rc0_field():
    """runner 的 .done 必须落 finished_rc0 语义（2026-11-05 OOM 回归）。

    事件：on/seed0 OOM（rc=1）仍写 .done，判读器无从区分「跑完」与「半程挂掉」。
    项目既有惯例（run_maskstat_l1.sh / run_fdose_l1.sh）本就要求该字段。
    """
    txt = (ROOT / "scripts/paper3_bpw/run_instrument.sh").read_text()
    assert "finished_rc0=" in txt, "runner 须在 .done 里落 finished_rc0"
    # 必须是按 rc 求值的，不是恒写 yes
    assert '"$([ "$rc" -eq 0 ] && echo yes || echo no)"' in txt, \
        "finished_rc0 必须由 rc 求值，不得恒写 yes"


def test_judge_consumes_finished_rc0():
    """判读器必须读 finished_rc0 并据此排除 rc!=0 的 run（两道闸联动）。"""
    txt = (ROOT / "scripts/paper3_bpw/judge_maskstat_instrument.py").read_text()
    assert "finished_rc0" in txt
    assert "rc=" in txt, "排除理由里要写明 rc"


def test_runner_precheck_follows_cuda_visible_devices():
    """显存预检必须跟随 CUDA_VISIBLE_DEVICES（2026-11-06 双卡派发前修）。

    旧实现 `nvidia-smi ... | head -1` 恒读**物理卡 0**：在 CUDA_VISIBLE_DEVICES=1
    时检查的是另一张卡的空闲量 ⇒ 双卡并行派发时预检保护失效（假通过）。
    实体证据：`CUDA_VISIBLE_DEVICES=1 nvidia-smi --query-gpu=memory.free | head -1`
    在 3090 上返回卡 0 的值（实测两卡 24121 vs 24072，命令仍返回 24121）。
    """
    txt = (ROOT / "scripts/paper3_bpw/run_instrument.sh").read_text()
    assert "CUDA_VISIBLE_DEVICES%%,*" in txt, "须从 CUDA_VISIBLE_DEVICES 取设备号"
    assert '-i "$_dev"' in txt, "须用 nvidia-smi -i <dev> 读该卡"


def test_runner_fails_closed_on_divergence():
    """R2_divergent 必须非零退出（2026-11-06 G3 审查 M6）。

    旧版只打印 "INSTRUMENT BROKEN" 措辞，末尾恒 `exit 0` ⇒ 仪器坏了批次仍报成功，
    下游照着这份「成功」出判决。现在 BROKEN 分支必须 exit 6。
    """
    txt = (ROOT / "scripts/paper3_bpw/run_instrument.sh").read_text()
    broken_idx = txt.index("INSTRUMENT BROKEN")
    tail = txt[broken_idx:]
    assert "exit 6" in tail, "BROKEN 分支必须 exit 6（fail-closed）"
    # OK 分支不得提前退出（否则后续清理逻辑被跳过）——只看**可执行行**，
    # 注释里提到 "exit 0" 不构成问题（本测试第一版因此误红）。
    ok_idx = txt.index("INSTRUMENT OK")
    block = txt[ok_idx:broken_idx]
    code_lines = [ln for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert not any("exit" in ln for ln in code_lines), f"OK 分支不应带 exit：{code_lines}"
