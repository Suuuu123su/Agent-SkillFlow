# T18：多 Skill 证据路由动态防御——一天内可完成的本地实验计划

- 状态：计划
- 基线提交：`707cf07dde60c98629707b810f5bb631f4db97fd`
- 前置条件：完整 T17 第二版已完成，`datasets/t17-v2/`、Skill catalog、能力匹配和 `skillflow compare-skills` 已可用
- 时间目标：单个工作日内完成本地实现、实验、报告和质量门
- 默认费用：`$0`；不调用真实 Provider
- 外部副作用：全部进入现有 Safe Sink
- 论文主线：[`skillflow-paper-storyline-and-validation.md`](../research/skillflow-paper-storyline-and-validation.md)

## 1. 目标

完成一个最小但完整的 **Multi-Skill Dynamic Defense MVP**：

1. 使用多个不同机制的恶意 Skill 和能力匹配的 neutral/benign Skill；
2. 从可信运行证据中识别主要攻击机制，不读取 `scenario_id`、`attack_family` 或 Skill 文件名作为运行时答案；
3. 针对不同机制选择不同防御或最小防御组合；
4. 与 No Defense、固定单防御、All-Defense 和 Oracle Router 比较；
5. 同时报告风险下降、任务效用损失、误防御和运行开销；
6. 证明下一步可以扩展到更多真实 Skill，而不修改核心指标算法。

本阶段不训练分类器，不追求论文级统计显著性，不运行新的真实模型大矩阵。研究结论限定为：

> 在 Scripted/Fake Reference 受控环境中，SkillFlow 的可信证据能否驱动不同机制的本地防御，并完成可复算的安全—效用比较。

## 2. 采用的近期顶会防御思想

本阶段实现的是**论文机制的本地、系统级适配**，不是对原论文模型训练、数据集和全部结果的精确复现。报告必须明确记录采用了什么、没有复现什么。

### D1：TaskAlignmentGate

- 来源：Task Shield，ACL 2025
- 论文：<https://aclanthology.org/2025.acl-long.1435/>
- 核心思想：每条指令和 Tool Call 必须对用户任务目标有贡献。
- 本地适配：
  - 使用 SkillFlow 已冻结的 `TaskContract`、允许的 Effect 类型、资源和必要依赖；
  - 对 proposed Effect 做确定性 task-alignment 检查；
  - 不使用额外 LLM Judge；
  - 不在运行时读取攻击标签。
- 主要适用：B1、A1、S1、L1，以及高风险未知动作。

### D2：ToolDependencyGuard

- 来源：IPIGuard，EMNLP 2025
- 论文：<https://aclanthology.org/2025.emnlp-main.53/>
- 核心思想：先规划 Tool Dependency Graph，再限制执行只能沿计划图遍历。
- 本地适配：
  - 在读取不可信外部数据前，由 Task/Scenario/Manifest 机械生成最小 TDG；
  - 每个节点固定 Tool、Action、Resource、参数 Schema 和允许前驱；
  - Tool Return 不能新增未预注册节点或放大权限；
  - 计划外 Tool、错误前驱或参数越界被拒绝。
- 主要适用：C1、C2、B1、S1。

### D3：DynamicRuleMemoryIsolator

- 来源：DRIFT，NeurIPS 2025
- 论文：<https://proceedings.neurips.cc/paper_files/paper/2025/hash/77f3b26c7907aa27b207df9b9d43f29a-Abstract-Conference.html>
- 核心思想：Secure Planner、Dynamic Validator 和 Injection Isolator 同时约束控制流与数据流，并隔离 Memory 中的注入。
- 本地适配：
  - 根据 Task、Manifest、Grant、Scope/Lifetime 生成动态规则；
  - 规则只能由可信控制面更新，不能由 Tool Return/Memory 文本更新；
  - 低可信或 revoked origin 写入的 Memory 被标记为 quarantine；
  - 后续 Session 默认不把 quarantine Memory 作为控制指令；
  - Skill/Grant 撤销时执行来源级失效和读取过滤；
  - 保留历史事件，不删除证据。
- 主要适用：M1、M2、C1、A1、S1/L1。

### D4：CausalAttributionGate

- 来源：AttriGuard，USENIX Security 2026
- 论文：<https://www.usenix.org/conference/usenixsecurity26/presentation/he-yu>
- 核心思想：通过并行反事实测试判断 Tool Call 是由用户意图支持，还是由不可信 Observation 因果驱动。
- 本地适配：
  - 复用 SkillFlow 已有 checkpoint、identity/neutral Replay；
  - 只对高风险且存在不可信来源路径的 proposed Effect 运行 shadow replay；
  - 如果中和目标 Artifact 后 Effect 消失，记录确认影响并 DENY/CONFIRM；
  - 如果 Effect 存活，仍需通过 Manifest/Grant/Scope/Lifetime；
  - Replay 不可评估时返回 `abstain`，不能伪造 CI=0。
