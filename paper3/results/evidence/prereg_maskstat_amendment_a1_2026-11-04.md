# MaskStat Amendment A1（2026-11-04，判读数据前修正）

> 账本：`P3-D2-016`（方向立项）；母文书 = `prereg_maskstat_2026-11-04.md`（§0 原文处留有取代指针）。

**触发**：smoke 40 帧 off 臂启动即出现 `Semantic insertion gate frame 0: 34748 person px
zeroed` —— 证明 `SemanticMask.enabled=true` **不是行为惰性开关**：该标志另有既有消费者
（前端语义插入门控 `utils/slam_frontend.py` ×4 处、`utils/dba_lite.py:731` 等 ≥5 处），
原设计的「两臂都开掩码计算、off 臂只算不消费」会把**他族机制行为混进 off 臂**，
单变量前提被破坏。冒烟 run 即杀（run 目录 `2026-11-04-02-53-24` 无 `.done`，
判据机天然拒绝；未产生任何判读数据）。

**修正条文**（判据**阈值与出口规则 §4 零改动**；只改 §0 的掩码供给方式与 G3 的
安全阀语义细化——掩码占比超 `max_mask_ratio` 被压成 None ⇒ w=0 属**定义性行为**，
非"判据改动"）：

1. **机制掩码自持**：MaskStat 直接调 `compute_semantic_dynamic_mask`（该函数内部无
   enabled 门），参数读 `Mapping.maskstat_*` 自持块（model / dynamic_classes /
   dilate_px / max_mask_ratio / conf_threshold / mask_threshold）。
   **永不读、永不设** `SemanticMask.*`。
2. **off 臂 = 纯基线**：config 不含任何语义掩码段 ⇒ 与 `bpw_off_person_tracking.yaml`
   同链逐位一致（唯一差别 save_dir）。
3. **掩码缓存自持属性**：`viewpoint.maskstat_mask` / `maskstat_ratio`，与
   `semantic_mask` 的 `dynamic_mask` 缓存互不干扰。
4. **fail-closed 细化**：maskstat 开而图像不可得 / 模型加载失败 ⇒ RuntimeError
   （不静默退化）；掩码占比超 `max_mask_ratio` 被安全阀压成 None ⇒ 机制含义就是
   "该视角几乎无静态证据"，取 w=0 且 trace 记 ratio=None（这是定义性行为，非退化）。
5. **单变量重述**：两臂 config 字段级 diff = **6 键**（`Mapping.maskstat_dens_stats`/
   `dilate_px`/`dynamic_classes`/`max_mask_ratio`/`model` 自持块 5 键 + `Results.save_dir`；
   2026-11-05 G2-3090 复核 resolved config 逐键展开实测）——自持块 4 键在 off 臂为死键；
   **行为变量唯一** = 致密化统计的 w 加权（`dens_stats` 开关）。
   （原句「唯一 config 差别 = dens_stats true/false」措辞不实，原文保留、此处带日期更正。）

**装置教训（入 PITFALLS 候选）**：复用既有 config 段做「惰性参数载体」前必须 grep
该段的所有消费者——本次 `SemanticMask.enabled` 有 5 处消费者，冒烟在第 0 帧即抓住。

## 诊断更正（2026-11-04，读 method.yaml 后；随 commit ecf48bee6 入库）

上文把冒烟日志的 `Semantic insertion gate … person px zeroed` 归因为「SemanticMask.enabled
混入他族机制」——**归因错误，原文保留**。真相：该门控与 `mask_mapping: true` 全部来自
`method_from: configs/experiments/combined_prune/method.yaml`（**标准基线栈自带**，
论文 1 机制；两臂同样继承）。smoke#1 的真实污染方向相反：我加的 `SemanticMask` 段把
基线的 `mask_mapping: true` **覆写成了 false**（还把 dilate 7→5），等于在 off 臂**关掉了
基线机制**。A1 的修正（自持参数块 + off 臂不设该段）恰好恢复纯基线，**修正本身维持不变**；
本更正只改归因句。A1 后两臂继承完全相同的语义段，唯一变量 = `Mapping.maskstat_dens_stats`。
