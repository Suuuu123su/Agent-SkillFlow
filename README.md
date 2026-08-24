# Agent-SkillFlow

SkillFlow 是一个面向 Agent Skill 安全研究的确定性测量原型，用于追踪 Skill 的影响如何经过共享上下文、持久记忆、其他 Skill 与工具传播，并区分数据来源、决策影响和真实授权。

当前仓库已完成到 **T06：双轨 Trace 与独立 Oracle**。这里已经固定研究边界、四级 Lifetime 语义和类型化数据契约，具备可重启的 SQLite/BlobStore 事件底座，并能从受控 YAML Scenario 驱动确定性 Scripted Skill 到 Mock Tool Receipt，同时为每次 Run 输出可按 Artifact/Effect ID 对齐的 Observed 与 Oracle JSONL。尚未实现 T07 来源图、T08 正式策略、风险指标、Checkpoint 或真实平台 Adapter。

## 当前能力

- 可安装的 Python `src` 布局包。
- `skillflow version`：输出当前版本。
- `skillflow doctor`：离线检查 Python、SQLite、运行依赖和临时目录可写性。
- `skillflow validate-manifest PATH`：只校验 Skill Manifest，不加载或执行 Skill。
- `skillflow validate-scenario PATH`：只校验 Scenario，不运行 fixture。
- Pydantic v2 核心安全模型、受控 Resource URI 和 `call | task | session | persistent` 菱形 Lifetime。
- `skill-manifest`、`scenario`、`experiment-matrix`、`risk-report` 四类模型生成静态 JSON Schema。
- SQLite EventStore：事件及输入输出边追加写入，数据库触发器拒绝历史 UPDATE/DELETE。
- Event、输入输出边、Decision 与 Effect 以一个 Envelope 原子提交；失败时不留下半条事件。
- 按 Run 隔离的受控 BlobStore：引用不暴露路径，读回时校验内容 hash 与长度。
- Persistent Memory 头可跨 Session 和进程重启恢复；历史事件仍保持不可变。
- Trace 默认只投影 hash 与结构化元数据，同一持久事件序列在重开数据库后得到相同哈希。
- 可注入虚拟时钟与确定性 ID 工厂，用于后续可重放实验。
- 最小 `HarnessAdapter` 只包含 `start_session`、`load_skill`、`invoke_skill`、`end_session`；没有提前伪实现 T10 的 checkpoint/restore。
- `MockHarnessAdapter` 与白名单 `ScriptedBackend` 不调用真实 LLM，也不动态导入 Scenario 指定的 Python 实现。
- Context、Persistent Memory、隔离 Workspace 文件和 Skill 六段生命周期都生成不可变 Artifact 或追加 Event。
- 普通 Tool 白名单固定为 `read_file`、`write_memory`、`read_memory`、`http_send`、`shell_exec`；用户确认和 Skill 撤销不在普通 Tool 面中。
- Tool 调用严格记录请求、规范化 Effect、参数 Artifact、Stub allow/deny、Mock 执行和强类型 Receipt；拒绝请求不产生 Effect 或 Receipt。
- HTTP 与 Shell 只有进程内结构化 Mock 记录，不建立网络连接、不创建子进程；文件只能访问每次运行独占的 Workspace 根。
- 同一 YAML、虚拟时间与 seed 的 Trace hash 一致；两个 Run 的 Context、Memory、Receipt 与 Workspace 状态互不累积。
- 每次 Scenario Run 同时创建 `observed-trace.jsonl` 与 `oracle-trace.jsonl`；默认只含结构化 ID、来源、关系、能力和 Receipt 引用，不含 Blob、Tool 参数明文或 fixture marker。
- Observed Writer 只投影 Harness 实际标签；Oracle sidecar 只接收 Scenario、受控 Manifest、Scripted action、Tool attempt 和 Receipt 的单向证据投影，不读取 Observed 标签或策略结果。
- 每个值和实际 Effect 使用稳定 Artifact/Effect ID，并记录 `COPY | DERIVE | WRITE | LOAD | INVOKE` 封闭父关系；被拒绝的 Tool attempt 仍保留可对齐的 argument 值，但不会伪造 Receipt 或 `GT_effect`。
- `OracleGrantResolver` 以 Manifest + 真实 Grant 双钥匙独立计算 `GT_auth`，支持四值菱形 Lifetime、时间窗和撤销 ID；Stub/Policy 结果不能改写真值。
- `drop_on_derive`、`drop_on_memory` 只破坏 Observed origins；相同真实步骤下 Oracle JSONL 保持不变，可用于后续来源 Recall 评价。
- Agent、Skill、Tool、Policy/Observed 运行模块没有 Oracle 反向导入；只有 Benchmark 的单向 bridge 同时接触两侧的中立合同。
- pytest、覆盖率、ruff 与 mypy 质量门禁。
- GitHub Actions 自动执行同一组质量门禁。
- 中文威胁模型、安全语义、形式化不变量和架构决策记录。
- 中文任务进度、仓库基线与逐任务总结。

## 环境要求

- Python 3.11 或更高版本。
- 测试和 CLI 不访问外网，不需要 API Key 或用户账号。

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
.\.venv-skillflow\Scripts\python.exe -m pytest tests\e2e\test_t06_dual_trace.py -q --no-cov
```

安装后也可以直接使用控制台命令：

```powershell
.\.venv-skillflow\Scripts\skillflow.exe --help
```

## 质量检查

```powershell
.\.venv-skillflow\Scripts\python.exe -m pytest -q
.\.venv-skillflow\Scripts\python.exe -m ruff check .
.\.venv-skillflow\Scripts\python.exe -m mypy src\skillflow
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli --help
```

当前 pytest 门禁仍按任务书使用 80% 最低阈值；T06 的最终测试项数与分支覆盖率记录在 [`docs/summaries/T06_Summary.md`](docs/summaries/T06_Summary.md)。T14 将把最终门槛正式提升到 90%。

## 项目范围

首版只面向单 Agent、2～3 个 Skill、共享 Context、Persistent Memory、多 Session 与安全 Mock Tool 的确定性实验。明确不包含真实网络外发、真实 Shell 子进程、真实凭据、生产级 UI、多 Agent 协作或通用平台适配。

完整任务依赖和验收标准见 [`SkillFlow_Codex_Task_Spec.md`](SkillFlow_Codex_Task_Spec.md)。冻结的研究边界见 [`docs/threat-model.md`](docs/threat-model.md)，安全语义见 [`docs/security-semantics.md`](docs/security-semantics.md)，架构决策见 [`docs/decisions/`](docs/decisions/)。当前进度见 [`docs/progress.md`](docs/progress.md)，逐任务总结见 [`docs/summaries/`](docs/summaries/)。
