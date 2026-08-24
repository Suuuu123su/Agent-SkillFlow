# T07 总结：来源图与路径查询

## 结论

T07 已完成。SkillFlow 现在可以只依赖 SQLite EventStore 中的持久事实，确定性重建 Artifact–Event 二部来源图和类型化 SecurityGraph，并对 Artifact、Principal、Grant、Decision 与 Effect 执行七类研究查询。每条返回路径都带有节点、语义边、Session 轨迹、证据 Event ID、Grant/Skill/Tool ID、撤销来源和五类边界深度，不再需要从日志文本猜测传播链。

Scenario Runner 现在还会在每次 Run 结束时自动生成脱敏 `security-graph.json`。导出不读取 Blob，不包含内容正文或任意 Event metadata，也不会把普通可达关系升级为 `INFLUENCE_CONFIRMED`。

本轮在 T07 停止。没有进入 T08，没有实现 Manifest/Grant 正式 matcher、PolicyEngine、稳定 reason codes、monitor/enforce 真值表或用户确认编排。

## 双层图结构

图的事实流固定为：

```text
SQLite EventStore（唯一事实源）
          │
          ▼
RunGraphFacts：Event / Artifact / Decision / Effect
          │
          ├── Event 投影 ──> Artifact–Event 二部来源图
          │                    Artifact --USED--> Event
          │                    Event --GENERATED--> Artifact
          │
          └── 安全投影 ──> Principal / Grant / Decision / Effect
                               + 封闭语义边
          │
          ▼
冻结的 NetworkX DiGraph ──> 七类查询 / 脱敏 JSON
```

两张图都在构建完成后冻结。公开属性返回的是再次复制并冻结的快照，调用方不能通过 NetworkX API 修改内部状态。图可以在数据库关闭、进程重启后重新构建；它不是第二套可变事实源。

### 类型化节点

| 节点 | 保留字段 | 刻意不保留 |
|---|---|---|
| Artifact | ID、类型、trust、创建 Session | Blob、正文、任意 metadata |
| Event | ID、EventType、Session、时间 | metadata、参数正文 |
| Principal | ID、保守推断的主体类型 | 动态权限或文本声明 |
| Grant | Grant ID | Grant 正文、未验证授权结论 |
| Decision | ID、authorized、executed | reason 文本和策略内部状态 |
| Effect | ID、action、executed | Tool 参数和 Receipt 正文 |

节点引用使用 `(kind, node_id)`，避免相同原始 ID 在不同节点类型间碰撞。面向用户的原始 ID 查询如果出现跨类型歧义会明确拒绝，而不是猜测端点。

## 封闭语义边

SecurityGraph 支持且只支持以下关系：

```text
READ | WRITE | LOAD | INVOKE | DERIVE | PERSIST
AUTHORIZE | INFLUENCE_CANDIDATE | INFLUENCE_CONFIRMED | REVOKE
```

T07 的普通 Event/Record 投影只会生成前八类、`INFLUENCE_CANDIDATE` 和 `REVOKE`。`INFLUENCE_CONFIRMED` 只在枚举合同中预留，当前没有生成路径。可达、时间先后或共享 Session 只能证明候选影响，不能替代后续反事实因果证据。

Grant、Decision 与 Effect 的连接是结构投影：

```text
AUTH_GRANT Event --AUTHORIZE--> Grant
Grant --AUTHORIZE--> Decision --AUTHORIZE--> Effect
TOOL_CALL_RESULT Event --INFLUENCE_CANDIDATE--> Effect
```

这不等于 T08 的授权正确性判断。T07 只回答“哪些持久事实和 ID 连接到该 Effect”，不回答“Manifest 与真实 Grant 是否合法覆盖该 Effect”。

撤销也不改写历史：

```text
Skill/Grant --REVOKE--> AUTH_REVOKE 或 SKILL_REVOKE Event
```

查询层另保留撤销发生时间。只有撤销时间不晚于目标路径的 Effect 时点时，才把对应祖先列为 `revoked_origin`；历史 Event、Artifact 和边保持不变。

## 七类查询

