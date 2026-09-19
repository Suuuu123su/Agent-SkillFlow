# 缺证可辨识性与证据恢复：独立查新和先导审查

日期：2026-09-19。

审查后端：**native gpt-5.6-sol / xhigh fallback**。`DOSSIER.md` 所述 Codex MCP reviewer 在当前环境不可用，因此未调用该工具。本审查只读检查了查新说明、合成见证、冻结计划、归档 predictor/views/reference 源码、v1 结果和后补有限参照结果；未运行模型实验、付费请求或业务动作。

## 总判定

**PROCEED WITH CAUTION。**收窄后的“agent 机制合同证据边界与恢复成本实证”通过本轮早期查新门；当前没有找到一篇已发表工作完整包含这组限定对象、通道级投影、同观察异真值见证和有限参照审计，因此不满足 `ABANDON` 条件。

算法性表述没有通过：缺证下的可靠监测、可能世界抽象、随新增观察更新判定和按成本主动取特征都有明确先例；本次 `contract_guided` 也没有优于按指标固定顺序的覆盖率证据。当前可守住的差异是一个**合同特定、离线、描述性的测量审计**，不是新三值逻辑、新不可辨识定理或新主动采集算法。

可核查的一句话差异应写成：

> 对固定的 agent 机制合同和许可观察接口，使用通道级缺证投影、同观察异真值构造和与 Full 分离的有限参照，测量确定判断覆盖、错误确定性以及恢复证据的离线代理成本。

这个差异仍然偏薄。它要成为论文贡献，至少需要出现不能从 predictor 的字段读取关系直接推出的、跨合同或跨运行来源仍成立的非平凡实证发现。

## 最近邻与真正剩余的空间

