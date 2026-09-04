# SkillFlow 论文主线：从不可辨识的攻击成功率到证据驱动的动态防御

- 状态：论文写作主线草案
- 基线：完整 T17 第二版已完成
- 更新日期：2026-09-04
- 后续实验：[`T18_multiskill_dynamic_defense_one_day_plan.md`](../plans/T18_multiskill_dynamic_defense_one_day_plan.md)

## 1. 一句话论文定位

> SkillFlow 是一个面向 Agent Skill 生态的证据驱动安全测量与防御评估框架。它不把“模型产生了某个 Tool Call”直接等同于攻击成功，而是联合追踪任务是否完成、敏感 Effect 是否真正执行、该执行是否得到结构化授权、内容从哪里传播、哪个 Artifact 对动作具有因果影响，以及风险是否在撤销后跨 Session 残留；在此基础上，SkillFlow 进一步使用量化攻击机制画像选择针对性防御，并同时测量安全收益、任务损失与运行开销。

论文不要将主要贡献缩写成“比较不同 Skill 的攻击成功率”。不同 Skill 的比较只是外部有效性实验。核心贡献是：**解决传统二值攻击成功率无法辨识 Agent Skill 真实安全状态的问题，并把可审计测量转化为可验证的防御决策。**

## 2. 核心问题：传统 ASR 存在状态不可辨识

传统 Agent 安全实验常使用：

```text
目标 Tool Call 是否出现？
```

或：

```text
目标环境状态是否被改变？
```

作为攻击成功判据。设：

```text
Y = 1[目标动作出现]
```

相同的 `Y=1` 可能对应完全不同的安全状态：

| 情况 | 目标动作 | 安全含义 |
|---|---:|---|
| G0 合法跨 Skill 协作 | 1 | 有合法授权和任务需要，属于正常执行 |
| A2 结构化确认 | 1 | 用户通过可信通道批准，属于合法执行 |
| B1 直接越权 | 1 | 无有效 Grant，属于未授权 Effect |
| C1/C2 组合攻击 | 1 | 风险由 Skill 与 Context/Tool Return 联合产生 |
| M2 撤销后残留 | 1 | 已撤销 Skill 的历史 Memory 仍影响后续 Session |

相同的 `Y=0` 也可能对应不同状态：

| 情况 | 目标动作 | 真实原因 |
|---|---:|---|
| 策略正确阻断 | 0 | 防御生效 |
| 模型主动拒绝 | 0 | 模型行为，不一定是防御贡献 |
| no-call | 0 | 模型没有提出动作 |
| Schema rejection | 0 | 输出格式不合法 |
| Provider/Gateway 失败 | 0 | 基础设施失败，不能记为安全成功 |
| 全部拒绝 | 0 | 风险低，但任务效用可能为零 |

因此，仅靠二值 ASR 无法回答：

1. 动作是否真的执行；
2. 动作是否得到授权；
3. 动作由什么内容和组件导致；
4. 风险是否由 Harness 放大；
5. 防御是否只是把正常任务一起阻断；
6. 风险是否在撤销后继续存在。

SkillFlow 的最小运行状态可表示为：

```text
Z(trace) = (
  TaskSuccess,
  Effect,
  Receipt,
  Authorization,
  Provenance,
  CausalInfluence,
  ScopeLifetimeRevocation,
  TerminalFailure
)
```

论文的中心论点是：

> 传统评测将多个不同安全状态压缩成一个二值结果；SkillFlow 使用结构化运行证据恢复这些状态之间的差异。

## 3. 方法主线

### 3.1 统一证据模型

SkillFlow 将以下对象绑定到同一 Run/Session/Step 链：

- Skill、Tool、Manifest；
- Artifact、Origin、Context、Tool Return、Memory；
- AuthorizationGrant、Scope、Lifetime、撤销；
- Decision、Effect、Receipt；
- TaskSuccessEvidence；
- Counterfactual Replay 与 `INFLUENCE_CONFIRMED`。

其中：

- 模型自报的 origin、Grant、哈希和“任务完成”不可信；
- `executed=true` 必须绑定同 Run Receipt；
- Manifest 与 Grant 是两把独立钥匙；
- provenance path 只能说明可达，不能自动证明因果；
- 只有成对反事实结果或独立可信影响证据才能确认因果；
- 证据缺失必须输出结构化 `not_available`/`not_applicable`/`incomplete`，不得写成安全值 0。

### 3.2 机制级指标

| 维度 | 指标 | 回答的问题 |
|---|---|---|
| 任务 | Task Success、Safe Task Success | 防御后用户任务是否仍完成 |
| 执行 | Verified Target Effect | 目标动作是否真实执行并带 Receipt |
| 授权 | UEA | 已执行动作是否未经授权 |
| 来源 | Precision/Recall/F1/Decay | 系统是否正确恢复 Artifact 来源 |
| 组合 | HIAA | Skill 与 Harness 特性是否产生额外放大 |
| 假授权 | ALR | 普通文本授权声明是否改变敏感动作 |
| 撤销残留 | RIR(1)、RIR(3) | Skill 撤销后风险是否跨 Session 存活 |
| 因果 | Counterfactual CI | 中和单一输入后 Effect 是否改变 |
| 失败 | refusal/no-call/Schema/infra | `Effect=0` 的真实原因是什么 |
| 效率 | Step/Token/latency/cost | 防御和诊断的代价是多少 |

