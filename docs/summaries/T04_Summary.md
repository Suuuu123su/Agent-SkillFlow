# T04 总结：Append-only EventStore 与持久状态

## 结论

T04 已完成。SkillFlow 现在具备可审计、可重启的持久化底座：安全事件及输入输出关系追加写入 SQLite，Event、Decision 与 Effect 以一个事务提交；运行态内容进入按 Run 隔离的 BlobStore；默认 Trace 只导出结构化元数据和内容 hash，并在数据库重开前后保持稳定。

本轮没有进入 T05，也没有实现真实 LLM、网络、Shell、Harness、来源图计算、授权策略或风险指标。

## 同时补正的 T03 遗漏

任务说明书的 T03 段已补成自包含约束，不再允许按 `session | task` 的最小集合实现：

- Lifetime 固定且仅允许 `call | task | session | persistent`，未知值全部拒绝；
- `call` 只在相同 `call_id` 的当前 Skill/Tool 调用有效；
- `task` 只在相同 `task_id` 有效，但可以跨 Session；
- `session` 只在相同 `session_id` 有效；
- `persistent` 可跨 Task/Session，直到 `expires_at` 或对应 `AUTH_REVOKE`；
- `SecurityEvent` 与 `AuthorizationGrant` 都包含可选 `call_id`，`call` Grant 缺少它时拒绝；
- Lifetime 使用菱形偏序：`call` 同时窄于 `task`/`session`，`task` 与 `session` 互不包含，二者都窄于 `persistent`。

这些模型、Schema 和单元测试已在 T03 实现；完整运行期 Grant 匹配仍按计划留在 T08。

## T04 交付物

| 组件 | 作用 |
|---|---|
| `EventStore` Protocol | 固定追加、读取、Artifact、Memory、刷新和关闭合同 |
| `SqliteEventStore` | 管理 SQLite 生命周期与稳定读取 |
| `schema.sql` | 建立 12 张指定业务表、外键、唯一约束和追加保护触发器 |
| `EventEnvelope` | 原子提交 Event、输入输出边、Decision 与 Effect |
| `RunBlobStore` | 按 Run 隔离运行态字节，不接受调用方提供的文件路径 |
| `BlobRef` | 只暴露 Run、随机 Blob ID、内容 hash 和长度 |
| `MemoryHead` | 保存 Persistent Memory 的当前头，不改写历史事件 |
| `build_run_trace` | 生成不含 Blob 明文和任意 Event metadata 的稳定 Trace |
| `VirtualClock` | 由测试显式推进的可注入时间源 |
| `DeterministicIdFactory` | 同 seed、同调用序列产生可重放 ID |

## 持久化结构

SQLite 已建立任务书指定的全部业务表：

1. `runs`
2. `sessions`
3. `principals`
4. `artifacts`
5. `events`
6. `event_inputs`
7. `event_outputs`
8. `grants`
9. `decisions`
10. `effects`
11. `revocations`
12. `memory_heads`

`events` 使用自增序号保存追加顺序。`events`、`event_inputs`、`event_outputs` 不仅没有公共修改接口，SQLite 触发器也会拒绝 UPDATE 和 DELETE。`event_outputs.artifact_id` 唯一，因而一个输出 Artifact 只能有一个生成 Event。

## 原子性与一致性

一次 `append_event` 在单个 SQLite transaction 中完成：

```text
Event
  ├─ input edges
  ├─ output edges
  ├─ DecisionRecord（可选）
  └─ EffectRecord（可选）
```

任何引用错误都会回滚整个 Envelope。除外键和唯一约束外，写入前还验证：

- Decision 必须引用当前请求 Event，且 ID 与 Event 一致；
- Effect 必须引用当前请求 Event；
- Effect 的 Decision 必须是当前 Event 的 Decision；
- Effect 的能力内容必须与 Event 中的 `requested_effect` 一致；
- 输出 Artifact 声明的生成 Event 必须是当前 Event；
- 输出 Artifact 的 Blob 必须属于当前 Run。

Artifact 元数据按 EventStore 合同先单独登记，再由输出边绑定生成 Event。因此，本任务保证的是 Event、边、Decision、Effect 的 SQLite 原子性，不把 Artifact 与文件系统 Blob 夸大成跨介质原子事务。

## BlobStore 与安全 Trace

测试使用的实验根为 `runs/<experiment_id>/`。BlobStore 在其 `blobs/` 下按 Run 哈希建立命名空间，并使用 48 位十六进制随机 ID 作为文件名。公开 API 不接受任意路径；读回时同时检查 Run、SHA-256 和长度。

Trace 只保留事件结构字段、Artifact ID/类型/hash/长度/MIME、请求能力和 Decision ID。它不导出 Blob 内容，也不复制任意 `SecurityEvent.metadata`。Trace 对排序后的规范 JSON 求 SHA-256，因此同一持久事件序列在关闭、重开数据库后得到相同 hash。

## 跨 Session 与进程重启证据

端到端测试完成了以下链路：

1. Session 1 将一段测试秘密写入 BlobStore；
2. 登记 Memory Artifact、追加 Memory Write Event，并设置 Memory 头；
3. 关闭 SQLite 和 BlobStore；
4. 重新打开后，在 Session 2 读取同一个 Memory 头和 Blob；
5. 追加 Memory Read Event，并再次关闭、重开数据库；
6. 验证两条历史事件顺序不变、内容可恢复、Trace hash 不变且测试秘密不在 Trace JSON 中。

这证明的是 T04 的持久化与重开恢复，不等于完整 Runtime checkpoint/restore。后者仍属于 T10。

## TDD 与最终验证

核心接口、确定性组件、BlobStore、SQLite 约束和重启场景均先以缺失实现或反例得到失败，再补实现。最终审阅还增加了“Effect 错用历史 Decision 且能力不匹配”的反例；该测试先失败，随后通过 Envelope 一致性校验修复。

最终结果：

- 全量 pytest：**93 passed**；
- 分支覆盖率：**90.60%**；
- T04 定向测试：**28 passed**；
- Ruff lint：PASS；
- Ruff format check：PASS；
- mypy strict：PASS，27 个源文件无类型错误；
- no-excuse 规则审计：`store` 7 个文件、`runtime` 2 个文件均无违规。

## 架构自审

### 已满足

- 存储接口与 SQLite 实现解耦，后续可替换实现；
- SQLite 资源生命周期与无状态事务写入已拆分，单文件没有继续膨胀；
- 历史事实采用追加模型，唯一可变状态明确限制为 `memory_heads`；
- 内容存储、元数据存储和导出投影是三个独立边界；
- 错误使用类型化异常，不依赖模糊字符串作为公共合同；
- 测试覆盖正常写入、失败回滚、直接 SQL 篡改、跨 Run 引用和进程重启。

### 明确限制

- SQLite 与文件系统没有分布式事务；元数据登记失败时，已经落盘的 Blob 可能成为不可达文件。本轮没有自动删除任何文件；
- `grants` 和 `revocations` 目前只有持久化表，完整运行期授权与撤销逻辑属于 T08；
- `flush`/重开只证明持久化，不是 T10 的 Runtime checkpoint；
- 没有提前实现 T05。

## 停止点

T04 到此完成并停止。下一项是 T05，但必须由用户另行明确要求后才能开始。
