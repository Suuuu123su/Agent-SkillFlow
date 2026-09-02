# 研究设想：SkillFlow-Rx——基于量化攻击机制画像的自适应防御编排

- 状态：研究设想，尚未实现
- 记录日期：2026-09-02
- 实施优先级：低于“现有指标补全与实验闭环”
- 前置计划：[`docs/plans/T17_metric_completion_experiment_plan.md`](../plans/T17_metric_completion_experiment_plan.md)

## 1. 一句话概述

SkillFlow-Rx 的目标不是只判断“当前是否存在攻击”，而是利用 SkillFlow 已记录的来源、授权、Effect/Receipt、跨 Session、撤销和反事实证据，形成一个可审计的**攻击机制画像**，再从防御目录中选择风险降低效果最好、任务损失最小的防御组合，并在应用防御后重新测量对应指标。

完整闭环为：

```text
运行证据 → 量化指标 → 攻击机制诊断 → 防御选择 → 再运行/反事实验证
```

## 2. 动机

不同 Agent Skill 攻击虽然都可能导致同一个敏感 Tool Effect，但传播机制并不相同：

- B1 更接近单 Skill 直接越权；
- C1/C2 依赖共享 Context 或 Tool Return；
- M1/M2 依赖 Persistent Memory 和跨 Session 传播；
- A1 依赖普通文本中的假授权声明；
- S1/L1 分别涉及授权 Scope 和 Lifetime；
- 动态 Skill 修改、资源放大等问题又位于其他控制边界。

如果所有风险都使用同一种“最强阻断”，虽然可能降低 Effect，但也容易造成正常任务失败。更合理的目标是：先判断风险主要来自哪个机制，再选择位于正确边界的最小防御。

## 3. 与已有工作的关系

已有研究分别证明了以下方向是可行的：

- **ASB** 已经系统化比较多类 Agent 攻击与对应防御，但实验者通常预先知道攻击类型；
- **SafeAgent** 将运行时安全视为状态化决策，并在风险、效用和代价之间选择干预；
- **AgentSentry** 使用时间因果诊断定位间接提示注入的接管点，再进行上下文净化；
- **AttriGuard** 使用并行反事实重放判断工具调用是否由不可信 Observation 因果驱动。

因此，本项目不应声称“首次根据攻击类型选择防御”。更稳妥的差异是：

> 使用 SkillFlow 可复算的来源、授权、生命周期、Effect/Receipt 和反事实证据，形成支持多标签与 abstain 的攻击机制画像；再选择最小防御组合，并使用同一证据链验证防御是否对症。

## 4. 研究假设

### H1：不同攻击机制具有可区分的证据指纹

不同攻击家族应在以下证据上形成不同组合：

- Manifest/Grant 匹配结果及 reason code；
- 来源路径经过 Context、Tool Return、Memory 还是授权声明；
- 是否跨 Session；
- 来源 Skill 是否已撤销；
- 中和某个 Artifact 后目标 Effect 是否消失；
- HIAA、ALR、RIR、UEA、provenance 和 Task Success 的联合变化。

### H2：针对性防御优于固定防御

基于攻击机制画像选择防御，应当比“固定只开一种防御”获得更高的风险下降，并比“所有防御全部开启”保留更高的良性任务成功率。

### H3：防御效果可以被同一证据链验证

系统不仅要给出防御建议，还必须在防御后证明：

1. 对应风险指标下降；
2. 目标 Effect/Receipt 按预期消失或转为合法执行；
3. B0、G0、A2 等良性任务尽量保持成功；
4. 额外 Agent Step、Token、费用和延迟在可接受范围内。

## 5. 不使用单一硬标签

一个攻击可能同时经过 Memory、跨 Skill Context 和假授权声明，因此诊断结果应为**多标签攻击画像**，而不是互斥类别。

建议的第一版结构：

```yaml
attack_profile:
  direct_unauthorized: 0.10
  context_composition: 0.72
  tool_return_influence: 0.08
  memory_persistence: 0.91
  authorization_laundering: 0.64
  scope_violation: 0.03
  lifetime_violation: 0.55
  unknown: 0.12

evidence_availability:
  authorization_hook: true
  provenance_hook: true
  influence_hook: false
  revocation_hook: true

impact:
  sink_type: mock-network-send
  severity: high
  observed_effect: true
  receipt_present: true
```

