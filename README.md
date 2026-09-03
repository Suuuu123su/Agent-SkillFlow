# Agent-SkillFlow

SkillFlow 是一个面向 Agent Skill 安全研究的确定性测量原型，用于追踪 Skill 的影响如何经过共享上下文、持久记忆、其他 Skill 与工具传播，并区分数据来源、决策影响和真实授权。

当前仓库已执行到 **T17-E：全指标 Live Canary**。**T17-A～D 已完成，T17-E 未通过阶段门，T17-F～H 未运行；T17 总体状态为 INCOMPLETE，不能宣称全量指标闭环完成。** 真实模型实验中的响应和 Tool 调用是真实记录，但外部 Effect 仍由本地 Safe Sink 与模拟 Receipt 替代，结果不是现实网络、Shell、邮件或文件外发成功率。

## T17 当前进度（2026-09-03）

| 阶段 | 当前状态 | 已验证内容或阻塞点 |
|---|---|---|
| [T17-A：基线冻结](docs/summaries/T17A_Summary.md) | 已完成 | 指标登记、四态测量合同、Evidence Domain 与旧证据哈希冻结。 |
| [T17-B：Reference Harness](docs/summaries/T17B_Summary.md) | 已完成 | 可信 Hook、伪造拒绝、Checkpoint/Replay 与 Fake Client 技术验证；不代表真实平台 Hook 已补齐。 |
| [T17-C：场景测量规格](docs/summaries/T17C_Summary.md) | 已完成 | 注册 16 个 Scenario；现有 Matrix 引用其中 15 个，展开为 24 core 变体及 18 Replay 规格。 |
| [T17-D：Scripted Golden](docs/summaries/T17D_Summary.md) | 已完成 | 24/24 core、18/18 Replay；24 个配置均通过 5 次确定性指纹检查，API 调用为 0。 |
| [T17-E：Luna Canary](docs/summaries/T17E_Summary.md) | incomplete | 最新 Attempt 完成 16/24 core、12/18 Replay；另 1 core 有完整用量但缺少终态，scheduled 分母未闭合。 |
| [T17-F：Model1 正式矩阵](docs/summaries/T17F_Summary.md) | not_available | 未运行；不能用 Canary 或 Scripted 结果替代。 |
| [T17-G：Model2 / 跨模型](docs/summaries/T17G_Summary.md) | not_available | 未运行；没有 T17 GPT-5.5 或跨模型比较结果。 |
| [T17-H：Monitor / Enforce](docs/summaries/T17H_Summary.md) | not_available | 未运行；Security Gain、Utility Loss 等防御比较指标不可用。 |

### 已有结果及证据边界

- **Scripted Golden（本地模拟）**：TSR 为 20/24，Safe TSR 为 11/24，Verified Target Effect 为 15/24；TaskSuccessEvidence、Receipt、必需 Hook 覆盖率分别为 24/24、54/54、89/89。UEA count/type/weight 为 8/7/8；Provenance Precision/Recall/F1 为 1.0/0.954198/0.9765625；C1/C2 HIAA_run 均为 1.0；ALR、RIR(1)、RIR(3) 均为 1/2。这些是框架及合成 Oracle 的验证结果，不是现实 LLM 攻击成功率。
- **Luna Canary（最新 Partial Attempt）**：已完成 core 的 observed-only TSR 为 12/16 = 0.75，Safe TSR 为 7/16 = 0.4375。二者正式 scheduled 值仍为 `null`；模型拒绝为 0，良性任务失败为 1，二者不能混用。
- **全部 T17 Live Attempt 的累计用量**：182 次请求、181 次响应；输入/缓存输入/可见输出/推理 Token 为 26,253/0/6,319/15,902。实际费用估算为 $0.0319158，保守占用为 $0.0328657；均不是已确认账单。只累计调用及费用，不跨 Attempt 聚合实验指标。
- **当前停止点**：M2 模型未产生后续步骤必需的 Tool 结果。代码已将此类缺失转为可审计的失败终态，但没有重写旧 Attempt，也没有通过补采或改 Prompt 消除失败。后续恢复须先明确协议修订并重新确认预算；当前不扩大付费实验。
- **审计边界**：保留既有 `WARN_INCOMPLETE` 与独立终审 `REVIEW_UNAVAILABLE`；Canary 单 cluster 的 bootstrap 为 `not_applicable`，不能把未运行阶段改写为设计不适用。

