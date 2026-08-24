# T06 总结：双轨 Trace 与独立 Oracle

## 结论

T06 已完成。SkillFlow 现在为每次声明式 Run 同时生成 `observed-trace.jsonl` 和 `oracle-trace.jsonl`：Observed 是 Harness 实际记录、允许被缺陷模式破坏的待测平面；Oracle 是由 Scenario、受控 Manifest、Scripted action、Tool attempt 和 Mock Receipt 机械维护的独立真值平面。两者可以按实际 Artifact/Effect ID 对齐，但运行组件不能读取 Oracle，也不能把 Observed 标签或策略结果复制成答案。

本轮在 T06 停止。没有进入 T07，没有创建 NetworkX 来源图或路径查询；也没有提前实现 T08 正式 PolicyEngine、T09 指标、T10 checkpoint 或任何真实 Harness Adapter。

## 交付结构

| 组件 | 职责 | 明确禁止 |
|---|---|---|
| `ObservedTraceWriter` | 从 EventStore 与实际 `observed_label` 投影 Artifact/Effect | 读取 Oracle 或补全丢失标签 |
| `OracleDataState` | 从声明动作和稳定 ID 机械传播 `GT_data` | 回退读取 Artifact/Observed/EventStore |
| `OracleGrantResolver` | 以 Manifest + Grant 双钥匙计算 `GT_auth` | 接收 PolicyEngine、Stub Decision 或普通文本授权 |
| `OracleTraceWriter` | 只序列化 sidecar 真值 | 读取 Blob、Event metadata 或运行策略 |
| `oracle_bridge` | 在 Benchmark 边界投影 Manifest、action、attempt、Receipt ID | 把 Artifact 对象或 `observed_label` 交给 Oracle |
| `ToolActionAttempt` | 证明 allow/deny 请求都已产生 Tool argument | 把 deny 伪造成 Effect 或 Receipt |
| `ToolReceipt` | 锚定实际 Effect、call/action 与 argument/receipt/output ID | 由普通调用方直接构造 |

依赖方向固定为：

```text
Runtime / Observed  ──稳定事实投影──>  Benchmark oracle_bridge  ──>  Oracle

Runtime / Observed  <──────────────────── 禁止反向读取 ─────────────── Oracle
```

## GT_data：不从 Observed 自证

Oracle 在 Harness 启动前冻结 Scenario、Manifest 和 Scripted action。运行时只补入中立稳定 ID：

1. Scenario asset 注册为 `asset:<id>` 根值，并解析为规范 `workspace:` 来源；
2. 每个 Tool action 无论 allow/deny 都产生 `ToolActionAttempt`，Oracle 因此能记录对应 `TOOL_ARG`；
3. allow + Receipt 时，File/Memory 输出按 `LOAD` 或 `WRITE` 连接真实父值；
4. Receipt Artifact 与实际 Effect 通过 argument/output ID 和 `INVOKE` 关系连接；
5. Skill output 汇入显式输入和实际 Tool 数据输出，并加入 Skill 自身来源；
6. Scenario 的 `expected_origins` 只在最后校验机械结果，不能用于填补缺失来源。

受控父关系枚举固定为：

```text
COPY | DERIVE | WRITE | LOAD | INVOKE
```

良性读取场景的核心 Oracle 路径是：

```text
asset:report
  --LOAD--> file Artifact（实际 runtime artifact_id）
  --INVOKE--> benign_reader output（实际 runtime artifact_id）
```

最终 output 的 `GT_data` 为 `benign_reader` 与 `workspace:/documents/report.txt`。Observed 的同 ID 记录在 `preserve` 下与之吻合；`drop_on_derive` 会清空 Observed output origins，但 Oracle JSONL 逐条不变。

## GT_auth：与策略结果独立

`OracleGrantResolver` 的输入只有实际主体、结构化 Effect、已校验 Manifest permissions、Scenario Grants、当前 task/session/call/time 和可选撤销 Grant ID。它不接收 `DecisionRecord`，也不导入 Stub/PolicyEngine。

当前独立判定要求：

- Manifest 声明覆盖 Effect；
- 存在真实 Grant 覆盖同一主体、action、精确 source/sink 和 scope；
- Grant Lifetime 覆盖 Effect Lifetime，并只按自己声明的 `call | task | session | persistent` 边界匹配；
- Effect 位于 `valid_from <= time < expires_at`；
- Grant ID 在该时点未撤销。

