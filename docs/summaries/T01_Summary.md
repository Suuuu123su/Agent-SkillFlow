# T01 总结：项目骨架与质量门禁

## 任务结论

T01 已完成。SkillFlow 现在具备可安装的 Python 包、Typer CLI、离线环境自检、本地质量门禁和 GitHub Actions CI；没有提前实现 T02 及之后的安全语义或实验功能。

## 核心产物

| 产物 | 作用 |
|---|---|
| `pyproject.toml` | 声明 Python 3.11+、依赖、构建、测试、覆盖率、ruff 与 mypy |
| `src/skillflow/` | 最小可导入包、版本与 CLI |
| `tests/unit/` | doctor 环境检查单元测试 |
| `tests/integration/` | CLI 成功/失败行为测试 |
| `tests/e2e/` | 真实 Python 子进程帮助入口测试 |
| `.github/workflows/ci.yml` | GitHub Python 3.11 自动质量检查 |
| `README.md` | 中文项目介绍、安装、使用、测试和范围说明 |

## CLI

```powershell
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli --help
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli version
.\.venv-skillflow\Scripts\python.exe -m skillflow.cli doctor
```

`doctor` 不访问网络，只检查：

1. Python 是否达到 3.11；
2. SQLite 版本；
3. Typer、Pydantic、NetworkX、PyYAML 和 jsonschema 是否安装；
4. 临时目录是否能实际创建并写入探测文件。

## 环境决定

现有 `E:\pytorch_cuda_env` 使用 Python 3.10.20，不满足项目版本要求，因此保持原样。SkillFlow 使用 Python 3.12.13 创建的 `.venv-skillflow`，避免破坏既有 PyTorch/CUDA 环境。

默认 LibreOffice Python 创建 `.venv` 时权限失败并留下不完整目录。由于项目规则禁止未经允许删除内容，该目录保留且被 Git 忽略；它不是 SkillFlow 的运行环境。

## 验证证据

| 检查 | 结果 |
|---|---|
| pytest | 6 passed |
| 分支覆盖率 | 92.06%，高于 T01 的 80% 门槛 |
| ruff check | PASS |
| ruff format --check | PASS |
| mypy | PASS |
| 模块 CLI help/version/doctor | 全部退出码 0 |
| 安装后的 `skillflow.exe --help` | 退出码 0 |
| `pip check` | 无损坏依赖 |
| Python 规则审计 | 9 个文件无违规 |

## 未实现内容

T01 没有实现以下功能：

- Principal、Artifact、Grant、Event 等安全数据模型；
- EventStore、Mock Harness、Observed/Oracle 双轨 Trace；
- 来源图、授权策略、UEA/HIAA/ALR/RIR/CI 指标；
- 场景 DSL、真实网络、真实 Shell、真实 LLM 或真实 Harness Adapter。

这些内容分别属于 T02 及之后的任务，不能被当前 CLI 骨架误报为已经完成。

## 下一任务

下一项可执行任务是 T02：威胁模型与安全语义冻结。当前未启动。
