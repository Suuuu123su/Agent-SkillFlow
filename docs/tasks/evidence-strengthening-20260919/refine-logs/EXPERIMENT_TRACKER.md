# SkillFlow 补强实验跟踪表

2026-09-19。以下全部为 **NOT_STARTED**，没有新增实验已完成的含义。`EXPERIMENT_PLAN.md` 是边界与验收依据；执行者必须逐阶段记录真实状态，更新根 README。历史240/235 query结果是开发材料，不在本表计作新留出。

| Run ID | Milestone | 目的 | 系统 / 变体 | Split | 关键检查 / 指标 | 优先级 | 状态 | 备注 |
|---|---|---|---|---|---|---|---|---|
| R001 | M0 | 固化当前基线与已修HIAA | 历史只读，记录Git/输入SHA | 开发 | 13项HIAA测试、48名单一致、历史档案不变 | MUST | NOT_STARTED | 不全量重跑旧模型实验 |
| R002 | M0 | 补齐跨字段依赖与收费owner | 新版dependency ledger / projector | 旧240/235+小fixture | 512 mask；0漏登记、0免费恢复、顺序无关 | MUST | NOT_STARTED | 重点provenance→source_object与failure资格 |
| R003 | M0 | 隔离与公平总byte门 | strategy sandbox / cost ledger | 开发 | 0标签/隐藏值影响；初始byte计费；0超预算 | MUST | NOT_STARTED | M0不过不得宣称效率，继续修开发 |
| R004 | M1 | 来源盘点与family预注册 | 已有外部harness优先；独立sandbox备选 | 12族：6开发+6留出 | 来源分类、48逻辑单元、代码/拆分SHA | MUST | NOT_STARTED | 外部不可用标NOT_AVAILABLE但继续sandbox |
| R005 | M1 | 独立记录与参照验证 | recorder / raw side-effect + grant oracle | 24开发单元 | UEA/TaskSuccess参照；ALR/RIR条件满足才评估 | MUST | NOT_STARTED | 不复用predictor或既有oracle判定；所有执行计数 |
| R006 | M2 | 强静态与预算冻结 | 通用固定/随机；最佳指标静态 | 仅开发 | ≤24候选/metric；≤10绝对byte点；3seed | MUST | NOT_STARTED | 旧pilot结果不变；冻结后不得按留出选顺序 |
| R007 | M2 | 一次冻结留出评估 | 所有必需静态策略 | 24留出单元/6族 | 整通道、随机、失败相关缺证；错误确定性+覆盖+总byte | MUST | NOT_STARTED | 总sandbox执行含分支/失败≤192；预算回放不是新任务 |
| R008 | M3 | 最简动态删除检验 | 至多1个冻结dependency-guided策略 | 开发设计，留出一次评估 | 对最强指标静态的配对正确覆盖/byte AUC | NICE | NOT_STARTED | R006前冻结是否做及策略，和R007同次留出；阴性删除算法贡献 |
| R009 | M3 | 论文贡献验收与复现 | 各source/family/metric分层 | 全部，开发/留出分开 | SUPPORTED_IN_SCOPE/PARTIAL/UNSUPPORTED | MUST | NOT_STARTED | Full!=真值；未知/N/A不计正确；不报虚假样本量 |

## 必填计数与停止条件

每次运行先记：`run_id`、`git_sha`、`plan_sha`、`source_id`、`family_id`、`execution_unit_id`、原始执行次数/累计次数、query数、重复评估行数、开始结束时间、实际模型调用数、结果目录。

- 新逻辑单元预算48，实际sandbox执行总上限192；失败/重试/干预分支也计数。每批最多48个新执行，CPU分析小批≤500 query；上限达到后只分析已有记录，不自动增样。
- 模型/API/付费调用0；不读取Key。任何需要外部访问/资源的未完成部分写NOT_AVAILABLE并继续本地可做项，不将未知标通过。
- M0泄漏或成本门失败：修开发，暂停效率与留出结论；不放宽测试。
- 留出发现bug：保留原结果，标明留出已接触；修后不再称未触碰验证，不为了阳性无限新建留出。
- 动态无优越性：保留阴性结果，完成R009；无需追求把负结果调成正结果。
- 任一执行无独立完整性证明：参照可用性标未知，不能算安全/防御成功。

## 交付记录（执行时追加）

| 日期 | 阶段 | 实际状态 | 命令/证据目录 | 独立单元/族/执行/查询/轨迹行数 | 主要结果与局限 | 根README已同步 |
|---|---|---|---|---|---|---|
| — | 尚未执行 | NOT_STARTED | — | — | 仅完成任务规划 | 执行者填写 |