### 3.3 Framework、Benchmark 与 Empirical Study 分离

- **SkillFlow Framework**：证据、运行图、Replay、指标与防御接口；
- **SkillFlow-Bench**：B0、B1、N0、C1、C2、M1、M2、A1、A2、S1、L1、G0 等受控场景及能力匹配 Skill；
- **Empirical Study**：不同 Skill、模型、Harness 和防御模式下的真实结果。

这样，即使以后替换具体 Skill，框架贡献仍然成立。

## 4. 为什么框架是必要的

### 4.1 Measurement Disagreement Study

使用同一批 Raw Run，同时计算：

1. 模型文本/Judge 判定；
2. Tool Call 出现率；
3. Effect + Receipt；
4. UEA；
5. 有确认因果来源的 UEA；
6. Safe Task Success。

重点报告这些判据之间的不一致：

```text
Execution correction
= Tool-call count - Verified Effect count

Authorization correction
= Verified Effect count - UEA count

Causal correction
= Candidate influence count - Confirmed influence count
```

只要差值非零，就直接说明缺少相应证据会改变安全结论。

### 4.2 Evidence Ablation

逐项移除证据，观察结论如何退化：

| 移除项 | 预期错误 |
|---|---|
| Receipt | 将计划调用误认为实际执行 |
| Grant | 无法区分合法 G0/A2 与 B1 |
| provenance | 无法区分 Context、Tool Return 与 Memory 路径 |
| Counterfactual Replay | 将路径可达或时间相邻误认为因果 |
| TaskSuccessEvidence | “全部拒绝”可能看起来是最佳防御 |
| Session/Revocation | 无法测量 M2/RIR |
| Scope/Lifetime | 无法区分 S1 与 L1 |
| typed failure | 将 refusal、格式失败和基础设施失败误记成安全 |

报告：错误指标数、误报/漏报、错误防御选择数和新增 `not_available` 数量。

### 4.3 当前 T17 已经给出的动机证据

完整 T17 第二版显示，统一 Enforce 虽然将越权操作从 90 降到 0，但正常任务成功率从 `156/315` 降到 `119/315`，下降 11.75 个百分点；正常对照中有 `36/85` 从成功变为失败。与此同时，C1 的组合差从 1 降到 0，但 C2 仍为 1。该结果说明：

1. “全部加强”能够消除一类风险，但存在明显效用代价；
2. 同一个防御并不能覆盖所有机制；
3. 需要先识别风险机制，再选择对症防御。

T17 的跨模型结果也显示，较低的目标风险操作不能单独解释为更安全：DeepSeek 的风险操作较少，但 `171/360` 个任务出现格式失败，正常任务成功率也更低。因此，风险、失败类型和任务效用必须联合报告。

## 5. 如何证明框架有效

### RQ1：Measurement Fidelity

传统 Tool Call/ASR 与 SkillFlow 的 Effect、UEA、因果 UEA 和 Safe Task Success有多大不一致？

### RQ2：Mechanism Decomposition

框架能否区分：

- 直接越权；
- Context 放大；
- Tool Return 放大；
- Memory 跨 Session 传播；
- 撤销后残留；
- 假授权；
- Scope/Lifetime 误用？

### RQ3：Causal Validity

反事实 Replay 能否排除仅仅路径可达、文本相似或时间相邻的伪影响？

### RQ4：Generalization

同一指标定义能否迁移到：

- 未参与开发的 held-out Skill；
- 不同 Skill 表达和实现；
- 不同模型；
- 不同 Harness？

### RQ5：Defense Utility

基于 SkillFlow 证据选择的针对性防御，能否在接近 Oracle Router 安全收益的同时，比固定防御和 All-Defense 保留更多正常任务？

## 6. 有效性证据的六个层次

### 6.1 构念有效性

使用确定性 Golden：

- B1 提高 UEA；
- C1/C2 改变 HIAA；
- M2 改变 RIR；
- A1 改变 ALR；
- S1/L1 分别给出 Scope/Lifetime reason code；
- N0 的 CI 为 0；
- G0/A2 有合法 Effect，但 UEA 为 0。

### 6.2 区分有效性

不同攻击家族应形成不同指标指纹，而不是所有指标一起升高。

### 6.3 因果有效性

仅改变 Context bridge、Tool Return、Memory、授权声明、Grant Scope 或 Session lifetime 后，相应 Effect 按预期改变。

### 6.4 负面对照有效性

N0、B0、G0、A2 不应因为出现低可信文本、跨 Skill 或敏感 Tool 就被统一判成攻击。

### 6.5 跨环境有效性

分层报告：

