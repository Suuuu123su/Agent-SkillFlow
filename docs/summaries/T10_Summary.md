# T10 总结：Checkpoint 与反事实重放

## 结论

T10 已完成。SkillFlow 现在可以在声明式 Scenario 的 Artifact 输出边界暂停执行，冻结完整运行态，并从同一个 checkpoint 恢复两条互相隔离的分支：

```text
共同前缀 ── checkpoint ── identity 派生 ── 原始后缀 ── Effect/Receipt
                     └── neutral 派生  ── 中和后缀 ── Effect/Receipt
```

两分支使用不同 `run_id` 和独立的 SQLite、Blob、Workspace，但恢复后的规范化 Trace 前缀哈希与完整状态哈希相同。Replay 只比较 Effect selector 命中的已执行 `EffectRecord`，并要求每个结果有同分支真实 `ToolReceipt`；自然语言输出、时序相关性和普通来源图都不能生成 `INFLUENCE_CONFIRMED`。

本轮在 T10 停止。没有实现 T11 的 HIAA、ALR、RIR，也没有接入真实 LLM、网络或 Shell。

## 完整 Checkpoint 合同

`CheckpointableHarnessAdapter` 在最小 `HarnessAdapter` 之上独立增加：

```python
checkpoint() -> HarnessCheckpoint
restore(checkpoint: HarnessCheckpoint) -> None
```

普通 Harness 的四个最小方法没有被扩大。`HarnessCheckpoint` 冻结以下状态：

| 状态类别 | 冻结内容 |
|---|---|
| EventStore/Blob | 有序 Event Envelope、Artifact 元数据和私有内容、Decision、Effect、Grant、撤销、Memory 头 |
| Workspace | 根目录内普通文件的相对路径、内容哈希、长度和 checkpoint 私有内容 |
| Context | 当前 Session 的 Artifact 顺序 |
| Memory | Run 级 key→Artifact 头 |
| Skill | 安装绑定、撤销集合、当前加载集合、活动调用集合 |
| Tool | Mock Network 和 Mock Shell 的结构化记录 |
| 授权 | 初始 Grant 是否已注册，以及 Store 中的全部 Grant/撤销事实 |
| 确定性 | 虚拟时间、ID seed 和各命名空间计数器 |
| 编排器 | Session/step 游标、Alias 绑定、已有输出和 Receipt |

Checkpoint 只允许在没有未完成 Skill 调用的静止 step 边界创建。恢复目标必须是一个全新的空分支；恢复过程重新写入逻辑 Store、复制 Blob 内容并重建 Workspace，不修改源分支。

### 两级哈希

- `prefix_hash`：规范化 Event/Artifact/Decision/Effect/Grant/撤销和 Memory 头；分支 `run_id` 被占位符替换。
- `state_hash`：在 `prefix_hash` 上继续覆盖 Context、Memory、Skill、Tool、虚拟时间、ID 计数、授权注册状态和 Workspace 摘要。

宿主路径、随机 Blob 文件名和 Artifact 正文不进入哈希。恢复后会立即重新捕获状态；任一哈希不等于源 checkpoint 都会拒绝继续。

## 可恢复 Scenario 编排

原有一次性 Runner 被拆为可恢复的 `ScenarioExecutor`，但 `ScenarioRunner` 的公开导入和行为保持不变。执行器支持：

- `run_until_alias(alias)`：执行到目标 Artifact alias 产生后暂停，并保持当前 Session 活动；
- `snapshot()`：冻结下一个 step 的游标、Alias→Artifact 绑定、输出和 Receipt；
- `replace_alias(alias, artifact_id)`：仅替换反事实目标的活动版本；
- `run_all()`：从当前游标继续执行剩余后缀并正常结束 Session。

这一设计避免重跑 checkpoint 之前的步骤，也避免通过场景 ID、删除 Skill 或手工跳步伪造反事实。

## Artifact 中和语义

每条恢复分支都追加一个新的 `ARTIFACT_DERIVE`：

- 原始分支使用 `identity`，派生内容与源内容相同；
- 中和分支使用 `neutral`，只去除目标内容的触发语义；
- 源 Artifact、历史 Event、Skill、Grant 和其他输入均不删除、不覆盖；
- 两个派生版本保持相同 Artifact 类型、MIME 和精确内容长度；
- JSON 使用同键、同容器和同标量种类的递归中和值，并在需要时以空格补齐长度；这里的 Schema 指可机械验证的结构 Schema，不是任意外部 JSON Schema；
- 文本用等长空格，其他二进制内容用等长零字节；零长度 Artifact 没有可定义的 neutral 形式，因此显式拒绝。

T10 的 JSON Golden fixture 中，`{"enabled":true }` 被中和为等长、仍可解析的 `{"enabled":false}`。两分支从相同 ID 计数器恢复，因此派生 Artifact ID 可直接对齐；分支数据库和 `run_id` 保持隔离，内容哈希则按预期不同。

## Effect、CI 与确认影响边

Scripted 配对固定使用：

```text
y_original = 原始分支是否存在 selector 命中的已执行 Effect/Receipt
y_neutral  = 中和分支是否存在 selector 命中的已执行 Effect/Receipt
CI         = int(y_original) - int(y_neutral)
```

`CI` 的类型域严格为 `-1 | 0 | 1`：

