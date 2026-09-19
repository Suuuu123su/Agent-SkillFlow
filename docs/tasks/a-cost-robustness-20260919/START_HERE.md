# 使用方法

任务包包含新会话所需背景。可把本包放入仓库 `docs/tasks/a-cost-robustness-20260919/`，新开本地Codex会话后发送：

> 完整读取 CODEX_GOAL.md、BACKGROUND_HANDOFF.md 和 refine-logs/EXPERIMENT_PLAN.md，实际执行 A 的小规模验证：先用现有记录做增益归因和两种成本稳健性检查，只有预定Gate通过才冻结并执行24个新单元。不要只给计划，不继续B，不为取得阳性改预算/成本/规则或自动扩样。按任务更新README、研究分支与PR。

也可直接把合并版 `SkillFlow_A_Small_Validation_Codex_Task.md` 附给Codex，要求完整阅读执行。合并版包含本包所有核心章节。

资源：默认0模型/Judge/付费API；新正式单元24，含sanity与必要重试总上限48。前两阶段不产生新业务执行。文件状态为READY_TO_EXECUTE，当前只完成任务编制。
