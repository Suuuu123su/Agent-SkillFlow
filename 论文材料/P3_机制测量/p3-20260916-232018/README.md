# P3 本地审查入口

状态：**COMPLETED_WITH_DOCUMENTED_GAPS**。新模型调用0、业务重放0；未commit/push。

1. [机制主表](P3_METRIC_MAIN.md)：HIAA→ALR→RIR→UEA/来源/CI→任务/失败→H比较。
2. [最终报告](P3_FINAL_REPORT.md)、[机器状态](P3_STATUS.json)、[缺口](GAP_LIST.md)、[主张证据矩阵](CLAIM_EVIDENCE_MATRIX.md)。
3. [150项指标合同](METRIC_CONTRACTS.json)、[合同差异](CONTRACT_DIFFERENCES.md)、[完整长表CSV](METRICS_LONG.csv)。
4. [独立核对](RECOMPUTE_CHECK.json)、[差异历史](DIFFERENCES.md)、[来源清单](SOURCE_MANIFEST.json)。
5. [Metric→Decision](METRIC_TO_DECISION_MAP.md)、[T18构念附表](T18_CONSTRUCT_APPENDIX.md)、[旧T19缺口](T19R_GAP_APPENDIX.md)。
6. [后续规划，未执行](FUTURE_PLAN.md)、[复现说明](REPRODUCE.md)、[提交清单](UPLOAD_MANIFEST.json)。

实际验证：正式F/G/H唯一核心990、Replay终态810；F+H比较630/540不重复计F。980个历史指标对象一致；独立逻辑1326项一致，T18 308×4端点核对一致。数值一致不消除pot、ALR显式原因、RIR条件队列及CI稳定性限制。

论文可用性：可本地审查的有脚注机制结果；未人工审查或批准发表。只在此新目录交付；根README追加文本作为提案保存，不覆盖用户修改。
