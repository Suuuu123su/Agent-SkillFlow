# SkillFlow 架构决策记录

本目录保存已经冻结的架构决策。状态为“已接受”的 ADR 会约束后续实现；若要改变决策，必须新增替代 ADR，不能静默改写历史记录。

| ADR | 状态 | 决策 |
|---|---|---|
| [0001](0001-use-artifact-event-graph.md) | 已接受 | 使用 Artifact–Event 二部图作为来源事实模型 |
| [0002](0002-separate-observed-and-oracle.md) | 已接受 | 严格分离 Observed Plane 与 Oracle Plane |
| [0003](0003-use-mock-harness-first.md) | 已接受 | 第一版只使用确定性 Mock Harness |