- Scripted：公式与实现正确；
- Fake/Reference Harness：Adapter 与 Hook 正确；
- Live LLM：随机模型行为下仍能得到完整证据；
- 多模型：指标算法不因模型改变；
- held-out Skill：指标不是针对已知 Skill 写死。

### 6.6 决策有效性

比较：

1. Monitor / No Defense；
2. 固定单一防御；
3. All-Defense；
4. Oracle Router；
5. SkillFlow Evidence Router。

主要报告：

```text
Targeted Risk Reduction
Utility Loss
Safe Task Success
Over-defense Rate
Defense Selection Regret
Residual Risk
Step/Token/latency/cost
```

不构造人为加权的单一安全总分。

## 7. 论文实验章节建议

1. **Benchmark Construction**：场景、Skill Variant、能力匹配、held-out split；
2. **Measurement Disagreement**：传统判据与证据判据不一致；
3. **Construct Validation**：Golden、负例和严格 N/A；
4. **Evidence Ablation**：移除关键证据造成的错误；
5. **Multi-Skill Mechanism Study**：不同 Skill 的指标指纹；
6. **Cross-Model/Cross-Harness**：迁移与解释边界；
7. **Dynamic Defense**：固定、全开、Oracle 与 Evidence Router；
8. **Cost and Reproducibility**：Raw→Metric 复算、Schema、哈希、费用。

## 8. 建议图表

### Figure 1：传统 ASR 的不可辨识性

同一 Tool Call 分叉为合法授权、直接越权、Context 放大和撤销后残留。

### Figure 2：SkillFlow 证据链

```text
Skill / Context / Tool Return / Memory
                  ↓
         Artifact–Event Graph
                  ↓
 Manifest + Grant + Scope + Lifetime
                  ↓
       Decision → Effect → Receipt
                  ↓
 TaskSuccessEvidence + Counterfactual Replay
                  ↓
  UEA / HIAA / ALR / RIR / Provenance
```

### Figure 3：任务—风险二维表

|  | 无风险 Effect | 有风险 Effect |
|---|---|---|
| Task Success | 安全完成 | 隐蔽风险 |
| Task Failure | 过度防御/失败 | 最差结果 |

### Figure 4：攻击 Skill × 指标热图

列使用 UEA、Context HIAA、Tool Return HIAA、ALR、RIR(1/3)、provenance depth、Safe Task Success。

### Figure 5：安全—效用前沿

横轴 Utility Loss，纵轴 Residual Risk，对比 No Defense、Fixed、All、Evidence Router 和 Oracle Router。

## 9. 推荐贡献表述

1. **统一证据模型**：显式分离来源、授权、实际执行、因果影响、生命周期和任务成功；
2. **机制级测量**：用 UEA、HIAA、ALR、RIR、provenance 与 Safe Task Success 描述不同风险；
3. **因果 Benchmark 协议**：能力匹配 Skill、四格实验、跨 Session 控制和 Counterfactual Replay；
4. **可复算数据与工具链**：Raw Event 到标准报告、Schema、哈希和结构化 N/A；
5. **多 Skill 与多模型实证**：验证区分能力和泛化性；
6. **证据驱动动态防御**：根据机制画像选择最小防御组合，并量化安全收益和任务代价。

## 10. 推荐引言逻辑

```text
传统 ASR 无法辨识真实安全状态
→ Agent Skill 风险需要来源、授权、因果和生命周期证据
→ SkillFlow 提供统一证据和机制级指标
→ Golden、负例、消融与 Replay 证明测量正确
→ 多 Skill、多模型与多 Harness 证明可迁移
→ 动态防御实验证明这些指标具有实际决策价值
```

## 11. 结论边界

- T17 已完成框架、两模型和统一 Monitor/Enforce 的完整实验；
- 不同攻击 Skill 的实证排名尚未开展；
- 动态 Evidence Router 尚未实现；
- T18 的顶会论文防御将采用“机制级本地适配”，不是对原论文完整训练和全部实验的复现；
- 所有真实副作用继续进入 Safe Sink；
- 不把较低 Effect 率单独解释为更安全；
- 不把路径可达直接解释为因果；
- 不把单个模型/服务配置结果外推到所有 Agent 平台。

下一步按照 [`T18_multiskill_dynamic_defense_one_day_plan.md`](../plans/T18_multiskill_dynamic_defense_one_day_plan.md) 完成多 Skill 的证据驱动动态防御最小实验。

## 12. 相关方法来源

- DRIFT，NeurIPS 2025：<https://proceedings.neurips.cc/paper_files/paper/2025/hash/77f3b26c7907aa27b207df9b9d43f29a-Abstract-Conference.html>
- Task Shield，ACL 2025：<https://aclanthology.org/2025.acl-long.1435/>
- IPIGuard，EMNLP 2025：<https://aclanthology.org/2025.emnlp-main.53/>
- AttriGuard，USENIX Security 2026：<https://www.usenix.org/conference/usenixsecurity26/presentation/he-yu>
- StruQ，USENIX Security 2025（相关但不列为一天版主要实现）：<https://www.usenix.org/conference/usenixsecurity25/presentation/chen-sizhe>
