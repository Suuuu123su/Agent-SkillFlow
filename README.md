# P2 Luna All 最终结果

仅新增All-SameLibrary，39/39有效原生判分。攻击C/P/S为17/5/4，正常为1/2/10；辅助U/V均可判定34/39，人工复核0。63次正式物理尝试和全部技术修订分开保留，历史Evidence只作HISTORY_ONLY参考，不称受控排名。

[最终报告](论文材料/P2/luna-all/P2_FINAL_REPORT.md) · [逐阶段结果](论文材料/P2/luna-all/analysis/outputs/RESULTS39.csv) · [版本限制及复算](论文材料/P2/luna-all/CURRENT_STATUS.md)。本Luna修订替代GLM默认；P0结项、P1延期，不自动开始其他阶段。以下为历史发布。

# Agent-SkillFlow

## 最新：P0收尾与论文材料

**[论文材料](论文材料/README.md)** 已整理P0结项、三模型五方法历史指标、辅助U/V/E_STS、可用措辞与来源哈希。P0数据处理结项，原状态PROCESSED_WITH_GAPS及人审0保留；不是新金标准或受控排名。本次仅从保存标签重排汇总，没有新增模型或业务工具重放。**P1因资源暂停，下一步P2为同组件库All-SameLibrary；当前P2实际进度与隔离修订见本页顶部入口。** [P0结项](论文材料/P0/CLOSEOUT.md) · [P2任务](论文材料/NEXT_CODEX_TASK.md)。

最新结果发布：**[ClawTrojan 三模型攻击实验汇总（2026-09-15）](benchmarks/clawtrojan/results/three-models-20260915/README.md)**。

包含 GLM-5、DS-V4-Pro、GPT-5.6-Luna 的五种方法，共390条攻击观测。已逐题复核全部计数，技术未知为0；本次新增实验请求为0。[正式 PDF](benchmarks/clawtrojan/results/three-models-20260915/PAPER_TABLES_GLM_DS_LUNA.pdf) · [逐题 CSV](benchmarks/clawtrojan/results/three-models-20260915/ATTACK_CASE_RESULTS.csv) · [校验记录](benchmarks/clawtrojan/results/three-models-20260915/VALIDATION.json)。

Luna TaskShield 使用排除个人全局指令后的最新39条重跑。DS Evidence 为历史混合版本；其他 Luna 方法部分 CLI 结果可能受个人指令影响，且各模型配置不同，不能作为受控排名。来源与剩余问题见汇总说明。本次仅发布既有结果，不改算法，不追加实验或远端 CI；旧文件保留。

冻结 benchmark 代码版本：**ClawTrojan / Evidence v3 冻结交付（2026-09-14）**。

## 当前入口

- [ClawTrojan 说明、原生 harness、冻结源码与复核方法](benchmarks/clawtrojan/README.md)
- [GLM-5 / DS-V4-Pro 正式表格](benchmarks/clawtrojan/results/实验指标v1.html) · [单页 PDF](benchmarks/clawtrojan/results/实验指标v1.pdf)
- [完整来源报告](benchmarks/clawtrojan/results/PAPER_TABLES.html) · [逐题结果 CSV](benchmarks/clawtrojan/results/CASE_RESULTS.csv)
- [版本清单](benchmarks/clawtrojan/RELEASE.json) · [GitHub 旧版本清理明细](docs/releases/clawtrojan-20260914-cleanup.json)

## 已有结果

|模型|Evidence 攻击 C/P/S|ATS/ASR ↓|正常 Utility ↑|
|---|---:|---:|---:|
|GLM-5|4 / 2 / 20|15.38%|100.00%|
|DS-V4-Pro|8 / 0 / 18|30.77%|92.31%|
|GPT-5.6-Luna|12 / 9 / 5|46.15%|46.15%|

每组26条攻击、13条正常。DS Evidence 使用选定的 v3 更新12条与原版历史 Safe 27条合并，完整来源随包保存；不称为统一 v3 新跑39条。不同模型和方法存在历史输出额度差异；TaskShield 为合同适配实验。Luna Evidence 攻击为 API 记录，正常任务含历史 CLI 上下文影响；最新隔离 TaskShield 攻击 C/P/S 为19/2/5，ASR73.08%，正常 Utility84.62%。结论边界、其他四组结果和指标定义见三模型汇总报告。

## 实际验证与未完成项

本次只发布已有实验与冻结代码，新增 API 请求和原生判分均为0。提供离线 SHA256、原生快照与逐题指标复核入口，以及原生 runner / scorer / Evidence 导入检查；受清理影响的11项本地兼容测试通过。详细检查结果见 [VALIDATION.json](benchmarks/clawtrojan/VALIDATION.json)。未运行全量测试或远端 CI，未声称模型重跑成功。

```powershell
python -B benchmarks/clawtrojan/verify_release.py
```

历史控制器仍保留原路径与准入约束，重新付费运行需要独立配置并验证可信提供方、隔离环境及共享配额；本发布不自动继续实验。原生代码和公开材料收录在带许可证的快照 ZIP 中，完整的干净机器付费运行安装流程尚未验证。

## 仓库保留与清理

公共 SkillFlow 源码、测试以及 T16–T18 内容保留。旧 T19 运行报告与归档从 GitHub 当前工作树移除；仅保留3个被公共源码/测试引用的兼容配置。本地所有实验、缓存、R14及未提交修改均未清理。远端父版本尚无 R14，因此此次没有把其他对话正在修改的本地 R14 强行纳入发布。历史提交未改写，旧版本仍可通过 Git 历史追溯。

后续工作以新的明确任务为准，不恢复旧优化搜索或防御实验。
