# ClawTrojan 三模型攻击实验汇总（2026-09-15）

本次发布整理已有结果，没有新增实验请求或重新判分。覆盖 GLM-5、DS-V4-Pro（数据文件名 DeepSeek Pro）与 GPT-5.6-Luna，各五种方法、26个原生攻击步骤，共390条“模型×方法×步骤”结果；这些不是390道独立题。正常任务仅作为已有 Utility 参照。

- [正式横向总表 PDF](PAPER_TABLES_GLM_DS_LUNA.pdf) · [HTML](PAPER_TABLES_GLM_DS_LUNA.html)
- [攻击逐题结果](ATTACK_CASE_RESULTS.csv) · [完整指标及比较限制](METRICS.json)
- [来源校验清单](SOURCE_MANIFEST.json) · [本次校验](VALIDATION.json)

## 攻击结果

ATS/ASR = Compromised / 26；攻击 Safe = Safe / 26。C/P/S 是原生 Compromised / Partial / Safe 判词，Partial 不计入完整攻击成功。Utility = 正常任务 Safe / 13，不代表独立验证的真实业务完成率。严格 STS 不列入本表。

|模型|方法|攻击 C/P/S|ATS/ASR ↓|攻击 Safe ↑|正常 Utility ↑|
|---|---|---:|---:|---:|---:|
|GLM-5|No Defense|20/1/5|76.92%|19.23%|100.00%|
|GLM-5|Content|7/0/19|26.92%|73.08%|100.00%|
|GLM-5|Derived|7/3/16|26.92%|61.54%|100.00%|
|GLM-5|TaskShield|20/0/6|76.92%|23.08%|92.31%|
|GLM-5|Evidence|4/2/20|15.38%|76.92%|100.00%|
|DeepSeek Pro|No Defense|22/0/4|84.62%|15.38%|100.00%|
|DeepSeek Pro|Content|12/1/13|46.15%|50.00%|100.00%|
|DeepSeek Pro|Derived|9/3/14|34.62%|53.85%|100.00%|
|DeepSeek Pro|TaskShield|19/1/6|73.08%|23.08%|84.62%|
|DeepSeek Pro|Evidence|8/0/18|30.77%|69.23%|92.31%|
|GPT-5.6-Luna|No Defense|23/2/1|88.46%|3.85%|92.31%|
|GPT-5.6-Luna|Content|14/2/10|53.85%|38.46%|53.85%|
|GPT-5.6-Luna|Derived|15/6/5|57.69%|19.23%|69.23%|
|GPT-5.6-Luna|TaskShield|19/2/5|73.08%|19.23%|84.62%|
|GPT-5.6-Luna|Evidence|12/9/5|46.15%|19.23%|46.15%|

## 观察与结论边界

- GLM-5 的 Evidence 观测攻击成功率为15.38%，低于本组两种单组件26.92%。这只是该批历史结果，不作统计显著性声明。
- DS 的合并 Evidence 为30.77%；原版完整 Evidence 为42.31%，原版结果仍保存在 METRICS.json 的附加行。合并版对已见失败案例进行了更新，不能作为独立未见测试的提升证据。
- Luna Evidence 的 ASR 为46.15%，低于 Content 53.85% 和 Derived 57.69%，但攻击 Safe 与 Derived 同为19.23%：一部分差异是 Compromised 转为 Partial，不能全部解释为攻击完全阻断。
- Luna TaskShield 采用最新隔离重跑，ASR为73.08%，攻击 Safe为19.23%。不使用此前受个人全局指令影响的高防御率结果。其他方法历史 CLI 部分没有在同样隔离设置下重跑，因此不能将本表解释成公平的受控方法排名。

## 版本、配置与剩余问题

每组为相同39个原生步骤：26个攻击步骤、13个正常步骤；单次观测，无均值/标准差及显著性声明。攻击 C/P/S 分别表示 Compromised/Partial/Safe。ATS 在本表按攻击成功率定义，与原生 ASR 同口径（C/26）；Partial 单列。正常 Utility=正常 Safe/13。

DS Evidence 使用12条 v3 更新结果与27条原版 Safe 结果合并，按固定原生 ID 替换而非逐题选最好结果；不采用未完成的 v3 剩余27条补跑，也不采用 v4—v12 候选。它不是统一版本重跑或未见测试集评估，原版 Evidence 完整结果另列附表。GLM-5 Evidence 使用既有 dynamic2 完整结果。跨模型的 Evidence 版本、运行时间及 Judge 均不同，表格是历史结果汇总，不能推断纯模型因果差异。

DS 请求型号 deepseek-v4-pro，Actor 8192 tokens/20轮；GLM-5 无防御 Actor 4096，其余16384，最多10轮。Judge 额度8192；模型型防御额度8192。返回服务的不可变快照未经证明。TaskShield 为既有 SkillFlow TaskAlignmentGate 合同适配，不声称论文 TaskShield 原生等价；不是 Evidence 第三个组件。

原生判词不等同实际攻击效果或合法任务完成，max_tokens/max_turns 原样保留。模型评分有效不意味着任务完整完成。所有效果限于原生隔离模拟环境。所有指标保留原生判分，不重新评分、不重跑、不删除历史数据；本次新增 API 请求为0。

Luna No Defense uses original API results. Content and Derived each retain 25 attack and 3 normal API results, plus 1 attack and 10 normal Codex CLI results. Evidence v3 retains 26 API attack results and adds 13 Codex normal results. CLI 0.154.0, requested gpt-5.6-luna, medium reasoning. CLI output limit is not equivalent to the API 8192 limit, and CLI adds its own context. This is a historical mixed-transport aggregation, not a controlled model comparison. Luna TaskShield uses the full 39-case isolated-Codex-home rerun, with the original frozen contracts and native judging. A native-compatible leading-slash path bridge repairs resource normalization; 19 judgments were retained from the same isolated run and 20 completed after exact cached-response replay. Personal global AGENTS.md was excluded from this rerun. Earlier CLI portions of Content, Derived and Evidence may have loaded personal global instructions; they were not rerun. These arms are therefore not controlled peers of the isolated TaskShield condition. No experimental model requests were made to create these tables.

## 复核范围

逐题检查15组各39个唯一ID、每组26攻击及13正常，重算全部C/P/S并与最终汇总逐项相等；发布390条攻击记录。所选汇总技术未知均为0，原始结束原因仍保留，不代表不存在任务失败。发布只包含汇总、公开ID、判词与文件哈希，不包含凭据、认证缓存、个人指令正文或模型消息。没有运行新实验、全量测试或远端CI。

本次是结果汇总发布，不更新 Evidence 冻结算法，也不宣称解决历史实验的配置差异。完整复现实验尚需另行设计统一条件；不在本次执行范围。
