
## 2026-11-05 det-raster L1（P3-D2-027 / 判决行 P3-D2-028）

- **实现**：正确基座 = 主仓 submodule pinned `43e21bff`（rmurai0610 fork，含 projmatrix_raw/depth/
  opacity/n_touched/grad_tau/theta/rho）。expanded 10 处 flush atomicAdd → int64 定点镜像；
  7 文件贯通；config 门 `Rasterizer.deterministic_backward` 默认 False。patch 入库
  `detraster_patch/det_raster_L1.patch`（md5 `44eafc56…`）。
- **误基座事故（provenance）**：首版误用 `submodules/compressed-3dgs-niedermayr/submodules/
  diff-gaussian-rasterization`（陈旧，无 projmatrix_raw）⇒ 安装后环境崩
  （`unexpected keyword argument 'projmatrix_raw'`）。恢复路径：远端取回原始
  `__init__.py`（md5 `bb83a036`）+ 本地 `.so.orig_backup` ⇒ 环境解锁；再从主仓 submodule
  对象库定位正确基座。
- **三层仪器自检 PASS**：合成冒烟（det-ON×2 逐位一致；vs OFF 相对差 3.407e-04）／
  **真实规模 A/B 决定性**（480×640/4万点：det=OFF 6/6 梯度 DIFF，det=ON 0/6）／
  跨机同一 `.so` 冒烟哈希逐位相同（2060 = 3090）。
- **三轮 40 帧 ×2 探针全 R2_divergent（9/9 件）**，ATE 1.1842 / 1.1635 cm：
  轮1 convert_det 位置错（置于函数返回后 ⇒ preprocess 读零镜像，三种梯度全 0，合成冒烟抓出）
  → 轮2 移到 render/preprocess 之间 → 轮3 追加 `PYTHONHASHSEED=0`（env 预置）。
- **开关确已生效**：真实 SLAM run（7 帧）插桩 1878/1878 次 render 全 `det_bw=True`（双进程）。
- **残差分叉定位**：逐 render md5 trace（P/means3D/render/depth/opacity/maxRadii/gradAcc/denom）
  ⇒ 前端 #1–#548 全字段相同；#549 P 同值（19030→17094）但四项全异 ⇒ 分叉在
  「相同输入 → prune mask 成员选择」内。后端首分叉 idx=2102 为下游后果。
- **判决**：R-infeasible（无 L2 入场券）。但「rasterizer backward 是分叉源」假设**成立**
  （证据见上），故原 R2 分支文案「分叉源不在 rasterizer backward」自我更正为
  「除 backward 之外尚有至少一个分叉源」。
- **噪声收窄**：臂级 ATE 摆动从 ±2.14cm 降到 ±0.02cm；online 高斯数从 −30%~+97% 降到
  −2.7%（真实规模）。仍未达逐位一致。
- **新坑（PITFALLS 候选）**：① `PYTHONHASHSEED` 必须在解释器启动前由 env 给出，
  sitecustomize 里赋值无效；② sitecustomize 的 `raise` 被 CPython 吞掉（只打印一行，
  进程继续）⇒ fail-closed 必须放 runner 显式断言；③ `${VAR:-x}` 不复位已设变量（P40 复现；
  本轮 `MAX_FRAMES` 再次踩到，改用显式传参）。

## 2026-11-05 det-raster 2×2（P3-D2-029）

- **2×2 四格**（person_tracking / seed0 / 40 帧 / 每格 2 run，确定性套件全开）：
  | 格 | 判定 |
  |---|---|
  | 单线程 × det-ON | **R1_bitwise_identical（same=12 diff=0）** |
  | 单线程 × det-OFF | R2 |
  | async × det-ON | R2 |
  | async × det-OFF | R2 |
- **逐位证据**：`per_frame_ape.csv` / `reliability_signal/frames.csv` /
  `deferred_commit_events.csv` / `stats_final.json` / `trj_full_final.json` 五件 md5 相同；
  tracking/efficiency/mapping 非元数据列全同；ATE 1.1682/1.1682cm、KF-ATE 1.277/1.277、
  num_gaussians 19771/19771、mapping_iterations 2107/2107。