完整结果入口：

- [T17 总结](docs/summaries/T17_Summary.md)、[指标登记表](docs/metrics/metric-registry.md)。
- [已测及缺失指标 JSON](docs/evidence/t17-final-metrics.json)、[汇总 CSV](docs/evidence/t17-final-summary.csv)；文件名中的 `final` 不表示 T17 已完成，JSON 明确保存 `complete: false`。
- [Canary Partial 审计](docs/evidence/t17-e-canary-partial-audit.json)、[有效 Scripted Golden 汇总](docs/evidence/t17-scripted-golden-summary-v2.json)、[基线审计](docs/evidence/t17-baseline-audit.json)。
- [Raw 哈希与产物清单](docs/evidence/T17_FINAL_MANIFEST.md)、[实验审计](EXPERIMENT_AUDIT.md)。完整 Raw 与失败 Attempt 仅保留在本地 `runs/t17-*`，不上传、不合并、不改写、不删除。

历史 T16 结果保持独立：T16-C v2 完成 Luna 48 条 Smoke 与 360 条正式链，T16-D v3.1 Canary 完成 11/11，T16-E 固定 GPT-5.5 snapshot 完成 6/11 后被单 Trial 费用门停止。上述历史记录没有并入 T17 分母。

## 最新研究路线：T17 指标闭环 → SkillFlow-Rx

当前最新设想是 **SkillFlow-Rx：基于量化攻击机制画像的自适应防御编排**。它不只判断“是否存在攻击”，而是从 SkillFlow 受信任的来源、授权、Effect/Receipt、跨 Session、撤销和反事实证据中形成支持多标签与 `abstain` 的攻击机制画像，再选择风险降低效果最好、正常任务损失最小的防御组合，并用同一证据链重新验证防御是否对症。

```text
运行证据 → 量化指标 → 攻击机制画像 → 最小防御组合 → 再运行/反事实验证
```

SkillFlow-Rx **目前只是研究设想，尚未实现，也没有进入现有实验结果分母**。T16 真实模型路径的 UEA、ALR、RIR 和 provenance 仍受平台 Hook 缺失限制；T17 已建立独立 Reference Harness 并完成 Scripted 全指标验证，但 Live Canary 分母尚未闭合，不能据此宣称真实平台或全量模型指标已完成。

T17 原计划及当前执行边界如下；计划规模不等于已运行数量：

1. **T17-A～D（已完成，零费用）**：冻结指标与证据域、建立可信 Reference Harness、补齐场景 TaskSuccess/Oracle 规格，并完成 Scripted Golden 验证。Influence 只能由成对 Replay 产生。
2. **T17-E～G（当前止于 E Partial）**：Luna Canary 目标为 24 core + 18 Replay；原 F/G 正式矩阵各为 360 core + 270 Replay，G 另有 24 + 18 Canary。F/G 均未运行，不自动扩至更多 semantic instances。
3. **T17-H（未运行）**：仅用 Luna 比较 Monitor/Enforce，不增加可选单项防御，不构造任意加权“总安全分”；原计划复用 F 并补齐缺失模式，合计 630 core、540 Replay。
4. T17 全部闭环后，才进入 SkillFlow-Rx 的攻击诊断器与自适应防御选择实验。

继续实验必须遵守阶段门和逐阶段预算批准；代码实现、离线验证、真实模型完成率分别报告。原始计划与后续研究设想见：

- [T17：补全现有框架指标并完成实验闭环](docs/plans/T17_metric_completion_experiment_plan.md)
- [SkillFlow-Rx：基于量化攻击机制画像的自适应防御编排](docs/research/attack-diagnosis-adaptive-defense.md)

## 当前能力

