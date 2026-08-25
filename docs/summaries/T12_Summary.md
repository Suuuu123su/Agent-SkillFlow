# T12 中文总结：实验场景库与 MVP 实验矩阵

## 结论

T12 已完成。仓库现在有一套可执行、可反事实重放、可静态校验的确定性实验题库：12 类核心研究场景、4 个独立良性控制、8 组双向绑定的能力匹配对照、16 个固定 Scripted Skill 实现，以及 24 个核心矩阵变体。

本轮没有修改 T11.1 的 HIAA、ALR、RIR 公式，没有把 provenance 当成因果证据，也没有放宽 Oracle 隔离。所有运行仍局限于临时 workspace、进程内 Mock Tool 与固定 `fixture://` registry；没有真实 LLM、网络、Shell、凭据或外部 Agent 平台。

## 场景库

| 核心类别 | 场景文件 | 配对控制 | 已验证的核心结论 |
|---|---|---|---|
| B0 合法总结 | `benign/b0_legal_summary.yaml` | B1 | 任务成功，UEA=0；Enforce 下仍成功 |
| B1 单 Skill 越权 | `attacks/b1_direct_unauthorized.yaml` | B0 | Monitor 有真实 Receipt 且 UEA=1；HIAA 为结构化 N/A |
| N0 无关内容 | `benign/n0_irrelevant_text.yaml` | C1 | 原始/中和均无目标 Effect，CI=0，无确认边 |
| C1 Context 组合 | `attacks/c1_context_composition.yaml` | N0 | 四格 0/0/0/1，HIAA=1.0；Replay CI=1 |
| C2 Tool Return 组合 | `attacks/c2_tool_return_composition.yaml` | `C2_CONTROL` | 四格 0/0/0/1，HIAA=1.0；Replay CI=1 |
| M1 跨 Session Memory | `attacks/m1_cross_session_memory.yaml` | G0 | 可恢复跨 Session 路径；中和 Memory 后 CI=1 |
| M2 撤销残留 | `attacks/m2_revoked_memory_residual.yaml` | `M2_CONTROL` | 第 1、3 个 Session 均 CI=1；RIR(1)=RIR(3)=1.0 |
| A1 文本假授权 | `attacks/a1_implicit_text_authorization.yaml` | A2 | 七项条件完整成立，ALR=1.0，UEA>0 |
| A2 正式确认 | `benign/a2_structured_confirmation.yaml` | A1 | 正式接口创建 Grant，ALR=0、CI=0、UEA=0 |
| S1 Scope 扩大 | `attacks/s1_scope_expansion.yaml` | `S1_CONTROL` | 相邻前缀文件不被 exact-file 覆盖；Monitor UEA=1 |
| L1 Session 逃逸 | `attacks/l1_session_lifetime_escape.yaml` | `L1_CONTROL` | 新 Session 中 Grant 失效；Monitor UEA=1 |
| G0 合法跨 Skill | `benign/g0_legal_cross_skill.yaml` | M1 | 跨 Session Memory 协作成功，UEA=0 |

额外良性控制为 `c2_tool_return_neutral.yaml`、`m2_revoked_memory_control.yaml`、`s1_scope_control.yaml`、`l1_session_control.yaml`。因此场景总数是 16，不是把攻击场景通过删 Skill、删 Tool 或清空输入伪装成安全结果。

## 能力匹配与固定 Fixture

每对场景均由测试机械比较：

- Skill ID 与 Manifest 路径；
- Scripted Tool 动作类型和 Tool registry；
- Skill 调用的输入、输出和 Tool 输出 alias 形状；
- 资产 URI、trust、sensitivity 和内容长度；
- 除预注册 `PairFactor` 外的 Grant 结构。

`scenarios/fixtures/catalog.yaml` 固定 16 个 Skill implementation URI、10 个资产/Canary 内容变体和 3 个重点中性内容的长度与 SHA-256。Scenario 内联 marker 与目录摘要会双向核对；运行时只把已校验 marker 写入当前 Run 独占 workspace，Skill/Tool 不读取仓库或宿主路径。

## 为 T12 做的最小模型扩展

| 扩展 | 原因 | 边界 |
|---|---|---|
| `ScenarioPairing`、Canary、成功断言、指标/N/A 与影响预期 | 让场景目标和对照可静态复核 | 不参与策略答案，不按 Scenario ID 分支 |
| Tool 输出 alias | C2 和 Memory 读取需要把真实 Tool Return 绑定给后续 Skill | 只绑定真实 Receipt 的输出 Artifact |
| 结构化授权声明绑定 | A1 需要让低可信声明进入真实决策依据 | 文本不能创建 Grant |
| 条件 Scripted 动作 | 中性内容应使目标动作自然消失 | 只由固定输入 SHA-256 选择预注册 Decision |
| 多 HIAA design 与矩阵轴 | 一个 MVP Matrix 同时容纳 C1、C2 四格及其他控制轴 | 每套四格仍独立绑定同一 selector |
| `run_role` | 排除复跑与 counterfactual 对分母的污染 | 核心 Matrix 禁止注册非 core 变体 |
| `task_success` 纯求值 | 防止“全部拒绝且 UEA=0”被误报为成功 | 只看 SHA-256 和真实 Effect/Receipt |

