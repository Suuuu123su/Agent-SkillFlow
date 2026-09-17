# 论文材料

本目录整理目前可用于写作的指标、限定性结论及下一步任务。更新时间：2026-09-15。

**P0数据整理与辅助测量分析已收尾；原状态仍为PROCESSED_WITH_GAPS，独立人工复核0。** 收尾不等于所有语义标签成为金标准。P1因API资源限制暂停；下一步为P2：同组件库All-SameLibrary对照，不是DASGuard或新的自建任务。

## 阅读入口

- [P0结项与解释修订](P0/CLOSEOUT.md)
- [可以写入论文的指标和措辞](PAPER_METRICS.md)
- [全部五方法、三模型、30个分层](P0/ALL_METHODS.md)
- [历史原生结果CSV](tables/native_history15.csv) · [P0端点CSV](tables/p0_endpoints.csv) · [30层CSV](tables/p0_30_strata.csv)
- [来源与哈希](metadata/sources.json) · [状态](metadata/status.json)
- [本地Codex下一任务与P2设计](NEXT_CODEX_TASK.md)
- [原有三模型报告](../benchmarks/clawtrojan/results/three-models-20260915/README.md)

## 使用规则

原生C/P/S、原始任务、已保存轨迹和方法版本不改。历史原生分数用于描述已执行配置；P0标签用于事后辅助的构念区分，必须保留unknown与未人审说明。它们不支持统一版本的三模型排名、Judge错误率、动态选择因果收益或真实外泄率。

本次发布只包含汇总、公开阶段/案例标识和来源哈希，不包含API Key、provider原日志、个人指令或模型私有推理。原始P0大包本地保留；本发布没有重新调用模型、裁判或业务工具。


<!-- P3_P4_PUBLICATION_20260917 -->
## P3/P3R机制测量与P4测量证据消融已发布（2026-09-17）

[论文三表](P4_测量证据消融/closeout-20260917-141455/PAPER_TABLES.md)、[P3/P4章节草稿](P4_测量证据消融/closeout-20260917-141455/PAPER_P3_P4_SECTION.md)、[六案例](P4_测量证据消融/closeout-20260917-141455/PAPER_CASES.md)与[结项报告](P4_测量证据消融/closeout-20260917-141455/P4_CLOSEOUT.md)已整理完成。P4管理状态CLOSED_WITH_DOCUMENTED_GAPS；原P4状态、分母、未知和限制保持不变。

Full独立参照覆盖190/192、已答一致190/190，人审0；来源删证损失8166=7472自身+694下游。F/H valid_only每格13对15的版本冲突、旧CI语义、ALR空分母和RIR因果限制均保留。机制测量放在论文前部，防御为应用展示，不据此主张框架唯一必要性。

本次发布四份完整审查包及展开材料；仅做归档/路径/哈希定向检查，未重算预测，新增模型和业务调用0。未运行全量或远端CI。原工作区T19-R修改未纳入，P1继续延期，P5/P6不启动。

[发布清单、完整包与复现边界](发布记录/p3-p4-20260917/README.md)。