这些分数只能由受信任的运行时和分析器生成。Skill、模型输出或普通文本不得直接提交攻击类别、置信度、origin、Grant 或“防御已完成”声明。

## 6. 画像输入

攻击诊断器的输入应是证据向量，而不是 Scenario ID 或攻击文件名：

| 输入组 | 具体信息 |
|---|---|
| 授权 | Manifest 匹配、Grant 匹配、Scope/Lifetime、过期与撤销 reason code |
| 来源 | origin trust、Artifact 父边、Context/Memory/Tool Return 路径、边界深度 |
| 执行 | Effect selector、accepted、executed、Receipt、Sink 类型 |
| 因果 | identity/neutral Replay、Effect diff、确认影响证据 |
| 时间 | Run/Task/Session、撤销时点、Session 偏移 |
| 任务 | TaskSuccessResult、逐断言证据、良性任务是否保留 |
| 效率 | Agent Step、Token、费用、延迟、重试与 Partial 状态 |
| 缺失 | 每一类 Hook 和指标的 N/A mask |

诊断器必须显式接收证据可用性。缺失 Hook 时应降低置信度或输出 `unknown/abstain`，不能把 N/A 当成 0。

## 7. 攻击机制与防御目录

| 机制 | 主要量化证据 | 首选防御方向 |
|---|---|---|
| B1 直接越权 | UEA、直接 Skill→Effect 路径、Grant 缺失 | Manifest/Grant 双钥匙、最小权限、敏感动作确认 |
| C1 共享 Context 组合 | Context 四格 HIAA、Context provenance path | Context 隔离、来源标签、provenance-aware capability gate |
| C2 Tool Return 组合 | Tool Return 路径、中和 Return 后 Effect diff | Tool Return 结构化隔离、净化、因果检查 |
| M1 跨 Session Memory | 跨 Session path、低可信 Memory origin | Memory provenance、TTL、读取隔离、可信派生检查 |
| M2 撤销后残留 | revoked origin、RIR(k)、撤销后 Effect | 撤销级联、verified forgetting、Memory rollback |
| A1 假授权 | ALR、decision basis、claim-neutralized Replay | 结构化 ConfirmationToken、可信 Grant 通道 |
| S1 Scope 扩大 | Grant 存在但资源不匹配 | 精确 Scope enforcement、参数收窄、Sandbox |
| L1 Lifetime 误用 | 过期或跨 Session Grant | Session-bound token、到期检查、撤销列表 |
| Skill 动态修改 | Skill hash/签名变化 | 代码签名、只读挂载、加载前后完整性验证 |
| 资源放大 | Step/Token/调用和费用异常 | Step、Token、费用预算与 Circuit Breaker |

基础安全不变量不能由诊断器关闭。即使攻击置信度较低，Grant、Scope、Lifetime、Receipt、预算和高风险 Sink 的最终控制边界仍应保持启用。

## 8. 防御选择问题

设候选防御组合为 `D`，可以将选择目标写为：

```text
最小化：防御后剩余风险
      + λ × 正常任务损失
      + μ × Token/费用开销
      + ν × 额外延迟
```

第一版不需要训练复杂模型，可先实现确定性规则路由：

```text
证据满足严格阈值 → 选择对应防御
证据冲突或缺失      → abstain + 人工确认/安全模式
多机制同时成立      → 选择最小防御组合
```

规则型版本通过后，再比较学习型多标签诊断器是否能在 held-out Skill 上提升泛化能力。

## 9. 离线与在线两级运行

HIAA 需要四格，ALR 需要成对中和，RIR 需要撤销后的后续 Session，因此不能假设所有指标都能在第一次 Tool Call 前实时计算。

建议分为两级：

### 9.1 部署前离线画像

在 Skill 安装或进入正式环境前运行完整 Matrix，得到：