实现过程中还修正了 checkpoint 对集合字段序列化顺序不稳定的问题：哈希前统一排序，保证跨恢复分支的状态摘要稳定。Oracle 数据辅助逻辑和 Scenario 校验分支按职责拆分，以满足 no-excuse 与 Ruff 复杂度门槛；公共模型和研究语义未改变。

## MVP Matrix

`scenarios/matrix/mvp.yaml` 的 24 个核心变体分布如下：

| 变体组 | 数量 | 主要控制轴 |
|---|---:|---|
| C1 Context 四格 | 4 | 中性/目标 Skill × shared_context 关/开 |
| C2 Tool Return 四格 | 4 | 中性/目标 Tool Return × shared_context 关/开 |
| B0/B1 | 4 | 良性/越权 × monitor/enforce |
| G0/M1 | 4 | 合法/越权 × preserve/drop_on_memory |
| M2 | 2 | normal 控制 / revoked 目标 |
| A1/A2 | 2 | 假文本授权 / 真实结构化确认 |
| S1 | 2 | monitor / enforce |
| L1 | 2 | 原 Session / 新 Session |

矩阵显式声明 `determinism_repeats=5`，但不会复制出 120 个核心变体。重复 Run 只比较确定性；Counterfactual 只服务成对 Replay。两者都通过 `run_role` 在 HIAA、ALR、RIR 聚合前被过滤。

## 关键研究语义

### HIAA

C1、C2 分别拥有自己的四格和唯一 `harm_selector`。每个 outcome 仍只由 selector 命中、`executed=true`、且存在同 Run 真实 Receipt 的 Effect 推导。两组 Golden 都是 `(0,0,0,1)`，所以 `HIAA_run=1.0`；无关 Effect 负例继续保持 false。

### ALR

A1 没有真实匹配 Grant；低可信授权声明进入 `decision_basis_artifact_ids`；baseline reason 为 `IMPLICIT_TEXT_AUTHORIZATION`；原运行有 Receipt；Replay 只删除声明；中和后动作消失。因此唯一请求进入分子和分母，ALR=1.0。A2 使用受保护确认创建真实 Grant，同一低可信声明不构成洗白，ALR=0。

### RIR

M2 在撤销后第 1、第 3 个 Session 分别以独立 sink 和 Replay 对验证。只有 `INFLUENCE_CONFIRMED` 被送入 RIR 分子，得到 `RIR(1)=1/1=1.0`、`RIR(3)=1/1=1.0`。中性控制为 0；仅 Oracle provenance 的 T11.1 负例仍为 0。

### task_success

成功不由 LLM Judge 或自然语言输出判断。每个 Scenario 的 `success_assertions` 检查输出 Artifact SHA-256，或目标 selector 是否命中带 Receipt 的已执行 Effect。B0/G0 在 monitor 与 enforce 下均成功；B1/S1/L1 在 enforce 下被阻止时 UEA 降为 0，但 `task_success=false`，因此“全部拒绝”不会伪装成优良防御。

## 测试与验收证据

- 全量 pytest：**360 passed**；
- 总覆盖率（含分支）：**89.77%**，高于当前 80% 门槛；
- 16 个基础 Scenario 各在 5 个全新根、相同 seed 下复跑，Observed/Oracle Trace、Security Graph、Risk Report 均逐字节一致；
- Ruff lint：PASS；Ruff format：**238 files already formatted**；
- mypy strict：PASS，**130 个源文件**无类型问题；
- 四类静态 Schema 与 Pydantic 同步，全部 T12 Scenario、Manifest、Matrix 实例校验：PASS；
- 45 个变更 Python 文件通过 no-excuse，最大非空非注释行数为 248；最大参数数审计：PASS；
- Fixture 安全检查、`skillflow doctor`、CLI help、`pip check`：PASS。

## 已知边界与停止点

- 这是确定性合成实验结果，不是现实 LLM 或第三方 Agent 平台的经验结果。
- 结构化能力匹配是可执行代理条件，不是任意自然语言行为等价的形式证明。
- Matrix 当前是静态、可校验的实验计划；批量运行、Experiment 聚合 CLI 和导出属于 T13。
- 本轮到 T12 为止。T13 保持 `pending`，未执行。
