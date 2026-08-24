# T03 总结：Schema 与核心数据模型

## 任务结论

T03 已完成。项目现在具备严格类型化的安全数据模型、四类模型生成静态 JSON Schema，以及只读 Manifest/Scenario 校验命令。实现没有进入 EventStore、运行期授权匹配、来源图、指标或 Harness 执行。

## 用户补充语义已落地

任务说明书原先漏写了完整 Lifetime。本次按用户明确要求固定为：

```text
call | task | session | persistent
```

它不是线性枚举，而是菱形偏序：

```text
       persistent
       /        \
    task        session
       \        /
          call
```

- `call` 只在相同 `call_id` 内有效；
- `task` 只要求相同 `task_id`，可以跨 Session；
- `session` 只要求相同 `session_id`；
- `persistent` 可以跨 Task 和 Session，直到 `expires_at` 或 `AUTH_REVOKE`；
- `task` 与 `session` 互不包含，未知 Lifetime 全部拒绝。

`AuthorizationGrant` 和 `SecurityEvent` 都已增加可选 `call_id`。这一纠正同时写入任务说明书、安全语义和 ADR 0004，防止 T08 再按旧的线性或双值假设实现。

## 核心产物

| 产物 | 作用 |
|---|---|
| `src/skillflow/models/` | 封闭枚举及核心安全、Scenario、Matrix、Report 模型 |
| `src/skillflow/schemas.py` | 从模型生成静态 Schema 的唯一入口 |
| `schemas/skill-manifest.schema.json` | Skill Manifest 输入契约 |
| `schemas/scenario.schema.json` | Scenario DSL 输入契约 |
| `schemas/experiment-matrix.schema.json` | 实验矩阵契约 |
| `schemas/risk-report.schema.json` | run/replay/experiment 判别报告契约 |
| `src/skillflow/validation.py` | YAML 校验与结构化错误定位 |
| `skillflow validate-manifest` | 只校验 Manifest，不加载 Skill |
| `skillflow validate-scenario` | 只校验 Scenario，不运行 fixture |
| `docs/decisions/0004-use-diamond-lifetime-lattice.md` | 冻结四值 Lifetime 与菱形偏序 |

## 已锁死的安全边界

1. 模型默认不可变并拒绝未知字段；封闭枚举拒绝未知 Principal、action、event、decision 和 lifetime。
2. Resource URI 只允许 `workspace:`、`context:`、`memory:`、`mock:`、`fixture:`；主机路径、盘符、空 scope、路径穿越和未知 scheme 都在加载边界拒绝。
3. 精确文件匹配只接受规范 URI 完全相等，不把父目录或相邻字符串前缀当作覆盖。
4. Skill Manifest 只能声明权限上限，不能携带 Grant 或伪装 `issuer_type=user`。
5. Grant 只允许 `USER` 或 `TRUSTED_POLICY` 签发；call/session lifetime 缺少对应 ID 会失败。
6. 声称已经执行的 EffectRecord 必须同时引用结果事件和 Tool Receipt。
7. Scenario 的 implementation 只能是 `fixture://<registry-id>`；禁止文件路径、模块路径和路径穿越。
8. Scenario 的 step、artifact alias、effect selector 和引用必须全局唯一且在同一文档内声明。
9. `user_confirm`、`revoke_skill`、`unload_skill` 只允许显式 `USER`/`TRUSTED_POLICY` actor。

## Schema 防漂移机制

四个 JSON Schema 不是独立手写真相，而是由 Pydantic 模型机械生成。测试会：

1. 重新生成模型 Schema；
2. 检查静态文件符合 JSON Schema Draft 2020-12；
3. 比较静态文件和模型生成内容完全相等；
4. 同时验证合法/非法文档在模型与 JSON Schema 边界得到一致结论。

这只能证明结构契约没有漂移，不代表运行期授权策略已经实现。

## TDD 与验证证据

| 阶段 | 先失败的证据 | 绿灯结果 |
|---|---|---|
| Lifetime / ResourceRef | 25 failed，1 passed | 四值偏序、规范化和精确匹配通过 |
| Grant / Event / Effect | 4 failed，5 passed | ID、时间窗、Receipt 约束通过 |
| Scenario DSL | `Scenario` 导入失败 | 11 个 Scenario 用例通过 |
| 静态 Schema | `ExperimentMatrix` 导入失败 | 6 个 Schema 契约用例通过 |
| 校验 CLI | 5 个命令用例失败 | 5 个命令用例通过 |

最终本地结果：

- pytest：65 passed，分支覆盖率 90.18%；
- Ruff：检查和格式门通过；
- mypy strict：18 个源文件无类型问题；
- CLI：合法文件退出码 0，非法文件退出码 2，并输出文件、字段路径、稳定代码和原因。

## 明确未完成

- 没有实现 T04 EventStore 或 SQLite 表；
- 没有实现 T08 Grant matcher、scope 包含算法或 PolicyEngine；
- 没有实现来源图、Oracle、Mock Tool、指标或实验执行；
- Risk Report 只是数据契约，不是实验结果；
- 没有进入 T04。

下一项可执行任务是 T04，但必须由用户另行明确要求。
