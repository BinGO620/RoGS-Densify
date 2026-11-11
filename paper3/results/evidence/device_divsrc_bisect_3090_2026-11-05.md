# 分叉源 config 二分诊断判决（3090；P3-D2-026）—— R-div-loop

> **性质**：装置测量诊断判决（非判效、非机制）。预注册：`prereg_divsrc_bisect_2026-11-05.md`
> （跑前锁定；G1 审查 Accept-with-conditions 条件全清 `d8ef49cc5`）。产出只进
> 「测量性结论」边界叙事与未来甲复活 prereg 的前置证据，**不作贡献主张**
> （`prereg_device_robust_estimand_2026-11-05.md` §4，用户 2026-11-05 重申）。

## 判决（机械出口，prereg §2）

**R-div-loop**：clone/split/prune 决策关停臂（D1）两全长 run 在确定性套件全开下
**9/9 件判据件 md5 逐位不同**（唯一逐位同 = 掩蔽 `save_dir` 的 config.yml；
比对件数 10/10 在位、无空串 md5——假阳性已排除）⇒ **该三类决策的阈值翻转
不是分叉放大到 O(+65%) 的必要环节**；分叉在其余管线内自行发散。原
「决策放大器」假设收窄：数值源更靠核心（优化循环本体 = 栅格化 backward →
梯度 → 优化器 → 地图/位姿，或仍活跃的 promotion/reset/插入门——本诊断
不进一步切分）。

## 读数（机读自 run 工件）

| 样本 | run 目录 | ATE (cm) | online | refined | elapsed |
|---|---|---:|---:|---:|---:|
| D1-run1 | `…/divsrc_nodens_…/seed_0/2026-11-05-06-23-12` | 36.1075 | 130,918 | 135,918 | 1498s |
| D1-run2 | `…/divsrc_nodens_…/seed_0/2026-11-05-06-48-10` | 58.0916 | 127,382 | 132,382 | 1483s |

- **报告项（不与任何臂比较，不写因果句——prereg §2 字面）**：决策关停态的
  地图行为 = online 130,918 / 127,382（scheduled 插入 595,000 / 600,000 减
  DeferredCommit 剪除 466,662 / 474,963 的净额）；ATE 36.1075 / 58.0916cm。
  仅描述，不作门、不作结论。
- **关键观察**：两 D1 run 的地图**规模**近乎相同（online −2.7%；插入为逐 KF
  scheduled、DeferredCommit 剪除为主控），而 **ATE 分叉 22cm**——轨迹/地图
  质量在 clone/split/prune 关停的情况下仍剧烈分叉，与 R-div-loop 互证：数值
  非确定性在优化循环本体（栅格化 backward → 梯度 → 优化器 → 地图/位姿）
  **或仍活跃决策门**（promotion/reset/插入门）内自行发散。
- 确定性注入自检：两 run console 各 2 条注入行（主进程 + BackEnd；FrontEnd
  进程内 run，同 P3-D2-024 C2 口径）。

## provenance（如实登记）

1. **首次冒烟 rc=1（11s）**：`densify_grad_threshold: 1.0e9` 被 PyYAML 解析为
   **字符串**（YAML 1.1 float 要求指数带符号）⇒ `Tensor >= str` TypeError。
   按 prereg §2 R-crash 用掉**一次有据修正**（`1.0e+9`，`fcafdb88a`）；
   坑入 PITFALLS（config 覆盖须验类型不只验值）。第二次冒烟 rc=0（372s）。
2. **决策关停验证（机制门；G2-致命项整改后的正确证据链）**：
   `Pruned N lineage(s)` 签名**唯一发射点 = DeferredCommit prune 臂**
   （`slam_backend.py:2344`），densify_and_prune 无独立日志签名——该签名
   **不能**用作 densify 静默证据（初稿误把 40 帧冒烟的 4 条安到全长 run 名下，
   实测全长 run1=116 / run2=117 条，G2 抓出）。densify 静默的**有效证据**：
   ① 四覆盖键 config 落位（派发前 `load_config` 逐键核过，含类型
   `isinstance float`）；② 主环门调度数学（主环 iteration_count 从 init 段
   消耗 `init_itr_num=1050` 后起步，`%1e9==50` 不可达）；③ init 段
   `min_opacity=-1` 不删任何 gaussian；④ **阳性对照 = 账目恒等式**：
   每run `insert_sum − removed_sum` = 595,000−466,662=128,338（run2
   600,000−474,963=125,037）与终态 online 130,918 / 127,382 同量级
   （差 ≈ init 基座）——若 clone/split 活跃，插入/剪除账目将脱离该恒等式。
3. 首次冒烟 rc=1 的 4 条 prune 行属 40 帧冒烟 console，不计入全长读数。
4. **G2 审查 = Reject（1 致命/3 重大/3 次要）→ 条件全清后本件才落盘**：致命项
   = 初稿把冒烟 prune 计数误安到全长 run（本件 §provenance 2 已按正确证据链
   改写）；判决核心读数（ATE/高斯数/比对 md5/R-div-loop 出口措辞）被审查方
   逐位核验为真、不受致命项影响。报告 `/tmp/slam_critic_g2_divsrc_2026-11-05.md`。
   **类登记**：判决验证计数必须附源 run 目录 + 命令输出（本轮新类，防复发）。

## 结论与出口（按 prereg §2/§3 机械应用）

1. **放大器假设收窄**：任何「仅针对 clone/split/prune 的决策稳健化」不足以
   恢复臂级判效力；分叉源在优化循环本体或仍活跃决策路径（未切分）。
2. **甲复活路径收敛**：结合 P3-D2-024（torch 确定性套件无效）+ 本判决
   （决策关停仍分叉），确定性栅格化（custom kernel 级代码改动 + 新 prereg）
   是恢复臂级判效力的唯一已知候选——**立项与否待用户拍板**，本判决不立项。
3. **丙框架 v2 的支撑**：E2 逐事件配对的目标量不应是 clone/split/prune 事件
   （可被关停而不消失分叉）；E1（装置无关机制门）作为主判据的地位加强。
4. **叙事用法**：装置敏感度证据链第 4 件（跨装置 1.5–4× → 同机 +96.8% →
   确定性套件无效 → 决策关停仍分叉）；全部为边界/讨论素材，不作贡献。

## 工件

- 2 run 判据件（13 件/run，含 `.done`/`detprobe_compare.json`/console.log）入库：
  `results/paper3_bpw/divsrc_nodens_person_tracking/datasets_bonn/
  divsrc_nodens_person_tracking/seed_0/{2026-11-05-06-23-12,06-48-10}/`
- runner 日志 3 件：`paper3/results/evidence/divsrc_{full_20261105-062307,smoke_20261105-061317,manual}.log`
- 仪器：`configs/experiments/paper3_bpw/divsrc_nodens_person_tracking.yaml` +
  `scripts/paper3_bpw/run_divsrc_bisect.sh`（`563720e9d`/`fcafdb88a`）
- 机器门：gate1_class_sweep rc=0 / sweep_citation_claims rc=0（G1-M7）；
  pytest 487 passed（infra 提交时点）
- 原始 run 与远端日志留存远程 `~/cron/monogs-ours`（同 HEAD）