- Context/Tool Return 放大风险；
- Memory 跨 Session 与撤销后风险；
- 授权声明敏感性；
- Scope/Lifetime 风险；
- 默认防御配置。

### 9.2 运行时快速路由

运行时只使用当前可观察的来源、Grant、Scope/Lifetime、撤销状态、路径和 Sink 敏感度。高风险或证据不足时暂停副作用，进入 Shadow Replay、用户确认或安全模式。

## 10. 实验验证

### 10.1 任务 A：攻击机制诊断

测试集至少覆盖 B1、C1、C2、M1、M2、A1、S1、L1、N0，以及 G0/A2 合法对照和少量混合攻击。

建议指标：

- Macro-F1；
- Multi-label F1；
- Top-k defense recall；
- Brier score 或其他校准指标；
- abstention accuracy；
- 攻击边界定位准确率；
- 诊断所引用证据路径的有效率。

数据必须按 Skill 划分 development、validation 和 held-out 集，不能把同一个攻击 Skill 的简单改写同时放入训练和测试。

### 10.2 任务 B：防御选择

至少比较：

1. No Defense / Monitor；
2. 固定单一防御；
3. 所有防御全部开启；
4. 文本分类器路由；
5. 人工真实攻击标签路由（Oracle upper bound）；
6. SkillFlow 证据驱动路由。

建议报告：

- Targeted Risk Reduction；
- Task Success 与 Utility Loss；
- 良性任务 Over-defense Rate；
- Defense Selection Regret；
- Residual Risk；
- Agent Step、Token、费用和延迟。

最有说服力的结果不是“所有攻击都被阻止”，而是不同机制由不同防御对症降低，同时良性任务不被统一阻断。

## 11. 与当前 SkillFlow 的关系

当前仓库已经具备 Event、Artifact/Origin、Manifest/Grant、Effect/Receipt、SecurityGraph、Replay、HIAA/ALR/RIR、TaskSuccessEvidence 和 Monitor/Enforce 等基础。但真实模型实验中，正式 UEA、ALR、RIR 和 provenance 仍因平台证据 Hook 不完整而保持 N/A；T16-E 第二模型 Canary 也只完成 6/11。

因此本设想当前只作为后续方向，不进入现有结果分母。实施前必须先完成：

1. T16-E 的全新完整 Attempt；
2. 真实/受控 Harness 的 Authorization、decision basis、provenance、influence 与 revocation Hook；
3. 全场景、严格 TaskSuccessEvidence 的指标补全实验；
4. Monitor/Enforce 的安全—效用对照；
5. held-out Skill 数据集。

具体顺序见 [`T17_metric_completion_experiment_plan.md`](../plans/T17_metric_completion_experiment_plan.md)。

## 12. 创新边界

不应将创新表述为“首次根据攻击类型选择防御”。更稳妥的研究贡献是：

> 使用可复算的来源、授权、因果和生命周期证据，形成支持 N/A/abstain 的多标签攻击机制画像；在风险、任务成功率和成本之间选择最小防御组合，并通过同一证据链和反事实实验验证防御是否对症。

## 13. 当前不可声称的内容

- 尚未实现攻击诊断器或 Defense Planner；
- 尚未证明现有指标能够准确分类未知攻击；
- 尚未证明自动路由优于固定防御或全部防御；
- 尚未完成多模型、held-out Skill 或混合攻击验证；
- 不能把目标 Effect 执行直接等同于未授权攻击成功；
- 不能在缺少 Hook 时把 UEA、ALR、RIR 或 provenance 的 N/A 写成 0。

## 参考工作

1. Zhang et al. **Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defenses in LLM-based Agents.** arXiv:2410.02644.
2. Liu et al. **SafeAgent: A Runtime Protection Architecture for Agentic Systems.** arXiv:2604.17562.
3. Zhang et al. **AgentSentry: Mitigating Indirect Prompt Injection in LLM Agents via Temporal Causal Diagnostics and Context Purification.** arXiv:2602.22724.
4. He et al. **AttriGuard: Defeating Indirect Prompt Injection in LLM Agents via Causal Attribution of Tool Invocations.** arXiv:2603.10749.
