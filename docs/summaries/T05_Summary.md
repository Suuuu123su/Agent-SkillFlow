# T05 总结：安全 Mock Harness 与插桩代理

## 结论

T05 已完成。SkillFlow 现在能从受控 YAML Scenario 启动隔离 Run，以固定 fixture registry 驱动 Scripted Skill，经过显式 Tool 请求、Stub allow/deny、Mock 执行，最终得到由 Mock Tool Adapter 签发的强类型 Tool Receipt。整个链路不调用真实 LLM、不建立网络连接、不执行 Shell 子进程，也不访问注入 Workspace 之外的文件。

本轮在 T05 停止。没有进入 T06，没有创建 Oracle Trace，也没有提前实现 T08 授权匹配或 T10 checkpoint/restore。

## 交付物

| 组件 | 当前职责 |
|---|---|
| `HarnessAdapter` | 固定 `start_session`、`load_skill`、`invoke_skill`、`end_session` 四个最小方法 |
| `MockHarnessAdapter` | 建立 Session 局部代理，保留 Run 级 Memory/Skill 状态，驱动安全 Mock 调用 |
| `ScriptedBackend` | 只解析进程内白名单 fixture registry，不接受模块路径或任意代码 |
| `ScenarioRunner` | 校验 YAML、复制 fixture asset 到独占 Workspace、按 Session 编排 Harness |
| `InstrumentedContext` | `add`、`read`、`summarize` 每次都创建新 Artifact 和 Event |
| `InstrumentedMemory` | `write`、`read`、`delete`；跨 Session read 连接原 Memory Artifact |
| `InstrumentedFile` | 只在注入 Workspace 根下读写，规范化后再次拒绝路径逃逸 |
| `InstrumentedSkill` | 记录 install、load、invoke、return、revoke、unload 六段生命周期 |
| `InstrumentedTool` | 分阶段记录 request、decision、execute、receipt |
| `MockToolAdapter` | 实现五个普通 Mock Tool，并独占 Receipt 的 API 级签发能力 |
| `StubDecisionProvider` | 只按 fixture key 返回 allow/deny，不复制 T08 正式授权逻辑 |

## Harness 与状态边界

每次 `ScenarioRunner.run` 都要求一个尚不存在的 Run 根目录，并创建独立的 SQLite、BlobStore、Workspace、Context、MemoryState、SkillState、MockNetworkSink 和 MockShellSink。已有目录会被拒绝，避免覆盖用户内容或把旧状态混入新实验。

Context 只属于当前 Session。MemoryState 和 Skill 安装/撤销状态属于当前 Run，可以跨 Session；跨 Session Memory read 创建新 Artifact，并把上一 Session 的 Memory 版本作为父节点。完整 Runtime snapshot/restore 没有实现，仍留给 T10。

Skill 以自己的 `actor_id` 和 `call_id` 发起调用。Harness 只负责连接生命周期、Backend 和 Tool，不被当作 Skill 的默认 authority。Session 结束时，仍加载的 Skill 会先追加 unload Event，再追加 session end Event；历史记录不被删除。

生命周期 Event 同时保存结构化 `skill_id`；install 还保存受控 `fixture://` implementation 引用。Memory、File 和 Tool Event 分别保存 key、规范化 resource 或 Tool 名，确保后续图构建能识别事件目标。T04 的默认 Trace 仍不导出任意 metadata，因此这些内部索引不会绕过脱敏投影。

## Tool 执行链

实际顺序固定为：

```text
ToolCallRequest
→ 白名单参数规范化为 CapabilityEffect
→ TOOL_ARG Artifact + TOOL_CALL_REQUEST
→ StubDecisionProvider(fixture key)
→ TOOL_CALL_ALLOW 或 TOOL_CALL_DENY
→ 仅 allow 时进入 MockToolAdapter
→ File/Memory 转换或 Network/Shell 内存记录
→ DecisionRecord + EffectRecord + TOOL_RETURN Receipt Artifact
→ TOOL_CALL_RESULT
```

普通 Tool 名称严格封闭为：

- `read_file`
- `write_memory`
- `read_memory`
- `http_send`
- `shell_exec`

