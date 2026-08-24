# SkillFlow 进度记录

## 语言约定

从 T00 起，项目文档、任务总结、决策记录与后续交付默认使用中文。为保持与任务书、命令行和数据模型的一致性，命令、路径、文件名、代码标识符及状态枚举保留原样；任务状态仍只使用 `pending`、`in_progress`、`blocked`、`completed`。

## 任务状态

| 任务 | 状态 | 验证 | 说明 |
|---|---|---|---|
| T00 | completed | 见 `docs/repository-baseline.md` | 已完成仓库基线记录，未创建功能实现。 |
| T01 | completed | 6 tests；覆盖率 92%；ruff/mypy/CLI PASS | 已建立可安装包、CLI、本地门禁与 GitHub CI。 |
| T02 | pending | 不适用 | 依赖 T01。 |
| T03 | pending | 不适用 | 依赖 T02。 |
| T04 | pending | 不适用 | 依赖 T03。 |
| T05 | pending | 不适用 | 依赖 T04。 |
| T06 | pending | 不适用 | 依赖 T05。 |
| T07 | pending | 不适用 | 依赖 T06。 |
| T08 | pending | 不适用 | 依赖 T07。 |
| T09 | pending | 不适用 | 依赖 T08。 |
| T10 | pending | 不适用 | 依赖 T07。 |
| T11 | pending | 不适用 | 依赖 T09 和 T10。 |
| T12 | pending | 不适用 | 依赖 T11。 |
| T13 | pending | 不适用 | 依赖 T12。 |
| T14 | pending | 不适用 | 依赖 T13。 |
| T15 | pending | 不适用 | 依赖 T14，且必须获得用户明确批准。 |

## T00：仓库勘察与执行基线

- 状态：completed
- 日期：2026-08-24（Asia/Shanghai）
- 项目根目录：`E:\Skill ＆ Harness\Agent`
- 任务边界：只检查并记录现有状态；未进行功能实现、项目骨架搭建、Git 初始化、依赖安装或测试创建。

### T00 中文总结

1. `E:\Skill ＆ Harness\Agent` 已确认直接作为 SkillFlow 项目根目录。任务书位于该目录，且用户已明确确认这一目录选择。
2. 项目当前是绿地项目（greenfield）：勘察时目录中只有 `SkillFlow_Codex_Task_Spec.md`，不存在源码、测试、README、构建配置、项目内 `AGENTS.md`、命令行入口或 Git 元数据。
3. 未发现任何同名但语义不同的 SkillFlow 既有实现，因此未触发 T00 的停手条件。
4. Git 命令返回“非 Git 仓库”；这只能记为 Git 不适用，不能误写为工作区干净。
5. 当前 Python 为 3.12.13，但 `pytest`、`ruff`、`mypy` 均未安装；由于没有项目代码或质量门禁配置，项目级测试、静态检查和类型检查均为“不适用”，不是“通过”。
6. `rg --files` 受本机 `rg.exe` 启动权限限制而无法执行；已用 PowerShell 递归盘点替代，并在基线中保留了该失败事实。

### T00 创建的文件

- `docs/progress.md`：任务状态、语言约定与决策日志。
- `docs/repository-baseline.md`：仓库、命令和环境基线。

### 关键决策

1. 直接使用 `E:\Skill ＆ Harness\Agent` 作为项目根目录。
2. 将项目状态记录为绿地项目，而不是误报为已有项目或 Git 干净工作区。
3. 不在 T00 初始化 Git，也不为了制造“通过的基线”而执行不存在的项目检查。
4. 不创建 `src/`、`tests/`、`pyproject.toml`、`.gitignore` 或任何 T01 产物。
5. 后续自然语言文档默认使用中文；仅保留技术标识符、命令和状态枚举的原始写法。

### 验证摘要

- `git -C "E:\Skill ＆ Harness\Agent" status --short` → 退出码 128：不是 Git 仓库。
- `rg --files "E:\Skill ＆ Harness\Agent"` → 无法启动：Windows 拒绝访问本机解析到的 `rg.exe`；PowerShell 递归盘点成功，勘察时仅发现任务书。
- `python --version` → 退出码 0：Python 3.12.13。
- `python -m pytest --version` → 退出码 1：模块未安装。
- `python -m ruff --version` → 退出码 1：模块未安装。
- `python -m mypy --version` → 退出码 1：模块未安装。

### 已知问题与后续约束

- 当前 Python 版本满足任务书的最低版本要求，但质量门禁工具尚未安装。
- 如果你后续明确要求执行 T01，T01 才应建立受控 Python 工具链与项目骨架。
- T00 未修改任何既有业务代码或用户文件；原项目根中本就不存在这些文件。

## T01：项目骨架与质量门禁

