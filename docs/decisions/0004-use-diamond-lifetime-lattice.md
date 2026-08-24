# ADR 0004：Lifetime 使用四值菱形偏序

- 状态：已接受
- 日期：2026-08-24
- 决策者：项目用户与 SkillFlow 实现

## 背景

原任务说明书要求实现 `Lifetime`，但漏写了完整取值、`call_id` 和包含关系。如果只实现 `task | session`，或把 Lifetime 当成线性枚举比较，会错误地让 `task` 覆盖 `session`，或者让 `session` 覆盖 `task`。这两种边界语义都不成立。

## 决策

`Lifetime` 是封闭四值枚举：

```text
call | task | session | persistent
```

边界匹配语义固定如下：

| Lifetime | 必须匹配的边界 | 跨边界能力 |
|---|---|---|
| `call` | 相同 `call_id` | 不跨调用 |
| `task` | 相同 `task_id` | 可以跨 Session |
| `session` | 相同 `session_id` | 不要求与 `task` 形成包含关系 |
| `persistent` | 不限制 Task/Session | 直到 `expires_at` 或 `AUTH_REVOKE` |

包含关系是菱形偏序：

```text
       persistent
       /        \
    task        session
       \        /
          call
```

`AuthorizationGrant` 与 `SecurityEvent` 都保留可选 `call_id`。`call` Grant 必须提供 `call_id`，`session` Grant 必须提供 `session_id`。所有未知 Lifetime 在输入边界直接拒绝。

## 结果

- T03 用封闭枚举和穷尽分支实现偏序，不能依赖枚举顺序或字符串比较。
- T08 的 Grant matcher 必须只检查当前 Lifetime 对应的边界 ID；其他 ID 只作为签发/事件上下文，不得叠加成隐藏限制。
- T08 必须提供 `CROSS_CALL_USE`、`CROSS_TASK_USE` 和 `CROSS_SESSION_USE` 等可区分原因。
- Schema、YAML 校验和 JSON 往返必须保留 `call_id`。
- 若以后改变四个取值或偏序关系，必须新增替代 ADR，不能静默修改本记录。

## 未在本 ADR 中决定

- Resource scope 的偏序与包含算法；
- Grant matcher 的具体存储查询和缓存方式；
- `AUTH_REVOKE` 的 EventStore 实现。

这些内容仍分别属于 T08 和 T04，不在 T03 提前实现。
