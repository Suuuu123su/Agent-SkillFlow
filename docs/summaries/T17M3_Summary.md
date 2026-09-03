# T17-M3：最终质量门与交付审计

- 日期：2026-09-03。
- 状态：`COMPLETED`，仅指最小离线技术验收，保留独立审查警告。用户已明确批准改用既有 CI 的综合覆盖率 ≥90% 门；最小测量链、离线质量检查及代码交付验证均完成。
- 独立终审：`REVIEW_UNAVAILABLE`，不冒充 PASS。
- 真实 API 调用和新增实验费用：0。M2 后未增加任何正式实验样本。

## 已执行质量检查

| 检查 | 结果 | 范围 / 证据 |
|---|---|---|
| 全量 pytest | PASS：1031 passed，0 failed/error/skipped | 一次最终全量运行；JUnit 411.751 秒，终端总耗时 411.76 秒 |
| 综合覆盖率 | PASS：23599/26200 = 90.072519% | 覆盖语句与分支机会合计，符合现有 CI 的 90% 配置 |
| 语句覆盖率 | 20369/21944 = 92.822639% | 独立列出，不冒充纯分支覆盖 |
| 纯分支覆盖率 | 单独披露：3230/4256 = 75.892857% | 未覆盖 1026 个分支机会；952 个部分覆盖分支；不满足原纯分支 90%，用户已批准本轮改用综合口径，不将此项改写为 PASS |
| Ruff check | PASS | `src tests`；不扫描用户历史 `.tmp` 快照 |
| Ruff format check | PASS：536 files | 仅排除已有未跟踪的 `src/skillflow/experiment/t17/protocol.py` 草稿；未改写它 |
| strict mypy | PASS：353 source files | 包含本地现有草稿；不代表该草稿纳入交付 |
| 静态 Schema | PASS：72 份 | 新增 16 份 minimal Schema；旧 56 份未变化；全量测试中的漂移与 JSON/JSONL 校验通过 |
| doctor / pip check | PASS | Python 3.12.13、SQLite 3.53.1、运行依赖、项目内临时目录；无依赖冲突 |
| 400 行上限 / no-excuse | PASS | 原 39 个新增/修改 Python 文件最大 294 行；后续 CI 修复新增 14 行测试 fixture，累计 40 个文件；无新增 typing.Any、忽略标记、skip/xfail 或宽泛异常兜底 |
| 禁网与边界测试 | PASS | 两域 23+12 E2E 在 socket 拒绝下完成；Runtime/Policy 等执行边界 AST 检查通过 |
| 公开结果扫描 | PASS（有界扫描） | 4 个新 JSON/CSV；凭据格式、宿主路径、正文键及仓库实际 10 个 fixture marker 均未命中 |
| 旧证据 | PASS（登记范围） | T17-A 登记的 53 份 canonical 文件、旧 T17 审计登记的 4 份公开指标哈希一致 |
| 独立审查 | REVIEW_UNAVAILABLE | 未核实独立审查者模型身份，不把执行者自查写成独立审查 |
| GitHub 代码交付 | PASS：修复后 1032 passed、综合 90.13% | `5392c18` 的 CI 33745413298 成功；Ruff、605 文件格式检查、352 源文件 strict mypy 与 CLI 通过；首轮失败保留，生产代码与正式结果不变 |

初次文本扫描把 Python 内置 `any()` 误匹配为 `Any`；改为大小写精确扫描后为 0 项，没有为消除误报修改源码或删测试。coverage JSON 的空字符串函数名也使首次 PowerShell 普通对象解析失败，改用标准 JSON 文档读取；没有改动原始覆盖率文件。

推送前发现 Git 的自动换行转换会改变两个新 CSV 的字节哈希。已仅对这两个冻结 CSV 增加 `.gitattributes` 字节保护；CSV、Raw、源码和 Schema 均未改动，因此只复核 Git 入库哈希，不重复全量测试。

## 证据文件