1. [Leucker et al., *Runtime Verification For Timed Event Streams With Partial Information*（2019）](https://arxiv.org/abs/1907.07761)已经用抽象事件流表示缺口内可能轨迹，并在不完整轨迹上产生可靠输出。它覆盖了“缺证时对所有相容轨迹保守判断”的一般思想。
2. [Kallwies et al., *Symbolic Runtime Verification for Monitoring under Uncertainties and Assumptions*（2022）](https://arxiv.org/abs/2207.05678)明确处理缺失或不精确输入，并随着新增观察迭代更新符号判定。它直接限制“补观察后从未知恢复判断”的理论新颖性。
3. [Li and Oliva, *Dynamic Feature Acquisition with Arbitrary Conditional Flows*（2020）](https://arxiv.org/abs/2006.07701)在预测时按信息价值和成本主动获取特征；[Galwaduge and Samarabandu, *Explanations-Driven Active Feature Acquisition for Algorithmic Recourse*（2026）](https://arxiv.org/abs/2609.12179)进一步用解释信号指导按成本取特征。因而，读取 `missing_evidence` 决定下一通道不能单独作为算法贡献。
4. [Vigil（2026）](https://arxiv.org/html/2606.26524v1)是 agent-skill 合同侧最近邻：它把跨调用时序和值流规范化为有限轨迹上的 SMT 检查，但 §III-C 明确假设可信采集器完整，§IV-B 依赖闭世界事实。SkillFlow 的剩余空间是实测该完整性假设被放松时，哪些具名机制结论仍可判定、哪些证据能恢复判定以及代价是多少。这里不能暗示 Vigil 在其假设内不可靠。

因此，最接近的组合不是一篇完全重合论文，而是“partial-information runtime verification + active feature acquisition + agent runtime contracts”。论文必须把贡献定位在三者交叉处的具体证据合同与实证发现，并清楚承认三部分基础均已有工作。

## 当前证据支持什么

| 命题 | 审查结论 | 证据边界 |
|---|---|---|
| 存在同观察、相反 UEA 真值的缺证世界 | **支持，有限构造** | 三对 receipt/grant/lifecycle 合成世界可见 JSON 哈希分别相同，合同真值相反；Full 和恢复后 6/6 正确，缺证后 6/6 未给点判断。独立真值函数未调用 Analyzer。|
| 当前投影上的点判断没有被 Full 反转 | **支持，属于同 predictor 一致性** | v1 的 53,040 行和有限参照扩展的 51,935 行中，没有发现 partial point 与 Full point 不一致；这不是自然世界正确性。|
| 有限构造上的错误确定性得到控制 | **支持，严格限于构造** | 扩展含 235 query 行、36 个分支文档、9 个 `independence_group`／构造族；128 个 query 有点真值，126 个得到点判断且 126 个与独立代码路径参照一致，2 个保留未知。不得把 235 或 126 当作独立任务数。|
| 合同导向自适应策略提高覆盖或成本效率 | **不支持** | v1 与扩展中，`contract_guided` 和 `metric_fixed` 在两个缺证条件的每个 family budget 上，点覆盖、未知率、Full 状态一致率和平均 family acquisition 完全相同。少量 byte 差异不足以建立方法优势。|
| 对历史／自然 agent 运行的正确性 | **不支持** | v1 只有 9 个 query 有有限参照，其中仅 5 个有点真值；其余历史结果主要是与 Full 的一致性。扩展全部来自 `CONTROLLED_CONSTRUCT`，且是看到 v1 结果后计划的有限检查。|
| 在线采集节省、全局最小证据或一般可辨识边界 | **不支持** | 当前成本是 family 数和序列化 JSON 字节代理；没有在线采集、时延、传输或日志系统开销，也没有枚举一般相容世界或全局最小子集。|

补充检查值得保留，因为它将 v1 的“5 个点参照”扩为可审计的有限构造检查，且计划明确披露其 post-v1 性质。它不是未触碰的验证集，也没有 CI query；CI 的实现问题不能由该扩展解除。

## 先导设计审查

### 1. 未发现直接的 Full／标签泄漏，但存在自依赖

v1 的选样只用 query、domain 和 registry `independence_group`；策略轨迹全部完成后才读取 `GOLD_PROVENANCE.jsonl` 和 Full。`choose_family` 不接收 Full、reference、原始隐藏文档或其他 query 结果。计划、runner 和归档哈希与结果状态中的记录一致。扩展选择所有冻结指标下的 `CONTROLLED_CONSTRUCT` query，也没有按 predictor 或 gold 结果筛选。就已检查源码而言，**没有直接 oracle/Full 标签泄漏**。

`contract_guided` 读取的是同一 Analyzer 返回的 `missing_evidence`。这不是标签泄漏，但它是被评估 predictor 对自身读取依赖的 introspection，无法证明可迁移策略优于该 predictor 的静态合同表。策略顺序也来自同一合同实现知识，计划在预测前冻结只能排除本轮结果窥视，不能形成跨实现或跨域的样本外验证。

独立参照代码没有 import predictor，也没有读取旧分数或 Full；但它与 predictor 使用同一批冻结构造事件和同一合同语义。应称为“独立代码路径有限参照”，不能称数据独立或自然语言 ground truth。

### 2. `missing_evidence` 没覆盖跨字段依赖

这是当前最具体的实现限制。`views.project` 在移除 provenance 时会清除 counterfactual 分支内的 `source_object`；Analyzer 的 `missing_evidence` 只记录经顶层 `get` 读到 `None` 的字段，不会把这个嵌套清理登记为 provenance 依赖。

结果已经暴露该问题：v1 的 all-nine-missing、budget 2 有 8 个 CI query，five-missing、budget 1 有 2 个 CI query，在 `metric_fixed` 与 `contract_guided` 间出现逐 query 状态差异。固定顺序恢复 provenance 后给出 bounded/eligible 状态；guided 根据显式 missing list 先恢复 receipt，却得到 eligibility unknown。两个策略的汇总点覆盖恰好相同，不能掩盖单 query 轨迹不同，也不能把 `missing_evidence` 称为完整合同依赖解释。

最小修复是把跨字段清理也输出为显式 dependency token，并为每种 profile 检查“所有被清理位置均映射到同一个收费通道”。若不做，应把 `contract_guided` 改名为“top-level missing-field heuristic”。有限参照扩展没有 CI，不能验证这项修复。

### 3. 停止规则在当前归档上可接受，但只表示最大预算

实现只在 `point` 或 `not_applicable` 时停止；bounded、eligibility unknown 和 predicate unknown 都继续恢复。在现有两批结果中，没有 definite point 或 definite eligibility 被 Full 反转，也没有有限参照下的错误点判断。因此，当前有限归档没有显示错误的早停。

不过，停止后的状态会在后续 budget 行重复，所以 budget 3 的结果表示“允许最多恢复 3 个 family，并可提前停止”，不是每个 query 恰好获取 3 个 family。Full 行的 `acquired_cost=9`、`added_json_bytes=0` 只是比较器编码，必须从成本图和成本均值中排除。当前观察不能证明新合同、任意证据子集或未知采集损坏下都满足单调性。

### 4. family 和 byte 预算不能互相替代

一次 family 恢复会恢复整个 query 文档及嵌套分支中的该通道，不同 family 的字段数和字节量相差很大。相同 family budget 只保证名义获取次数相同，不保证证据量、日志调用数或在线开销相同。

`added_json_bytes` 将每一步 `after_size-before_size` 截为非负后累加；跨字段投影可使通道交互和路径顺序影响该值。它还不计 five-missing 条件一开始已有的 4 个 family，因此两个缺证条件之间不能用 `added_json_bytes` 直接比较总成本。最低限度应同时报告 `initial_json_bytes + net(final_size-initial_size)`、实际恢复事件/字段数和 family 数，并在统一总 byte 阈值下重算曲线。未测真实采集时延或传输开销前，只能称“序列化负载代理”。

### 5. 统计单位和 post-hoc 扩展必须保持可见

v1 有 240 个不同 registry unit，但主要样本集中在少数历史 source block 和共享模板；registry unit 唯一并不证明任务独立。8 个随机顺序 seed 是同一批 query 的重复测量，不能扩充样本量。

有限参照扩展的 235 个 query 来自 36 个分支文档和仅 9 个 independence group／构造族；每族包含多个 request、protocol 或 horizon query。正确表述是“在 9 个具名构造族的枚举 query 上未观察到错误确定判断”，不要给基于 126 个独立 Bernoulli 样本的置信区间。扩展是在看到 v1 参照不足后制定，适合做实现健全性检查，不适合叫 held-out validation。

### 6. 缺证机制覆盖仍窄

先导只实现 all-nine-missing 和按哈希固定保留 4/9 family 两种条件。它没有估计自然缺失分布，也没有实现按失败相关的缺失机制。若论文提出“对现实采集损坏稳健”，至少要预注册整通道故障和与失败／执行结果相关的压力条件；否则限定为人为 channel mask audit。

## 最小修改与继续条件

1. **删除算法优势主张。**把 `contract_guided` 与 `metric_fixed` 的相同覆盖曲线作为阴性结果；全局固定顺序较差只说明按指标写静态依赖顺序有用，不能证明动态策略有用。
2. **补全依赖账本。**冻结每个合同的顶层和跨字段依赖，特别是 provenance→counterfactual `source_object`；让投影、收费和 policy 可见依赖使用同一份机器可检验映射。
3. **分开一致性和正确性。**Full 只作为同 predictor 参照；有限构造参照单列；unknown 和 N/A 不计为正确。若要外推到真实 agent 运行，需要新的、独立标注或外部记录器参照。
4. **按真实实验单位报告。**v1 至少按 source block／模板／运行簇拆分；扩展按 9 个构造族报告。所有 policy、budget 和 seed 保持配对，不作为新任务。
5. **统一成本。**给出 family、字段/事件、总序列化字节三种曲线，包含初始证据成本；只有实际测量在线采集后才讨论时延或系统节省。
6. **若继续追求论文贡献，使用冻结的跨合同或跨来源留出。**策略设计和依赖映射在开发合同上冻结，在没有用于制定顺序的新 metric 实现或外部 trace source 上验证。否则将结果定位为当前 SkillFlow predictor 的实现审计。

## 校准后的可用措辞

可以写：

> 在固定的 SkillFlow 机制合同和许可观察接口上，我们执行通道级缺证审计。三对合成 UEA 世界证明当前观察不足以区分相反合同真值；在九个有限构造族中，所有具有点参照且被系统确定回答的 query 都匹配独立代码路径参照。按指标固定恢复顺序与基于 `missing_evidence` 的启发式在每个 family budget 上得到相同汇总覆盖，因此本先导不支持自适应策略优势。

不能写：“首个缺证运行验证框架”“通用可辨识性理论”“最小安全证据”“自适应恢复显著优于静态策略”“235 个独立任务上 100% 正确”“验证了自然 agent 真值”或“降低了在线成本”。

HIAA 资格修复应继续作为测量合同修复和可复现性工作单列；本 evidence-recovery pilot 明确没有 HIAA query，不能用它为 HIAA 修复提供额外机制贡献。