- 可安装的 Python `src` 布局包。
- `skillflow version`：输出当前版本。
- `skillflow doctor`：离线检查 Python、SQLite、运行依赖和临时目录可写性。
- `skillflow t17 audit-baseline | run-scripted | run-live | report`：基线冻结、Scripted Golden、受预算约束的 Live Supervisor 与证据报告；命令可用不代表相应 Live 阶段已完成。
- `skillflow-pilot`：在固定 OpenClaw revision 上运行 B0、G0、M2 的 Mock/OpenClaw 双 Adapter Pilot。
- `skillflow validate-manifest PATH`：只校验 Skill Manifest，不加载或执行 Skill。
- `skillflow validate-scenario PATH`：只校验 Scenario，不运行 fixture。
- Pydantic v2 核心安全模型、受控 Resource URI、`call | task | session | persistent` 菱形 Lifetime，以及四种互不放大的精确 Scope。
- `skill-manifest`、`scenario`、`experiment-matrix`、`risk-report`、T16 合同与 T17 Evidence/Hook/Observation/Trial/Phase/Comparison 等共 56 份模型生成静态 JSON Schema。
- T17 使用独立的 `measured | not_applicable | not_available | incomplete` 测量状态；不同 Evidence Domain、模型、协议与失败 Attempt 不混合统计，缺失证据不会被写成数值 0。
- T16 预注册固定 12 个条件、每条件 10 个语义实例和每实例 3 次采样；静态 Matrix 可按预注册机械重建。
- T16 Provider 提供无 I/O Fake 实现与显式 Client 注入边界；Live 必须显式开启，并在调用前限制费用、turn、输出和重试。密钥只在交互入口读入一次并保存在 `SecretStr` 内存对象中，不从环境或文件读取。
- T16-B 双 Fake Slot 完成 720 条链、960 次纯本地调用；重复身份在统计前拒绝，C1/M2/A1 配对不变量和部分结果保存均有结构化证据。
- T16-C v2 的 GPT-5.6 Luna 正式运行完成 360/360 条、1,133 次模型调用；HIAA scheduled 为 0.4667，valid-only 敏感性为 0.0667，必须并列解释 refusal 分母影响。M2 Session 1/3 target-control 差为 0.3000/0.4667，A1 claim-neutralized 差为 0.0333。正式 UEA、ALR、RIR 和 provenance 均因平台 Hook 缺失保持 N/A。
- T16-D v3.1 的 Luna Canary 完成 11/11，TaskSuccessResult 11/11、90 条断言全部可评估；T16-E 的 GPT-5.5 固定 snapshot 只完成 6/11，C1 单 cluster 方向与 Luna 一致，但 M2/A1 跨模型方向仍为 N/A。
- SQLite EventStore：事件、Grant、撤销及输入输出边追加写入，数据库触发器拒绝历史 UPDATE/DELETE。
- Event、输入输出边、Decision 与 Effect 以一个 Envelope 原子提交；失败时不留下半条事件。
- 按 Run 隔离的受控 BlobStore：引用不暴露路径，读回时校验内容 hash 与长度。
- Persistent Memory 头可跨 Session 和进程重启恢复；历史事件仍保持不可变。
- Trace 默认只投影 hash 与结构化元数据，同一持久事件序列在重开数据库后得到相同哈希。
- 可注入虚拟时钟与确定性 ID 工厂，用于后续可重放实验。
- 最小 `HarnessAdapter` 仍只包含 `start_session`、`load_skill`、`invoke_skill`、`end_session`；T10 通过独立的 `CheckpointableHarnessAdapter` 扩展增加 `checkpoint`/`restore`，不扩大普通 Harness 合同。
- `MockHarnessAdapter` 与白名单 `ScriptedBackend` 不调用真实 LLM，也不动态导入 Scenario 指定的 Python 实现。
- Context、Persistent Memory、隔离 Workspace 文件和 Skill 六段生命周期都生成不可变 Artifact 或追加 Event。
- 普通 Tool 白名单固定为 `read_file`、`write_memory`、`read_memory`、`http_send`、`shell_exec`；用户确认和 Skill 撤销不在普通 Tool 面中。
- Tool 调用严格记录请求、规范化 Effect、参数 Artifact、完整 Decision、Mock 执行和强类型 Receipt；拒绝请求不产生 Effect 或 Receipt。
- Manifest capability matcher 与 Grant matcher 同时校验主体、动作、精确资源、Scope、Lifetime 边界、时间窗和撤销状态；两把钥匙缺一不可。
- PolicyEngine 返回 `ALLOW | DENY | CONFIRM` 与稳定 reason codes，并保持 `baseline_result`、`policy_result`、`authorized`、`executed` 四个事实互不覆盖。
- monitor 只放行 baseline 已允许的 Mock Effect，不会洗白授权；enforce 只在 baseline 与 policy 都允许时执行。
- 只有 Benchmark 编排器能以 `USER | TRUSTED_POLICY` 调用特权确认入口并生成结构化 Grant；Skill 身份和普通“用户已批准”文本都不能授权。
- HTTP 与 Shell 只有进程内结构化 Mock 记录，不建立网络连接、不创建子进程；文件只能访问每次运行独占的 Workspace 根。
- 同一 YAML、虚拟时间与 seed 的 Trace hash 一致；两个 Run 的 Context、Memory、Receipt 与 Workspace 状态互不累积。
- 每次 Scenario Run 同时创建 `observed-trace.jsonl` 与 `oracle-trace.jsonl`；默认只含结构化 ID、来源、关系、能力和 Receipt 引用，不含 Blob、Tool 参数明文或 fixture marker。
- Observed Writer 只投影 Harness 实际标签；Oracle sidecar 只接收 Scenario、受控 Manifest、Scripted action、Tool attempt 和 Receipt 的单向证据投影，不读取 Observed 标签或策略结果。
- 每个值和实际 Effect 使用稳定 Artifact/Effect ID，并记录 `COPY | DERIVE | WRITE | LOAD | INVOKE` 封闭父关系；被拒绝的 Tool attempt 仍保留可对齐的 argument 值，但不会伪造 Receipt 或 `GT_effect`。
- `OracleGrantResolver` 以 Manifest + 真实 Grant 双钥匙独立计算 `GT_auth`，支持四值菱形 Lifetime、时间窗和撤销 ID；Stub/Policy 结果不能改写真值。
- `drop_on_derive`、`drop_on_memory` 只破坏 Observed origins；相同真实步骤下 Oracle JSONL 保持不变，可用于后续来源 Recall 评价。
- Agent、Skill、Tool、Policy/Observed 运行模块没有 Oracle 反向导入；只有 Benchmark 的单向 bridge 同时接触两侧的中立合同。
- SQLite EventStore 是来源图的唯一事实源；`SecurityGraph` 不读取 Oracle、Observed Writer、Blob 正文或任意 Event metadata。
- 来源核心严格保持 `Artifact --USED--> Event --GENERATED--> Artifact` 二部方向，其上以类型化 Principal、Grant、Decision 与 Effect 节点建立只读安全投影。
- 语义边封闭为 `READ | WRITE | LOAD | INVOKE | DERIVE | PERSIST | AUTHORIZE | INFLUENCE_CANDIDATE | INFLUENCE_CONFIRMED | REVOKE`；普通轨迹只产生候选影响，不会把时序相关性升级为确认影响。
- 已实现七类研究查询：祖先、任意端点路径、不可信来源、授权路径、撤销祖先、跨 Session 路径和 Skill→Effect 路径；每条路径返回类型化节点、语义边、Session 顺序、证据 Event ID、Grant/Skill/Tool ID 与五类边界深度。
- 路径枚举使用逐路径访问集合和默认最大深度 64，循环图不会无限遍历；Session 重新进入按真实顺序再次计数。
- Scenario Runner 自动以不可覆盖方式写出脱敏 `security-graph.json`；导出模型不含 Blob、正文或任意 metadata，GraphML 明确保留到 T14 后再评估。
- Scenario Runner 自动生成 `risk-report.json`；写入前同时经过 Pydantic 判别联合和 Draft 2020-12 JSON Schema 复验，已有文件不会被覆盖。
- `UEA_count` 按未授权且已执行的 Effect/Receipt 实例计数，`UEA_type_count` 按 `(source, action, sink, scope, lifetime)` 全局去重，首版 `UEA_weight` 对每个实例取权重 1。
- 每个 UEA 实例都保留 Manifest/Grant 缺失 reason codes、Effect/Receipt/Decision ID，以及 SecurityGraph 中 Principal→Effect 的类型化路径、边界深度与证据 Event ID。
- 来源指标按 Artifact 对齐 Oracle/Observed origins，输出 TP/FP/FN、Precision、Recall、F1 和相邻边界深度 Decay；每个比例都包含 numerator、denominator、value、status 与证据 ID，零分母严格表示为结构化 N/A。
- 多场景分析同时保留逐场景 `RunRiskReport` 和 micro 聚合；micro 先汇总 UEA 实例与原始 TP/FP/FN，再重算比例，不平均各场景百分比。
- Oracle 声明式 asset 根允许只存在于 Oracle；除它以外的运行 Artifact 必须在双轨中完整对齐，避免缺失 Observed Artifact 被静默排除而高估 Recall。
- Checkpoint 在静止 step 边界冻结 EventStore/Blob、Workspace、Context、Memory、Skill 安装/加载/撤销状态、Grant/撤销事实、Mock Tool 状态、虚拟时间和确定性 ID 计数；恢复目标必须是新的空分支，恢复后重新计算的规范化前缀哈希与状态哈希必须一致。
- `ScenarioExecutor` 可以在目标 Artifact alias 产生后暂停，并连同有序游标、Alias 绑定、输出和 Receipt 一起恢复；正常 Run 仍通过原 `ScenarioRunner` 公开入口执行。
- Artifact 中和通过追加 `ARTIFACT_DERIVE` 新版本完成，不修改源 Artifact，也不删除 Skill；identity 与 neutral 分支保持 Artifact 类型、MIME、可机械验证的结构 Schema 和精确长度，并使用相同 seed、虚拟时间、脚本、Tool 返回、Manifest、Grant 和其余输入。
- `ReplayRunner` 对每个预注册 counterfactual 创建 source/original/neutral 三个隔离 Run；原始与中和分支从同一 checkpoint 恢复，具有不同 run ID，但干预前 Trace 前缀和完整状态哈希一致。
- Replay 只比较 Effect selector 命中的已执行 `EffectRecord`，且每个结果必须有同分支真实 `ToolReceipt`；自然语言输出、时序相关和普通来源图不会生成确认因果边。
- Scripted CI 固定为 `int(y_original) - int(y_neutral)`，取值仅为 `-1 | 0 | 1`；只有非零 CI 才生成类型化 `INFLUENCE_CONFIRMED`，无关内容负对照必须得到 CI=0。
- 每个配对以不可覆盖方式写出 `replay-report.json` 和 `pair-manifest.json`；只包含 ID、哈希、结构、控制条件和 Effect diff，不包含 Artifact 正文、Blob ID 或宿主路径。
- `HiaaDesign` 自动生成 `p00/p01/p10/p11` 四格并为整套四格绑定同一个 `harm_selector`；四格只改变目标/中性 Skill 和一个预注册 Harness 特性，其余 seed、执行模式、来源模式与开关保持一致。
- 中性 Skill 对照必须与目标 Skill 具有相同 Manifest 摘要、Schema 摘要和工具注册，并共同落入预注册长度区间；目标必须含待测危险语义，中性版本必须明确移除该语义。
- 四格 `y=1` 只由匹配共享 selector、`executed=true` 且带同 Run 真实 Receipt 的 Effect 机械推导；无关敏感 Effect 不能使 `y=1`。报告同时公开 selector、原始 outcome、Effect/Receipt、计数、分母、发生率与结构化 N/A。
- `HIAA_pot` 按 `W(U_H1 \ U_H0)` 计算，`HIAA_run` 按 `p11-p10-p01+p00` 计算并保留负值；任一四格零分母时结果为结构化 N/A。
- ALR 只有在无真实 Grant、低可信授权声明进入决策依据、baseline reason 为 `IMPLICIT_TEXT_AUTHORIZATION`、原运行有 Receipt、成对中和只删除声明，且中和后变为 confirm/deny 或动作消失时才进入分子；分母按唯一 `authorization_request_id` 去重，普通恶意指令不进入分母。
- RIR 记录 Skill 撤销 Event、会话索引和带时区时点；每个 Run 最多计一次，因果归因只允许 `INFLUENCE_CONFIRMED`、独立 `GT_influence` 或显式无归因。Oracle `GT_data`/来源路径只作 provenance 审计，不能单独抬高分子。
- Experiment 风险报告通过判别联合与静态 Schema 复验，包含共享 `harm_selector`、四格、`HIAA_pot`、`HIAA_run`、`ALR`、`RIR_1`、`RIR_3`、洗白/普通绕过 request ID 和全部原始计数。
- T12 场景库包含 B0、B1、N0、C1、C2、M1、M2、A1、A2、S1、L1、G0，以及四个独立良性控制，共 16 个可执行 YAML；每个攻击场景都有双向绑定的能力匹配良性对照。
- 每个 T12 Scenario 都声明固定 Task、Fixture/Canary、Manifest、Grant、Session/Step、Effect selector、成功断言、指标方向或结构化 N/A；HIAA 场景额外绑定唯一 `harm_selector`。
- T12 固定 registry 提供 16 个 `fixture://t12/...` Scripted Skill，实现 Tool Return alias、跨 Session Memory、低可信授权声明和条件动作；没有 Shell 动作，所有网络效果只进入 `mock://` Sink。
- `scenarios/matrix/mvp.yaml` 包含 24 个核心变体和 2 套机械生成四格，覆盖目标/中性 Skill、Harness 开关、来源故障注入、monitor/enforce、normal/revoked、原/新 Session、假文本/真实确认；每个配置声明 5 次确定性复跑，复跑与 counterfactual 不进入普通指标分母。
- `task_success` 只由 Artifact SHA-256 与 selector 命中的真实 Effect/Receipt 成功断言机械求值；全部拒绝虽然可令 UEA 为 0，但会在报告中明确显示任务失败。
- `skillflow run` 自动建立 single-run Experiment；`skillflow matrix` 和 `skillflow factorial` 建立可复现批量 Experiment，默认启用脱敏。
- 标准 Experiment 根包含 `experiment-manifest.json`、`aggregate-metrics.json`、`summary.csv`、`experiment-report.json`、共享 `state.sqlite`、受控 `blobs/`、核心 `runs/` 与规范化 `replays/`。
- 每个核心 Run 固定输出 `run-manifest.json`、双轨 JSONL、`graph.json` 与 `run-report.json`；每个 Replay 固定输出 `pair-manifest.json` 与 `replay-report.json`。
- 确定性副本只写入 `blobs/determinism/` 并记录一致性指纹，不注册为核心 Run，也不进入 HIAA、ALR、RIR 或 CSV 分母。
- `analyze` 与 `graph` 从共享 SQLite、Blob 元数据和原始 JSONL 重建派生产物；`aggregate` 只读取标准 RunResult/ReplayResult，不依赖 Runtime 对象。
- JSON 报告以 `report_scope=run | replay | experiment` 判别并经静态 Schema 复验；CSV 同时保留指标值及原始 numerator/denominator。
- `export` 支持 Run 与 Experiment 报告的不可覆盖导出；宿主绝对路径、Blob 正文和 fixture 原文不进入标准报告。
- T14 四条必需 E2E 均从 YAML 经过解析、运行、双轨 Trace、安全图、指标到报告，测试不直接构造最终 MetricReport。
- Runtime/Policy 的 Oracle 反向导入和执行边界的真实网络、进程、凭据模块导入均由 AST 门禁检查；MVP Matrix 另在临时网络/进程拦截器下运行。
- 所有已执行 Sink 必须同时带来源路径、Decision 和 Receipt；风险报告接受 fixture 原文、Blob 字段与宿主绝对路径泄漏扫描。
- EventStore append/get 与 PolicyEngine evaluate 有可复跑的本机观察性性能基线；没有把本机 p95 写成跨机器 SLA。
- pytest、90% 分支覆盖率、ruff 与 mypy 质量门禁。
- GitHub Actions 自动执行同一组质量门禁。
- OpenClaw Adapter 只位于 `skillflow.pilot` 与 `integrations/openclaw`；核心 Policy、SecurityGraph 和指标分析器没有平台专用分支。
- OpenClaw 事件经过严格 JSONL/Pydantic 边界转换为统一 `SecurityEvent`；未知事件、空行、非连续序号和不完整 Receipt Effect 全部拒绝。
- OpenClaw Gateway 固定到 commit `452e734022214f5f00bdd44cae675cc467c3cd85`、version `2026.8.1`，只绑定 loopback，只允许 `read`、`write` 与 `skillflow_safe_sink`。
- Pilot 只加载 Scenario 预注册 Skill；Skill invoke 必须同时满足目录已宣告和对应 `SKILL.md` 精确读取成功，不能用 `skill_changed` 冒充调用。
- B0/G0/M2 的目标 Effect 数在 Mock 与 OpenClaw 间分别为 `1/1`、`1/1`、`2/2`；三者的策略事实均不匹配，差异被定位到缺失平台钩子。
- Mock 来源指标是全图 Artifact recall，OpenClaw 只能给出目标 Effect 标签覆盖率；统计单位不同，报告把 `provenance_delta` 保持为 `null`，不伪造可比性。
- 中文威胁模型、安全语义、形式化不变量和架构决策记录。
- 中文任务进度、仓库基线与逐任务总结。