| 配对结果 | CI | 允许的结论 |
|---|---:|---|
| 原始有 Effect，中和无 Effect | 1 | 对消失的 Effect 建立 `INFLUENCE_CONFIRMED` |
| 两边相同 | 0 | 不建立确认边 |
| 原始无 Effect，中和新增 Effect | -1 | 对新增的 Effect 建立 `INFLUENCE_CONFIRMED` |

确认边只能从被干预的源 Artifact 指向机械计算出的 removed/added Effect。报告模型会拒绝以下不一致：相同分支 `run_id`、错误 CI、错误 Effect diff、零 CI 携带确认边，或确认边指向非差异 Effect。

## 正因果与负对照 Golden Test

同一 Scenario 预注册两个 counterfactual：

1. `cause` 是 consumer 的第一个输入。原始内容选择 `allow-original`，中和后选择 `deny-neutral`。
2. `irrelevant` 是第二个输入。中和它不会改变 consumer 对第一个输入的判定。

结果固定为：

| 目标 | y_original | y_neutral | CI | 确认边 |
|---|---:|---:|---:|---|
| `artifact:cause` | true | false | 1 | 1 条 |
| `artifact:irrelevant` | true | true | 0 | 0 条 |

该 fixture 使用 `monitor`，是为了单独验证 Scripted 内容门控与 Effect 因果差异：Skill 输出保持 `UNTRUSTED`，正式 policy 仍会记录来源拒绝；结构化 Grant 使原始 baseline 允许，monitor 只按 baseline 执行。两分支的 Grant、Manifest、policy、Tool 集合和来源状态完全相同，唯一变化是目标 Artifact 的派生内容。

## Replay 产物与泄漏边界

每个 counterfactual 目录独占创建：

- `replay-report.json`：原始/中和 run ID、干预 Artifact ID、两边 Effect ID、removed/added diff、`y_original`、`y_neutral`、CI 和确认边；
- `pair-manifest.json`：checkpoint ID/哈希、两分支恢复哈希、控制条件摘要、干预结构摘要和 Effect diff。

控制条件摘要覆盖 seed、Script、Decision、Manifest、Grant、虚拟时间和 checkpoint 状态。输出只保留允许的 ID、枚举、长度和 SHA-256，不包含 Artifact 正文、Tool 参数正文、Blob ID 或宿主绝对路径。两个完全不同的新输出根在相同 Scenario/seed 下生成的报告和清单逐字节一致。

## 主要实现位置

- `src/skillflow/adapters/checkpoint.py`、`mock_checkpoint.py`：完整 Harness checkpoint、规范化哈希和恢复验证；
- `src/skillflow/store/checkpoint.py`、`runtime/workspace_checkpoint.py`：Store/Blob 与 Workspace 的逻辑导出、隔离导入；
- `src/skillflow/benchmark/scenario_execution.py`：可暂停、快照、Alias 替换和后缀恢复；
- `src/skillflow/instrumentation/artifact_intervention.py`：identity/neutral 结构保持派生；
- `src/skillflow/benchmark/replay.py`：source/original/neutral 分支编排；
- `src/skillflow/benchmark/replay_analysis.py`：真实 Receipt 匹配、Effect diff、CI 和确认边；
- `src/skillflow/benchmark/replay_models.py`：报告外的分支证据与控制条件合同；
- `tests/e2e/test_t10_counterfactual_replay.py`：正因果、无关负对照、泄漏和字节确定性 Golden Test。

## TDD、回归与质量证据

1. `ReplayRunner` 尚不存在时，T10 E2E 先以 `ModuleNotFoundError` 红灯，证明测试不是对既有路径的空断言。
2. Checkpoint 单元/集成测试先固定完整状态清单、不同 run ID、空恢复根和源分支隔离，再实现捕获与恢复。
3. 首次成对运行得到 `CI=0`，实际 Decision 证据显示 `UNTRUSTED_ORIGIN` 在 enforce 下阻断原始 Effect；Golden fixture 明确改用 monitor 隔离内容门控，同时保留 policy 拒绝事实，没有放宽生产策略。
4. 正因果与无关负对照转绿后，第二个全新输出根的报告与清单逐字节相同。
5. T05–T09 端到端定向回归：**13 passed**。
6. 整理后的 T10 单元、集成和端到端专项：**21 passed**。
7. 最终全量门禁：

   - pytest：**275 passed**；
   - 分支覆盖率：**89.39%**，高于当前 80% 门禁；
   - Ruff lint：PASS；
   - Ruff format：PASS，**204 个 Python 文件**格式一致；
   - mypy strict：PASS，**116 个源文件**无类型问题；
   - T10 变更 Python no-excuse：PASS，**26 个文件**无违规；
   - CLI help、`skillflow doctor`、`pip check`：PASS。

## 明确限制与停止点

- 当前只有确定性 Scripted Backend 可以生成 `INFLUENCE_CONFIRMED`；真实 LLM Pilot 必须等待 T15 的人工门控和预注册统计阈值。
- JSON 中和保持键、容器、标量种类和可解析性，但不是通用 JSON Schema 求解器；若中和值无法在源长度内编码，会显式失败。
- Replay 当前针对 Scenario 中的 Artifact alias；Memory 和授权的运行状态已完整进入 checkpoint，但它们的专用中和 DSL 尚未扩展。
- Pair 输出采用 `schema_version=0.1`，正式公开发布前仍需版本迁移策略。
- 所有 HTTP 和 Shell 继续使用进程内安全 Mock，不产生真实外部副作用。
- T10 到此完成并停止；T11 保持 pending。
