# P4结项实施说明：只收尾，不重新开实验

## 1. 输入优先级与单次整理

已完成P4的原生输出是数值来源；外部复核是解释、二次核对与结论边界来源；本任务包中的参考数仅用于核对，不作为预设正确答案。原报告与外部解释出现差异时并列登记，不回写旧数据。

建议输入：

|用途|P4原包成员|
|---|---|
|范围/状态|P4_STATUS.json、LOCAL_BINDINGS.json、SOURCE_MAP.json、MANIFEST.json|
|指标汇总|P4_METRIC_MAIN.csv、P4_METRIC_MAIN.md、ABLATION_LONG.csv|
|原定义|METRIC_CONTRACTS.csv/json/md、MASK_DEPENDENCY_MAP.json|
|消融转移|FULL_TO_VIEW_TRANSITIONS.csv、ELIGIBILITY_UNKNOWN_TABLE.csv|
|参照|INDEPENDENT_REFERENCE_SCORES.csv、GOLD_PROVENANCE.jsonl|
|最小证明|IDENTIFIABILITY_WITNESSES.json、CASEBOOK.json/md、TASK_EVIDENCE_RECONSTRUCTION.csv|
|必要逐查询核对|QUERY_REGISTRY.jsonl、results/V00…V12.jsonl|
|复现与旧检查|REPRODUCE.md、checks/PORTABLE_RECOMPUTE.json、checks/ZIP_ROUNDTRIP_RECOMPUTE.json|

优先读已经完成的汇总，不重新构造许可视图或运行全套预测。某个分层需要逐查询数据时，允许一次读取保存的JSONL做机械聚合，但不要同时将results/QUERY_RESULTS.jsonl和V00…V12重复加入分母。

本轮新增处理记录与旧检查次数分开。hash一致只保证提交字节一致，不证明原始自然语言语义真值、提供方不可变权重或所有执行历史。

## 2. 结项不能“修好”哪些历史限制

必须在RETAINED_LIMITATIONS.md保留：

|问题|本轮准确表述|
|---|---|
|自然语言真值|独立参照来自有限模型与受控状态机；没有新增自然语言人审|
|Full两项未知|来自同一个缺reason构念的两种ALR合同；Full许可视图不是全知库|
|旧CI|593个结构有效对中289个中和破坏JSON，另304个语义有效性未自动确认；不是精准控制语义因果gold|
|新Live ALR|原敏感请求分母0/0，不写0%洗白风险|
|RIR|目标/中性chain各0/4，不撤销同样无目标风险；不能说明撤销因果收益；confirmed-prefix缺合格数据|
|pot|旧观测效果集合差与新声明有限域静态可达量分开，不回填旧T17|
|Task证书|1059条可由独立对象与会话事实恢复；证书形式并非独占必要，任务完成信息仍重要|
|Scope参照覆盖|动作级参考引擎没有完整生产Scope语义；本子集无变化不证明Scope无用|
|有限见证|证明声明观察限制内不可辨识，不证明框架唯一性或任意平台上的普遍下界|
|最小证明|保存合同级支持路径，不宣称遍历全部证据子集找出全局最小|
|研究版本|P0/P2的历史模型和传输混杂不因P4而解决；各STS不能混名混分母|

这些是结项保留边界，不是本轮新增补样或修改算法的待办。

## 3. 三张表怎样编排

### 表A：机制实证（放在前）

显示列建议：`execution_domain / study / model_or_engine / metric / contract / design / unit / numerator_or_cells / denominator / value / status / limit / source_ref`。

按机制而非防御名排序。HIAA显示四格和差中差；pot区分observed与declared；ALR区分旧推导reason点值、T11_explicit_reason严格范围和identity附加门；RIR区分legacy、chain和confirmed-prefix以及k；CI标题明确旧整对象消融差。不要给不能相除的指标硬填一个统一numerator/denominator，使用null并填写cells/witness/unit。

