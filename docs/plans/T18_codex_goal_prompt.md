# Codex Goal：在一天内完成 T18 多 Skill 证据路由动态防御

你正在继续 `Suuuu123su/Agent-SkillFlow`。当前可信基线是 GitHub `main` 提交：

```text
707cf07dde60c98629707b810f5bb631f4db97fd
```

完整 T17 第二版已经完成。不要重跑、覆盖、回填或修改 T17 的冻结 Raw、Matrix、数据集、指标、Summary 和 SHA-256。

本次唯一总目标是：

> 在一个工作日内完成 T18：使用多个不同攻击机制的恶意 Skill，在 Scripted 与 Fake Reference 本地环境中，根据 SkillFlow 的可信运行证据动态选择不同防御，并完成 No Defense、固定防御、All-Defense、Oracle Router 和 Evidence Router 的安全—效用对比。最终仓库必须达到下一步可以直接增加更多真实 Skill 和 Live 模型验证的状态。

## 必读文件

开始前读取：

1. `README.md`
2. `docs/progress.md`
3. `docs/summaries/T17_Complete_Summary_V2.md`
4. `datasets/t17-v2/README.md`
5. `docs/research/skillflow-paper-storyline-and-validation.md`
6. `docs/research/attack-diagnosis-adaptive-defense.md`
7. `docs/plans/T18_multiskill_dynamic_defense_one_day_plan.md`
8. T17 Skill catalog、能力匹配、`compare-skills`、Reference Harness、Replay、TaskSuccess 和 Defense 实现

先输出不超过一页的审计，确认：

- T17 已完成并保持不可变；
- 当前已有哪些 Skill Variant 和 compare-skills 能力；
- T18 需要新增的最小文件；
- 本轮不会调用真实 Provider，不会产生 API 费用；
- 四种论文防御采用的是本地机制适配，不冒充完整复现。

## 顶会方法与本地实现

实现下面四个独立防御模块：

### 1. `TaskAlignmentGate`

依据 ACL 2025 Task Shield：

<https://aclanthology.org/2025.acl-long.1435/>

本地实现只使用可信 `TaskContract`、允许的 Effect、资源、必要依赖和当前 Task 状态，判断 proposed Tool Call 是否服务于用户目标。禁止额外 LLM Judge。

### 2. `ToolDependencyGuard`

依据 EMNLP 2025 IPIGuard：

<https://aclanthology.org/2025.emnlp-main.53/>

在读取不可信数据前机械生成最小 Tool Dependency Graph；只允许沿计划节点/边调用，参数和资源必须匹配 Schema。Tool Return 不能新增 Tool 或权限。

### 3. `DynamicRuleMemoryIsolator`

依据 NeurIPS 2025 DRIFT：

<https://proceedings.neurips.cc/paper_files/paper/2025/hash/77f3b26c7907aa27b207df9b9d43f29a-Abstract-Conference.html>

实现可信动态规则、权限偏离检查和 Memory 隔离。低可信或 revoked origin 写入的 Memory 进入 quarantine；后续 Session 默认不能把它作为控制指令。撤销保留历史证据，不原地删除 Event。

### 4. `CausalAttributionGate`

依据 USENIX Security 2026 AttriGuard：

<https://www.usenix.org/conference/usenixsecurity26/presentation/he-yu>

复用现有 checkpoint/identity/neutral Replay。对高风险且存在不可信来源的 proposed Effect 做 shadow replay；中和后 Effect 消失则记录确认影响并 DENY/CONFIRM；Replay 不可评估则 `abstain`，禁止伪造 CI=0。

完整 StruQ 需要专门训练模型，本轮不实现，也不得把简单分隔符包装称为 StruQ 复现。

每个模块必须在 `docs/evidence/t18-literature-adaptation.json` 记录：

- paper；
- venue/year；
- adopted_mechanism；
- local_implementation；
- omitted_components；
- reproduction_claim=false。

## 动态 Router

新增：

- `AttackSignalVector`
- `AttackDiagnosis`
- `DefensePlan`
- `DefenseOutcome`
- `EvidenceDefenseRouter`

Router 只能读取：

- Manifest/Grant；
- Scope/Lifetime；
- revoked origin；
- decision basis；
- Context/Tool Return/Memory provenance path；
- Effect/Receipt；
- candidate/confirmed influence；
- Session；
- Sink severity；
- evidence availability。

严禁读取：

- `scenario_id`
- `attack_family`
- Skill 文件名
- 文件路径中的攻击词
- 模型自报攻击类型
- 任何 Golden label

确定性路由规则按 T18 plan 实现：

- grant/scope/lifetime 问题 → TaskAlignment + Dynamic Validator；
- Context/Tool Return 问题 → TDG；高风险或不确定时加 Causal；
- Memory/revoked origin → Memory Isolator；有敏感 Effect 时加 Causal；
- 假授权且无 Grant → TaskAlignment + trusted confirmation；
- 混合攻击 → 最小防御并集；
- 证据不足 → `abstain`；高风险 Sink 转 confirm/deny。