| API | 回答的问题 |
|---|---|
| `find_ancestors(artifact_id)` | 哪些上游节点能够到达该 Artifact？ |
| `find_paths(source_id, sink_id)` | 两个唯一类型化端点之间有哪些有限简单路径？ |
| `find_untrusted_paths(effect_id)` | 哪些 EventStore 明确标记为 untrusted 的 Artifact 可到达该 Effect？ |
| `find_authorization_path(effect_id)` | 哪些 AUTH_GRANT Event / Grant / Decision 结构路径连接到该 Effect？ |
| `find_revoked_ancestors(effect_id)` | 哪些在 Effect 时点前已撤销的来源仍能到达它？ |
| `find_cross_session_paths(run_id)` | 哪些根到 Effect 路径实际跨越了 Session？ |
| `find_skill_to_effect_paths(skill_id)` | 指定 Skill 可通过哪些候选影响路径到达 Effect？ |

每个 `SecurityPath` 返回：

- 按顺序排列的强类型节点与语义边；
- 按实际路径顺序压缩相邻重复后的 Session 轨迹；
- 去重但保持首次出现次序的证据 Event ID；
- `context / memory / session / skill / tool / total` 边界深度；
- 跨 Session 次数；
- revoked origin 与对应撤销 Event；
- 路径中的 Grant、Skill 与 Tool ID。

Session 计数不是全局集合大小。`Session A → B → A` 的轨迹保留为 `(A, B, A)`，因此记为两次跨越。

## 路径终止与资源边界

路径枚举使用显式 DFS 栈。每个候选路径都维护自己的 visited 集合，因此即使图中存在：

```text
Skill A → Event → Artifact → Event → Skill A
```

也不会把同一节点再次加入当前路径。查询同时有两层有限边界：

- 默认 `max_depth=64`，非正值明确拒绝；
- 单次最多物化 512 条简单路径。

这些限制保证环路不会无限执行，也防止高分支图无限占用内存。它们是资源边界，不是“被截断部分不存在”的研究结论。

## Golden 跨会话路径

T07 的集成 fixture 通过真实 `RuntimeRecorder`、`RunBlobStore` 和 `SqliteEventStore` 写入两次 Session：

```text
Skill A
→ SKILL_RETURN / Skill A output（untrusted）
→ MEMORY_WRITE / Persistent Memory
→ Session 2 的 MEMORY_READ / Context
→ SKILL_INVOKE / Skill B
→ SKILL_RETURN / Skill B output
→ TOOL_CALL_REQUEST / Tool argument
→ TOOL_CALL_RESULT / final Tool
→ Network Effect
```

同一 fixture 还写入：

- 在 Effect 前发生的 `SKILL_REVOKE(Skill A)`；
- 一个 `AUTH_GRANT` Event；
- Grant→Decision→Effect 关联；
- Blob 和 Event metadata 中的秘密哨兵；
- 可选的 Skill A 环路。

验收查询能够同时识别：

- 原始 `Skill A` 和传播后的 `Skill B`；
- 最终 `tool:http_send`；
- 恰好一次 Session 1→Session 2 转换；
- Context、Memory、Skill 和 Tool 各自的边界深度；
- 精确边界深度为 Context=1、Memory=2、Session=1、Skill=3、Tool=2、total=9，没有把同一 Event 的 Artifact 边和 Principal 边重复计数；
- Skill A 是 Effect 时点前已经撤销的来源；
- 关联 Grant ID 与 Grant Event；
- Golden 链中的全部因果 Event ID；
- 从 untrusted Artifact 到 Effect 的候选影响路径。

## 真实 Runner 断链修复

最初 Golden 查询全部通过，但真实 T06 Runner 在数据库重启后无法查询 `benign_reader → Effect`。这不是测试问题，而是 Runner 的真实事件顺序与 Golden 显式输入不同：Tool 请求发生在 Skill 返回之前，而且该请求没有 `input_artifact_ids`。

脱敏运行图给出的直接证据是：

```text
benign_reader → TOOL_CALL_REQUEST：不存在
TOOL_CALL_REQUEST → Effect：存在
```

只在内存中补上 actor Skill→请求 Event 后，`nx.has_path` 从 `False` 变为 `True`，最短路径成为：

```text
benign_reader
→ TOOL_CALL_REQUEST
→ TOOL_ARG
→ TOOL_CALL_RESULT
→ Effect
```