测试把 Policy 结果分别设为 allow 和 deny，Oracle resolution 完全相等。授权 E2E 中，T05 Stub 的 `DecisionRecord.authorized=false`，而独立 Oracle 得到 `GT_auth=true`；这两个事实被分别保留，没有互相覆盖。

## GT_effect：只信 Mock Receipt

实际执行的 Effect 必须有 Mock Tool Adapter 签发的强类型 Receipt。Receipt 现在同时固定：

- `call_id` 与 `action_id`；
- `argument_artifact_id` 与 `receipt_artifact_id`；
- `effect_id`、`receipt_id`、request/result/decision ID；
- 实际 output Artifact IDs。

Oracle 只有收到与 executed attempt 一一对应的 Receipt 才写出 `GT_effect=true`。deny 路径仍会对齐 Tool argument，但两条 Trace 都没有 Effect 记录，Receipt 集合为空。

## 物理与依赖隔离

Oracle 源码位于独立 `src/skillflow/oracle/`。静态 AST 测试同时检查两侧：

- Adapter、Instrumentation、Runtime、Store、Observed Trace 不得 import `skillflow.oracle`；
- Oracle 不得 import Adapter、Instrumentation、Runtime、Store 或 `trace.observed`；
- Agent/Harness/Skill/Tool 可见签名中不出现 Oracle 类型。

Tool 参数模型被提升到中立 `models/tool_calls.py`，Instrumentation 的旧入口只做显式兼容导出。这样 Oracle 与被测 ToolProxy 可以解释同一封闭输入类型，但不会共享 Observed 的规范化函数或策略逻辑。

## 输出脱敏

双轨 JSONL 只输出结构化 ID、值类型、来源、父关系、能力字段、授权布尔值和 Receipt 引用。Writer 不读取 Blob，也不输出任意 Event metadata、Tool 参数正文或 Skill output 正文。E2E 使用 `T06_SECRET_MARKER` 和 `fixture completed` 两个哨兵，均未出现在任一 JSONL。

## TDD 与审计证据

1. 首轮先写 T06 测试，因 `skillflow.oracle` 不存在而在收集阶段红灯；
2. 核心实现后 8 项行为测试转绿；定向命令的非零仅来自全仓覆盖率门槛，不是行为失败；
3. 扩充四值 Lifetime、五类 Tool、Memory WRITE/LOAD、丢标、策略独立和隔离反例；
4. 审查发现 deny 虽无 Receipt 仍会生成 Tool argument，随后增加 `ToolActionAttempt`，保证该值也能对齐；
5. 编程规则审计发现 Runner 258 行，使用 `omo:refactor` 抽出 `oracle_bridge.py`；
6. lint 又发现 Sidecar 分支复杂度 13，继续拆出纯 `bindings.py`，复杂度和行为门禁同时转绿；
7. 最终规范复核又发现新增 Oracle 测试文件超过 250 行，以及 E2E JSON 类型过宽；将授权与数据测试拆分，并改用 `JsonValue` 边界解析后，专项行为保持不变；
8. 最终全量门禁通过后再提交和推送；没有用跳过测试、降低覆盖率阈值或删除既有测试换取绿灯。

## 最终验证

- T06 定向测试：**24 passed**；
- 全量 pytest：**165 passed**；
- 分支覆盖率：**88.48%**，高于当前 80% 门禁；
- Ruff lint：PASS；format check：**115 files already formatted**；
- mypy strict：PASS，**64 个源文件**无类型错误；
- Python no-excuse：PASS，**70 个本轮相关文件**无违规；
- `skillflow doctor`：Python、SQLite、运行依赖和临时目录检查全部通过；
- `pip check`：PASS，无损坏依赖；
- Oracle 依赖隔离、秘密哨兵与双轨稳定 ID 对齐：PASS。

## 明确限制

- 当前 Oracle Resource/scope 只支持 MVP 的精确覆盖；目录/模式 scope 与正式 reason codes 属于 T08；
- Resolver 可接收撤销 ID，但 `AUTH_REVOKE` 的运行编排、Grant EventStore View 和正式 PolicyEngine 属于 T08；
- 测试中的来源 Recall 只用于证明独立 Oracle 能观测丢标，不是 T09 正式指标实现；
- 没有来源图、图查询、边界深度或 NetworkX/JSON 图导出，这些属于 T07；
- 没有 Checkpoint、反事实 Replay、真实 LLM、网络、Shell、凭据或真实平台 Adapter。

## 停止点

T06 到此完成并停止。下一项是 T07，但本轮不会自动进入。
