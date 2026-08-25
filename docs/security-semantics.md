# SkillFlow 安全语义

## 1. 文档状态与规范词

- 任务：T02
- 状态：已冻结
- 适用实现：T03～T14 的确定性 MVP

本文使用“必须”“不得”“仅当”表达规范要求，使用“可以”表达允许但非强制的实现选择。若本文与任务书冲突，以 `SkillFlow_Codex_Task_Spec.md` 为准；若后续需要改变任务书第 1、2 节边界，必须先向用户确认。

## 2. 语义对象与事实源

### 2.1 Principal

MVP 至少有 `USER`、`TRUSTED_POLICY`、`HARNESS`、`SKILL` 和 `TOOL` 五类 Principal。

- 每个 Skill 必须拥有独立 `principal_id`。
- Harness 是连接主体、数据面和执行能力的桥接层，不是默认授权主体。
- 只有 `USER` 或 `TRUSTED_POLICY` 可以成为 Grant 的 issuer。
- Tool Receipt 由受控 Mock Tool Adapter 创建，不能由 Skill 创建。

### 2.2 不可变 Artifact 与追加 Event

Artifact 表示一个不可变的数据版本。任何复制、拼接、总结、Memory 读取或文件更新都必须创建新 Artifact，并通过 Event 连接父 Artifact；不得原地改写历史血缘。

SQLite EventStore 是运行事实的唯一来源。`SecurityGraph`、报告、`revoked_at` 等都是只读投影，不能反向修改历史记录。

### 2.3 Effect 的三个阶段

| 阶段 | 记录 | 含义 |
|---|---|---|
| 请求 | `TOOL_CALL_REQUEST` + `CapabilityEffect` | 某主体申请产生结构化效果 |
| 决策 | `DecisionRecord` | baseline、policy、authorized 和 executed 的判断 |
| 结果 | `EffectRecord` + Tool Receipt | Mock Tool 是否实际产生了效果 |

请求存在不等于效果已经发生；`policy_result=ALLOW` 也不等于存在 Receipt。

## 3. 三种 Provenance 必须分开

| 关系 | 核心问题 | 权威证据 | 允许的结论 |
|---|---|---|---|
| 数据来源 `data provenance` | 这个 Artifact 从哪里派生？ | Artifact–Event 血缘、SecurityLabel | 能回溯 origins 和父 Artifact |
| 决策影响 `decision influence` | 某输入是否实际改变了敏感动作？ | 候选依赖 + 能力匹配的反事实 Replay | candidate 或 confirmed influence |
| 授权来源 `authorization provenance` | 谁有权批准这个 Effect？ | 结构化、有效且匹配的 Grant | authorized 或 unauthorized |

这三类关系必须使用不同字段、事件和边类型，不得压缩为一个 `source`、`trusted` 或 `authorized_by_text` 字段。

### 3.1 数据来源

基础二部图为：

```text
Artifact --USED--> Event --GENERATED--> Artifact
```

对 Artifact 的处理规则：

- 复制：保留全部 origins、父 Artifact 和最保守 trust。
- 拼接或总结：origins 与 parent IDs 取并集，trust 取最保守等级。
- 写入 Memory：创建新 Artifact 和 `PERSIST` 关系，不删除输入来源。
- 新 Session 读取 Memory：创建当前 Session 的新 Artifact，并连接原 Memory Artifact。
- 普通 Skill 不得清空 origins、提升 trust 或删除 parent IDs。

Observed Plane 可以在实验缺陷模式下丢失来源；Oracle Plane 始终按真实场景步骤机械传播。

### 3.2 决策影响

某 Artifact 被读取、与请求同时出现或位于请求上游时，只能标记 `INFLUENCE_CANDIDATE`。

仅当以下条件全部成立时，才能标记 `INFLUENCE_CONFIRMED`：

1. 原运行和中和运行来自同一预注册 Replay 对；
2. 中和保持类型、Schema、Manifest、Grant、工具集合、近似长度和 seed；
3. 只改变目标输入的攻击语义，不删除整个 Skill；
4. Mock Tool Receipt 的目标 Effect 结果发生变化。

时序先后、字符串相似度、共同出现或 LLM-as-Judge 都不能单独确认因果影响。

### 3.3 授权来源

授权来源只由结构化 `AuthorizationGrant` 和对应的 `AUTH_GRANT` Event 建立。以下内容一律只是普通数据：

- Skill Manifest；
- Skill 文档或输出；
- Context、Memory、网页内容；
- Tool Return；
- 文本“用户已批准”“管理员允许”“系统策略要求”。

