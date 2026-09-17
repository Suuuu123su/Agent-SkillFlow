# 复算差异记录

1. 原算法复算先封存：`audit/FIRST_COMPUTATION_SEAL.json`；封存后才解析历史分数。任务包02自带历史参考数字，阅读时不可避免看到，但没有作为计算输入或通过门槛。
2. 980 个原指标对象与阶段/完整F+H历史报告**精确一致**，包括原区间。没有回写旧分数或修改旧事实。
3. 独立核对首轮 1321/1326 一致。五项 UEA_weight 差异是新核对器把 sensitivity 当单位权重：F 210→90，G 70→52，E14→6，G预检6→3，F+H monitor210→90。源合同明确每操作1。首次证据保存在 `audit/RECOMPUTE_CHECK_FIRST_PASS.json` 与 `audit/independent-first-pass.py.txt`；只定向重算权重，最终1326/1326一致。
4. T18 初始通用字段抽取发现 metadata.harm_selector 为空；没有用该空值假称四格零风险。最终按 T18 原 report_data.hiaa_trials 的 task risk selector 和 frozen matrix 生成22组四格；308条任务/安全任务/UEA/目标端点分别与保存投影一致。过程说明见 `audit/T18_TARGET_BINDING_REFINEMENT.json`。
5. 原实现和更强理论语义的差异不是数值bug，见 `CONTRACT_DIFFERENCES.md`。没有为了与历史一致改变原合同。

`RECOMPUTE_CHECK.json` 的 PASS 只表示所列逻辑核对，不能推导全文论文主张 PASS。独立检查未完全另写 Grant 求值、图深度拓扑、bootstrap 及辅助历史用量算法。