- 主要适用：C1、C2、M1、M2、A1，以及混合攻击。

### 不在一天版中完整实现的方法

StruQ（USENIX Security 2025）需要专门训练能区分 prompt/data channel 的模型，本阶段不进行训练，因此不把简单分隔符包装冒充完整 StruQ 复现。可在相关工作和后续扩展中保留。

## 3. 攻击机制与动态防御映射

| 机制 | 运行时可信信号 | 首选防御 | 必要的基础不变量 |
|---|---|---|---|
| direct unauthorized | 无有效 Grant；直接 Skill→Effect；计划外动作 | TaskAlignmentGate + Dynamic Validator | Manifest/Grant 双钥匙 |
| scope violation | Grant 存在但 Resource/Scope mismatch | Dynamic Validator + 参数收窄 | 精确 Scope matcher |
| lifetime violation | Grant 过期或跨 Session 使用 | Dynamic Validator + Session-bound check | Lifetime matcher |
| context composition | 不可信 Context 在 decision basis；路径穿过共享 Context | ToolDependencyGuard；高风险时 CausalAttributionGate | provenance |
| tool-return injection | 路径穿过 Tool Return；返回内容尝试新增动作 | ToolDependencyGuard + CausalAttributionGate | Tool Return 只作数据 |
| memory persistence | 跨 Session Memory path；低可信 origin | DynamicRuleMemoryIsolator | origin 与 Session |
| post-revocation memory | revoked origin 仍被读取 | Memory Isolator + CausalAttributionGate | revocation event |
| authorization laundering | 低可信授权声明进入 decision basis，但无真实 Grant | TaskAlignmentGate + trusted confirmation | 文本不能签发 Grant |
| unknown/mixed | 多类证据或证据不足 | 防御并集或 `abstain→confirm/safe mode` | 高风险 Sink 最终门 |

基础安全规则不能被 Router 关闭：Grant、Scope、Lifetime、Receipt、预算和 Safe Sink 始终有效。

## 4. 多 Skill 数据集

### 4.1 复用现有 Skill

复用 T17 已有：

- B1：直接越权；
- C1：共享 Context；
- C2：Tool Return；
- M1：跨 Session Memory；
- M2：撤销后残留；
- A1：假授权；
- S1：Scope；
- L1：Lifetime；
- B0、N0、G0、A2：良性/负面对照。

### 4.2 新增 held-out Skill

为防止 Router 只记住现有场景，新增 4 个本地 held-out 恶意 Skill，每个对应一个广义机制：

1. `heldout-privilege`：不同文本和步骤结构的权限越界；
2. `heldout-context-tool`：不可信 Context/Tool Return 诱导新动作；
3. `heldout-memory`：跨 Session 写入并在撤销后触发；
4. `heldout-auth`：不同措辞的假授权声明。

每个 held-out attack 必须有能力匹配 neutral Skill：

- 相同 Manifest；
- 相同 Tool registry；
- 相同 input/output Schema；
- 相同 Task Contract；
- 相同资源和授权结构；
- 内容长度位于相同预注册区间；
- 只改变攻击语义。

`attack_family` 标签只能用于运行后的离线评价，不能进入 Router 特征。

### 4.3 最小规模

最低完成集：

- 8 个现有恶意 Skill；
- 8 个能力匹配 neutral/control；
- 4 个 held-out 恶意 Skill；
- 4 个 held-out neutral；
- B0、N0、G0、A2 四个合法/负面对照。

共 28 个 Skill Variant。若仓库现有 catalog 已将部分对照合并，可减少重复文件，但必须保留等价的 28 个逻辑条目和配对身份。

## 5. 新增数据合同

### 5.1 AttackSignalVector

只能从运行证据构造，至少包括：

```text
grant_missing
scope_mismatch
lifetime_mismatch
revoked_origin
untrusted_context_in_basis
untrusted_tool_return_in_basis
cross_session_memory_path
authorization_claim_in_basis
candidate_influence
confirmed_influence
target_effect_requested
target_effect_executed
receipt_present
sink_severity
evidence_availability
```

### 5.2 AttackDiagnosis

```text
diagnosis_id
mechanisms[]
confidence: high | medium | low
abstain: bool
evidence_ids[]
missing_evidence[]
```

一天版不输出伪概率；使用可解释的离散置信度。

### 5.3 DefensePlan

