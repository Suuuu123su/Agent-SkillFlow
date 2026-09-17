# 新对话背景与输入地图

## 1. 研究对象

SkillFlow把Skill、工具、Artifact、Memory、真实授权、Scope/Lifetime、Decision、Effect、Receipt、任务完成及反事实证据连接到同一Run/Session/Step。目标是分开表示：动作被提出还是执行；内容可追踪还是具有授权；来源可达还是确认影响；当前风险还是撤销后残留。[S1]

Evidence是下游防御消费者，不是框架本身。Content检查来源控制要求，Derived检查派生候选/决策依据。这里是CT版本的概述；旧T/P/M或R10结构域不能直接当作CT v3内部模块。

新版论文先写HIAA/ALR/RIR等机制量化，再写P0测量不一致，后面才是防御应用。外部防御排行榜、持续优化ASR、Oracle最优性不再是必做主张。

## 2. 已有阶段与本轮关系

|阶段|已有内容|P3怎么使用|
|---|---|---|
|T11/T11.1|指标合同、类型边界、正负例|核对定义，不把测试通过数当机制风险数|
|T12—T14|确定性Golden与Replay|构念附表，不声称真实模型样本|
|T17-F|Luna正式360核心/270 Replay终态|主要机制主表|
|T17-G|DS V4 Flash正式360核心/270 Replay终态|独立模型/服务配置分层|
|T17-H|新增270核心/270 Replay；复用F形成630/540比较|机制干预表，不能再加F一遍|
|T18|Scripted264、Fake/Reference44|独立分域构念/接口附表|
|旧T19-R R4|核心1824与审计1152的历史计划；许多审计未完成|只查必要指标缺口，不恢复|
|P0|三模型×五方法×39阶段=585条选定观测|辅助任务/效果分析已结项，不重新标注|
|P1|历史运行条件统一|额度不足，延期|
|P2|Luna All已有39条选定结果；历史对照有限制|只作应用背景，不重跑|
|P3（本轮）|尚未执行|零API恢复/复算机制量化|

T17、CT及旧T19的同名指标不自动共享分母。T17各模型的360条来自24条件×5表述簇×3采样，不是360个独立任务模板。P0的585条也不是585道独立题。[S1,S2]

## 3. 仓库与本地路径

- 仓库：`Suuuu123su/Agent-SkillFlow`。
- 参考提交：`06e78a602caf074c0e2593f9dd057c13ea4de7cc`，本包生成时只读取得。
- 本地：`E:/Skill ＆ Harness/Agent`；外部交付包可能在父目录。
- 不应再查`Suuuu123su/skillflow`来替代正确仓库；老交接中“仓库未找到/尚未上传”是历史状态。
- 第一步读相关AGENTS、当前HEAD与git status，不强制拉取覆盖。若数据在旧提交，优先git show/独立只读导出或隔离worktree，不切换正在工作的脏工作区。

## 4. 精确入口，按优先顺序

### 主实验与离线重算

```text
datasets/t17-v2/README.md
datasets/t17-v2/stages/f/
datasets/t17-v2/stages/g/
datasets/t17-v2/stages/h/
datasets/t17-v2/model-pair-contract.json
datasets/t17-v2/reports/
scripts/t17_delivery/t17_collection.py

docs/summaries/T17_Complete_Summary_V2.md
docs/summaries/T17F_V2_Summary.md
docs/summaries/T17G_V2_Summary.md
docs/summaries/T17H_V2_Summary.md
```

上游数据README提供以下历史离线命令。先静态检查入口与依赖，输出用不存在的新目录，不原样覆盖历史示例目录：

```powershell
Set-Location 'E:\Skill ＆ Harness\Agent'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
# 仅在确认入口是纯报告/计算后使用；不是调用runner的授权
.\.venv-skillflow\Scripts\python.exe scripts/t17_delivery/t17_collection.py `
  --from-collection datasets/t17-v2 `
  --output 'runs/p3-t17-offline-new'
```

如该入口会处理E/G预检，可保留独立输出但不纳入正式主表。已有离线report函数可以用于复现原算法；独立核对器另写，不能只用同一函数算两遍。

### 定义与局部验证

```text
docs/summaries/T11_Summary.md
docs/summaries/T11.1_Summary.md
src/skillflow/analysis/hiaa.py
src/skillflow/analysis/authorization_laundering.py
src/skillflow/analysis/residual_influence.py
src/skillflow/analysis/effect_selection.py
src/skillflow/models/advanced_metrics.py
src/skillflow/models/residual_metrics.py
src/skillflow/models/matrix_design.py
schemas/experiment-matrix.schema.json
schemas/risk-report.schema.json
```

文件名为已知定位线索；实际冻结版本若使用不同位置，通过其manifest解析并记录，不造函数名或路径。

### 辅助与应用

```text
datasets/t18-local/
docs/summaries/T18_Summary.md
论文材料/P0/
论文材料/P2/
benchmarks/clawtrojan/results/three-models-20260915/
benchmarks/clawtrojan/frozen/src/evidence_v3/semantic_review.py
```

旧T19-R只从其manifest和报告追踪需要的四格/反事实字段。缺失1140个审计任务不是待你续跑的队列。

## 5. 历史报告参考值：只用于最后核对

这些是[S1]和前轮GitHub报告转录，不是本包已经做完Raw→Metric。不要把它们作为分析函数输入或预期必胜门槛。代码与证据不符时报告差异，不倒推事件。

|指标|T17-F Luna|T17-G DS V4 Flash|
|---|---:|---:|
|Context HIAA_run（主口径）|1|3/5|
|Tool Return HIAA_run（主口径）|1|7/15|
|两类HIAA_pot|0、0|0、0|
|ALR|14/24|6/15|
|RIR(1)、RIR(3)|各0/13|各条件分母为空，N/A|
|UEA操作数 / 受影响Run|90 / 90|52 / 52|
|Provenance TP/FP/FN|3224/0/178|1556/0/2|
|Provenance F1|6448/6626|3112/3114|
|有效Replay平均有符号CI|107/237|22/122|
|TaskSuccess / SafeTaskSuccess|169/360、111/360|125/360、93/360|

T17-H监测/强制：UEA90→0、C1 HIAA1→0而C2仍1、ALR14/24→0/22；正常义务完成156/315→119/315。不要把不同条件分母下ALR差写成固定同一群请求的纯因果效应。

T17-G已报告171/360含格式失败，valid-only C1没有完整四格、C2仅一个完整簇；原scheduled与valid-only的研究问题不同。

## 6. Evidence当前输入的已核对事实

[S3]的`project_context`返回binding、task、content/current、observations、tools、object_kind、cross_session；`validate_route`依据intent、source_instruction_present及来源绑定选择Content/Derived，并调用效果边界的最低检查逻辑。该入口没有显示读取HIAA、ALR或RIR数值的字段。

这说明：**当前CT v3是消费局部证据的动态原型，而非已证明“聚合机制指标驱动”的策略。**不是说它完全没用SkillFlow。当前本地工作区如有新增实现，应按真实入口另列，不能用这个静态快照覆盖事实。

历史`semantic_review.py`构造体有`model='glm-5'`，实际Luna/DS传输可能在提供方层转换；P3只静态读取，绝不能实例化这个类“试一下”。不要把旧构造字段当作当年实际请求模型的完整证明。