这些文本可以记录为 `AUTH_CLAIM_OBSERVED`，也可以成为 `decision_basis_artifact_ids`，但不得创建 Grant 或升级 authority。

## 4. Trust 与 Authority 分离

`SecurityLabel.trust` 描述数据可信程度，Grant 描述批准 Effect 的权力。二者没有自动转换关系：

```text
high_trust(data)  != can_authorize(data)
low_trust(data)   != automatically_malicious(data)
```

- 一个高可信 Tool Return 仍不能授权新的 Shell 或网络动作。
- 一个低可信 Artifact 可以被真实 Grant 覆盖的流程合法处理。
- `USER` 输入只有通过 Benchmark 特权接口转化为结构化 Grant 时才提供 authority；普通聊天文本仍是 Artifact。

## 5. Manifest 与 Grant 的双钥匙语义

| 属性 | Skill Manifest | AuthorizationGrant |
|---|---|---|
| 表达内容 | Skill 声明需要或可能使用的能力上限 | 用户或可信策略对具体主体、动作和范围的授权 |
| 提供 authority | 否 | 是 |
| 签发者 | Skill 包或场景配置 | 仅 `USER` / `TRUSTED_POLICY` |
| 是否足够执行 | 否 | 否，仍需 Manifest 声明 |
| 是否受 task/session/time/revoke 约束 | 声明静态上限 | 是 |

Effect `e` 被授权，当且仅当存在 Grant `g`，同时满足：

```text
authorized(e) :=
  manifest_declares(actor(e), e)
  AND g.issuer_type IN {USER, TRUSTED_POLICY}
  AND g.grantee_id matches actor(e)
  AND g.action == e.action
  AND g.source_pattern covers e.source
  AND g.sink_pattern covers e.sink
  AND scope_covers(g.scope, e.scope)
  AND boundary_matches_by_lifetime(g, e)
  AND g.valid_from <= effect_time
  AND (g.expires_at is absent OR effect_time < g.expires_at)
  AND no effective AUTH_REVOKE exists before effect_time
```

其中 lifetime 边界匹配固定为：

```text
call       -> g.call_id == current_call_id
task       -> g.task_id == current_task_id
session    -> g.session_id == current_session_id
persistent -> 不限制 task_id / session_id / call_id
```

`persistent` 仍受 `expires_at` 和 `AUTH_REVOKE` 约束。Grant 中保留的其他 ID 只记录签发上下文，不能被错误地叠加成额外 lifetime 边界。

Lifetime 是菱形偏序：`call` 同时窄于 `task` 与 `session`；`task` 和 `session` 互不包含；二者都窄于 `persistent`。禁止按枚举顺序或字符串大小实现。

首版 Scope 固定为 `exact-file | exact-key | exact-sink | command`，四者构成离散反链：每个值只覆盖自身。资源覆盖使用规范化 URI 的精确相等，不允许用字符串前缀伪造目录、Key 或 Sink 包含关系。未来如要支持目录或模式 Scope，必须先扩展模型和偏序，不能悄悄改变当前含义。

匹配失败必须保留结构化 reason code。T08 已把 Resource、Scope、Lifetime、时间、撤销和来源检查落实为独立 matcher 与 PolicyEngine；实现不读取 Oracle。

## 6. DecisionRecord 的四个独立事实

`DecisionRecord` 必须同时保存：

| 字段 | 含义 | 不得混同为 |
|---|---|---|
| `baseline_result` | 未加固实验 Harness 原本会 `ALLOW`、`DENY` 或 `CONFIRM` | 真实授权 |
| `authorized` | Manifest 与有效 Grant 是否覆盖 Effect | 是否已执行 |
| `policy_result` | SkillFlow 策略建议 | Harness 原行为 |
| `executed` | 在当前 mode 下 Mock Tool 是否实际执行 | policy allow |

固定决策语义：

```text
monitor:
  baseline_result == ALLOW  -> executed=true
  authorized 可以为 false

enforce:
  baseline_result == ALLOW AND policy_result == ALLOW -> executed=true
  其他情况 -> executed=false
```

因此：

- `monitor` 只表示观察而不阻断，绝不能把未授权动作改写为已授权；
- `auto_approve_tools=true` 只是脆弱 Harness 行为，不创建 Grant；
- `implicit_text_authorization=true` 只允许基线受文本影响，并必须记录对应 Artifact，不创建 Grant；
- `executed=true` 的最终证据仍是 Mock Tool Receipt。

## 7. Task、Session 与持久状态

### 7.1 边界定义

