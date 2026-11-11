# MaskStat 组件生效验证记录（2026-11-04；DISCIPLINE「组件生效验证」#9 强制项）

> 回答两个问题：**①代码发挥正确作用了吗（语义）②在真实 run 里发挥作用了吗（激活）**。
> 结论先行：**①②均有硬证据成立**；ATE 无可判效应归因为 **n=2 方向不一致（不确定性
> 失败，纪律 #11）**，不是"组件没生效"，也不是"配置或依赖错误"。

## ① 语义正确（代码做的是声明的事）

| 证据 | 内容 |
|---|---|
| 单元语义 | `tests/densification/test_maskstat_stats.py` 11/11 PASSED（G1 weight=None 与原式全等 / G2a w=1.0 全等 / G2b w=0.25 精确缩放 accum 与 denom / G2c w=0 零贡献 / G3 fail-closed / G4 trace / C1 默认关）。工件 `maskstat_gates_pytest_2026-11-04.txt` |
| 点位审计 | 双调用点真实传 weight：`utils/slam_backend.py:426-428`（init 段）、`:897-902`（map 段，逐 entry 从 `stats_views_acm[idx]` 取视角）；累积器分支 `gaussian_splatting/scene/gaussian_model.py:1500-1505`（weight=None 走原式原操作） |
| 判据机忠实性 | slam-critic G2 复算全部数字成立；其指出的 2 处实现缺陷（rule 5 缺 n≥3 第二臂 / rule 1 槽位倒置）已修复并重跑，判决不变（`maskstat_judge_l1_n2_2026-11-04.{md,json}` 由修复后判据机产出） |

## ② 真实 run 里生效（激活与作用量）

| 证据 | 读数 |
|---|---|
| 激活计数（落盘） | on 臂 run 级 `maskstat_trace.csv`：seed0 **9769** calls / seed1 **9381** calls，`maskstat: active` 起始行在 console；off 臂无 trace 文件（tracer 从不实例化 = 默认关路径零副作用） |
| 加权真实发生 | 两 seed `share_w_lt_1` = 0.757/0.769（多数 entry 权重 <1）、`mean_w` = 0.906/0.904（< 0.98 过门）、平均动态占比 0.094/0.096（person_tracking 合理量级） |
| 作用传导到剂量 | 终态高斯 on/off = **0.815**（seed0）/ **0.950**（seed1）——同一外生世界下唯一 config 差异是加权，剂量分布系统性改变 |
| 单变量证明（生效 config 对拍） | run 内保存的合并 config 逐字段 diff：**off vs bpw_off = 322 字段仅 5 个纯输出路径差异（零机制差异）**；**on vs off = 仅 5 个 `Mapping.maskstat_*` 键 + 输出路径**。单变量在生效 config 层面成立 |
| RNG 无扰动 | G2 复核：双臂 frame-0 前 200 行 console **逐位一致**（因果孪生成立）；掩码计算 no_grad + eval + 无随机算子；探针实测跨 torch.manual_seed 掩码逐位一致 |
| fail-closed 实弹 | 判据机对真实冒烟工件（40 帧）判 rc=2（帧数闸拒）、对作废件（无 .done）判 rc=2——两条废件 provably 排除在判读外 |

## ③ 如实登记的边界（未决项）

- **掩码重算探针差 0.0075 未复现**：独立进程用真实加载器重算 frame-0 掩码得
  w=0.8794，而两次 run 的 trace 一致给 0.8869（帧 0–29 扫描无一命中）。同一环境内
  确定性成立（跨种子逐位一致、两 run 互证一致），差异在"探针环境 ≠ run 环境"的某个
  复现细节，**未定位**。影响面评估：trace 数值驱动剂量（剂量比 0.815/0.950 的作用
  独立可见），该 0.7% 像素差不动摇"机制生效"结论；但若 MaskStat 重开，应先补一个
  trace-vs-离线重算的对拍门（新 prereg 附件）。
- **"指向正确位置"的更深验证**（w 是否真的绕开人物剪影、 densify 是否转向静态区）
  属行为级问题，本装置 n=2 无判别力——这正是 ATE 判不可判的同一边界，不是生效
  验证能回答的问题。

## ④ 三分归因（纪律 #9）

| 归因项 | 判定 | 依据 |
|---|---|---|
| 组件本身无效？ | **否**（未证） | 激活+作用量+剂量传导全有证据；但 n=2 无判别力，不能证"对 ATE 无效"也不能证"有效" |
| 配置或依赖错误？ | **否** | 生效 config 单变量成立；fail-closed 未触发；RNG 无扰动；G6 非爆炸过 |
| 工件错位？ | **部分**（已披露） | A1 修正前 smoke#1 的掩码供给设计错误（已在判读数据前修正）；探针重算差 0.0075 未决（上节） |

**最终口径**：MaskStat L1 出口 = 不可判（预注册规则 5，`P3-D2-017`）。机制按规格
运行且产生了真实作用量；其 ATE 效应在本装置 n=2 下不可判。