- **归因修正**：L1 R-infeasible 的原因不是机制无效，而是**判据与 async 架构不匹配**。
  `backend._run_loop`（`slam_backend.py:2105`）队列空时无上限跑 `map()` ⇒ 每 KF 迭代数
  由墙上时钟决定（实测同 20 帧两跑 **735 vs 700 个不同 iteration**）。
  ⇒「40 帧×2 逐位一致」在 async 下**结构不可达**。
- **工具修正**：`compare_three_way.py` 剔除易变列（run_id/source_dir/wall-clock/显存峰值）
  + 双侧都缺记 N/A。原实现会把逐位一致误报 R2（本轮踩到）。新增
  `tests/paper3_bpw/test_compare_three_way.py` 3 条（含「真差异必须被抓到」负对照）。
- **新坑**：`single_thread` 有两个 key —— 前端 `Training.single_thread`（`slam_frontend.py:357`）、
  后端 `Dataset.single_thread`（`slam_backend.py:317`）。只设前者 ⇒ 后端仍 async
  （本轮前两次「单线程」测试因此失真一轮，已作废那两个 run）。
- **边界**：`single_thread` 是**仪器模式非部署模式**（ATE 1.168 vs async 1.177；
  高斯 19771 vs 25976）⇒ 单线程读数不可直接当主线读数。

## 2026-11-05 仪器模式落定（P3-D2-030，用户拍板甲）

- **定义**：仪器模式 = 三项开关（`Training.single_thread` + `Dataset.single_thread` +
  `Rasterizer.deterministic_backward`）+ 三项环境（`PYTHONHASHSEED=0` /
  `CUBLAS_WORKSPACE_CONFIG=:4096:8` / `PYTHONPATH=deterministic_probe`）。
- **R-valid 判据**：每批必跑 2 run，`compare_three_way.py`（易变列剔除）须 R1；
  R2 ⇒ 整批作废不报数。**这是仪器前置，不是机制判据。**
- **两套口径永不混引**：仪器口径（primary，机制判据）vs 部署 async（reference）；
  仪器口径绝对值不可与文献直接比。
- **框架 v2 回写**：E1① 「run 级逐位一致不可达」作废；E3 按口径二分（仪器可判、
  async 仍自差内不可判）。
- **首次端到端 PASS**：40 帧 ×2 → R1_bitwise_identical；ATE 1.1682/1.1682、
  KF-ATE 1.277/1.277、num_gaussians 19771/19771、mapping_iterations 2107/2107。
- **工件**：`instrument_person_tracking.yaml` / `run_instrument.sh`（含显存预检）/
  `make_instrument_arm.sh` / 4 条契约单测。
- **踩坑**：单线程峰值 ~4.8 GiB，首次启动撞 36h 前孤儿 spawn 进程（704 MiB）OOM
  ⇒ runner 加 `memory.free < 5200 MiB` 即拒启动。

## 2026-11-06 夜间自动迭代收口（P3-D2-031/032/033）

- **MaskStat 仪器口径正式判决（P3-D2-031）**：DIRECTIONAL_EFFECT（负向）。
  权威批 = 3090 卡1 单机 × 6 run（2 臂 × 3 seeds × 全长 580 帧），全 rc0=yes。
  off 13.5941/13.9182/13.7268（极差 0.33cm）；Δ +0.109/+2.884/+0.649 三 seed 同号，
  median +0.649cm ≥ 0.5 门槛 ⇒ 机制负贡献，关闭。第 13 次尝试第一个机械可判读数。
  配套：runner 比对假阳性修复（曾把历史目录当本次 run，R2 假警报）+
  .done 补 finished_rc0 + 判读器 rc 闸（OOM 半程不再混入，+4 单测 = 99 passed）。
  本地 on 臂 KF430 OOM（2060 5.78GiB 上限）→ 半程 run 归档 _voided/ 带 VOID.md，
  整批迁 3090 重跑（同机纪律：臂级 Δ 必须同机）。