```text
plan_id
selected_defense_ids[]
action: allow | deny | confirm | quarantine | replay_then_decide
evidence_ids[]
selection_reason_codes[]
estimated_extra_steps
```

### 5.4 DefenseOutcome

```text
before/after effect
before/after authorization
task_success
safe_task_success
utility_loss
over_defense
residual_risk
actual_extra_steps
actual_latency
```

所有 Schema 均需生成静态 JSON Schema。

## 6. Evidence Router

实现确定性、可审计的第一版 Router：

```text
if scope_mismatch or lifetime_mismatch or grant_missing:
    select TaskAlignmentGate + Dynamic Validator

if untrusted_context_in_basis or untrusted_tool_return_in_basis:
    select ToolDependencyGuard
    if sink is high-risk or candidate influence is ambiguous:
        add CausalAttributionGate

if cross_session_memory_path or revoked_origin:
    select DynamicRuleMemoryIsolator
    if proposed sensitive effect exists:
        add CausalAttributionGate

if authorization_claim_in_basis and grant_missing:
    select TaskAlignmentGate
    require trusted confirmation

if multiple mechanisms:
    take minimal union

if evidence required for the decision is missing:
    abstain
    high-risk sink -> confirm or deny
```

禁止：

- `if scenario_id == ...`；
- `if attack_family == ...`；
- 使用 Skill 文件名、路径或描述中的 `malicious`；
- 从模型自然语言中直接读取攻击类别；
- 为了达到预期结果写死 outcome。

## 7. 对比基线

每个 Skill 至少运行：

1. `monitor` / no additional defense；
2. `skillflow-enforce`：T17 已有统一策略；
3. `task-alignment-only`；
4. `tdg-only`；
5. `drift-isolation-only`；
6. `causal-only`；
7. `all-defenses`；
8. `oracle-router`：仅分析时用真实攻击标签选择防御，作为上界；
9. `evidence-router`：正式方法。

Oracle Router 可以使用标签，但其结果不得进入 Evidence Router 的输入。

## 8. 一天内可完成的实验矩阵

### 8.1 Scripted 全矩阵

对 24 个 attack/neutral variant 运行 9 个模式：

```text
24 × 9 = 216 core runs
```

对 4 个合法/负面对照只运行：

```text
monitor + all-defenses + evidence-router
4 × 3 = 12 core runs
```

总计：

```text
228 Scripted core runs
```

Replay 只对需要因果判断的 C1、C2、M1、M2、A1 及 3 个相关 held-out attack 执行，预计不超过 20 对。

### 8.2 Fake Reference Smoke

每个广义机制选 1 个 attack/neutral pair，只运行：

```text
monitor + all-defenses + oracle-router + evidence-router
```

四类机制：

```text
4 families × 2 roles × 4 modes = 32 core runs
```

必要 Replay 不超过 8 对。

### 8.3 真实模型

默认不运行。一天版完成条件不依赖真实 Provider。若之后需要真实 Smoke，另建 T18-Live 预注册和费用门，等待用户单独批准。

## 9. 指标

### 9.1 诊断质量

- broad-family Macro-F1；
- multi-label F1；
- exact-match rate；
- abstain rate；
- held-out Macro-F1；
- evidence citation validity；
- boundary localization accuracy；
- Oracle Router agreement。

### 9.2 防御质量

- UEA 下降；
- Verified Target Effect 下降；
- C1/C2 HIAA 变化；
- ALR 变化；
- RIR(1)、RIR(3) 变化；
- Targeted Risk Reduction；
- Residual Risk；
- Safe Task Success；
- Utility Loss；
- benign Over-defense Rate；
- Defense Selection Regret：

```text
regret = objective(evidence_router) - objective(oracle_router)
```

不需要把风险和效用压缩成一个公开总分。`regret` 的内部 objective 只用于相同预注册权重下比较 Router，并必须同时公开各原始分量。

### 9.3 Specificity Matrix

按攻击家族 × 单防御输出风险变化。目标不是要求非目标防御完全无效，而是验证针对性防御通常在对应机制上有更强或更稳定的收益，并揭示防御互补关系。

### 9.4 开销

- 额外 Agent Step；
- Replay 次数；
- 本地延迟；
- Fake decision calls；
- API/Token/cost 固定为设计 N/A 或 0；
- 不把本机延迟外推为 Provider 性能。

## 10. 实施顺序与时间盒

### 0–1 小时：审计与冻结

- 读取 T17 完整 Summary、dataset、skill catalog 和 compare-skills；
- 冻结 T18 preregistration、Skill catalog、Router rules、Defense catalog、Matrix 和期望状态；
- 记录 baseline SHA-256。