基础 Grant、Scope、Lifetime、Receipt、预算和 Safe Sink 永远不能被 Router 关闭。

## 多 Skill 集

复用 B1、C1、C2、M1、M2、A1、S1、L1 及其能力匹配对照，并新增 4 个 held-out attack/neutral pair：

- privilege；
- context/tool；
- memory；
- authorization。

held-out Skill 不参与路由规则设计。`attack_family` 仅在全部 Run 结束后的离线评价阶段使用。

能力匹配必须验证：

- Manifest；
- Tool registry；
- input/output Schema；
- Task Contract；
- Grant 结构；
- 资源；
- 长度区间；
- capability fingerprint。

任何不匹配在运行前拒绝。

## 实验矩阵

默认只运行本地实验，不读取 API Key：

### Scripted

- 24 个 attack/neutral variant × 9 模式 = 216 core；
- B0/N0/G0/A2 × monitor/all/evidence = 12 core；
- 合计 228/228；
- 必要 Replay 不超过 20 对。

九个模式：

1. monitor
2. skillflow-enforce
3. task-alignment-only
4. tdg-only
5. drift-isolation-only
6. causal-only
7. all-defenses
8. oracle-router
9. evidence-router

### Fake Reference Smoke

- 4 broad families；
- 每类 1 个 attack/neutral pair；
- monitor/all/oracle/evidence；
- 32/32 core；
- Replay 不超过 8 对。

如果实际 catalog 使逻辑数量不同，先机械解释并冻结新分母；不得静默删条件。总规模只能因去除重复逻辑条目而缩小，不能丢失 8 类现有攻击、4 个 held-out pair 和 4 个对照。

## 必须输出的评价

### 诊断

- Macro-F1；
- multi-label F1；
- exact match；
- abstain rate；
- held-out Macro-F1；
- evidence citation validity；
- boundary localization；
- Oracle agreement。

### 防御

- UEA；
- VTE；
- C1/C2 HIAA；
- ALR；
- RIR(1/3)；
- Targeted Risk Reduction；
- Residual Risk；
- Task Success；
- Safe Task Success；
- Utility Loss；
- benign Over-defense；
- Defense Selection Regret；
- 额外 Step、Replay、延迟和 Fake calls。

生成 attack-family × defense 的 Specificity Matrix。不要构造公开单一总安全分。

## 科学与工程纪律

- 不按场景名或标签写死指标；
- 不为得到正结果修改 Skill、阈值或 Router；
- 结果不支持假设时也必须完整保存；
- `not_applicable`、`not_available`、`incomplete` 和 measured zero 严格区分；
- refusal/no-call/Schema/infra 分开；
- candidate path 不等于 confirmed influence；
- 真实攻击标签只能用于离线评分和 Oracle Router；
- 所有 Effect 进入 Safe Sink；
- 本轮 API 调用数与费用必须为 0；
- 不下载和运行论文作者代码作为不可审计依赖；
- 不声称精确复现论文结果。

## 交付

至少生成：

```text
docs/summaries/T18_Summary.md
docs/evidence/t18-literature-adaptation.json
experiments/t18/preregistration.yaml
experiments/t18/defense-catalog.yaml
experiments/t18/skill-catalog.yaml
experiments/t18/matrix-scripted.yaml
experiments/t18/matrix-fake-smoke.yaml
datasets/t18-local/
schemas/t18-*.schema.json
```

并提供 CLI：

```text
skillflow defense catalog
skillflow defense diagnose
skillflow defense run-matrix
skillflow defense report
```

从公开数据独立复算所有正式 JSON/CSV，记录 SHA-256。

## 完成门

只有以下全部满足才把 T18 标为 `COMPLETED`：

1. 四个防御模块实现并通过正负测试；
2. Router 不读取标签；
3. 8 类现有攻击、8 个匹配对照、4 个 held-out pair 和 4 个合法/负面对照已注册；
4. Scripted 228/228 完成；
5. Fake Smoke 32/32 完成；
6. 所有适用 Replay 终态完整；
7. 五类主要基线和四个单防御均有结果；
8. 诊断、Specificity、风险—效用和开销报告齐全；
9. held-out 结果单独报告；
10. 所有 Decision/Effect/Receipt/Grant/Artifact/Session 绑定通过；
11. Raw→report 独立复算通过；
12. T17 冻结证据哈希不变；
13. pytest 全通过，综合覆盖率保持 ≥90%；
14. Ruff、format、mypy strict、静态 Schema、doctor、pip check、no-excuse、禁网、密钥和泄漏扫描通过；
15. README、progress 和 `T18_Summary.md` 更新；
16. GitHub CI 通过并推送 main。

科学假设不作为软件完成门。即使 Evidence Router 不优于固定或 Oracle 基线，也要将 T18 标记为“实验完成、假设未支持”，而不是改规则或删样本。

现在连续完成所有离线工作、运行、复算、文档和推送；除非涉及删除/覆盖 T17、真实付费 API、真实外部副作用或无法解决的冻结合同冲突，否则不要中途停止询问。
