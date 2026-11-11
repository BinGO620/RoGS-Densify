# 装置门决定性模式探针判决（3090；P3-D2-024）—— R2：丙坐实

> **性质**：装置测量诊断判决（非判效）。预注册：`prereg_device_gate_2026-11-05.md`
> Part B（跑前锁定）。目的：判定 3090 同 config 同 seed 分叉能否被 PyTorch 官方
> 确定性套件消除。全部 run rc=0、580 帧、单卡（GPU0）串行、确定性标志全进程树生效
> （**2/2 解释器**：主进程 + BackEnd 子进程各一条注入日志；FrontEnd 为进程内对象
> `slam.py:358` 直接 `run()` 不 fork，runner 日志的第 3 条注入行来自 selfcheck
> 解释器，非管线进程）。

> **时序锚（防钟差误读）**：run 目录名时间戳 = **远程钟**，实测落后本地 ~6m11s
> （2026-11-05 05:10:18 本地 vs 05:04:07 远程）。预注册两 commit 本地时刻
> 03:24:54（`2bbb7d243`）/ 03:26:48（`fb0530df8`）早于样本 A 开跑（远程
> 03:23:38 = 本地 ~03:29:49；其 runner 日志头部锚 `HEAD: 27375229c`，该
> commit 本地 03:29:06 才存在 ⇒ 同步链证明 run 在 commit 之后）。**判据先于
> 全部三样本成立。**逐 run HEAD：A=`27375229c`，B/C=`9d11ad78c`（两 commit
> 只动 runner 脚本 3+/1-，slam.py/config 未动 ⇒ 管线等价）。

## 判决（机械出口，prereg B3-R2）

**R2_divergent**：三样本（同 config `maskstat_off_person_tracking`、同 seed 0、
同机同卡、确定性套件全开 fail-closed）两两逐位比对，**全部 9 件判据件 md5 不同**
（唯一逐位相同件 = 掩蔽 `save_dir` 后的 `config.yml`）。⇒ **丙坐实**：
官方确定性套件（`use_deterministic_algorithms(True, warn_only=False)` +
`CUBLAS_WORKSPACE_CONFIG=:4096:8` + cudnn deterministic/no-benchmark + TF32 双关）
**不能**消除本管线重跑分叉；臂级读数维持 Part A2「自差内不可判」降级；
丙（对装置非确定性稳健的估计量）成为唯一有判效潜力的路径。

## 读数（机读自 run 工件）

| 样本 | run 目录 | 确定性 | ATE (cm) | online | refined | elapsed |
|---|---|---|---:|---:|---:|---:|
| A | `…/seed_0/2026-11-05-03-23-38` | ON | 9.4819 | 56,011 | 61,011 | 1435s |
| B | `…/seed_0/2026-11-05-03-49-26` | ON | 10.7710 | 92,593 | 92,593 | 1449s |
| C | `…/seed_0/2026-11-05-04-13-35` | ON | 11.4110 | 58,137 | 63,137 | 1413s |

- online 极差：56,011 → 92,593 = **+65.3%**（仍宽多模态，B 为高值离群）
- ATE 极差：9.48 → 11.41 = **1.93cm**
- 对照（确定性**关**态装置地板，`device_floor_3090_2026-11-05.md`）：
  online 47,973/53,527/94,390 极差 +96.8%。**确定性模式未把分叉压回可判带**
  （+65.3% 与 +96.8% 同数量级）——甲（确定性模式下按机标定窄门）在本管线
  现状下不可行。
- 确定性模式墙钟开销：**不做主张**。det-OFF 参照实存（floor 批 elapsed
  1513/1520/1528s）但共卡并行 + 异 HEAD，按 `DISCIPLINE.md`「测量口径」#5
  不可配对；det-ON 三样本 1413–1449s 不与该参照混引。
- **样本数偏差（明写）**：prereg B2 注册 2 run，实跑 3（A = smoke bug 补充样本，
  B/C = 注册 run1/run2）。判决按 3 样本两两比对 = 比注册更严；B–C 注册对独立
  成立 R2（9/9 diff），A 只是加严，不改变出口。

## 分叉进入点（诊断，console.log 归一化剥时戳后 B vs C diff）

- 两日志归一化后各 783 行，diff 输出 472 行（`<`/`>` 双侧合计，即 **236 处
  位置不同**）；
- 最早的分叉行在**最初建图阶段**（首个 KF 处理期）：B `Pruned 1 lineage(s)` vs
  C `Pruned 8 lineage(s)`，随后首个中间 Eval 已不同
  （RMSE ATE 0.0122874 vs 0.0122325）；