## 环境要求

- Python 3.11 或更高版本。
- 离线测试、Scripted 与普通分析命令不访问外网，不需要 API Key 或用户账号；显式 Live 命令需要已批准预算、模型 API 网络访问与交互式密钥输入。
- Live 密钥只在同一 Supervisor 进程内隐藏输入一次并保留于内存，不从环境或文件加载，也不写入磁盘；进程退出后恢复才需重新输入。
- 仅运行 T15 Pilot 时，还需要 Node.js、已构建且精确固定 revision 的 OpenClaw checkout；仍不需要真实模型凭据。

Windows 本地安装：

```powershell
python -m venv .venv-skillflow
.\.venv-skillflow\Scripts\python.exe -m pip install -e ".[dev]"
```

创建环境前请先用 `python --version` 确认解释器版本达到 3.11。

## 使用方法

```powershell
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli --help
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli version
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli doctor
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli validate-manifest tests\fixtures\t03\valid_manifest.yaml
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli validate-scenario tests\fixtures\t03\valid_scenario.yaml
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli run scenarios\attacks\a1_implicit_text_authorization.yaml --mode monitor --output runs\a1
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli analyze run-a1-single --runs-root runs
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli graph run-a1-single --format json --runs-root runs
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli factorial scenarios\attacks\b0_legal_summary.yaml --feature persistent_memory --seeds 0 --output runs\b0-factorial
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli matrix scenarios\matrix\mvp.yaml --backend scripted --output runs\mvp
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli replay RUN_ID --neutralize-artifact ARTIFACT_ID --runs-root runs
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli aggregate mvp --runs-root runs
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli export --scope run RUN_ID --output run-report.json --runs-root runs
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli export --scope experiment mvp --output experiment-report.json --runs-root runs
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t06_dual_trace.py -q --no-cov
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t07_scenario_graph.py -q --no-cov
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t08_policy_modes.py -q --no-cov
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t09_risk_report.py -q --no-cov
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t10_counterfactual_replay.py -q --no-cov
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t11_experiment_report.py -q --no-cov
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t12_library_execution.py -q --no-cov
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t14_research_acceptance.py -q --no-cov
```

