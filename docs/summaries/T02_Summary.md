# T02 总结：威胁模型与安全语义冻结

## 任务结论

T02 已完成。SkillFlow 的研究边界、主体、资产、攻击者能力、授权语义、跨 task/session 规则和三项架构决定已经以中文 Markdown 冻结。没有提前实现 T03 数据模型或后续实验逻辑。

## 核心产物

| 文件 | 作用 |
|---|---|
| `docs/threat-model.md` | 固定可信主体、攻击者、资产、Sink、边界、威胁、成功判据和手工路径 |
| `docs/security-semantics.md` | 固定三种 provenance、Manifest/Grant、Decision、跨边界和撤销语义 |
| `docs/decisions/0001-use-artifact-event-graph.md` | 决定使用 Artifact–Event 二部图 |
| `docs/decisions/0002-separate-observed-and-oracle.md` | 决定隔离 Observed 与 Oracle |
| `docs/decisions/0003-use-mock-harness-first.md` | 决定 T14 前只使用确定性 Mock Harness |

## 冻结的核心边界

1. 每个 Skill 是独立 `Principal`，Harness 是桥接层和被测系统，不是默认授权者。
2. 普通内容、Manifest、高可信数据、自动批准和 monitor 执行均不能替代真实 Grant。
3. 数据来源、决策影响和授权来源分别由血缘图、反事实 Replay 和结构化 Grant 证明。
4. Tool 请求、策略允许和实际 Receipt 是不同事实；只有 Receipt 能证明 Mock Effect 已执行。
5. Persistent Memory 可以跨 Session 传播数据，但必须保留父链和 origins，且不能延长旧授权。
6. Grant 默认不跨 task；跨 task 数据读取也不携带旧 task 的 authority。
7. revoke、unload 和 delete 不删除历史，只通过后续事件改变未来有效性。
8. Observed 是被评估对象，Oracle 是被测系统不可读取的独立 Ground Truth。

## 形式化不变量

T02 共冻结 9 条不变量，覆盖：

- 普通内容不能签发 Grant；
- Manifest 不能替代 Grant；
- 跨 Session Memory 必须保留来源；
- 撤销不删除历史；
- Skill 主体隔离；
- 候选影响与确认影响分开；
- monitor 不改变授权真值；
- Oracle 运行时隔离；
- Grant 不跨 task 隐式继承。

## 手工路径

| 路径 | 语义预期 |
|---|---|
| G0：完整授权的跨 Skill 协作 | Manifest 和 Grant 双匹配，`UEA=0` |
| A1：普通文本授权洗白 | 无 Grant 的 Effect 被执行；能力匹配中和后停止才计 ALR |
| M1：跨 Session Memory 传播 | 新 Artifact 连接旧 Memory，Observed 缺陷不污染 Oracle |
| M2：撤销后残余影响 | 历史保留、新派生物带 revoked origin，符合条件时进入 RIR |

这些只是语义 Golden 预期，不是实验结果。

## 研究问题—指标接口

| 研究问题 | 指标 |
|---|---|
| 数据流向 | Provenance Precision/Recall/F1、Decay、跨 Session 路径 |
| 实际决策影响 | CI、confirmed influence |
| 真实授权覆盖 | UEA、授权路径、ALR |
| Harness 风险放大 | HIAA |
| 撤销后残余影响 | RIR(1)、RIR(3) |

## 验证结果

- 6 个 T02 必需文档均为严格 UTF-8；
- 9 条形式化不变量、1 条良性路径和 3 条攻击路径结构审计通过；
- RQ1～RQ5 与全部后续指标映射通过；
- 本地 Markdown 链接和 `git diff --check` 通过；
- 原有 6 个测试全部通过，覆盖率 92.06%；
- Ruff、Mypy 和 `skillflow doctor` 通过。

## 未完成内容

- 尚未实现 Pydantic 模型、JSON Schema 或 URI 校验；
- 尚未实现 EventStore、Harness、Oracle、来源图、授权 matcher 或风险指标；
- 尚无任何攻击发生率或安全效果实验结果。

以上内容属于 T03 及之后任务。下一项可执行任务是 T03，当前未启动。
