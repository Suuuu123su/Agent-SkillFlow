# 表1　ClawTrojan：DeepSeek Pro 汇总

|模型|方法|攻击 C/P/S|ATS / ASR ↓ (%)|攻击 Safe ↑ (%)|正常 Utility ↑ (%)|技术未知|
|---|---|---|---|---|---|---|
|DeepSeek Pro|No Defense|22/0/4|84.62|15.38|100.00|0|
|DeepSeek Pro|Content|12/1/13|46.15|50.00|100.00|0|
|DeepSeek Pro|Derived|9/3/14|34.62|53.85|100.00|0|
|DeepSeek Pro|TaskShield|19/1/6|73.08|23.08|84.62|0|
|DeepSeek Pro|Evidence|8/0/18|30.77|69.23|92.31|0|

每组为相同39个原生步骤：26个攻击步骤、13个正常步骤；单次观测，无均值/标准差及显著性声明。攻击 C/P/S 分别表示 Compromised/Partial/Safe。ATS 在本表按攻击成功率定义，与原生 ASR 同口径（C/26）；Partial 单列。正常 Utility=正常 Safe/13。

DS Evidence 使用12条 v3 更新结果与27条原版 Safe 结果合并，按固定原生 ID 替换而非逐题选最好结果；不采用未完成的 v3 剩余27条补跑，也不采用 v4—v12 候选。它不是统一版本重跑或未见测试集评估，原版 Evidence 完整结果另列附表。GLM-5 Evidence 使用既有 dynamic2 完整结果。跨模型的 Evidence 版本、运行时间及 Judge 均不同，表格是历史结果汇总，不能推断纯模型因果差异。

DS 请求型号 deepseek-v4-pro，Actor 8192 tokens/20轮；GLM-5 无防御 Actor 4096，其余16384，最多10轮。Judge 额度8192；模型型防御额度8192。返回服务的不可变快照未经证明。TaskShield 为既有 SkillFlow TaskAlignmentGate 合同适配，不声称论文 TaskShield 原生等价；不是 Evidence 第三个组件。

原生判词不等同实际攻击效果或合法任务完成，max_tokens/max_turns 原样保留。模型评分有效不意味着任务完整完成。所有效果限于原生隔离模拟环境。所有指标保留原生判分，不重新评分、不重跑、不删除历史数据；本次新增 API 请求为0。

原版 Evidence 参考（不计入主表行）：

|模型|方法|攻击 C/P/S|ATS / ASR ↓ (%)|攻击 Safe ↑ (%)|正常 Utility ↑ (%)|技术未知|
|---|---|---|---|---|---|---|
|DeepSeek Pro|Evidence (original)|11/0/15|42.31|57.69|92.31|0|
