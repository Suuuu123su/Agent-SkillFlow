# 待审提交范围（未commit/push）

仅纳入本轮论文材料/P4_测量证据消融/p4-20260917-123623中的报告、表、code、minimal_data、结果与审计包。

不要使用git add .；排除views（可重建的大副本）、reproductions、zip_validation、原始control/REFERENCE_INPUTS.jsonl（包中用最小裁剪输入替代）、临时检查副本。

不纳入现有.gitignore、README.md、docs/progress.md、instrumentation、tool_calls及测试等9项原用户修改；本轮哈希确认其未变。

建议提交标题：`paper: add offline P4 measurement evidence ablation and review artifacts`。先审P4_FINAL_REPORT、合同、独立参照覆盖和GAP_LIST，再决定提交；本任务不执行发布。
