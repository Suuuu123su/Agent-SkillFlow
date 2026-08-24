# ADR-0001：使用 Artifact–Event 二部图

- 状态：已接受
- 日期：2026-08-24
- 决策任务：T02

## 背景

SkillFlow 需要回答一个值如何经过 Context、Memory、Session、Skill 和 Tool 传播，并把最终 Effect 回溯到具体转换。只记录“当前对象来自哪个 Skill”无法表示多输入总结、版本更新、跨 Session Memory 读取，也无法区分数据与产生数据的动作。

## 决策

来源事实模型采用 Artifact–Event 二部图：

```text
Artifact --USED--> Event --GENERATED--> Artifact
```

- Artifact 是不可变数据版本；
- Event 表示读取、转换、持久化、调用、决策或效果；
- 每个输出 Artifact 有且仅有一个生成 Event；
- 多输入变换通过多个 `USED` 边表达；
- 更新 Context、Memory 或文件时创建新 Artifact，不改写旧节点；
- Principal、Grant、DecisionRecord 和 EffectRecord 通过各自 Event 映射到只读 `SecurityGraph` 投影视图；
- SQLite EventStore 是唯一事实源，NetworkX 图只是可重建查询视图。

## 理由

1. **可审计**：每个派生结果都能定位到具体 Event，而不是只有模糊标签。
2. **适合多输入**：总结、拼接和 Tool 参数构造可以保留所有父节点。
3. **版本明确**：Memory 或文件更新不会覆盖旧血缘。
4. **跨 Session 可表达**：新 Session 的读取 Artifact 可以连接旧 Memory Artifact。
5. **支持后续查询**：能够实现 ancestor、source-to-sink、revoked origin 和 skill-to-effect 路径。
6. **支持双轨对齐**：Observed 和 Oracle 可以在相同事件坐标上比较来源集合。

## 被否决方案

### 只在对象上保存 `source_skill_id`

无法表达多父节点、非 Skill 来源、跨 Session 版本和中间 Event；也会把直接来源误当作完整血缘。

### 只使用 Principal-to-Principal 调用图

能够说明“谁调用谁”，不能说明具体哪份数据经过哪些转换影响了哪个 Effect。

### 直接使用属性图作为可修改事实源

图节点和边容易被更新，难以保持 append-only 历史；也会让持久化层与分析层耦合。MVP 使用 EventStore 作为事实源，图只读重建。

## 后果

正面后果：

- 来源查询和证据导出有统一结构；
- 撤销可以追加 Event 而不删除历史；
- Provenance、CI、RIR 等指标能回到同一组 Event 和 Receipt。

代价：

- 节点数量高于原地更新模型；
- 所有转换都必须插桩；
- 图一致性需要测试“唯一生成 Event”和“不存在悬空 Artifact”。

## 验证要求

后续实现至少验证：

- 一个输出 Artifact 有且仅有一个生成 Event；
- 多输入变换保留全部输入边；
- Memory 跨 Session 读取连接旧 Artifact；
- EventStore 重建出的图和导出 Trace 哈希稳定；
- 撤销后旧节点和边仍可查询。
