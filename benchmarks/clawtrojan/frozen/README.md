# Evidence v3 · 冻结结果快照

此目录保存选定的 Evidence v3 方法源码及 ClawTrojan DS / GLM 历史结果。最新指本次冻结快照，不表示最新版方法已统一重跑39条。

DS Evidence 合并结果：攻击8 Compromised / 0 Partial / 18 Safe，ASR 30.77%；正常12 Safe / 1 Partial，Utility 92.31%。其ASR在本次汇总中低于Content（46.15%）和Derived（34.62%），但正常Utility低于两者（100%）。不能据此声称所有指标均优于单组件或统计显著。

## 组成与复核

12条来自v3已见失败案例更新，27条来自原版历史Safe；逐题来源见 results/DS_CASE_PROVENANCE.json。两份原样方法源码均冻结于src，避免把混合来源归为单一版本。GLM-5沿用既有dynamic2完整结果；各组模型、Judge、额度和运行时间差异见带说明表格。

results/PAPER_TABLES_CLEAN.html 为仅表格展示版；results/PAPER_TABLES.html 保留研究说明。展示版与说明版数值相同。

不修改任务、载荷或原生评分。Safe不等于合法任务全部完成；原生Compromised不等于真实外发。本次未发起API实验。没有加入私有凭据、provider日志、个人资料或原始模型推理。

此为源码和结果冻结包，不能声称仅凭此包可以独立重跑完整原生harness。原生上游版本与本地适配依赖需另行安装；缺失材料不得静默替换。

使用 `python -B verify_snapshot.py` 核对文件SHA256与结果计数。不要直接编辑冻结目录；修订应创建新的带版本快照。