- 实现提交：`9c0d8bd8774ae17b673209eb462d85cb69eaed59`（最小框架、配置、Schema 与测试）；结果和文档随后独立提交，属于同一次交付。
- [质量审计 JSON](../evidence/t17-minimal-quality-audit-20260903.json)：原始计数、检查范围、命令结果、待办及用户文件排除项。
- [验收确认与逐项补充 JSON](../evidence/t17-minimal-acceptance-addendum-20260903.json)：记录用户“同意”、采用的综合覆盖率门、已观察 CI 成功、15 项完成条件和保留的独立审查警告；不覆盖批准前质量快照。
- 全量 JUnit：`.tmp/t17-minimal-work-20260903-01/full-final-01.xml`；SHA-256 `0e0ad067379ee72699a1dba8bc8aed16043f7145bd3161d2888effb8ef6b3506`。
- 覆盖率 JSON：`.tmp/t17-minimal-work-20260903-01/full-final-coverage-01.json`；SHA-256 `dfeaa711b31739974a1db85bcc982ac2c02968d851fd2dea0828f77afd41d35f`。
- 覆盖率数据：`.tmp/t17-minimal-work-20260903-01/.coverage-full-final-01`。用户原 `.coverage-v3-*` 和 `.tmp/` 内容保留。
- 正式 Matrix、Phase、Raw、JSON/CSV 哈希见 [M2 清单](../evidence/T17_MINIMAL_MANIFEST_20260903.md)。

## 修订与版本边界

继续保留用户批准的 `skillflow-normal-task/2.0.0` 最小修订：普通任务与风险 Effect 分离，合法 Effect/Receipt、内容与 Session 绑定不削弱。实现和逐场景说明见 [M1](T17M1_Summary.md)，实际结果见 [M2](T17M2_Summary.md)。

按已批准设计“不改写旧 Summary”的约束，旧 `T17_Summary.md`、`EXPERIMENT_AUDIT.md/json` 及其已登记哈希原样保留；本轮最终结论写入独立 [T17 Minimal Final Summary](T17_Minimal_Final_Summary_20260903.md) 和新质量审计，不覆盖冻结入口。README 区分本轮与历史入口。

## 验收口径确认与停止边界

纯分支 75.89% 不能写成 90%。用户已针对“沿用现有 CI 的综合覆盖率 ≥90% 作为覆盖率验收口径”回复“同意”，因此只将验收规则调整为已明确批准的口径。代码、覆盖率配置、实验预注册、Raw 和指标均不改变，不追加历史分支测试或重跑本地全量测试。原质量审计中的 incomplete/FAIL 是批准前快照，保留原样；解除项由新补充记录解释。

本阶段不修订模型/Provider、不申请 API Key、不补旧 Live Attempt、不运行论文级矩阵、不实现 SkillFlow-Rx。历史 T17-E 保持 incomplete，原 F/G/H 未运行；独立终审仍 `REVIEW_UNAVAILABLE`。本轮最小离线技术验收标记 COMPLETED，不等于原 T17 v1 全量真实模型实验完成，也不等于独立审查 PASS。

## GitHub 首轮失败与最小修复

[运行 33743815190](https://github.com/Suuuu123su/Agent-SkillFlow/actions/runs/33743815190) 为 1016 passed、1 failed、14 setup errors，综合覆盖率 88.06%。日志明确显示两处 CLI 测试使用仓库外系统临时目录，被 `_inside_project` 拒绝；14 个共享 fixture 用例因此未执行，并非正式实验 Raw 校验失败。

新增项目内独占 `t17_cli_root` 测试 fixture，修正 freeze/run/report 和非法 domain 测试的输出位置。未放宽真实 CLI 边界，未修改生产源码、Schema、正式配置或 Raw，未新增正式 Trial/API。相关 20 项测试通过（JUnit 36.257 秒），Ruff 与格式检查通过；按用户要求不重复本地全量测试。失败 CI、RED 和定向 GREEN 均分别保留，见 [独立修复审计](../evidence/t17-minimal-ci-portability-audit-20260903.json)。

[后续运行 33745413298](https://github.com/Suuuu123su/Agent-SkillFlow/actions/runs/33745413298) 已完成并成功：1032 passed，581.84 秒，综合覆盖率 90.13%；所有后续静态、类型与 CLI 步骤通过。本地新增定向边界回归使测试数从 1031 增为 1032，不能混淆为新实验样本。

口径确认后再次只读核对：每域 1041 个 Raw 文件的哈希与长度、46 个 JSONL 的 521 条记录、424 个冻结源码/Schema 文件均无差异；53 个登记旧 canonical 和 4 个旧 T17 公开指标一致。最终文档交付的提交与 CI 另记新本地回执，不覆盖第一次回执或冻结结果。
