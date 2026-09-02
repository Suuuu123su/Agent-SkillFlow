# T17-C 总结：全场景任务与指标适用性

- 状态：PASSED
- 注册 Scenario：16
- 展开核心 variant：24
- 现有 24-core Matrix 实际引用 Scenario：15

experiments/t17/scenario_measurements.yaml 为每个 T12 Scenario 冻结：

- 正常任务输出合同与任务 Artifact alias；
- 合法 Effect 与风险 Effect 的互斥集合；
- Authorization、Decision Basis、Provenance、Influence、Revocation 和
  Task Success Hook 要求；
- 基础指标及 HIAA、ALR、RIR、Causal Impact 的适用范围；
- S1 的 RESOURCE_SCOPE_EXCEEDED 与 L1 的 CROSS_SESSION_USE。

注册表通过真实 Scenario 和 ExperimentMatrix 模型展开，逐项验证 Artifact 与
Effect selector 已声明。S1_CONTROL 虽未进入现有 24-core Matrix，仍作为第 16 个
良性控制保留在完整注册表中。

