# 证据合同补强：实际执行记录

Run ID: `strengthening-20260919-085337`。模型调用 0；实际执行预算 192。

此目录记录本轮新实验；旧240/235查询仅作开发回归。合作式输入隔离，不是OS强隔离。

|阶段|状态|累计实际执行|结果与下一步边界|
|---|---|---:|---|
|M0|IMPLEMENTED_PENDING_GATE|0|已预注册48单元/12族与全部随机种子；待依赖、隔离、费用及HIAA回归门通过，尚无新增执行。|
|M0|PASSED|0|依赖掩码、隔离、字节计费和回执绑定测试通过；HIAA13测试/48名单及旧CI8+2差异已复核。下一步只收集24个开发单元。|
|M1|PASSED_CONTROLLED_SCOPE|24|24开发单元/6族已实际执行；UEA/TaskSuccess独立参照与Full核对通过；ALR/RIR原因和污染前缀不足仍未知。下一步冻结强静态、预算和动态。|
|M2|R006_FROZEN|24|开发候选选择已完成；每指标至多24静态候选、统一绝对字节预算和1个动态策略已封存。下一步执行24留出单元，禁止按留出修改。|
|M2|R006_FINAL_AMENDED_FREEZE|24|留出前复核修正：所有oracle原始sidecar与查询输入独立封存；开发静态选择先平均随机seed，与主结果口径一致。旧冻结/候选保留，实际执行仍24。|
|M2|HELDOUT_COLLECTED_NOT_EVALUATED|48|24留出单元/6族已按冻结代码执行并封存；尚未读取其oracle/Full；下一步一次性回放全部冻结策略后再连接参照。|
|M2|R007_R008_EVALUATED_ONCE|48|全部冻结静态与动态策略轨迹先封存，随后才连接留出独立参照；未知、失败及不可行预算均保留。下一步只统计与审查，不调参或扩样。|
|M3|COMPLETED_WITH_SCOPE_LIMITS|48|已完成独立参照、冻结留出、公平预算、动态删除检验与主张表；结果与限制见SUMMARY/RESULTS_CN。受控程序结论不外推外部agent；旧材料与原工作区校验未变。|

[状态](STATUS.json) · [原始执行预算账本](ATTEMPTS.jsonl) · [访问日志](ACCESS_LOG.jsonl)

完成材料见 RESULTS_CN.md、SUMMARY.json、CLAIM_EVIDENCE_MATRIX.md、REPRODUCE.md；尚未生成的文件不表示通过。

## 最终审查

[最终中文验收](FINAL_REVIEWED_RESULTS.md)和[审查后机器摘要](FINAL_REVIEWED_SUMMARY.json)为论文表述入口。自动数值门原件保留，但动态强算法与通用效率主张不成立；完整生产合同/外部agent验证未完成。