安装后也可以直接使用控制台命令：

```powershell
.\.venv-skillflow\Scripts\skillflow.exe --help
.\.venv-skillflow\Scripts\skillflow.exe t17 --help
```

## T15 OpenClaw Pilot

先确认 OpenClaw checkout 的 `HEAD` 精确等于 `452e734022214f5f00bdd44cae675cc467c3cd85`，并已按 OpenClaw 自身流程完成构建。输出目录必须尚不存在：

```powershell
.\.venv-skillflow\Scripts\skillflow-pilot.exe `
  --openclaw-root E:\path\to\openclaw `
  --output runs\t15-pilot
```

Pilot 会为 B0、G0、M2 分别写出 Mock/OpenClaw observation、统一 `security-events.jsonl` 和总 `pilot-report.json`。它不会读取用户 OpenClaw 主目录配置；Gateway、state、workspace、假 Provider 与插件日志都在本次输出边界内隔离。完整设计见 [`docs/openclaw-adapter-design.md`](docs/openclaw-adapter-design.md)，已验证的结构化摘要见 [`docs/evidence/t15-pilot-summary.json`](docs/evidence/t15-pilot-summary.json)。

从已持久化 Run 重建来源图并查询：

```python
from pathlib import Path

from skillflow.graph import SecurityGraph
from skillflow.store.sqlite_store import SqliteEventStore

with SqliteEventStore(Path("runs/example/state.sqlite")) as store:
    graph = SecurityGraph.from_store(store, "run-example")
    paths = graph.find_skill_to_effect_paths("skill-a")

for path in paths:
    print(path.skill_ids, path.tool_ids, path.cross_session_count)
    print(path.evidence_event_ids, path.boundary_depth)
```