- `run_id`：一次声明式场景执行的唯一实例。
- `call_id`：一次 Skill/Tool 调用边界；仅 `call` lifetime 要求精确匹配。
- `task_id`：授权和业务目标边界；仅 `task` lifetime 要求精确匹配，可以跨 Session。
- `session_id`：一次 Harness 会话边界；Context 默认在 Session 结束时失效。
- `session` lifetime：仅要求相同 `session_id`，与 `task` lifetime 互不包含。
- `persistent` lifetime：可以跨 Task 和 Session，直到过期或被 `AUTH_REVOKE`。
- Persistent Memory：可以跨 Session 存在，但不自动携带 authority。

### 7.2 跨 Session

同一 task 内从旧 Session 读取 Memory 时必须：

1. 创建新的当前 Session Artifact；
2. 把旧 Memory Artifact 放入 `parent_artifact_ids`；
3. 保留旧 Artifact 的全部 origins；
4. 把 `created_session_id` 设为当前 Session；
5. 通过 Event/边记录 `MEMORY_READ` 和跨 Session 关系；
6. 单独重新判断当前 Effect 的 Grant、session、time、lifetime 和 revoke 状态。

旧 Session 的 Grant 不因数据进入 Memory 而延长。`lifetime=session` 必须精确匹配当前 `session_id`；`lifetime=task` 可跨 Session，但必须匹配当前 `task_id`；`lifetime=call` 不能跨调用；`lifetime=persistent` 可跨 Session，但仍受时间和撤销约束。

### 7.3 跨 Task

MVP 的跨 Task 规则按 lifetime 区分：

- `lifetime=call` 只匹配原 `call_id`，不能跨调用；
- `lifetime=task` 的 `task_id` 必须与当前 task 完全相等；
- `lifetime=session` 只按 `session_id` 匹配，不与 `task` lifetime 互相包含；
- `lifetime=persistent` 可以跨 Task 和 Session，直到 `expires_at` 或 `AUTH_REVOKE`；
- 旧 task 的普通文本授权声明、Manifest、Decision 或 Tool Return 不能授权新 task；只有仍在有效期内且未撤销的 `persistent` 结构化 Grant 可以跨 Task；
- 如果声明式场景显式允许读取跨 task Persistent Memory，必须创建当前 task 的新 Artifact、连接旧父 Artifact 并保留 origins；
- 新 Artifact 的 `task_id` 记录当前消费 task，原创建 task 仍可由父链回溯；
- Context 默认不跨 task；跨 task 数据只能经过显式持久化边界；
- 跨 task 读取保留数据来源，但只可使用当前 Effect 明确匹配的有效 Grant；不得把数据传播本身解释为授权传播。

T02 不引入跨 run 的隐式全局状态。任何跨 run fixture 必须由 Benchmark 显式声明，不能成为生产状态假设。

## 8. Revoke、Unload 与 Delete

| 操作 | 从何时生效 | 对未来执行的影响 | 对历史的影响 |
|---|---|---|---|
| `SKILL_UNLOAD` | Event 时间 | 移除当前可执行实现 | 不撤销来源、不删除 Memory、不改历史 |
| `SKILL_REVOKE` | Event 时间 | 禁止该 Principal 后续直接调用；派生物标记 revoked origin | 不删除旧 Event、Artifact 或边 |
| `AUTH_REVOKE` | Event 时间 | 目标 Grant 对后续 Effect 失效 | 不追溯改写先前授权判断或 Effect |
| `MEMORY_DELETE` | Event 时间 | 后续普通读取不再得到被删除的当前 Memory 头 | 追加删除 Event，历史版本与来源仍可审计 |

撤销后的派生传播规则：

```text
if artifact origins contain revoked skill S at derivation time:
    S must appear in revoked_origins of the new artifact
```

`revoked_origins` 是来源状态，不等于该 Effect 必然未授权；最终仍需对发起主体和当前 Grant 做完整匹配。RIR 只统计撤销后实际发生、未授权且能由 Oracle 路径或确认影响归因于该 Skill 的 Effect。

## 9. Observed Plane 与 Oracle Plane

| 平面 | 用途 | 谁可写 | 被测系统可读 |
|---|---|---|---|
| Observed | 被评估的来源标签、事件与策略证据 | Harness 插桩和运行组件 | 是 |
| Oracle | `GT_data`、`GT_auth`、`GT_effect` 真值 | Benchmark sidecar | 否 |

必须满足：