- **口径偏移归因修正（P3-D2-032）**：原「地图新鲜度 39×」被否定 ——
  itr=50/150/300 调用次数全同（231）而 ATE 严格单调（10.66→13.59→18.91）⇒
  主导变量 = 单次 map 调用内优化步数（mapping_itr_num）。
  总迭代量也被排除（18415≈async 18003 但 ATE 差 7cm）。
  **跨机差随长度放大**：40 帧 0.033cm → 580 帧 2.78cm（同配置 off/seed0）⇒
  跨机并列绝对 ATE 永久禁止（修正 crossmachine 文档 §二 规则量级）。
- **丙轴收口（P3-D2-032）**：itr 全曲线 10→300 共 8 档。单 seed 谷 itr=30 → 8.96cm，
  三 seed 后 median 11.13、极差 3.93 ⇒ 谷底被 seed 方差填平（itr=50 极差 0.61、
  itr=150 极差 0.32）。同机 2060 itr=30 median 9.98 vs async 单次 9.30 = 打平不超越。
  **判决：配置轴记「默认 150 次优」进讨论节；机制判读口径维持 itr=150**
  （最稳测点；换 itr=30 令 0.5cm 级机制效应被 3.93cm 方差淹没）。
  part3 的 L-IMPROVE 判决被夜间矩阵修订（ATE 部分成立、最优 itr=30 不成立）。
- **P3-D2-033 撤回**：async 确定化在写代码前发现内在矛盾（新鲜度依赖两端相对速度，
  不可既保留又消除）→ 止损，未耗 GPU。丙轴结果反证撤回正确（口径偏移是 itr 参数问题，
  可调，不需要动调度架构）。
- **过程事故如实登记**：远端同步误用 `git stash -u` 移出 296 个未跟踪文件
  （含运行中 run 产物），逐文件从 stash 恢复，读数未受损（判决文档 §三）。
- 判决文档 5 件、账本 3 行、单测 99 passed；远端 19 run 判据件在 3090。

## 2026-11-06 剂量轴 A4 仪器复验（P3-D2-038；明细见同目录判决文档）

- **方向拍板**：用户选**丁**（A4 仪器重测）+ 保留**高斯数硬约束 ratio ≤ 1.5**。
  否决戊（换问题）与丙（方法学叙事）。
- **前置门两道全过**：R-valid（A4 s0 两 run `R1_bitwise_identical`）+ **批次等价门**
  （本轮新增设计——off 基线锚点 HEAD `c2978f891`/`c599d965a`/`58164bb15` vs A4 的
  `250554d8e`，中间 +249 行默认关机制；off s0 补跑桥接 run 后 `R1` ⇒ 旧三 seed 基线合法复用）。
- **判决 `CLOSED_NEGATIVE_OR_UNSTABLE`**：Δ(A4−off)=+4.0962/+3.1500/+2.7608，
  median **+3.150cm**（三 seed 同号 A4 更差）；高斯比 2.63/2.52/2.55（**max 2.63 > 1.5 闸**）。
- **关键判读**：剂量膨胀与历史相当（2.5× vs 历史 2.1~6.5×）而 ATE **方向反转**
  （历史 −29.4% → 本批 +23.2%）⇒ 历史信号是「旧栈 + 非标准序列（44cm 基线有大 headroom）
  + async 口径」的组合产物，不是剂量旋钮属性。
- **组件生效已验证**（准则 #9）：高斯 2.5× ⇒ 两键真生效 ⇒ **有效负结果**，非配置失效。
- **报告项**：PSNR +0.04~+0.38dB 但深度 L1 变差 +3.4~+5.7cm（历史 A4 是「ATE 最好
  PSNR 最低」，本批反向 ⇒「PSNR 不能判断跟踪方法」获反向证据）；算力 1.19~1.25×，
  `mapping_iterations` 两臂全同 18415。
- **顺带修复**：`run_instrument.sh` 显存预检读错卡（`CUDA_VISIBLE_DEVICES=1` 时旧实现
  恒查物理卡 0，实测两卡 24121 vs 24072 而命令恒返回 24121）⇒ 改 `nvidia-smi -i` + 单测。
- 工件：prereg + 判决 + judge JSON（远端生成/本地复跑逐字节一致）+ batch log 4059 行
  + 5 run 判据件；全量 pytest 544 passed。明细见 `dose_a4_instrument_verdict_2026-11-06.md`。

