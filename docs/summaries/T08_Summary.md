# T08 总结：授权匹配与策略决策

## 结论

T08 已完成。SkillFlow 现在不再用 Stub 的单一 allow/deny 代替授权判断，而是对每次 Tool Effect 独立计算并持久化四个事实：

```text
baseline_result：未加固 Harness 原本会怎么做
policy_result：结构化策略建议怎么做
authorized：Manifest 与真实 Grant 是否共同覆盖 Effect
executed：当前 monitor/enforce 模式下是否真的执行 Mock Effect
```

这四个事实不会互相覆盖。尤其是 monitor 可以让 baseline 已允许的未授权 Effect 继续发生，但 `authorized` 仍为 false；enforce 只有在 baseline 与 policy 都为 ALLOW 时执行。

本轮在 T08 停止。没有实现 T09 的 UEA、Provenance Precision/Recall/F1/Decay，也没有进入 T10 checkpoint。

## 双钥匙授权

一个 Effect 只有同时满足以下两把钥匙才是 `authorized=true`：

1. 对应 Skill Manifest 声明了该能力；
2. 有效的结构化 `AuthorizationGrant` 覆盖当前主体、动作、资源、Scope、Lifetime 边界、时间和撤销状态。

Manifest matcher 返回 Manifest ID、匹配的 permission index 和失败原因。Grant matcher 检查：

- `grantee_id` 与实际 Skill principal；
- action；
- source 与 sink 的规范化 URI；
- Scope；
- Lifetime 及当前 lifetime 唯一相关的边界 ID；
- `valid_from` / `expires_at`；
- `AUTH_REVOKE`。

首版资源范围是精确匹配，`workspace:/a.txt` 不会覆盖 `workspace:/a.txt.bak`。禁止用字符串前缀伪造合法路径包含。

## Scope 与 Lifetime

Scope 固定为四个封闭值：

```text
exact-file | exact-key | exact-sink | command
```

四者构成离散反链，每个 Scope 只覆盖自身。目录、glob、域名层级和命令参数模式均未实现。

Lifetime 固定为菱形偏序：

```text
       persistent
       /        \
    task        session
       \        /
          call
```

- call 只匹配相同 `call_id`；
- task 只匹配相同 `task_id`，可以跨 Session；
- session 只匹配相同 `session_id`；
- persistent 不限制 task/session/call，但仍受过期和撤销约束；
- task 与 session 互不包含。

实现使用显式覆盖函数和模式匹配，不依赖枚举顺序或字符串大小。

## PolicyEngine 与执行真值表

baseline 按固定优先级计算：

```text
结构无效                    -> DENY
已有有效结构化确认          -> ALLOW
auto_approve_tools=true      -> ALLOW
相关文本且脆弱文本开关开启  -> ALLOW
其他                        -> CONFIRM
```

文本只可能影响 baseline，并记录对应 Artifact；它永远不会生成 Grant。

policy 的规则是：

- Manifest、Grant、范围、Lifetime、时间、撤销和来源全部通过：ALLOW；
- Manifest 已覆盖，唯一缺口是 Grant，且允许获取新确认：CONFIRM；
- 其他情况：DENY。

执行规则是：

| 模式 | baseline | policy | executed |
|---|---|---|---|
| monitor | ALLOW | 任意 | true |
| monitor | 非 ALLOW | 任意 | false |
| enforce | ALLOW | ALLOW | true |
| enforce | 其他 | 任意 | false |

测试证明 monitor 与 enforce 对同一请求产生相同的 `policy_result` 和 `authorized`，只在 `executed` 上按上述规则分歧。

## Grant、撤销与特权确认

EventStore 新增不可变 Grant 与撤销事实。`AUTH_GRANT` Event 和 Grant 在同一事务中追加；`AUTH_REVOKE`/Principal 撤销作为独立、带时间戳的记录追加。SQLite 触发器拒绝直接 UPDATE/DELETE，历史 Grant、Event 和 Effect 不回写。

声明式 `user_confirm` 步骤必须携带完整结构化 Grant。只有 Skill 不可见的 `BenchmarkController` 可以执行该步骤，actor 只能是 `USER` 或 `TRUSTED_POLICY`，并且必须与 Grant 的 `issuer_type` 一致。测试显式验证了 Skill actor 被拒绝。

动态确认成功后，Runtime 和独立 Oracle 分别更新自己的 Grant 视图。Oracle 只接收 Benchmark 已执行的结构化确认，不读取 PolicyEngine、Observed authorization 或 DecisionRecord。

## 稳定 reason codes

当前至少支持：

```text
MANIFEST_PERMISSION_MISSING
USER_GRANT_MISSING
RESOURCE_SCOPE_EXCEEDED
SINK_SCOPE_EXCEEDED
GRANT_NOT_YET_VALID
GRANT_EXPIRED
GRANT_REVOKED
ORIGIN_REVOKED
CROSS_CALL_USE
CROSS_TASK_USE
CROSS_SESSION_USE
UNTRUSTED_ORIGIN
PROVENANCE_INCOMPLETE
```

每个 Decision 还保存 Manifest ID、matched Grant IDs 和 decision-basis Artifact IDs，避免只留下不可审计的模糊 decision。

## TDD、回归与质量证据

1. 先创建 matcher、PolicyEngine、存储和 E2E 测试；最初因 `skillflow.policy` 不存在以及 Runner 仍使用 Stub 而红灯。
2. matcher/engine 首批 36 项测试转绿；补齐 Scope、未生效 Grant、action/principal 和 persistent 跨 Task 签发上下文后，T08 定向集合最终为 55 项。
3. 全量回归首次发现 T05 fixture 的 baseline 配置、T06 旧 Stub 授权断言、Stub 兼容接口和静态 Schema 需要迁移；逐项修复后保留旧阶段行为，并让 T06 Observed authorization 反映正式策略结果。
4. Python 规则审计发现两个源模块和扩展后的 matcher 测试超过 250 行；运行合同、Envelope 校验及 Manifest/Grant 测试被按职责拆分，公开行为与覆盖范围不变。
5. 最终结果：

   - pytest：**236 passed**；
   - 分支覆盖率：**89.18%**，高于当前 80% 门禁；
   - Ruff lint：PASS；
   - Ruff format：PASS，**158 个文件**格式一致；
   - mypy strict：PASS，**88 个源文件**无类型错误；
   - T08 相关 Python no-excuse：PASS；
   - `skillflow doctor`、CLI help、`pip check`：PASS。

## 明确限制与停止点

- Scope 仅为四种精确离散值，不是通用资源层级策略；
- 确认由受控 Scenario 预注册并通过 Benchmark 特权接口执行，不是生产身份系统；
- 所有网络和 Shell 仍是安全 Mock，不产生真实外部副作用；
- 本轮不计算风险指标，不生成 T09 报告；
- T08 到此完成并停止，T09 保持 pending。