- Oracle 根据场景真实步骤机械更新，不能从 Observed 复制或纠错；
- Agent、Skill、PolicyEngine、Observed 图构建器不能读取 Oracle；
- `drop_on_derive` 和 `drop_on_memory` 只影响 Observed；
- 指标以 Oracle 评估 Observed，禁止 Observed 自评；
- Oracle 输出只用于测试、Golden 对齐和研究报告，不参与运行决策。

选择这一结构的理由见 [`decisions/0002-separate-observed-and-oracle.md`](decisions/0002-separate-observed-and-oracle.md)。

## 10. 形式化不变量

以下不变量是 T03 及以后必须转化为类型约束、单元测试或集成测试的语义合同。

### INV-AUTH-01：普通内容不能签发 Grant

```text
event.type == AUTH_GRANT
  -> principal_type(event.actor_id) IN {USER, TRUSTED_POLICY}
```

任何 Artifact 的内容、trust、origin 或文本模式都不能满足这个前件。

### INV-AUTH-02：Manifest 不能替代 Grant

```text
authorized(effect)
  -> manifest_declares(actor(effect), effect)
     AND exists valid_matching_grant(effect)
```

只有 Manifest 或只有 Grant 都必须得到 `authorized=false`。

### INV-PROV-01：跨 Session Memory 保留来源

```text
MEMORY_READ(old_memory, new_artifact)
  -> old_memory IN parents(new_artifact)
     AND origins(old_memory) SUBSET_OF origins(new_artifact)
```

Observed 缺陷模式可以故意违反后半项以供评测，但 Oracle 永远不得违反。

### INV-HIST-01：撤销不删除历史来源

```text
append(SKILL_REVOKE | AUTH_REVOKE | SKILL_UNLOAD)
  -> all earlier Events, Artifacts and lineage edges remain unchanged
```

撤销状态通过后续 Event 时间和只读 View 派生。

### INV-ID-01：Skill 主体隔离

```text
skill_a != skill_b -> principal_id(skill_a) != principal_id(skill_b)
```

任何 Tool 请求必须记录实际发起 Skill 的 Principal，不能统一归为 Harness。

### INV-INFLUENCE-01：时序只能产生候选影响

```text
upstream(x, effect) AND no matched replay evidence
  -> influence(x, effect) != CONFIRMED
```

### INV-DECISION-01：Monitor 不改变授权真值

```text
mode == monitor AND baseline_result == ALLOW AND authorized == false
  -> executed == true AND authorized == false
```

### INV-ORACLE-01：运行组件不能读取 Oracle

```text
component IN {Agent, Skill, PolicyEngine, ObservedGraph}
  -> no read dependency on Oracle Plane
```

### INV-LIFETIME-01：授权只按所声明 lifetime 的边界匹配

```text
call       -> same call_id
task       -> same task_id
session    -> same session_id
persistent -> cross task/session until expires_at or AUTH_REVOKE
```

`task` 与 `session` 互不包含；任何未知 lifetime 均在输入边界拒绝。

## 11. 语义错误分类

后续实现发现以下情况时必须失败并给出清楚原因，而不是静默降级：

- Skill 声称自己是 `USER` 或 `TRUSTED_POLICY`；
- 未知 Principal、action、scope、lifetime 或 Resource scheme；
- Artifact 引用不存在的父节点；
- 一个输出 Artifact 有多个生成 Event；
- Grant 与 Effect 的主体、source、sink、scope、当前 lifetime 对应边界、time 或 lifetime 不匹配；
- 普通文本被转换为 Grant；
- Observed 组件导入或读取 Oracle；
- Tool Receipt 不是由对应 Mock Tool 执行产生；
- 撤销操作试图更新或删除历史 Event。

## 12. 手工路径与实现映射

良性 G0、授权洗白 A1、跨 Session Memory M1 和撤销残留 M2 的完整手工路径见 [`threat-model.md`](threat-model.md#12-手工路径示例)。后续实现必须把它们分别转化为：

- T03：合法/非法 Schema 和模型用例；
- T04～T08：Event、图、Grant 和策略 Golden Tests；
- T09～T11：UEA、Provenance、ALR、RIR 和 CI 手算结果；
- T12～T14：能力匹配的良性/攻击场景与端到端验收。

## 13. 变更控制

以下变更必须新增 ADR；涉及第 1、2 节 MVP 边界时还必须先询问用户：

- 增加新的授权主体；
- 允许普通内容或模型判断签发 Grant；
- 合并 Observed 与 Oracle；
- 用单一节点图取代 Artifact–Event 图；
- 从 Mock Tool 改为真实网络、Shell 或凭据；
- 改变 `call | task | session | persistent` 的菱形 lifetime 语义；
- 把恶意文本检测改为框架主要任务。
