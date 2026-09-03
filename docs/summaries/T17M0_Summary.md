# T17-M0：最小技术验收离线审计

- 日期：2026-09-03。
- 状态：`COMPLETED`（仅离线审计与修订决策）；审计先发现 `TASK_RISK_CONTRACT_CONFLICT` 并暂停，随后取得用户明确批准。此处不是指标实现或实验完成结论。
- 当前 main：`d5506e25e927c2eb4225ee54eab4c01069d408c0`；[本次 README 推送 CI 已通过](https://github.com/Suuuu123su/Agent-SkillFlow/actions/runs/33729711994)。
- 已读取：progress、T17 原计划、SkillFlow-Rx 设想、安全语义、评估协议、最新 T16-C/v3.1/T16-E 总结，以及当前 Matrix/场景注册、Reference Harness、TaskSuccessEvidence、Replay/报告入口。

## 已确认事实

1. 原有 Reference Harness 和 24 core + 18 Replay 的 Scripted/Fake 完整路径已有实现与测试；不需要从头重建平台或扩大样本。
2. T17-A 登记的 53 个 canonical 旧证据重新计算哈希及长度，53/53 一致。该结论只覆盖登记清单，不扩大为未扫描文件的全局保证。
3. C1/N0 共享同一正常任务，但成功断言对同一风险 Effect 要求相反；T17 v1 的任务测量沿用了这种耦合。旧 TSR/Safe TSR 保持原合同下的历史结果，不能当作新技术验收的正常效用结论。
4. S1_CONTROL 已存在并注册，但未进入旧 24-core Matrix；最小验收应补入该现有控制，不能仅凭注册表宣称控制已跑过。
5. 现有完整 Defense 汇总绑定大矩阵规模；本轮需要独立的最小配对报告，不能伪造 630/540 个单位或直接构造最终指标。

## 最小修复建议

用户已回复“按照你的最小修订来，后续summary的时候写进去”。据此新增版本化正常任务合同，将正常任务断言和风险 Golden 分开；保留合法任务的必需 Receipt 与全部绑定，不降低证据门槛。旧 YAML、Golden、Run、Attempt、JSONL、版本化 Summary 和哈希不回写。

候选规模为每域 23 core + 12 Replay，Scripted 与 Fake Reference 两域分开运行；每条件仅 1 semantic instance × 1 repeat。B0/B1 现有两组模式配对用于最小 Defense，无额外防御样本。完整说明见 [最小设计草案](../plans/T17_minimal_technical_acceptance_20260903.md)。该规模尚未冻结或执行。

## 修改、测试与费用

- 本部分只新增合同审计 JSON、批准记录、最小设计和本 Summary，并同步 README/progress；未修改实验代码或冻结配置。
- 新实验 Run、真实模型请求和新增 API 费用均为 0。GitHub 只读核对不是模型实验调用。
- 本轮没有重新运行本地测试；当前源码基线的 GitHub CI 为 success，不能用它替代未来新代码的质量门。
- 独立审计仍为 `REVIEW_UNAVAILABLE`，以上是执行者只读事实核对，不是独立审查 PASS。
- 结构化证据与各输入 SHA-256：[t17-minimal-contract-audit-20260903.json](../evidence/t17-minimal-contract-audit-20260903.json)。

## 下一阶段

批准已解除本次合同修订阻塞，进入 T17-M1 离线实现。审计 JSON 保留为批准前的不可变快照，批准单独记录在 [修订批准](../evidence/t17-minimal-revision-approval-20260903.json)；后续 Summary 必须记录新旧任务合同的区别，不把旧风险 Golden 重算成正常任务效用。真实 API 仍须另行预算批准。
