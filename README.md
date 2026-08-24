# Agent-SkillFlow

SkillFlow 是一个面向 Agent Skill 安全研究的确定性测量原型，用于追踪 Skill 的影响如何经过共享上下文、持久记忆、其他 Skill 与工具传播，并区分数据来源、决策影响和真实授权。

当前仓库已完成到 **T04：Append-only EventStore 与持久状态**。这里已经固定研究边界、四级 Lifetime 语义和类型化数据契约，并具备可重启的 SQLite 事件底座、按 Run 隔离的 BlobStore 与脱敏稳定 Trace；尚未实现 T05 Harness、来源图计算、运行期授权策略、风险指标或场景执行器。

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

当前 pytest 门禁仍按任务书使用 80% 最低阈值；T04 全量分支覆盖率实测为 90.60%。T14 将把最终门槛正式提升到 90%。

## 项目范围

首版只面向单 Agent、2～3 个 Skill、共享 Context、Persistent Memory、多 Session 与安全 Mock Tool 的确定性实验。明确不包含真实网络外发、真实 Shell 子进程、真实凭据、生产级 UI、多 Agent 协作或通用平台适配。

完整任务依赖和验收标准见 [`SkillFlow_Codex_Task_Spec.md`](SkillFlow_Codex_Task_Spec.md)。冻结的研究边界见 [`docs/threat-model.md`](docs/threat-model.md)，安全语义见 [`docs/security-semantics.md`](docs/security-semantics.md)，架构决策见 [`docs/decisions/`](docs/decisions/)。当前进度见 [`docs/progress.md`](docs/progress.md)，逐任务总结见 [`docs/summaries/`](docs/summaries/)。
