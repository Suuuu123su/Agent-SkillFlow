# T17 最小技术验收修订设计（2026-09-03）

- 状态：`APPROVED_FOR_OFFLINE_IMPLEMENTATION`；用户已批准最小修订，但 Matrix/Phase Contract 尚未冻结，实验尚未运行。
- 源码基线：`d5506e25e927c2eb4225ee54eab4c01069d408c0`，GitHub main。
- 用户新目标：补齐所有指标的受信证据链并完成最小端到端技术验收；不要求统计显著性、大样本、多模型或 SkillFlow-Rx。
- 新付费请求 / 新实验 Run：0 / 0。

## 1. 必须先解决的合同冲突

C1 与 N0 的 `task.id`、prompt 和正常输出 commitment 相同，但原 Scenario 的 `success_assertions` 分别要求 `context-harm` 执行与不执行。T17 v1 注册表也把 C1 的风险 Effect 列为任务成功必需项。因此原 task_success 混合了任务输出与攻击触发预期，不能直接作为本轮正常任务效用验收。

用户已回复“按照你的最小修订来，后续summary的时候写进去”，批准新增版本化正常任务合同；不得改写旧 Scenario、注册表、Golden、Raw、Summary 或原分母。修订不能简单删除所有 Receipt 断言：B0 等真正依赖合法读取的任务仍须有相应 Effect/Receipt，正常任务输出仍须通过可信 Artifact、内容 commitment 和 Session 绑定验证。攻击触发预期保留在独立风险 Golden 中。批准不包含新的付费调用。

证据及 SHA-256 见 [合同审计](../evidence/t17-minimal-contract-audit-20260903.json)。

## 2. 仅保留两个技术验收主张

| 主张 | 最小证据 | 不作出的主张 |
|---|---|---|
| 现有指标能沿完整运行链从 Raw 复算 | 现有 YAML、可信 Runtime、双轨 Trace、Graph、Replay、TaskSuccessEvidence、标准报告与 Schema/哈希绑定 | 真实模型攻击率或生产平台等价性 |
| 安全与正常任务效用能独立测量 | B0 良性与 B1 风险的 Monitor/Enforce 配对，分别报告风险差、任务差和 Over-defense | 任意加权安全总分、普遍防御优势或统计显著性 |

## 3. 最小 Matrix 候选

每域 23 个 core，1 个 semantic instance、1 个主要 repeat：

- 保留 C1/C2 各 4 格；N0 已由 C1 中性格覆盖。
- 保留 B0/B1 的 Monitor/Enforce，共 4 个 core，直接复用为最小防御对照，不追加防御 Run。
- G0 只保留 preserve；M1 保留 preserve/drop_on_memory，满足来源消融。
- 保留 M2 target/control，真实到达撤销后的 Session 1、3。
- 保留 A1/A2；ALR 依赖各自 claim-only Replay。
- S1 保留 monitor 并补入现有 `S1_CONTROL`；省去重复的 S1 enforce。原 24-core Matrix 未运行这个能力匹配控制。
- 保留 L1 原 Session/新 Session 配对。

相对旧 24-core Matrix：移出 `g0-drop-memory` 与 `s1-enforce`，补入现有 `S1_CONTROL`，共 23 core。不另建新的场景体系。

只保留 12 个必要 Replay pair：C1 的 p01/p11、C2 的 p01/p11、G0 preserve、M1 preserve、M2 control 与 target 各 2 个（Session 1、3）、A1/A2 各 1 个。每组正因果链保留相应负对照。其他无助于技术覆盖的 Replay 不运行。

分别在 Scripted 与 Fake Reference Harness 中执行；合计 46 core、24 Replay，两个域分别报告，绝不 pooled。真实 API 默认不运行；若离线验证暴露确需真实模型的剩余问题，另提最小 Canary 与费用，等待用户批准。

## 4. 指标与门禁

- 保留 Task/Safe Task、VTE、UEA count/affected-trial-rate/type/weight、provenance TP/FP/FN/P/R/F1/Decay、HIAA scheduled/valid-only/potential、ALR、RIR(1/3)、CI/确认影响、失败分类和效率字段。
- scheduled 为主分母；valid-only 只作敏感性。计数、值、状态、证据 ID 及分母均须从实际运行数据复算。
- 单 semantic instance 的 bootstrap、跨模型方向和论文级泛化不属于本轮验收，按设计说明 N/A；不能借此隐藏应有 Hook 缺失或不完整配对。
- 失败注入单独验证 refusal/no-call/Schema/infra/预算等分类和 Partial 用量，不进入核心分母；模拟用量不得冒充实际模型 Token 或费用。
- Defense 只针对预注册 B0/B1 配对报告风险、效用、Safe TSR、Over-defense 与开销变化，不声称全场景防御有效。
- 不把 `model_construct` 或手写最终指标当实验结果；最终 JSON/CSV 必须由 Raw 读取器和正式分析器生成。

## 5. 执行次序

| 子阶段 | 内容 | 当前状态 |
|---|---|---|
| T17-M0 | 仓库审计、旧哈希复核、最小设计 | 已完成；合同修订已获用户批准 |
| T17-M1 | 新任务/Phase Contract、最小 Matrix 与报告接口，定向 red→green | 进行中 |
| T17-M2 | Scripted 与 Fake Reference 最小端到端运行、复算与 Defense | 未开始 |
| T17-M3 | 全量 pytest ≥90%、静态/Schema/doctor/pip/no-excuse/禁网/密钥审计与最终文档 | 未开始 |

单个修复只跑定向回归；最后按用户最新技术验收要求运行一次完整质量门。新增/修改代码遵守 400 行上限。全部临时文件与新 Run 仅放在项目下的新目录；旧文件不删除。

每个子阶段同步 README、progress、Summary、指标状态、费用与 SHA-256。旧 T17 v1 的 E Partial、F/G/H 未运行和独立终审 `REVIEW_UNAVAILABLE` 保持历史原状；本轮技术验收结论另行版本化记录。
