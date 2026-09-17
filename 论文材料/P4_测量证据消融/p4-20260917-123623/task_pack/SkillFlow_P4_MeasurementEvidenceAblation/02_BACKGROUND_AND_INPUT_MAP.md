# 新对话背景与输入地图

## 1. 研究中心与阶段状态

SkillFlow将来源、对象版本、授权用途、实际Effect/Receipt、Session/撤销、任务完成及反事实证据分开绑定。HIAA/ALR/RIR等量区分不同机制，防御原型只是下游应用。本轮属于框架测量验证，不比较哪套防御ASR更低。

P0完成585条历史观测的辅助标注，尚未独立人审；P1延期；P2 All完成但与历史Evidence非严格同环境。P3先恢复旧指标，P3-R进一步补静态有限域、严格三值、原始M2失败定位和少量Live可测性。不能将旧暂停、旧未知或部分支持状态因P4而抹掉。

## 2. 当前直接输入

原P3-R审查包上传名 `91e6e0d7-231b-47a6-964a-db3cc391ebf6.zip`；本地交付名可能不同。请按以下成员、来源哈希和SOURCE_MANIFEST定位。

|成员/入口|本轮用法|不能怎么用|
|---|---|---|
|`P3R_FINAL_REPORT.md`、`P3R_METRIC_MAIN.md`、`METRIC_CONTRACTS_P3R.md`|确认版本、范围、统计单位与已有边界|不能把旧结果列作为当前待测预测输入|
|`SOURCE_MANIFEST_P3R.json`|定位T17原分卷及本地源码；记录本地头曾为21efe89a11b56b2f48ae6f351ef46cca467913fb|不是当前远端HEAD，不reset到它|
|`construct/execution-v1/`、`construct/unknown_reason_observation.json`|读取既存正负/缺证状态、事件、Artifact和回执|不执行构念生成器，不把case名称输入预测|
|`review_slice/units/`、`review_slice/observations/`|便携的已有构念事实|index的expected与答案只进评估侧|
|`review_slice/index.json`|离线控制器建立单位/分支清单|不能把expected或positive等ID语义泄漏给分析器|
|`POT_SETS_AND_WITNESSES.json` / `review_slice/pot.json`|提取有限域原始model声明；独立状态枚举作参照|model和result要拆开；预测器不得直接读result|
|`evidence/CI_RAW_INTERVENTION_OBJECTS.jsonl`、`CI_FULL_AND_STABILITY.csv`|读取旧original/neutral字节、配对与稳定性；解析完整性核对|CSV中ci、旧valid标签不是新精准因果gold|
|`evidence/ALR_ORIGINAL_DATABASE_LOOKUP.jsonl`、`ALR_STRICT_FUNNEL.csv`|追溯实际请求与原因缺失；旧表只核对|推导reason不能伪装直接记录|
|`live/units/**/state.json`、`LIVE_UNITS.csv`及生命周期表|新Live观测、实际前缀/后缀/Session|不把summary中的eligible/status当原始事实；不得读取凭据|
|`datasets/t17-v2/stages/f,g,h/`与各自dataset-manifest分卷|HIAA四格、UEA、来源、旧Replay的全量事实|不得只读首卷；不能把H复用F重复加入|
|T18既存原始记录与`T18_ALR_RIR_RECOVERED.csv`|已保存Scripted/Fake构念分层|仅有汇总不能作逐例准确率gold|

实际ZIP确认有P3-R的`analysis/`、`construct/`、`review_slice/`、`legacy/`和`live/`。分析器不允许动态导入整个analysis目录；其中包含串行控制器和参考业务执行器。只读源码后提取无副作用计算函数或另建标准库适配器。

任务包不附几十MB原始数据，用户本地已有这些输入。`references/`仅提供短报告与合同副本；P4真实数据要从上表绑定。

## 3. 数量和复用关系

历史主域：F360、G360、H新增270，共990个核心观测；F/G/H原Replay候选各270，共810。593个旧结构有效配对=237+122+234，仍含因果解释限制，不是593个全合格控制语义反事实。预检48与36 Replay不混入正式主域。

P3-R新增Live：原账本292请求已结束，52个实际单元=34 RIR+16 ALR+2 TECH。其来源树共享前缀，26个RIR后缀中的78个会话并不是78个独立任务。6个neutral未执行及2个TECH未用保留为原计划状态；P4不补跑。

T18为264 Scripted、44 Fake/Reference的历史域；本轮只纳入相关机制可恢复事实，实际范围在QUERY_REGISTRY冻结。T17与T18、构念与Live、新旧RIR/ALR合同互不混分母。

## 4. 必须继承的最新研究限制

- HIAA_run是target/neutral × bridge on/off四格目标效果差，不能替换成Evidence−All的ASR差，也不恒等于UEA。
- 旧HIAA_pot枚举观测执行集合，不是静态全能力；新declared_v1仅限已声明有限域。
- 旧ALR暴露F24/G15的直接baseline_reason未追回。严格F为0真/10假/14未知，G为0/9/6；H为0/22/0。T11第5条件与新参考引擎附加identity门分开。
- 新Live ALR没有network.send请求，分母0；不能为P4补虚构敏感请求。测量逻辑正例由既存受控构念验证。
- 新RIR目标4、中性4前缀都形成Memory，主要撤销original分支k1/k3各0/4；不撤销对照也为0，不证明撤销改善。confirmed-prefix仍无合格队列。
- 当前RIR后缀保留完整前缀对话；neutral只改Memory，不是剥离全部历史语义。
- 593个旧CI配对中289个neutral破坏原JSON可解析性；其中58个正差也受影响。其余304个不自动通过业务语义保持。旧CI可作整对象消融效应描述，不作精准控制语义的gold。
- 原统计、方法版本、人审0、历史模型别名和上下文差异不因本轮离线处理改变。

以上来自本轮读取的P3-R原报告、合同及外部复核；不是P4新计算结果。必要引用与原文件哈希在`source_refs.json`。

## 5. 后续算法不在本轮

当前Evidence的局部来源/意图/版本证据和HIAA/ALR/RIR聚合画像不是一回事。本轮不实施Evidence-Profile-v1、不调整Router或恢复，不从新证据消融结果推出防御收益。后续是否需要画像接口，待P4形成清楚的“哪些证据支撑什么判断”后另议。
