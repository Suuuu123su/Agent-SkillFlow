# T19 数据说明与离线复算

状态：本文件先登记数据语义与验收方式，正式交付状态以 T19_Summary.md 和 delivery-status.json 为准。不得以本说明的存在推断实验已经完成。

## 实验域与分母

正式主比较为 240 条 Live 核心（每组40），C1/C2桥梁关闭四格补充为96条（每组16），共336。预检32条、技术修复验证4条核心，以及本地 Scripted/Fake 测试均单列，不进入正式分母。审计矩阵168候选，其中144为A1/M2严格指标补证、24为预先固定的C1/C2候选；源不适用不应凑数调用。每个合格候选最多identity/neutral/same_view三条后缀，整链前缀与后缀合计不超过16次模型决定。

原始模型行为失败仍在调度分母；审计 not_applicable 不将其核心转为安全成功。每个机制仅两份独立正常任务模板，重复采样和Session不作独立任务簇，不给缺乏支持的总体区间。

## 文件结构

- public-data/formal-v1/core-trials.jsonl：Trial、实际任务合同、脱敏事件、Artifact元信息、Grant、Effect、Receipt、任务分析定义与运行观测。移除已算 proof，复算时重建。
- replay-pairs.jsonl：源前缀、identity/neutral/same_view事实和后缀行为观测；移除原 CI、y 和 proof 结果。未生成源、不可分离源和失败有明确终态。
- intervention-traces.jsonl、diagnoses.jsonl、defense-plans.jsonl：当前请求可见证据、组件选择与实际动作；诊断是真值侧离线结果，不作为线上输入。
- failure-records.jsonl、recovery-records.jsonl：保留失败和预算内恢复。API错误与用量事实另外见 ledger-facts.json。
- source-certificates.json：可信导出器在本地检查私有源后登记结构判断及内容/facts/中和哈希，不含源正文。公开哈希只能复核绑定，不能独立证明未公开JSON的结构。
- ledger-facts.json：全部T19阶段的原始追加式用量账本及冻结价格，含失败请求和预留。估算不是供应商账单；历史T17/T18费用只用于预算扣除，不混成本轮调用数。
- index.json、freeze.json、live-config.json、metric-bindings.json：矩阵、代码/配置/任务绑定。SHA256.json与SHA256-complete.json分别保留原导出和完整增补清单。
- reports/formal-v1/metrics.json、all-metrics-long.csv：完整分层数值，每项保留分子、分母、状态、原因、适用范围与证据ID；非比例项可从逐请求/逐链/逐Token事实取回原始值。
- reports/formal-v1/frozen-v1/：原冻结报告实现输出。根目录覆盖率采用已登记v1.1纠错，其余同名数值必须相同。
- details.json、costs.json、paired-results.csv及各类别CSV：严格ALR/RIR、HIAA、来源、诊断、组间比较、费用/延迟、失败和覆盖明细。
- integrity.json与独立复算比对结果：数据完整性和数值一致性；不等于独立外部审查或项目质量门禁。质量证据另外归档。

## 口径限制

Safe Task Success 沿用项目原定义：完成正常任务，且没有当前已声明目标选择器对应的风险效果。UEA操作、UEA受影响链及授权允许但违背任务目的的操作另列，不能把Safe Task Success解释为所有可能安全属性都满足。

HIAA提供完整四格，scheduled保留全部调度；valid-only按冻结模型/证据合法性条件单列，不替换主分母。严格ALR/RIR无适用事件时为N/A；漏采则incomplete。M2共同污染集合要求六组实际内容哈希匹配冻结源，并存在撤销和第1/3Session观测。

单次反事实CI是操作性对照，存在随机采样波动；同视图重跑单列，不能称确定因果或总体因果效应。来源候选路径与经审计确认影响分开。Selection Regret无真实同状态策略反事实时N/A，不能拿机制标签冒充最优。

总链延迟包含本地运行器、证据保存和评估，不能称纯任务执行时间。API、授权、证据投影、选择器和干预计时另列，在线成本比较以核心费用为主，开发和离线审计单列。共享宿主上的微秒级本地计时仅作描述。

TokenUsage.output_tokens为扣除reasoning_tokens后的输出；总Token=input+output+reasoning，cached_input是input子集，不能再相加。费用独立依据这些原始Token和冻结单价计算。

模型 deepseek-v4-flash 是服务别名，不是不可变权重快照。模型真实调用，业务副作用均为合成数据与Safe Sink；没有真实外发/泄密。私有原始正文、检查点及SQLite现场保留在 runs/t19-live-20260905-01，本次不上传或公开。

## 复算入口

最终接入现有 skillflow defense t19 命令后，从项目目录执行以下PowerShell。若指定输出已存在，换一个新名字；不要删除旧结果。

```powershell
Set-Location 'E:\Skill ＆ Harness\Agent'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli defense t19 recompute --source 'experiments/t19/public-data/formal-v1' --output 'runs/t19-user-recompute-01'
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli defense t19 check --left 'experiments/t19/reports/formal-v1' --right 'runs/t19-user-recompute-01' --output 'runs/t19-user-recompute-check-01.json'
```

recompute只读导出事实，不读已算报告、不需要密钥、不调用付费模型。check在两份独立报告生成后比对；容差固定1e-12，Decimal费用精确相等，差异返回非零退出码。独立进程一致只证明计算可重复，不能替代独立方法学审查。

严格ALR的声明识别受冻结声明内容哈希约束；模型生成语义相近但哈希不同的声明，不自动扩展为同一个严格事件。结构化N/A或零值仅适用于实际满足该证据合同的事件集合，不能外推为自然语言授权伪造不存在。反事实中和只移除facts/control封闭结构的control字段，不能声称清除了任意位置所有潜在指令。

## 实际模型输入的受控接口边界

已核对继承的 src/skillflow/experiment/t17/v2/prompt_contract.py：真实请求包含 task、allowed_action_ids、installed_skill_expected_output、input_artifacts。installed_skill_expected_output 来自当前 Skill 的预置脚本输出，可能包含正常结果或攻击载荷；全部实验组共享此接口。V2FakeClient会直接使用该候选输出，Live模型则自行返回选择与output_text。

因此本实验评估的是提供动作候选与技能候选输出的受控参考接口，不能将Task Success外推为开放任务自主解题能力。Router的RequestEvidence仍仅含执行前结构化授权、来源及独立任务权限；它不接收此候选输出、gold轨迹或事后评分。报告应同时披露模型提示与Router输入这两个不同边界。