P3原表中的bootstrap区间保留原名称，缺证识别范围另列。有限模型pot=2是权重和，不写成200%。若相关P3已存源文件不在本地，先链接其准确来源并登记缺项；不能从记忆补一个“已核对”数字。

### 表B：P4指标×证据视图（主结果）

完整附表沿用 `view_id, domain, study, phase, metric, protocol, horizon, source_variant, branch` 分组字段，固定查询分母不能因消融后资格未知而变小。

汇总状态保留：point、bounded、unknown、not_applicable、conflict、analysis_error；eligible_unknown是资格维度，不能又加到总体上。表中“可判断”应明确是可给点值，点值可以为布尔、数值或集合，不是风险发生率。

另外生成自身/下游影响表，建议字段：

`view_id, masked_family, affected_metric, relation(self_or_downstream), full_point_n, view_point_n, point_loss, point_to_bounded, point_to_unknown, eligibility_transition, query_denominator, mapping_basis`。

self/downstream由事先解释的证据—命题关系决定，不随数值大小改归类。只在能确定且已经存在的分类上填值，不臆造每类全部下游语义。来源例子的核对式为：`8166 = 7472 + 87 + 593 + 14`；7472/8166约91.50%，不是7472/19392。

### 表C：独立参照、覆盖与一致性

同时展示参考查询数、真值确定且适用数、可判断数、已判断一致数、错误确定数与覆盖。不把314、308、192、190混成一个分母。已答为0时一致率为空，不填100%。

13视图全部保留，并按UEA/ALR/RIR/pot等合同列附表。总览只是有限参考集合的描述，单查询或同源多个合同不增加独立任务数。

核对行：Full190/192；V01 Receipt137/192；V02 Grant48/192；V03 Provenance176/192；V06生命周期51/192；V05任务证书190/192。其余视图从原表读取，不依照这些例子推断。

## 4. 指标显示名对照（仅报告层）

|原字段/合同|建议显示方式|不能混用|
|---|---|---|
|P4 E_STS|STS_target_contract；附原metric和protocol|P0辅助E_STS、UEA型STS|
|P0 E_STS|E_STS_posthoc(P0)；仅解释，不重算|受控工具事件金标准|
|ALR / T11_explicit_reason|ALR—显式reason原七条件|P3R_identity_guard|
|ALR / P3R_identity_guard|ALR—附加identity执行门|旧T17推导reason点值|
|HIAA_pot_observed|观测未授权效果集合差|静态穷尽能力|
|HIAA_pot_declared|声明有限域可达能力差|任意平台能力上界|
|CI legacy|旧整对象消融的有符号效果差|精准移除控制语义的因果效应|
|RIR legacy/chain/confirmed_prefix|逐合同与k标明|统一无条件残留率|

这些是本轮建议的显示别名，不声称源代码已经改名。表内必须同时保留原ID，所有原CSV/JSON字段保持不变。

## 5. 六张已有案例卡

|卡|必需来源与说明|
|---|---|
|W1|V02下unexecuted_but_reachable与authorized_excluded_from_U；相同许可观察、真实pot2/0|
|W2|V10下unexecuted_but_reachable与same_sets_true_zero；相同许可观察、真实pot2/0|
|R1|从已有重建表挑一条任务证书冗余案例；列余下对象/义务/会话足够的实际路径|
|S1|从已有案例挑有效Grant或其他已知false使ALR保持false；缺一个条件不强制全unknown|
|I1|F/Context scheduled Full HIAA=1，去Receipt为[-1,1]；四格哪些效果资格未知|
|U1|unknown_reason-alr-original的Full未知；参照有真值、许可输入未暴露原因|

不得新增更“好看”的样本，不把同一有限对重复计成独立证据。若原实际ID与显示名不同，绑定实际ID并保存别名。每卡用简短中文说明，带原文件哈希/JSON pointer或行号。