最终修复只对“没有显式输入 Artifact”的 Tool 请求补这条结构边。如果请求已有 Skill output 等显式输入，则继续沿 Artifact 传播，避免生成绕过完整 Golden 证据的捷径。

## JSON 导出与秘密边界

`ScenarioRunner` 在 Observed/Oracle JSONL 之后重开 EventStore 视图，调用 `SecurityGraph.from_store`，并写出：

```text
security-graph.json
```

导出使用 `SecurityGraphExport` 强类型白名单，不做任意对象序列化。测试把同一秘密哨兵同时放入 Blob 内容和 Event metadata，再验证：

- JSON 可以被 `SecurityGraphExport` 完整读回；
- 秘密哨兵不存在；
- `metadata` 字段不存在；
- fixture output 正文不存在；
- 同一输出路径已存在时拒绝覆盖。

GraphML 没有实现，按任务书保留为 T14 后的可选增强。

## TDD、重构与审计证据

1. 先写 Golden、七类查询、循环、最大深度、导出和依赖隔离测试；首次因 `skillflow.graph` 不存在而在收集阶段红灯。
2. 核心实现后，15 项定向测试中 14 项通过；唯一失败是实际 Runner 重启后的 Skill→Effect 路径为空。
3. 使用真实失败运行的脱敏 JSON 定位断点并完成内存开关证明；最小修复后原失败用例从红转绿。
4. 全部 15 项转绿后，编程规则审计发现 `event_projection.py` 与 `pathing.py` 超过 250 行。
5. 重构技能促使代码按职责拆分：普通事件投影与特殊 Principal/Grant/撤销投影分离，路径搜索与路径指标计算分离；没有改变公开 API。
6. NetworkX 类型桩暴露出运行时类不可直接下标的问题；改用仅供类型检查解析的字符串 TypeAlias，同时把 NumPy 开发约束固定在兼容 Python 3.11 类型目标的范围。
7. 最终语义复核发现全局 Session 去重会把 `A → B → A` 误算为一次；新增测试先红，再改成按顺序压缩相邻重复。
8. 增加导出防覆盖测试，确认第二次写入同一路径会返回强类型错误，不会覆盖已有证据。
9. 提交前逐边审计又以精确 Golden 深度测试暴露并消除了 Skill/Tool 边界重复计数；节点闭包测试也把 Principal/Grant/Decision/Effect 从 Artifact–Event 核心图移回上层 SecurityGraph。
10. T07 定向测试最终为 17 项；没有删除测试、放宽覆盖率、跳过 mypy 或依赖 Oracle 答案换取通过。

## 最终验证

- T07 定向测试：**17 passed**；
- 全量 pytest：**182 passed**；
- 分支覆盖率：**87.93%**，高于当前 80% 门禁；
- Ruff lint：PASS；
- Ruff format check：PASS，**138 个文件**格式一致；
- mypy strict：PASS，**78 个源文件**无类型错误；
- Python no-excuse：PASS，**25 个 T07 Python 变更文件**无违规；
- `skillflow doctor`：Python、SQLite、运行依赖和临时目录全部通过；
- `pip check`：PASS；
- 真实 Runner 手工 QA：`effect_reached=True`，2 条 Skill→Effect 路径中 1 条识别 `tool:read_file`，并成功生成 JSON 图；
- Golden 完整证据、环路终止、Runner 重启查询、Session 重新进入、图包依赖隔离和秘密哨兵：PASS。

## 明确限制

- Grant/Decision/Effect 目前只做事实连接，不做 T08 的权限覆盖判定；
- 没有 Manifest capability matcher、Grant scope matcher、PolicyEngine 或 reason code；
- `INFLUENCE_CANDIDATE` 不是因果确认，当前不会生成 `INFLUENCE_CONFIRMED`；
- 最多 512 条路径和默认深度 64 可能截断超大图结果，调用方必须显式解释该边界；
- 没有 T09 指标、T10 checkpoint、GraphML、真实 LLM、真实网络、真实 Shell、真实凭据或真实平台 Adapter。

## 停止点

T07 到此完成并停止。下一项是 T08，但本轮不会自动进入。
