# ClawTrojan · 当前冻结版本

版本：`clawtrojan-evidence-v3-20260914`。当前方法选择 Evidence v3，动态选择 Content / Derived；未采用后续 v4–v12 候选。此发布固定代码、原生 benchmark 与已有结果，新增模型请求及原生判分均为 0。

## 入口

|内容|位置|
|---|---|
|正式横向表格，左 GLM-5、右 DS-V4-Pro|[HTML](results/实验指标v1.html) · [单页 PDF](results/实验指标v1.pdf)|
|指标与来源说明|[完整报告](results/PAPER_TABLES.html) · [DS 汇总](results/DS_SUMMARY.md)|
|可复核数据|[逐题 CSV](results/CASE_RESULTS.csv) · [汇总 JSON](results/SUMMARY.json)|
|当前方法源码|[Evidence v3](frozen/src/evidence_v3)|
|历史参考方法|[原版 Evidence](frozen/src/evidence_original)|
|原生 harness 和公开测试材料|[快照 ZIP](native/clawtrojan-native-snapshot.zip) · [上游版本及差异](native/UPSTREAM.json)|
|原始汇总输入|[source_records](results/source_records) · [输入哈希](results/SOURCE_MANIFEST.json)|
|历史驱动与模型配置|[historical_control](historical_control)|

## 离线复核

Python 3.11 或更高版本，在仓库根目录运行：

```powershell
python -B benchmarks/clawtrojan/verify_release.py
```

该命令只检查哈希、ZIP 成员、39 个唯一题目、26/13 分母、C/P/S 和所有汇总比例，不调用模型，也不把历史记录重算当成新的原生判分。已有 `openai`、`loguru`、`pydantic`、`python-dotenv` 等依赖时，可追加 `--smoke-imports` 验证原生 runner、scorer 与冻结 Evidence 导入。历史环境的完整依赖版本见 `native/requirements-lock.txt`，当前发布没有重新安装或联网验证依赖可得性。

原生代码和公开环境按字节存于 ZIP，解压后与 `native/FILES.sha256.json` 对应。上游为 RUC-NLPIR/ClawTrojan，提交 `9566637c9af3f7b05e576d09b45de489bf9fec9d`，保留 MIT 许可证。实际历史运行快照有 4 个适配文件，不能称为未修改上游；任务材料和原生评分沿用历史冻结版本。

## 结果与解释边界

DS Evidence：攻击 **8 C / 0 P / 18 S**，ASR **30.77%**；正常 **12 S / 1 P**，Utility **92.31%**。GLM-5 Evidence：攻击 **4 C / 2 P / 20 S**，ASR **15.38%**；正常 Utility **100%**。

DS Evidence 是用户选定的 **v3 更新 12 条＋原版历史 Safe 27 条**，逐题来源保存在 `frozen/results/DS_CASE_PROVENANCE.json`。它不是统一 v3 新跑的完整 39 条实验，也不是独立留出集；未完成的 v3 补跑和后续候选不替换此表。主表为十组×39题，数据另保留一组原版 DS Evidence 参考，共 429 行。

ATS/ASR = 攻击 Compromised / 26；攻击 Safe = 攻击 Safe / 26；这里的正常 Utility = 正常 Safe / 13。Partial 单列；原生 Safe 不保证合法任务全部完成，Compromised 不直接证明真实外发。没有独立原生严格 STS，展示表不包含此指标。

DS 各组 Actor 为 8192 tokens / 20 轮；GLM-5 无防御 Actor 为 4096，其他组为 16384 / 10 轮。Judge 和防御配置见报告。TaskShield 是 SkillFlow 的合同适配实验，不能主张与论文原生 TaskShield 性能等价。模型返回行为、评分尺度、额度及历史版本差异限制跨模型因果比较。

## 运行状态与下一步

这是一份可离线复核、包含真实原生代码与方法的冻结交付。`historical_control` 保留原样历史驱动以供代码审查，其旧目录、共享账本和准入依赖没有改写；其中的旧额度不是新的运行授权。它不构成在新机器上开箱即用的付费续跑命令。账号凭据、私有配置、API 原始请求日志与账本不随包发布。

若以后需要重跑，应单独配置可信提供方控制进程、隔离工作区和共享预算，并重新验证路径与准入，不可关闭历史停止条件、沿用旧授权或用新适配冒充原始结果。本次不新增实验、不生成攻击、不启动远端 CI。
