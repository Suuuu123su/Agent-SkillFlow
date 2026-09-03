# T17 最小技术验收总结（2026-09-03）

**结论：最小离线测量链已完成；最终技术验收仍 INCOMPLETE。**

阻塞不是实验缺样：Scripted 与 Fake Reference 已各完成 23 core、12 Replay，并从 Raw 复算完整指标。当前纯分支覆盖率为 75.892857%，未达到文字要求的 90%；现有 CI 使用的综合覆盖率为 90.072519%。两种口径不可互换，待用户确认。独立终审为 `REVIEW_UNAVAILABLE`，不是 PASS。

## 最小修订与证据边界

用户批准“按照你的最小修订来，后续 summary 的时候写进去”。本轮新增正常任务 evaluator `2.0.0`，将正常任务成功与攻击风险 Golden 分离；保留真实任务所需的合法 Effect/Receipt、可信 Artifact 内容 hash、正确资源和 Session。S1 错误文件、L1 错误 Session 不算成功。旧 Scenario、旧 evaluator、旧 Golden、Raw、Summary 和分母不重写。

本轮最终总结使用新文件，保护已冻结的 `T17_Summary.md` 及旧审计哈希。历史总结仍可查，不混入当前结果。

## 阶段结论

| 阶段 | 状态 | 结果 |
|---|---|---|
| [M0](T17M0_Summary.md) | completed | 旧证据审计、合同冲突识别、最小修订获准 |
| [M1](T17M1_Summary.md) | completed | 新正常任务合同、可信证据/复算接口、16 新 Schema、CLI、定向拒绝与绑定测试 |
| [M2](T17M2_Summary.md) | completed | 两个独立离线域各 23/23 core、12/12 Replay；151 项域级指标 + 19 项最小防御条目 |
| [M3](T17M3_Summary.md) | incomplete | 1031 测试全通过、静态/安全门通过；纯分支覆盖率未达 90%，独立审查不可用；GitHub 交付另记回执 |

## 已测指标

以下是每域分别得到的结果，绝非 pooled micro rate：

- 正常 TSR 20/23 = 0.869565；Safe TSR 13/23 = 0.565217。
- VTE 15/23；预注册风险 trial rate 9/23；UEA count/type/weight = 8/7/8，affected trial rate 7/23。
- TaskSuccessEvidence 23/23；core Effect/Receipt 和 binding 49/49；必需 Hook 85/85；scope/lifetime observation 54/54。
- Provenance TP/FP/FN = 234/0/6，Precision = 1，Recall = 0.975，F1 = 468/474；逐深度 Decay 原始分子/分母全部列出。
- C1/C2 HIAA scheduled 和 valid-only 均 1，potential 均 0；ALR、RIR(1)、RIR(3) 均 1/2。
- Replay CI negative/zero/positive = 0/5/7，确认影响边 7；每对分支与恢复前缀均复验。
- 最小 B0/B1 防御：风险配对各项安全差值为 1，良性 Utility Loss 0/1、Over-defense 0/1；全部两配对 TSR delta -1/2，Safe TSR delta 0/2。不存在普遍无代价的防御改善结论。
- 每域 core Step 56；Fake Reference core decision calls 56。实际 API、API 费用和预算占用均为 0；本机单次 Harness latency 有实测，不当作 Provider 性能。

Scripted 域 135 measured / 16 not_applicable；Fake Reference 域 138 measured / 13 not_applicable；每域另有防御 14 measured / 5 not_applicable。没有因缺少 Hook 而标成 not_available 的本轮指标，也没有 incomplete 的域级测量项；这不覆盖项目级的覆盖率验收缺口。

无真实 Provider：Token、Provider latency/refusal 等为结构化设计 N/A。单实例不估计 cluster bootstrap、跨簇稳定性或跨模型方向。Wilson 95% 区间明确为链级描述性区间，不是泛化置信区间。

## 完整产物

- [指标合同与分母](../metrics/t17-minimal-metric-registry.md)。
- [Scripted JSON](../evidence/t17-minimal-scripted-metrics-20260903.json) / [CSV](../evidence/t17-minimal-scripted-metrics-20260903.csv)。
- [Fake Reference JSON](../evidence/t17-minimal-fake-reference-metrics-20260903.json) / [CSV](../evidence/t17-minimal-fake-reference-metrics-20260903.csv)。
- [Raw/Phase/配置/报告哈希及记录数](../evidence/T17_MINIMAL_MANIFEST_20260903.md)。
- [最终质量审计](../evidence/t17-minimal-quality-audit-20260903.json)。
- [首次 GitHub CI 失败与测试目录修复审计](../evidence/t17-minimal-ci-portability-audit-20260903.json)：首次 CI 为 1 failed / 14 setup errors；只修复测试输出目录，20 项定向回归通过，生产代码和正式指标未改变。修复后远端 CI 需重新验证。

本地完整 Raw：`runs/t17-minimal-scripted-20260903-01/execution`、`runs/t17-minimal-fake-reference-20260903-01/execution`。每域清单登记 1041 个文件、46 个 JSONL、521 条 JSONL 记录。Raw、开发失败记录和完整覆盖率只留本地；公开产物只含合同、Schema、汇总、审计和哈希。

## 严格区分四种结论

1. **框架技术验证**：完整最小测量链已跑通；项目最终验收因纯分支门未满足仍 incomplete。
2. **最小真实模型观察**：本轮没有新增。历史 T17-E 仍为 16/24 core、12/18 Replay 的 Partial，不续跑、不补采、不回填。
3. **论文级大样本实验**：原 F/G/H 没有运行；本轮 Fake/Scripted 不能替代真实模型、多模型或统计显著性结果。
4. **SkillFlow-Rx**：仍是后续独立研究设想，未实现攻击诊断或自适应防御编排。

下一步只需处理覆盖率口径或补充对应历史分支测试；不自动增加实验或任何费用。独立终审不可用和历史 Live incomplete 均保留原状。