- 状态：completed
- 日期：2026-08-24（Asia/Shanghai）
- 任务边界：只建立可安装包、CLI、环境检查、测试与质量门禁；未实现任何来源追踪、授权、策略、图、指标、场景执行或真实 Harness Adapter。

### 修改文件

- `pyproject.toml`：声明 Python 3.11+、运行/开发依赖、包构建、pytest 覆盖率、ruff 和 mypy 配置。
- `.gitignore`：忽略虚拟环境、缓存、构建物、SQLite 临时文件和 `runs/`。
- `.gitattributes`：统一 Markdown、Python、TOML 与 YAML 的 LF 换行规则。
- `README.md`：增加中文项目说明、安装、CLI、质量检查和 MVP 边界。
- `.github/workflows/ci.yml`：在 Python 3.11 上运行测试、覆盖率、ruff、mypy 和 CLI help。
- `src/skillflow/__init__.py`：定义包版本 `0.1.0`。
- `src/skillflow/cli.py`：实现 Typer 根命令、`version` 与离线 `doctor`。
- `tests/unit/test_doctor.py`：覆盖正常环境和临时目录拒绝写入。
- `tests/integration/test_cli.py`：覆盖 version、doctor 成功和失败退出码。
- `tests/e2e/test_cli_module.py`：通过真实 Python 子进程验证模块帮助入口。
- `configs/.gitkeep`、`schemas/.gitkeep`、`scenarios/.gitkeep`：保留 T01 要求的基础目录。
- `docs/summaries/T01_Summary.md`：T01 中文总结。

### 关键决定

1. 保留现有 `E:\pytorch_cuda_env` 不变。它是 Python 3.10.20，低于任务书规定的 3.11 下限，且承担既有 PyTorch/CUDA 用途。
2. 使用本机可用的 Python 3.12.13 创建项目专用 `.venv-skillflow`，依赖只安装在该环境中。
3. LibreOffice Python 首次创建 `.venv` 时因权限失败并留下不完整目录。遵守“不删除任何内容”的规则，没有清空该目录；改用新的 `.venv-skillflow`。
4. `doctor` 完全离线，只检查 Python、SQLite、运行依赖和指定临时目录的真实写入能力。
5. 质量门禁采用任务书指定的 pytest、pytest-cov、ruff 与 mypy；T01 覆盖率门槛为 80%。
6. GitHub CI 只有只读仓库权限，不执行发布、部署、网络外发测试或凭据操作。

### TDD 记录

- 红灯：先创建测试和 CLI 未实现接口；首次运行得到 5 个 `NotImplementedError` 失败、1 个帮助入口通过，证明失败来自待实现行为。
- 绿灯：补齐最小实现后，6 个测试全部通过。
- 重构与复核：修正中文 lint 规则、测试包标记和代码格式；无借助场景 ID 或硬编码测试结果。

### 验证结果

- `.venv-skillflow\Scripts\python.exe -m pytest -q` → PASS，6 passed，分支覆盖率 92.06%。
- `.venv-skillflow\Scripts\python.exe -m ruff check .` → PASS。
- `.venv-skillflow\Scripts\python.exe -m ruff format --check .` → PASS，14 files already formatted。
- `.venv-skillflow\Scripts\python.exe -m mypy src\skillflow` → PASS，2 个源文件无类型问题。
- `.venv-skillflow\Scripts\python.exe -m skillflow.cli --help` → PASS，退出码 0。
- `.venv-skillflow\Scripts\python.exe -m skillflow.cli version` → PASS，输出 `SkillFlow 0.1.0`。
- `.venv-skillflow\Scripts\python.exe -m skillflow.cli doctor` → PASS，四项检查全部通过。
- `.venv-skillflow\Scripts\skillflow.exe --help` → PASS，退出码 0。
- `.venv-skillflow\Scripts\python.exe -m pip check` → PASS，无损坏依赖。
- Python 规则审计脚本 → PASS，9 个 Python 文件无违规；最大源文件为 `cli.py`，103 行有效代码，低于 250 行上限。

### 验收条件

- [x] 包可导入并可编辑安装。
- [x] CLI help、version、doctor 均返回 0。
- [x] doctor 对临时目录拒绝写入返回清楚错误和退出码 1。
- [x] pytest、覆盖率、ruff、mypy 和格式检查通过。
- [x] README 写明安装、测试和 MVP 范围。
- [x] 未创建 Web UI、真实 LLM SDK 或平台 Adapter。

### 遗留问题

- 不完整的 `.venv` 由首次失败的 LibreOffice Python 尝试产生，当前被 Git 忽略且未删除；实际使用 `.venv-skillflow`。
- GitHub Actions 需要在推送后由远端运行；本地已验证工作流 YAML 可解析，但远端运行结果不在本地测试结论内。
- 下一项可执行任务是 T02，尚未启动。