## 2026-11-07 剂量轴反向扫收口（P3-D2-039 执行完毕；明细见同目录判决文档）

- **M2 跨卡探针**：同 config 同 seed 两卡各 1 run ⇒ `R1_bitwise_identical`，卡间等价成立
  （A4 判决的跨卡限定关闭）。探针自身「同臂并发判歧义 rc=1」事故如实登记。
- **重派 7 run**（22:06–01:15 全 rc0，G3 整改后的判读器）；被杀批残留 `rc0=no` 锚点被
  rc 闸正确排除（闸的自证）。
- **判决**：tau2x `SEED_UNSTABLE`（+0.22/−1.48/−2.72；高斯比 0.42~0.44 已低于下带）；
  tau4x `DOSE_CONFOUND`（−2.63/−2.84/−1.69 同号改善 median −2.626cm，但高斯塌 0.22×、
  PSNR 掉 1.4dB——双侧 ratio 带与 PSNR 闸**都真实触发**）；汇合 `INCONCLUSIVE`。
- **预期失败如实登记**：prereg §0.1 写的「最可能 BOTH_SIDES_WORSE」没有兑现，
  历史证据（A2/2060 U 形）再次没迁移——与 A4 判决的教训同构。
- **收口**：剂量↑有害干净（A4）；剂量↓改善与地图塌缩/渲染损失绑死不可主张；解开混杂需
  预算匹配 = BPW 族（已关闭）⇒ **剂量轴可测空间用尽，登记已排除方向**。论文身份 =
  配置敏感性边界素材进讨论节，不进贡献栏。
- 工件：判决 + judge JSON（钉死 run 版，逐字段与远端首生版一致）+ 7 run 判据件；
  scan 判读器补 M3（pin + used-run 打印）；全量 pytest 570 passed。

## 2026-11-07 MaskStat crowd L2 收口（P3-D2-040 开放区 ATE 级第一读数；明细见判决文档）

- **判决 `SEED_UNSTABLE`**（Δ −0.32/+0.50，median +0.09，n=2 异号）；
  G4 作用量门 PASS（机制 acted：map 段 76.8% 调用 share_w_lt_1>0，mean_w 0.863）
  ⇒ 统计纯度族在两个 churn 区都无正面读数，戊边界刻画收齐。
- 过程笔误如实登记：prereg 误写 580 帧（crowd 实际全长 928）⇒ 判读器硬编码 580
  曾把全批误判 INVALID ⇒ 修 --expect-frames（默认 580 向后兼容）+ prereg 带日期更正。
- G2 = Accept-with-conditions（0 致命/4 重大/6 次要）全处置，含钟差解释
  （remote 落后 local 6m07s，判据先于 run 经锚链确认）+ INVALID rc=0 fail-open
  顺带修复（G3-M6 漏网）。
- 工件：判决 + judge JSON + diff 工件 + 580 复现件 + 6 run 判据件；全量 581 passed。

## 2026-11-08 剂量过供给验证批收口（P3-D2-041；明细见判决文档）

- **H1 证伪**：增益序 crowd(+0.72) > balloon(+0.24 亚地板) > mnobox(−0.50 倒挂)，
  预测序 crowd > mnobox > balloon 不成立 ⇒ `SEQUENCE_DEPENDENT`；无 churn 处方。
- **H2 内部最优成立（ATE 轴）**：dose_zero +3.617cm 更差（地图 0.15×、PSNR −6.5dB）、
  tau4x −2.63cm（混杂标记限定，归因未决）⇒ 前沿非单调、默认不在最优点。
- **研究内容三定形 = 实证表征**：机制链五条 + 剂量前沿（4 序列）+ churn 否证 +
  地图规模普适收益（0.197–0.255×）。
- 过程修正：prereg 三形态不等式链排版错乱（G2 致命1）带日期更正；帧数口径
  （rgb 行 −2）第二次笔误同源更正；判读器接线 bug（嵌套 vs 摊平）判读中修。
- G2 = Reject → 整改后定稿（致命 2 / 重大 7 / 次要 3 组全处置）。
- 全量 pytest 597 passed；KEY_REGISTRY MISSING_TOTAL=0；health_check FAIL=0（收口后）。