不可辨识论证只需说明：两个有限世界的许可观察一致而真值不同，所以只用该观察的估计器无法保证对二者都输出正确点值。不要进一步声称SkillFlow唯一、所有系统都需要同一种证书或所有场景都受同一限制。

## 6. 好坏例子：收尾只改解释，不改事实

|不好|应当这样写/做|
|---|---|
|P4有252096次独立安全实验|19392个固定查询×13视图的离线结果；共享事实、合同、会话相关|
|所有视图准确率100%，一样好|同时给可判断覆盖和已答一致；Full190/192，删Grant48/192|
|删来源损失最大，所以来源最重要|分别显示7472个自身查询与694个下游查询的点值损失|
|F严格ALR一定14/24|旧点值14/24；显式reason严格范围[0,15/24]；加identity范围[0,14/24]|
|P4的E_STS可以直接与P0合并|逐条命名合同；风险selector端点和辅助实际违规V不同|
|任务证书没影响，所以不需要检查任务完成|当前对象、义务、会话提供了可替代证明路径|
|把unknown补成false以完成结项|状态管理可结项，未知和NA原样保留|
|为了让附录更齐全重跑全部视图|读已保存结果做必要汇总；算法和预测不重启|
|把上次832条复算记为本轮新增验证|外部既有检查和本轮文档核对分别列明|
|顺手开始P5画像算法|仅归档原规划，状态保持NOT_STARTED|

## 7. 最小交付结构

```text
论文材料/P4_测量证据消融/closeout-<timestamp>/
  README.md
  P4_CLOSEOUT.md
  P4_CLOSEOUT_STATUS.json
  INTERPRETATION_AMENDMENTS.md
  METRIC_NAME_MAP.csv
  PAPER_TABLES.md
  tables/
    mechanism_results.csv
    metric_ablation.csv
    self_vs_downstream.csv
    independent_reference.csv
    paper_tables.tex
  PAPER_P3_P4_SECTION.md
  PAPER_CASES.md
  CLAIM_EVIDENCE_MATRIX.csv
  RETAINED_LIMITATIONS.md
  SOURCE_MANIFEST.json
  CLOSEOUT_CHECKS.json
  REPRODUCE.md
  COMMIT_REVIEW_LIST.md
  code/                 # 实际生成/验证这些新表的轻量脚本（如需要）
```

不用新增评分器或大数据镜像，不要求生成图像、PPT、PDF或完整论文。将P3/P4章节草稿控制为可以直接放入论文的初稿，而不是再复制十几份历史日志。

REPRODUCE说明两个不同入口：本轮汇总从已存表重建；原P4的可选原始预测复算入口仅供未来审查者使用，本轮不默认执行。相对链接须能解析；原包字节无法装入审查包时提供准确哈希和实际本地获取路径，说明依赖，不伪称单包可复算全实验。

## 8. 八项本轮验收

1. 输入身份：所用P4版本、成员及来源可追踪；不把旧任务包当完成结果。
2. 表格一致：MD/CSV/LaTeX同源生成；状态及分母与保存结果相同。
3. 分解一致：自身/跨指标影响不重复，来源8166分解可复算。
4. 合同一致：ALR两种严格合同、旧点值及各STS显示不混淆，别名不修改原字段。
5. 主张一致：192不是独立任务；范围不是置信区间；0错误仅限独立参照已答集合。
6. 案例一致：6张卡可定位；两组见证范围有限；无新增人工确认或模型结论。
7. 保全与发布边界：旧输入/预测/标签不变；用户既有修改不覆盖；无commit/push。
8. 可交付性：链接/哈希/ZIP成员可检查；状态真实，有缺口就记录；不启动后续阶段。

定向检查失效时先修文档或汇总脚本；只有发现真实预测数值矛盾才登记问题，不能在收尾任务中静默修改算法和全量重算。结项不以所有已答问题正确、所有删证都变差、所有历史指标都有点值为门槛。
