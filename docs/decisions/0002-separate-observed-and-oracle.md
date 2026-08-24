# ADR-0002：严格分离 Observed Plane 与 Oracle Plane

- 状态：已接受
- 日期：2026-08-24
- 决策任务：T02

## 背景

SkillFlow 要评估 Harness 插桩记录的来源是否正确。如果使用 Observed 标签本身作为 Ground Truth，来源丢失、错误升级或错误授权会被系统自我证明为正确，指标失去意义。

## 决策

每次运行维护两个物理和依赖关系上隔离的平面：

- **Observed Plane**：Harness 实际记录的 Artifact、标签、Event 和决策证据，是被评估对象；
- **Oracle Plane**：Benchmark sidecar 根据声明式场景真实步骤机械维护 `GT_data`、`GT_auth` 和 `GT_effect`。

Agent、Skill、PolicyEngine、Observed 图构建器不得导入、读取或依据 Oracle 做运行决策。Oracle 不从 Observed 复制标签，也不使用 Observed 来填补缺失来源。

## 理由

1. **避免自证**：被评估标签不能同时充当答案。
2. **能测来源丢失**：`drop_on_derive`、`drop_on_memory` 只破坏 Observed，Oracle 保持真值。
3. **能测错误授权**：真实 Grant 与 Harness 的文本授权行为可以独立比较。
4. **可机械复现**：Scripted 场景的真值来自明确步骤，不依赖 LLM Judge。
5. **支持 Golden Test**：每个指标可对照固定的 Oracle 路径、Effect 和授权集合。

## 被否决方案

### 直接把 Observed 来源当 Ground Truth

会让来源丢失无法被发现，并把错误 trust/authority 升级纳入“正确答案”。

### 使用 LLM-as-Judge 生成来源或攻击成功真值

判断不可机械复现，且 Judge 可能读取与被测系统相同的错误证据。MVP 只接受场景 sidecar 和 Mock Receipt。

### 运行后从 Trace 人工补 Oracle

容易受到结果偏见，无法保证大规模运行的一致性。人工只审阅预注册场景和 Golden 预期，不逐次重写真值。

## 后果

正面后果：

- Provenance Precision/Recall/F1 有独立参照；
- 未授权 Effect、ALR 和 RIR 可由 Grant 真值与 Receipt 交叉验证；
- 故意的 Observed 缺陷模式不会污染答案。

代价：

- 同一场景需要维护两套状态；
- 必须增加导入隔离和运行时不可访问测试；
- 场景 Loader 必须拒绝矛盾或缺失的 Oracle alias。

## 验证要求

后续实现至少验证：

- PolicyEngine 和 Agent 侧没有 Oracle 依赖；
- Observed 来源被故意丢弃时 Oracle 不变；
- Oracle 引用无效 Artifact/Effect alias 时场景加载失败；
- 指标只从 Oracle 评价 Observed，不允许 Observed 自评；
- Oracle 文件不进入 Agent 可见 Context、Memory 或 Tool Return。
