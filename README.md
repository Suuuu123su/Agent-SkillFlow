# Agent-SkillFlow

SkillFlow 是一个面向 Agent Skill 安全研究的确定性测量原型，用于追踪 Skill 的影响如何经过共享上下文、持久记忆、其他 Skill 与工具传播，并区分数据来源、决策影响和真实授权。

当前仓库只完成到 **T01：项目骨架与质量门禁**。这里还没有实现来源图、授权策略、风险指标、场景执行器或真实 Harness Adapter。

## 当前能力

- 可安装的 Python `src` 布局包。
- `skillflow version`：输出当前版本。
- `skillflow doctor`：离线检查 Python、SQLite、运行依赖和临时目录可写性。
- pytest、覆盖率、ruff 与 mypy 质量门禁。
- GitHub Actions 自动执行同一组质量门禁。
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

T01 的覆盖率门槛为 80%。后续 T14 才会按任务书将最终门槛提升到 90%。

## 项目范围

首版只面向单 Agent、2～3 个 Skill、共享 Context、Persistent Memory、多 Session 与安全 Mock Tool 的确定性实验。明确不包含真实网络外发、真实 Shell 子进程、真实凭据、生产级 UI、多 Agent 协作或通用平台适配。

完整研究语义、任务依赖和验收标准见 [`SkillFlow_Codex_Task_Spec.md`](SkillFlow_Codex_Task_Spec.md)。当前进度见 [`docs/progress.md`](docs/progress.md)，逐任务总结见 [`docs/summaries/`](docs/summaries/)。