`user_confirm`、`revoke_skill` 不在普通 Tool 枚举中。Skill 只能获得 `InstrumentedTool`，拿不到 `BenchmarkController`；撤销和卸载由 Benchmark 可信主体入口调用。T05 Stub 明确拒绝 `confirm`，结构化确认和 Grant 留给 T08。

## Receipt 与副作用约束

`ToolReceipt` 是冻结、禁止普通构造的强类型对象。只有 `MockToolAdapter` 持有签发器并在 Mock Effect 已执行后创建它；Receipt 与 `EffectRecord` 共享 request、decision、result 和 effect 标识。该边界是 MVP 的进程内 API 约束，不宣称密码学不可伪造性。

HTTP 和 Shell 的“执行”只向内存 Sink 追加结构化记录。Shell 测试使用了一个若被真实执行就会创建哨兵文件的命令，最终哨兵不存在；实现中没有 `subprocess`、`os.system` 或网络客户端调用。Denied Tool 只保留请求和拒绝 Decision，不写入 Effect 表，也不产生 Receipt Artifact。

## EventStore 一致性补强

T05 的最终 Tool 结果 Event 需要携带指向较早请求 Event 的 Decision 与 Effect，因此扩展了 T04 的 Envelope 校验，使请求 Event 和结果 Event 可以分离。同时增加反例：即使两个请求都真实存在，也不能让 Decision 指向请求 A、Effect 指向请求 B，再拼成同一个结果 Event。该反例先失败，随后通过“Decision 与 Effect 必须共享 request_event_id”的写入前校验修复。

Memory delete 只删除可变 `memory_heads` 当前投影，所有历史 Event、Artifact 和 Blob 引用仍保留。

## TDD 证据

本轮按边界逐层得到红灯后再补实现：

1. 包、模块、公开类型缺失：先出现 1、12、12 个合同失败，再建立职责边界；
2. Context/Memory/File 行为缺失：5 个集成失败转为 5 个通过；
3. Tool 类型、Stub 与 Receipt 缺失：合同和直接构造测试先失败，再转绿；
4. Tool 完整链缺失：5 个集成失败转为 5 个通过；
5. Skill 生命周期与 YAML Runner 缺失：4 个失败转为 4 个通过；
6. EventStore 请求错绑反例：先确认没有抛错，再补一致性校验并通过；
7. Skill 生命周期事件缺少目标标识：新增 metadata 断言先失败，再补齐结构化事件目标；
8. Tool 模块超过 250 行规则后，拆出 `decision_stub.py` 与 `tool_effects.py`，回归测试保持通过。

## 最终验证

- 全量 pytest：**141 passed**；
- 分支覆盖率：**89.19%**，高于当前 80% 门禁；
- T05 定向测试：**47 passed**；
- Ruff lint：PASS；
- Ruff format check：PASS；
- mypy strict：PASS，46 个源文件无类型错误；
- Python no-excuse 规则审计：46 个源文件无违规；
- 相同 Scenario、seed、虚拟时间的两次独立 Run：Trace hash 相同；
- 路径逃逸：拒绝；
- Denied Tool：Effects 表计数为 0，且无 Receipt；
- Shell 哨兵：未创建；
- YAML 良性场景：成功到达 `TOOL_CALL_RESULT` 和 Tool Receipt。

## 明确限制

- `StubDecisionProvider` 不是授权策略，只能作为 T05 fixture seam；
- Scenario 顶层的通用 `write_memory`、`read_memory`、`request_tool` 和 `restart_runtime` 步骤在 T05 没有足够参数，Runner 会显式拒绝；Tool 动作由注册的 FixtureScript 描述；
- `execution.mode` 的完整 monitor/enforce 真值表、Manifest/Grant matcher、confirm 和稳定 reason codes 属于 T08；
- 没有 Observed/Oracle 双轨输出；这属于 T06；
- 没有 Runtime checkpoint/restore；这属于 T10；
- 没有真实 LLM、网络、Shell、凭据或真实 Harness Adapter；真实 Pilot 仍受 T15 单独批准门控。

## 停止点

T05 到此完成并停止。下一项是 T06，但本轮不自动进入。