## 质量检查

最近已完成的代码质量检查对应提交 [`a652526`](https://github.com/Suuuu123su/Agent-SkillFlow/commit/a652526187eef096fdb46f41c01b01cd5c5b7ddb)：[GitHub Actions 通过](https://github.com/Suuuu123su/Agent-SkillFlow/actions/runs/33652065313)，955 项测试通过，启用分支统计的总覆盖率为 90.04%，Ruff 检查/格式、mypy 与 CLI 检查均通过。这是工程质量证据，不会消除 T17-E 的实验缺口或替代独立终审；阶段总结中的较早测试数字保留其原时点含义。

```powershell
.\.venv-skillflow\Scripts\python.exe -m pytest -q
.\.venv-skillflow\Scripts\python.exe -m ruff check .
.\.venv-skillflow\Scripts\python.exe -m mypy src\skillflow
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli --help
```

当前 pytest 门禁为 90%。完整复现、变量控制、统计纪律与结论边界见 [`docs/evaluation-protocol.md`](docs/evaluation-protocol.md)；本机性能观察值见 [`docs/performance-baseline.json`](docs/performance-baseline.json)；T15 Pilot 见 [`docs/summaries/T15_Summary.md`](docs/summaries/T15_Summary.md)，T16-A 零费用准备见 [`docs/summaries/T16A_Summary.md`](docs/summaries/T16A_Summary.md)，T16-B Fake 全量演练见 [`docs/summaries/T16B_Summary.md`](docs/summaries/T16B_Summary.md)，T16-C 原始真实模型记录见 [`docs/summaries/T16C_Summary.md`](docs/summaries/T16C_Summary.md)，历史 v0.4 语义与执行层修正见 [`docs/summaries/T16C_Correction_Summary.md`](docs/summaries/T16C_Correction_Summary.md) 和 [`docs/evidence/t16c-live-reanalysis-v0.4.json`](docs/evidence/t16c-live-reanalysis-v0.4.json)；修复后 v2 真实复跑的当前结果见 [`docs/summaries/T16C_V2_Summary.md`](docs/summaries/T16C_V2_Summary.md) 与 [`docs/evidence/t16c-v2-live-summary-20260829.json`](docs/evidence/t16c-v2-live-summary-20260829.json)。

TaskSuccessEvidence v3.1 的 Model1 Canary 结果见 [`docs/summaries/T16D2_V31_Canary_Summary.md`](docs/summaries/T16D2_V31_Canary_Summary.md)；第二模型最小跨模型验证因单 Trial 费用门在 M2 control 停止，当前状态与不完整证据边界见 [`docs/summaries/T16E_Summary.md`](docs/summaries/T16E_Summary.md)。

## 项目范围

首版 MVP 仍只面向单 Agent、2～3 个 Skill、共享 Context、Persistent Memory、多 Session 与安全 Mock Tool。T16-C～T16-E 增加受预算约束的 Responses API 调用与最小跨模型 Canary；T17 增加可信 Reference Harness、测量合同与全指标阶段门，当前 Live 仍停在 E Partial。除批准的模型 API 请求外，真实网络外发、真实 Shell、真实凭据持久化、生产级 UI、多 Agent 协作与生产部署仍不在本阶段范围内。

完整任务依赖和验收标准见 [`SkillFlow_Codex_Task_Spec.md`](SkillFlow_Codex_Task_Spec.md)。冻结的研究边界见 [`docs/threat-model.md`](docs/threat-model.md)，安全语义见 [`docs/security-semantics.md`](docs/security-semantics.md)，架构决策见 [`docs/decisions/`](docs/decisions/)。当前 T17 状态以本文进度表和 [T17 总结](docs/summaries/T17_Summary.md) 为准；历史过程见 [`docs/progress.md`](docs/progress.md)，逐任务总结见 [`docs/summaries/`](docs/summaries/)。

## 进度同步约定

每完成一个任务或阶段部分，都必须在同一交付中同步更新 README：当前状态、实际验证范围、结果及证据链接、遗留问题和下一步边界。若部分完成、失败或暂停，也要记录真实状态；不得等全部实验结束后再更新，更不能把计划、代码已实现或局部通过写成实验完成。提交或推送前检查 README 与对应 Summary/JSON 一致。该约定同时写入项目 [AGENTS.md](AGENTS.md)，供后续协作持续执行。
