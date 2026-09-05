# T18 交付清单

当前：T18 实验、指标、指定明细、公开数据、本地验证和远端质量检查均已完成。提交 49e28ba 的 GitHub Actions 运行 33935572308 全部通过，整体状态为完成。

- [修订预注册](../../experiments/t18/preregistration.yaml)、[技能目录](../../experiments/t18/skill-catalog.yaml)、[防御目录](../../experiments/t18/defense-catalog.yaml)。
- [脚本矩阵](../../experiments/t18/matrix-scripted.yaml) 264 个任务；[模拟矩阵](../../experiments/t18/matrix-fake-smoke.yaml) 44 个任务。仅补缺格，不增加重复；正式旧版运行数为 0。
- [规则冻结](../../experiments/t18/router-rule-freeze.json) 早于留出变体构造；正式阶段各自保留输入与运行源文件的独立 SHA-256。
- [完整可复算数据](../../datasets/t18-local/README.md)：356 个文件，共 74,426,015 字节；不含真实模型正文、密钥或私有数据库。根目录九类指定明细含 308 条任务、21 对重放和 258 行既有配对结果；这些结果不是新增实验样本。
- [脚本文件清单](../../datasets/t18-local/scripted/manifest.json)与[模拟文件清单](../../datasets/t18-local/fake_reference/manifest.json)登记全部正式事实和报告的逐文件 SHA-256。清单自身及入口 README 不纳入自引用哈希。
- [全部正式指标独立复算](t18-recompute-check.json)通过：两域原报告与根目录明细合计 16 份文件逐字节一致；[本地质量检查](t18-quality-check.json)保留首次失败与定向修复，不宣称全量重跑通过。
- [远端质量检查](https://github.com/Suuuu123su/Agent-SkillFlow/actions/runs/33935572308)通过：1,354 项测试、90.172280% 综合覆盖率，静态检查、格式、486 个源文件严格类型和命令入口全部通过。
- [论文机制适配](t18-literature-adaptation.json)、[完整中文结果](../summaries/T18_Summary.md)，包括 C2 漏检、任务损失和未获支持的研究假设。

完整本地原始记录仅在 `runs/t18-local-scripted-v1/` 与 `runs/t18-local-fake-v1/`。独立复算输出在 `runs/t18-recomputed-01/`；开发测试与日志在 `.tmp/t18-20260904-01/`。没有重跑或删除正式记录，没有重新计算全部 T17 私有 Raw 哈希。

T17 的已跟踪冻结配置、数据、格式、指标和总结相对起始提交 `e54f7d0` 无差异。用户未提交的 T12 README 段落、T12 说明文档、两个覆盖率文件、`.tmp/`、T17 清单／旧汇总／协议草稿全部保留，不纳入 T18 提交。