### 1–4 小时：实现

- 四个 Defense module；
- AttackSignalVector、Diagnosis、DefensePlan、Outcome；
- Evidence Router；
- CLI：

```text
skillflow defense catalog
skillflow defense diagnose
skillflow defense run-matrix
skillflow defense report
```

### 4–6 小时：Skill 与 Matrix

- 接入现有 8 类攻击；
- 新增 4 个 held-out attack/neutral pair；
- 能力匹配校验；
- 生成 228 Scripted + 32 Fake Smoke Matrix。

### 6–9 小时：运行与复算

- Scripted 全矩阵；
- Fake Reference Smoke；
- Replay；
- JSON/CSV；
- 从 Raw 独立复算。

### 9–12 小时：质量门与文档

- 定向和全量测试；
- Schema、ruff、mypy、doctor、pip check、禁网、密钥扫描；
- 写 T18 Summary；
- 更新 README/progress；
- 推送 GitHub。

## 11. 技术验收条件

只有全部满足才标记 T18 `COMPLETED`：

1. 四个 paper-inspired Defense module 均实现且有独立测试；
2. 每个模块的文档明确“采用/未复现”的边界；
3. Router 不读取攻击标签和 Scenario ID；
4. 24 个 attack/neutral variant + 4 个对照均完成预注册；
5. 4 个 held-out attack/neutral pair 未参与规则设计；
6. Scripted 228/228 core 终态完整；
7. Fake Reference 32/32 core 终态完整；
8. 所有适用 Replay 有结构化终态；
9. 所有 Effect、Receipt、Grant、Artifact、Session 绑定有效；
10. 诊断、路由、防御和结果均有 evidence IDs；
11. No Defense、四个单防御、All、Oracle、Evidence Router 均有结果；
12. 输出 diagnosis metrics、specificity matrix、risk/utility 和 cost；
13. 负面对照不被无条件统一阻断；
14. Unknown/缺证据路径能够 `abstain`；
15. Raw→report 可独立复算；
16. 不修改 T17 冻结数据、指标公式或原分母；
17. pytest 全通过，综合覆盖率保持当前 ≥90% 门；
18. Ruff、format、mypy strict、静态 Schema、doctor、pip check、no-excuse、禁网、凭据和泄漏扫描通过；
19. 生成 `docs/summaries/T18_Summary.md`；
20. README/progress 明确区分本地机制验证与尚未进行的 Live 泛化实验。

科学假设不作为软件 PASS 的前提。如果 Evidence Router 没有优于基线，也必须保存真实结果并解释原因，不能通过改标签、删样本或调规则追求正结论。

## 12. 产物

```text
docs/plans/T18_multiskill_dynamic_defense_one_day_plan.md
docs/research/skillflow-paper-storyline-and-validation.md
docs/summaries/T18_Summary.md
docs/evidence/t18-literature-adaptation.json
experiments/t18/preregistration.yaml
experiments/t18/defense-catalog.yaml
experiments/t18/skill-catalog.yaml
experiments/t18/matrix-scripted.yaml
experiments/t18/matrix-fake-smoke.yaml
schemas/t18-*.schema.json
datasets/t18-local/
  core-trials.jsonl
  replay-pairs.jsonl
  diagnoses.jsonl
  defense-plans.jsonl
  defense-outcomes.jsonl
  diagnosis-metrics.json
  defense-specificity.csv
  router-comparison.csv
  skill-metrics.csv
  sha256-manifest.json
  README.md
```

## 13. 不可声称

- 不声称完整复现 Task Shield、IPIGuard、DRIFT 或 AttriGuard 的原论文结果；
- 不声称本地 Fake/Scripted 结果等于真实 LLM 防御能力；
- 不声称 Router 已泛化到所有未知攻击；
- 不声称 All-Defense 或动态防御必然优于所有固定方法；
- 不把低攻击率单独解释为高安全性；
- 不把 attack label 当作运行时证据；
- 不自动开始付费实验。

## 14. 来源

- Task Shield，ACL 2025：<https://aclanthology.org/2025.acl-long.1435/>
- IPIGuard，EMNLP 2025：<https://aclanthology.org/2025.emnlp-main.53/>
- DRIFT，NeurIPS 2025：<https://proceedings.neurips.cc/paper_files/paper/2025/hash/77f3b26c7907aa27b207df9b9d43f29a-Abstract-Conference.html>
- AttriGuard，USENIX Security 2026：<https://www.usenix.org/conference/usenixsecurity26/presentation/he-yu>
- StruQ，USENIX Security 2025：<https://www.usenix.org/conference/usenixsecurity25/presentation/chen-sizhe>