- 全程无确定性 raise（套件 fail-closed 未触发任何算子报错）⇒ 分叉源**不在
  PyTorch 原生算子层**。结合 B1 的事前预测：最优先机制候选 = **custom CUDA
  栅格化 backward 的 atomicAdd**（`diff-gaussian-rasterization` 梯度累加，
  不在 `use_deterministic_algorithms` 管辖范围）；前端/后端进程调度竞态
  为次优候选。定位到算子级不在本探针范围。

## provenance（如实登记，含两次 runner bug）

1. **样本 A 由 smoke bug 产生**：runner smoke 段 `MAX_FRAMES=${MAX_FRAMES:-40}`
   因头部已默认 0（已设非空，`:-` 不触发）⇒ "冒烟"实为全长。处置 = 让其跑完
   充作确定性样本 A（冒烟门唯一目的"防崩早停"被更严的全长通过覆盖；偏差已
   记录，`9d11ad78c` 修复）。
2. **runner 的机判行 "R1 3/3" 无效（已作废）**：compare 段动态变量赋值
   `DETPROBE_RUN${idx}="$run"` 在 bash 中被当命令执行（rc=127、变量恒空）⇒
   R1/R2 为空串 ⇒ 空对空假阳性。本判决的 R2 来自**独立三方比对**
   （`detprobe_compare.json`，判据件逐件 md5，掩蔽口径同 prereg B3），
   不依赖 runner 机判行（`89c25f67b` 修复，供未来使用）。
3. **比对集偏差**：prereg B3 所列 `plot/summary.json` 本管线不产出（该 run
   目录无此件），按缺席处理不参与比对；实际比对 **10 件** = 逐位件 9
   （run 内 7：tracking/per_frame_ape/efficiency/mapping CSV + plot 终态
   3 json；共享 tables 末行快照 2）+ `config.yml`（掩蔽 `save_dir` 行）1。
4. **比对生成器入库（G2-C3）**：三方比对由
   `scripts/paper3_bpw/deterministic_probe/compare_three_way.py` 生成
   （md5 逐件、掩蔽口径同 B3），机读结果 = 各 run 目录 `detprobe_compare.json`
   （远↔近 24 件 md5 逐位一致已核，仅本 json 为本地生成后回推远程）。

## 结论与出口（按 prereg B3 机械应用）

1. **丙坐实**：臂级终态比较在 3090 上不可修复地受管线非确定性支配
   （torch 官方套件无效）。Part A2 乙降级为**常驻终态**，不再是临时状态。
2. **甲关闭**（本管线现状）：除非后续引入确定性栅格化（代码改动 + 新 prereg +
   重测地板），甲不复活。**本探针不构成任何"机制应改名"依据**。
3. **丙立项待拍板（D2）**：逐事件配对/分布形态类估计量的新 prereg 设计
   （判据设计变更，须用户拍板方向后才开工）；其设计前置 = `DISCIPLINE`
   「测量口径」#5 报噪声地板 + 本探针的分叉进入点证据。
4. **叙事用法**：R2 结果无论走向都进论文 3「测量性结论」的装置敏感度小节
   （跨装置 1.5–4×、同机 −30%~+97%、确定性套件无效三件套证据链齐）。
5. **探针不主张**：不判任何机制死活；不改既往判决（P3-D2-022/023 维持）；
   单机结论不外推 2060。

## 工件

- 3 run 判据件（13 件/run，含 `.done` 锚点、`detprobe_compare.json`、console.log）
  已入库：`results/paper3_bpw/maskstat_off_person_tracking/datasets_bonn/
  maskstat_off_person_tracking/seed_0/{2026-11-05-03-23-38,03-49-26,04-13-35}/`
  （远↔近逐位一致性已核：24 件 md5 全同）
- runner 日志（判据链：假 R1「3/3」落盘文本 + selfcheck 行 + 逐 run elapsed）
  入库：`paper3/results/evidence/detprobe_{smoke_20261105-032333,full_20261105-034921,manual}.log`
- 三方比对生成器：`scripts/paper3_bpw/deterministic_probe/compare_three_way.py`
  ；机读件 = 各 run 目录 `detprobe_compare.json`
- 驱动：`scripts/paper3_bpw/run_device_gate_probe.sh`（`89c25f67b`）+
  `scripts/paper3_bpw/deterministic_probe/sitecustomize.py`
- 机器门：pytest 482 passed / health_check 38 通过 0 失败（判决落盘前复跑，
  见 LOG 当日条）
- 原始 consolelog 与远端 run 目录留存远程 `~/cron/monogs-ours`（同 HEAD）
