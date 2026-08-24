# SkillFlow 仓库基线

## 记录范围

本文档是 SkillFlow 的 T00 仓库基线，目标项目根目录为：

```text
E:\Skill ＆ Harness\Agent
```

记录日期为 2026-08-24（Asia/Shanghai）。它如实描述功能实现前的现状，不是项目骨架、实现方案或后续任务的替代品。

## 仓库盘点

| 项目 | 观察结果 |
|---|---|
| 项目分类 | 绿地项目（greenfield） |
| T00 输出前的文件数 | 1 |
| 已有项目文件 | `SkillFlow_Codex_Task_Spec.md` |
| 任务书 | 1,619 行；SHA-256：`66F595BE1373645B50219A7A3F13C74B9EEA354537A44BC2B33314E78727C2A8` |
| 源代码 | 无 |
| 测试 | 无 |
| 包/构建配置 | 无；未发现 `pyproject.toml`、setup 文件、requirements 文件或等价配置 |
| 入口点/CLI | 无 |
| README/设计文档 | 无 README 或独立设计文档；任务书是唯一设计参考 |
| 项目内 `AGENTS.md` | 无 |
| 原有 `docs/` 目录 | 无；由本次 T00 按任务书要求创建 |
| 既有 SkillFlow 实现 | 无 |

因此，该目录未触发 T00 中“存在同名但语义不同的既有实现”这一停手条件。

## Git 基线

目标目录及其父级链均不是 Git 工作树。这里不能写为“工作区干净”，因为不存在 Git 索引可用于区分已跟踪或未跟踪改动。

| 命令 | 结果 | 退出结果 |
|---|---|---|
| `git -C "E:\Skill ＆ Harness\Agent" status --short` | `fatal: not a git repository (or any of the parent directories): .git` | 128 |
| `git -C "E:\Skill ＆ Harness\Agent" rev-parse --show-toplevel` | 同样返回非 Git 仓库错误 | 128 |

T00 未执行任何会改变 Git 历史、索引、分支或工作文件的操作。

## 文件发现基线

任务书要求使用 `rg --files` 盘点文件。该命令已尝试执行，但本机解析到的可执行文件无法启动：

| 命令 | 结果 | 退出结果 |
|---|---|---|
| `rg --files "E:\Skill ＆ Harness\Agent"` | Windows 拒绝访问 `C:\Program Files\WindowsApps\OpenAI.Codex_...\resources\rg.exe`，进程未能启动。 | 不适用：进程未启动 |
| PowerShell 递归文件盘点 | 成功完成；在 T00 输出前仅发现 `SkillFlow_Codex_Task_Spec.md`。 | 0 |

PowerShell 盘点只是 `rg` 失败时的替代性目录清单，不掩盖 `rg` 启动失败这一事实。

## 环境与质量检查基线

| 检查 | 结果 | 退出结果 |
|---|---|---|
| `python --version` | Python 3.12.13 | 0 |
| `py -3 --version` | `PATH` 中没有 Python Launcher。 | 不适用：PowerShell 无法解析该命令 |
| `python -m pytest --version` | `No module named pytest` | 1 |
| `python -m ruff --version` | `No module named ruff` | 1 |
| `python -m mypy --version` | `No module named mypy` | 1 |

项目中没有源码、测试文件或工具配置，也就没有可运行的项目级 `pytest`、lint 或类型检查命令。因此 T00 没有伪造这些检查；它们的基线状态为“不适用”，不是“通过”。

## 项目规则与可复用材料

- 选定根目录中没有项目内 `AGENTS.md`。
- 没有 README、包清单、构建配置、源代码、测试、CLI 入口点或可复用实现。
- 唯一的项目参考是 `SkillFlow_Codex_Task_Spec.md`；T00 按其确定了任务边界、输出文件、验收条件和停手条件。
- 从本次记录起，自然语言说明统一使用中文；命令、路径、文件名、代码标识符和任务状态枚举保留原样。

## T00 决策日志

1. 在用户明确确认后，直接使用 `E:\Skill ＆ Harness\Agent` 作为项目根目录。
2. 只创建任务书规定的 T00 输出：`docs/progress.md` 与 `docs/repository-baseline.md`。
3. 保持 `SkillFlow_Codex_Task_Spec.md` 不变。
4. 不创建 `src/`、`tests/`、`pyproject.toml`、`.gitignore`、配置文件或任何其他 T01 产物。
5. 将依赖安装、Git 初始化和所有功能性工作推迟到用户明确要求的后续任务。

## 尚存基线问题

1. 本机 `rg.exe` 启动被拒绝；后续若需要仓库级搜索，应先修复该环境问题，或明确记录替代工具。
2. Python 版本满足最低要求，但 T01 指定的质量工具尚未安装。
3. 项目尚未初始化 Git；若后续要采用版本控制，需由用户明确决定是否以及何时初始化。
