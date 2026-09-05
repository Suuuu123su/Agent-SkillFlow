# T19 离线报告补充 v1.1

此文件在 formal-v1 已开始执行后登记，属于离线验收与统计实现补充。正式执行仍由 runs/t19-phases/formal-v1/freeze.json 与 code-and-contracts.zip 绑定，不把本补充冒称首次正式预注册。没有新增模型请求、任务、重放候选或改变评分目标。

## 必需观测覆盖率纠错

冻结的 core_metrics.py 将所有 ScenarioStep 放入分母，却只用模型决定、模型失败、输入超限和来源边界记录作分子。因此 M2 的真实撤销、A2 的真实结构化确认被错误漏计。v1.1 的 observations.py 分别核对模型步骤和控制器步骤；控制器证据必须匹配事件种类、Session、可信主体、目标 Skill 或完整 Grant。没有事件依然是未观测，不能由任务成功或低风险补齐。分母不变，其他研究指标不变。

原版完整结果保存在复算目录 frozen-v1/；最终根目录 metrics.json 只替换明示在 details.json/metric_corrections 的覆盖率键。其它同名指标有差异即拒绝交付。单元测试包括真实 M2/A2 控制事件、移除事件后的缺失，以及自动卸载不能冒充可信用户步骤。验证记录 delivery-v3.xml、delivery-v4.xml。

## 离线完整性与分层交付

新增 source_certificates.py、integrity.py、detail_views.py、delivery.py、cli.py，仅在可信宿主之外读已完成事实。逐条核对 336 核心、168 预定审计终态、响应账本、原授权事实、回执、来源先后、整链16步及重放源前缀。

源结构证书由可信导出器读取本地检查点后记录 facts/control 结构是否有效、原文/中和文/facts 哈希及字节长度，不导出正文。公开数据能够检查绑定和前缀，JSON 结构有效性仍依赖可信导出器的观察，不能宣称仅凭哈希公开证明正文结构。

ALR/RIR/HIAA 沿用原项目严格公式。增加所有冻结分层、共同 Memory 污染集合、恢复费用、审计费用和失败类型明细；没有新增安全权重、阈值或事后样本过滤。共同污染集合必须六组实际内容哈希与冻结源匹配；未齐全是 incomplete，齐全而无共同合格集合才是 not_applicable。

## 验收范围与方法

两个独立进程从同一脱敏事实重建 proof、CI、任务指标及 Token 费用；生成时不读第一份报告。最后才比较，浮点绝对/相对容差均为首次冻结的 1e-12，Decimal 费用及分层模型精确相等。原 journal 的费用字段仅用作断言，重算费用来自 Token 与冻结单价。保留全部历史诊断调用与在途预留，不能以低费用代替费用闭合。

本补充源码在最终交付时另存完整哈希与代码归档，与正式执行快照明确区分。独立外部审查目前 REVIEW_UNAVAILABLE。

## 追加的开销与失败分母视图

operational_views.py从响应账本直接计算实际API延迟，按原冻结分层输出refusal/no-call/schema的实际模型决定分母；核心恢复决定包含在内。未隔离的纯任务执行时间明确not_available，不能用总链延迟减API近似后声称实测。它不改变任务、安全或因果评分。operational-v1.xml中3项定向测试通过（含既有费用/共同污染视图）。

完整无网络验证位于runs/t19-validation/offline-matrix-v1，336核心/168审计、0真实API，原18045项分层结果无incomplete，完整性通过。该进程启动时尚未加载最后追加的operational_views；最终正式数据复算将加载登记的完整v1.1源码。

## 恢复费用分类纠错

实际账本确认：重放分支会复用call_id，但完整CallIdentity中的run_id与运行单元不同。原新增明细仅按call_id累计，可能将分支首次请求误分类为恢复。v1.1改为(unit_id, call_id)组合计数；总Token、调用数、逐调用费用与核心评分均不变，仅恢复/首次调用类别重新归属。该纠错未修改正式执行或任何原始账本。

recovery-classification-v1.xml保留最初测试夹具错误：它错误地让跨分支完整CallIdentity也相同，因此被既有防重采规则拒绝。修正为真实分支具有不同run_id后，recovery-classification-v2.xml中3项测试通过；Ruff与类型检查通过。不会把失败测试删除或冒充一次通过。


## 最终质量定向修复与交付闭合（2026-09-05）

唯一全量1506项为1505通过1失败，原覆盖率89.93152692297446%。只修复可信host.py的getpass精确安全测试入口、增加禁止其他能力与执行层导入宿主的反向测试，并修复host拒绝未验证输出目录后错误写失败文件的路径。正式有效job语义不变，修改发生在正式结束后。已有用户protocol.py仅末尾换行、AST不变，原件另存；test_t19_live.py仅格式修复。定向18项首次有3个新夹具缺attempt_id失败，修正后仅重跑3项通过。最终综合覆盖率90.09004209068144%，未降阈值；无已知未解决失败。保留全部原始结果，未再次全量。详见quality/resolution.json。
