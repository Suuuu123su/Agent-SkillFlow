# SkillFlow 进度记录

## 语言约定

从 T00 起，项目文档、任务总结、决策记录与后续交付默认使用中文。为保持与任务书、命令行和数据模型的一致性，命令、路径、文件名、代码标识符及状态枚举保留原样；任务状态仍只使用 `pending`、`in_progress`、`blocked`、`completed`。

## 任务状态

| 任务 | 状态 | 验证 | 说明 |
|---|---|---|---|
| T00 | completed | 见 `docs/repository-baseline.md` | 已完成仓库基线记录，未创建功能实现。 |
| T01 | completed | 6 tests；覆盖率 92%；ruff/mypy/CLI PASS | 已建立可安装包、CLI、本地门禁与 GitHub CI。 |
| T02 | completed | 文档审计 PASS；6 tests；ruff/mypy/doctor PASS | 已冻结威胁模型、安全语义与 3 份 ADR。 |
| T03 | completed | 65 tests；覆盖率 90.18%；ruff/mypy/Schema/CLI PASS | 已完成核心模型、四类 Schema 和只读校验 CLI。 |
| T04 | completed | 93 tests；覆盖率 90.60%；ruff/mypy/重启测试 PASS | 已完成追加式 SQLite EventStore、BlobStore、稳定 Trace 与持久恢复。 |
| T05 | completed | 141 tests；覆盖率 89.19%；ruff/mypy/YAML E2E PASS | 已完成安全 Mock Harness、插桩代理、ScriptedBackend 与 Tool Receipt 链。 |
| T06 | completed | 165 tests；覆盖率 88.48%；ruff/mypy/隔离 E2E PASS | 已完成双轨 JSONL、机械 Oracle、独立 GT_auth/GT_effect 与依赖隔离。 |
| T07 | completed | 182 tests；覆盖率 87.93%；ruff/mypy/Golden E2E PASS | 已完成 EventStore 重建的双层来源图、七类查询、边界深度与脱敏 JSON 导出。 |
| T08 | completed | 236 tests；覆盖率 89.18%；ruff/mypy/策略 E2E PASS | 已完成双钥匙 matcher、PolicyEngine、Grant/撤销事实、monitor/enforce 与特权确认。 |
| T09 | completed | 254 tests；覆盖率 89.28%；ruff/mypy/Golden E2E PASS | 已完成结构化 UEA、来源指标、micro 聚合、证据路径与风险报告。 |
| T10 | completed | 275 tests；覆盖率 89.39%；ruff/mypy/Replay Golden E2E PASS | 已完成完整 Checkpoint、隔离恢复、结构保持中和、成对 Receipt 差异、CI 与确认影响边。 |
| T11 | completed | 303 tests；覆盖率 88.76%；ruff/mypy/Schema/Golden PASS | 已完成四格矩阵、HIAA、ALR、RIR 与 Experiment 风险报告。 |
| T11.1 | completed | 310 tests；覆盖率 88.98%；ruff/mypy/Schema/语义负例 PASS | 已收紧 RIR、ALR、HIAA 三项研究语义。 |
| T12 | pending | 不适用 | 依赖 T11.1。 |
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
3. LibreOffice Python 首次创建 `.venv` 时因权限失败并留下不完整目录。T01 完成时遵守“不删除任何内容”的规则，没有清空该目录；改用新的 `.venv-skillflow`。T02 开始前，该不完整目录已由用户手动删除。
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

- 不完整的 `.venv` 由首次失败的 LibreOffice Python 尝试产生；T02 开始前已由用户手动删除。实际环境始终是 `.venv-skillflow`。
- GitHub Actions 需要在推送后由远端运行；本地已验证工作流 YAML 可解析，但远端运行结果不在本地测试结论内。
- T01 完成时的下一项任务是 T02；T02 已在后续轮次完成，记录见下节。

## T02：威胁模型与安全语义冻结

- 状态：completed
- 日期：2026-08-24（Asia/Shanghai）
- 任务边界：只冻结研究语义和架构决定；未实现 T03 数据模型、Schema、验证 CLI 或任何后续运行逻辑。

### 修改文件

- `docs/threat-model.md`：可信主体、攻击者、资产、敏感 Sink、信任边界、范围内/外攻击、成功判据、研究问题—指标映射及手工路径。
- `docs/security-semantics.md`：三种 provenance、Manifest/Grant 双钥匙、Decision 四事实、跨 task/session、revoke/unload、Observed/Oracle 和形式化不变量。
- `docs/decisions/0001-use-artifact-event-graph.md`：选择 Artifact–Event 二部图。
- `docs/decisions/0002-separate-observed-and-oracle.md`：隔离 Observed 与 Oracle。
- `docs/decisions/0003-use-mock-harness-first.md`：T14 前只使用确定性 Mock Harness。
- `docs/decisions/README.md`：ADR 索引和变更规则。
- `docs/summaries/T02_Summary.md`：T02 中文总结。
- `README.md`：把当前阶段和文档入口更新为 T02。
- `docs/summaries/T01_Summary.md`：记录不完整 `.venv` 已由用户在 T02 前手动删除。
- `docs/progress.md`：更新任务状态、验证证据和本节记录。

### 关键设计决定

1. 每个 Skill 是独立 `Principal`；Harness 只是连接 Skill、数据面和 Tool 的桥接层，不提供默认 authority。
2. 数据来源、决策影响和授权来源分别由血缘图、反事实 Replay 和真实 Grant 证明，不能合并。
3. Manifest 与 Grant 是双钥匙；普通文本、高 trust 数据、自动批准和 monitor 执行都不能替代 Grant。
4. 同一 task 的跨 Session Memory 读取创建新 Artifact、连接旧父节点并保留 origins；授权按 `call | task | session | persistent` 的对应边界匹配，数据传播本身不传播 authority。
5. revoke/unload/delete 均追加事件，不删除历史；撤销后的新派生物携带 `revoked_origins`。
6. EventStore 是唯一事实源，Artifact–Event 图是可重建只读视图。
7. Observed 是被评估对象，Oracle 是不可被运行组件读取的独立真值。
8. T01～T14 只使用确定性 Mock Harness；真实 Harness 仍由 T15 单独门控。

### 形式化不变量

文档冻结了 9 条不变量：

- 普通内容不能签发 Grant；
- Manifest 不能替代 Grant；
- 跨 Session Memory 必须保留来源；
- 撤销不删除历史；
- Skill 主体必须隔离；
- 时序只能建立候选影响；
- monitor 不改变授权真值；
- 运行组件不能读取 Oracle；
- Grant 只按声明的 lifetime 边界匹配，`task` 与 `session` 互不包含。

### 手工语义路径

- G0：具有完整 Manifest 和 Grant 的跨 Skill 良性协作。
- A1：普通文本“用户已批准”导致的授权洗白。
- M1：Skill→Memory→新 Session→其他 Skill→Tool 的未授权传播。
- M2：Skill revoke/unload 后，历史 Memory 继续触发未授权 Effect。

这些路径是后续任务的 Golden 预期，不是已经运行出的实验结果。

### 验证结果

- T02 文档审计 → PASS：6 个必需文档存在且为严格 UTF-8。
- 研究问题—指标映射 → PASS：RQ1～RQ5 覆盖 Provenance、CI、UEA、ALR、HIAA 和 RIR。
- 手工路径审计 → PASS：1 条良性路径、3 条攻击路径。
- 形式化不变量审计 → PASS：9 条。
- 本地 Markdown 链接检查 → PASS。
- `git diff --check` → PASS。
- `.venv-skillflow\Scripts\python.exe -m pytest -q` → PASS，6 passed，覆盖率 92.06%。
- `.venv-skillflow\Scripts\python.exe -m ruff check .` → PASS。
- `.venv-skillflow\Scripts\python.exe -m ruff format --check .` → PASS，21 files already formatted。
- `.venv-skillflow\Scripts\python.exe -m mypy src\skillflow` → PASS。
- `.venv-skillflow\Scripts\python.exe -m skillflow.cli doctor` → PASS，四项环境检查通过。

### 验收条件

- [x] 明确可信主体、攻击者、资产、敏感 Sink 和信任边界。
- [x] 明确范围内/外攻击，且未把恶意文本检测定义为主要任务。
- [x] 明确区分数据来源、决策影响和授权来源。
- [x] 明确 Skill 是 Principal，Harness 是桥接层。
- [x] 明确 Manifest/Grant、revoke/unload 和跨 task/session 语义。
- [x] 3 个架构决定均有独立 ADR。
- [x] 至少 4 条形式化不变量；实际冻结 9 条。
- [x] 至少 1 条良性和 3 条攻击路径。
- [x] 每个后续指标至少对应一个研究问题。
- [x] 未改变任务书第 1、2 节 MVP 边界。

### 风险或遗留问题

- 本任务只冻结语义，没有提供代码或实验结果；对应不变量必须在 T03 及以后转化为类型、Schema 和测试。
- Resource URI 与 lifetime 菱形偏序已在 T03 落地；完整 scope matcher 和稳定 reason codes 仍属于 T08。
- Oracle 隔离要到 T06 才能通过代码依赖和运行时测试验证；当前只有架构合同。
- T03 已在后续轮次完成；下一项可执行任务是 T04，但本轮不进入 T04。

## T03：Schema 与核心数据模型

- 状态：completed
- 日期：2026-08-24（Asia/Shanghai）
- 任务边界：只实现稳定数据契约、静态 Schema 和只读校验；未实现 T04 EventStore 或任何后续运行逻辑。

### 修改文件

- `src/skillflow/models/`：封闭枚举、ResourceRef、授权、效果、来源、事件、Manifest、Scenario、Experiment Matrix 和风险报告模型。
- `src/skillflow/schemas.py`：四类模型生成静态 JSON Schema 的唯一入口。
- `src/skillflow/validation.py`：YAML 加载、Pydantic 校验和结构化问题报告。
- `src/skillflow/cli.py`：新增 `validate-manifest` 与 `validate-scenario`，均只校验不执行。
- `schemas/*.schema.json`：Skill Manifest、Scenario、Experiment Matrix、Risk Report 四类静态 Schema。
- `tests/unit/models/`、`tests/integration/test_validation_cli.py`、`tests/fixtures/t03/`：模型、引用、Schema、CLI 和 JSON 往返测试。
- `docs/decisions/0004-use-diamond-lifetime-lattice.md`：冻结四值菱形 Lifetime。
- `docs/summaries/T03_Summary.md`：T03 中文总结。

### 关键设计决定

1. `Lifetime` 只允许 `call | task | session | persistent`，未知值全部拒绝。
2. Lifetime 采用菱形偏序：`call` 同时窄于 `task`/`session`，二者互不包含，`persistent` 同时宽于二者。
3. `AuthorizationGrant` 与 `SecurityEvent` 均包含可选 `call_id`；`call` Grant 必须提供它。
4. Pydantic v2 模型默认冻结并拒绝未知字段，Manifest 不能嵌入 Grant 或伪造 issuer。
5. Resource URI 只允许五种 scheme，拒绝主机绝对路径、空 scope、路径穿越和未知 scheme；精确匹配不使用字符串前缀。
6. Scenario 只能引用受控 Manifest 路径和 `fixture://<registry-id>`，所有 step/output/effect 引用必须在同一 Scenario 声明。
7. 静态 Schema 由模型生成；一致性测试防止手写副本漂移。

### TDD 记录

- Lifetime/Resource 第一轮：先得到 25 个失败、1 个通过，再补四值偏序、URI 规范化与精确匹配。
- 核心模型第二轮：先得到 4 个失败、5 个通过，再补 call/session 边界 ID、Grant 时间窗和 Effect 执行证据。
- Scenario、Schema、CLI 均先以缺失接口或缺失命令失败，再逐层补最小实现。
- 没有按 Scenario ID 特判结果，也没有加载任意 Python 实现路径。

### 验证结果

- `.venv-skillflow\Scripts\python.exe -m pytest -q` → PASS，65 passed，分支覆盖率 90.18%。
- `.venv-skillflow\Scripts\ruff.exe check src tests` → PASS。
- `.venv-skillflow\Scripts\ruff.exe format --check src tests` → PASS。
- `.venv-skillflow\Scripts\python.exe -m mypy src\skillflow` → PASS，18 个源文件无类型问题。
- 四类静态 JSON Schema → Draft 2020-12 结构检查 PASS，且与模型生成内容完全一致。
- `validate-manifest` / `validate-scenario` → 合法 fixture 退出码 0；非法文档退出码 2，并包含文件、字段路径、代码和原因。

### 验收条件

- [x] 合法 Manifest/Scenario 通过，缺 ID、重复 ID、未知 action/lifetime 和非法 URI 被拒绝。
- [x] Skill 不能伪装授权签发者，Manifest 声明不会生成 Grant。
- [x] 精确文件 scope 不覆盖父目录或相邻前缀。
- [x] 未声明 artifact/effect alias 与任意实现路径被拒绝。
- [x] JSON 往返不丢失字段，包括 `call_id`。
- [x] 四类静态 Schema 与 Pydantic 模型保持一致。
- [x] 未实现 EventStore、运行期 matcher、图、指标或 Harness。

### 风险或遗留问题

- T03 只定义数据契约。`lifetime_covers` 已表达菱形偏序，但 Grant 对当前 call/task/session 的完整运行期匹配属于 T08。
- ResourceRef 的精确匹配已实现；目录或模式 scope 的合法包含算法仍属于 T08。
- Risk Report 当前是报告 Schema，不代表 UEA、HIAA、ALR、RIR 或 CI 已经计算。
- T04 已在后续轮次完成；本段仍只记录 T03 当时的数据契约交付。

## T04：Append-only EventStore 与持久状态

- 状态：completed
- 日期：2026-08-24（Asia/Shanghai）
- 任务边界：只实现可审计、可重启的事件与运行态内容持久化底座；未实现 T05 Harness、来源图计算、策略匹配、指标或完整 Runtime checkpoint。

### 修改文件

- `src/skillflow/store/event_store.py`：定义 EventStore Protocol、原子 Event Envelope、StoredArtifact 与 MemoryHead。
- `src/skillflow/store/schema.sql`：建立 T04 要求的 12 张业务表、引用约束与追加保护触发器。
- `src/skillflow/store/sqlite_store.py`、`sqlite_writer.py`：实现 SQLite 生命周期、查询、原子写入和显式 Memory 头更新。
- `src/skillflow/store/blob_store.py`：实现按 Run 隔离、使用不可预测文件名且不接受调用方路径的 BlobStore。
- `src/skillflow/store/trace.py`：实现不导出任意 Event metadata 或 Blob 明文的稳定 Trace 投影。
- `src/skillflow/runtime/determinism.py`：提供可注入虚拟时钟与确定性 ID 工厂。
- `tests/unit/store/`、`tests/integration/store/`、`tests/e2e/test_store_restart.py`：覆盖接口、数据库、Blob、重启、Memory 与 Trace。
- `SkillFlow_Codex_Task_Spec.md`：在 T03 任务段补全四值 Lifetime、`call_id` 与菱形偏序遗漏。
- `README.md`、`docs/summaries/T04_Summary.md`：更新当前能力和中文交付总结。

### 关键设计决定

1. `events` 以自增序号保留稳定追加顺序；`events`、`event_inputs`、`event_outputs` 同时由公共接口和 SQLite 触发器保护，UPDATE/DELETE 均失败。
2. Event、输入边、输出边、Decision 与 Effect 通过 `EventEnvelope` 在同一 SQLite transaction 提交；引用失败时整体回滚。
3. Artifact 元数据先以不可变记录登记，再由输出边绑定唯一生成 Event；输出 Artifact 上的唯一约束阻止第二个生成 Event。
4. Blob 内容保存在 `runs/<experiment_id>/blobs/<run-namespace>/`，文件名由密码学随机数生成；公开引用仅含 Run、Blob ID、hash 和长度。
5. Blob 读回同时校验 Run、hash 和长度；SQLite 输出边触发器阻止 Event 绑定其他 Run 的 Blob。
6. `memory_heads` 是唯一显式可变的当前状态投影，更新前必须证明 Artifact 确由同 Run、同 Session 的指定 Event 输出；历史 Event 不被改写。
7. Trace 只投影结构化事件字段与 Artifact hash/长度/MIME 等元数据，刻意忽略任意 Event metadata 和 Blob 内容，并对规范 JSON 求 SHA-256。
8. SQLite transaction、`flush`/关闭后重开和完整 Runtime checkpoint 是三个不同承诺；T04 只实现前两项，checkpoint/restore 留到 T10。

### TDD 记录

- 先以缺失模块和公开类型合同得到失败，再建立 EventStore、BlobStore、Trace 与确定性边界。
- 虚拟时钟、确定性 ID、Blob 持久化/跨 Run 拒绝、SQLite 原子回滚和进程重启都先得到失败，再补最小实现。
- 跨 Run Blob 测试曾暴露仅在文件系统层隔离仍不足，随后增加 Artifact 的 Blob Run 字段与输出边数据库触发器。
- 最终审阅新增“Effect 错用历史 Decision 且能力不匹配”反例；该测试先失败，再将请求 Event、Decision 和能力三者的一致性纳入 Envelope 校验。
- SQLite 主实现接近单文件规模警戒线后，将无状态事务写入拆到 `sqlite_writer.py`，保持存储资源生命周期与写入算法分离。

### 验证结果

- `.venv-skillflow\Scripts\python.exe -m pytest -q` → PASS，93 passed，分支覆盖率 90.60%。
- T04 定向测试共 28 项，覆盖合同、确定性、Blob、SQLite 与重启场景。
- `.venv-skillflow\Scripts\ruff.exe check src tests` → PASS。
- `.venv-skillflow\Scripts\ruff.exe format --check src tests` → PASS。
- `.venv-skillflow\Scripts\python.exe -m mypy src\skillflow` → PASS，27 个源文件无类型问题。
- Python no-excuse 规则审计 → `store` 7 个文件、`runtime` 2 个文件均无违规。

### 验收条件

- [x] 12 张指定业务表全部建立。
- [x] 重复 Event ID、缺失 Artifact、重复输出生成关系和跨 Run Blob 均被拒绝。
- [x] Event、关系边、Decision 与 Effect 原子提交；失败后不留下半条 Event 或相关记录。
- [x] 公共接口不提供历史修改能力，直接 SQL 修改也被触发器拒绝。
- [x] Persistent Memory 可从 Session 1 跨进程重启到 Session 2 读取，历史事件顺序保持稳定。
- [x] 同一持久事件序列在数据库重开前后产生相同 Trace hash，测试秘密不进入 Trace JSON。
- [x] 虚拟时钟和确定性 ID 工厂可注入、可重放。

### 风险或遗留问题

- SQLite transaction 不能与文件系统形成分布式事务；若 Blob 已落盘而后续元数据登记失败，可能留下不可达 Blob。T04 不做自动清理，也未删除任何文件。
- Artifact 登记是 Event Envelope 之前的独立追加步骤；本任务保证 Event、边、Decision、Effect 原子，不宣称 Artifact 与 Blob 的跨介质原子提交。
- `grants` 与 `revocations` 表已经预留，完整签发、撤销和 lifetime/scope 运行期匹配仍属于 T08。
- 完整 Runtime state checkpoint/restore 仍属于 T10。
- 本轮在 T04 停止，没有进入 T05。

## T05：安全 Mock Harness 与插桩代理

- 状态：completed
- 日期：2026-08-24（Asia/Shanghai）
- 任务边界：只实现确定性 Scripted Backend、安全 Mock Harness、运行期插桩代理和 YAML 良性场景；未实现 T06 Oracle、T08 正式授权策略、T10 checkpoint 或任何真实外部副作用。

### 修改文件

- `src/skillflow/adapters/`：最小 Harness Protocol、Mock Harness 和 Benchmark 特权控制入口。
- `src/skillflow/benchmark/`：白名单 Scripted Backend 与 YAML Scenario Runner。
- `src/skillflow/instrumentation/`：Context、Memory、File、Skill、Tool、Stub Decision 和强类型 Receipt。
- `src/skillflow/runtime/session.py`：当前 Session 的确定性事实记录器。
- `src/skillflow/store/`：增加 Memory 头删除，以及跨请求/结果 Event 的 Decision/Effect 一致性校验。
- `tests/unit/adapters/`、`tests/unit/instrumentation/`、`tests/integration/harness/`：T05 合同、生命周期、Tool 管线和安全边界测试。
- `tests/fixtures/t05/benign_read.yaml`、`tests/e2e/test_t05_scenario.py`：从 YAML 到 Receipt 的良性端到端场景与确定性/隔离验证。
- `README.md`、`docs/summaries/T05_Summary.md`：当前能力、限制和中文交付总结。

### 关键设计决定

1. `HarnessAdapter` 固定只有 start/load/invoke/end 四个方法；checkpoint/restore 不提前占位。
2. Scripted Backend 只解析进程内 fixture registry；Scenario 不能指定 Python 模块或任意代码。
3. Context 为 Session 局部状态；Memory 和 Skill 安装/撤销状态只在同一 Run 内跨 Session。
4. 文件代理只接受 `workspace:`，解析后再次检查目标仍位于注入根目录。
5. 普通 Tool 只有五个白名单动作；BenchmarkController 不提供给 Skill。
6. T05 决策只使用 fixture allow/deny，confirm 与正式 Grant 逻辑明确留给 T08。
7. Tool Receipt 由 Mock Tool Adapter 在执行后创建；这是 API 级强类型约束，不夸大为密码学保证。
8. Network/Shell 只追加内存记录；Shell 不创建子进程，HTTP 不建立连接。
9. Decision 与 Effect 即使由结果 Event 一起提交，也必须共享同一个原请求 Event。
10. Skill/Memory/File/Tool Event 保存受控目标 metadata，但默认脱敏 Trace 继续忽略任意 metadata。

### TDD 与验证

- 模块合同、插桩行为、Tool 链、Skill 生命周期、YAML Runner 和 EventStore 反例都先获得失败再补实现。
- T05 定向测试 → PASS，47 passed。
- 全量 pytest → PASS，141 passed，分支覆盖率 89.19%。
- Ruff lint/format → PASS。
- mypy strict → PASS，46 个源文件无类型错误。
- Python no-excuse 规则审计 → PASS，46 个源文件无违规。
- 同 seed Trace hash → 一致；两个 Run 的 Workspace、Context/Memory 与 Receipt 累积状态隔离。
- 路径逃逸、Stub confirm 与 Receipt 直接构造 → 拒绝。
- Denied Tool → 不产生 Effect/Receipt。
- Shell 哨兵文件 → 未创建。

### 验收条件

- [x] 最小良性 YAML Scenario 可运行到 Tool Receipt。
- [x] Context、Memory、File、Skill 和 Tool 边界均生成 Artifact/Event。
- [x] 跨 Session Memory read 连接原 Artifact。
- [x] 普通 Tool 面不包含用户确认或 Skill 撤销。
- [x] HTTP/Shell 没有真实外部副作用。
- [x] 相同 seed 的 Trace hash 一致，不同 Run 无状态积累。
- [x] 没有进入 T06。

### 风险或遗留问题

- 当前 Runner 的通用顶层 Memory/Tool/Restart 步骤会显式拒绝；参数化 Tool 动作来自固定 FixtureScript。
- 正式授权匹配、monitor/enforce 语义和 confirm 属于 T08，当前 Stub 结果不能作为授权正确性证据。
- Oracle 隔离、双轨 Trace、来源图、指标和 checkpoint 均尚未实现。
- 本轮在 T05 停止，下一项是 T06，必须由用户另行要求后才能开始。

## T06：双轨 Trace 与独立 Oracle

- 状态：completed
- 日期：2026-08-24（Asia/Shanghai）
- 任务边界：只实现 Observed/Oracle 双轨 Trace、机械 Ground Truth、稳定 ID/父关系与隔离审计；未实现 T07 来源图、T08 正式 PolicyEngine、T09 指标或 T10 checkpoint。

### 修改文件

- `src/skillflow/trace/`：双轨共用的稳定父关系、不可覆盖 JSONL 写入器和 Observed Trace 投影。
- `src/skillflow/oracle/`：独立 GT_data 状态、动作/Receipt 绑定、Grant 解析、预注册断言校验和 Oracle Writer。
- `src/skillflow/benchmark/oracle_bridge.py`、`manifests.py`：Runner 与 Oracle 之间唯一单向桥，并从受控相对路径加载 Manifest。
- `src/skillflow/models/tool_calls.py`：把 Tool 参数与 attempt 合同提升到中立模型层；旧 instrumentation 入口只做显式兼容导出。
- `src/skillflow/instrumentation/tool_receipt.py`：增加 call/action/argument/receipt Artifact 稳定 ID，使 Receipt 能锚定 GT_effect。
- `src/skillflow/runtime/provenance.py`：只对 Observed origins 应用 `drop_on_derive` / `drop_on_memory`。
- `scenarios/manifests/benign_reader.yaml`、`tests/fixtures/t06/`：受控 Manifest、授权场景和丢标配对。
- `tests/unit/test_t06_oracle*.py`、`tests/e2e/test_t06_dual_trace.py`：独立授权、四值 Lifetime、五类动作、Memory 传播、依赖隔离、双轨对齐、丢标和拒绝路径测试。
- `README.md`、`docs/summaries/T06_Summary.md`：更新当前能力、限制和中文交付总结。

### 关键设计决定

1. Observed Writer 可以读取 EventStore 和实际 `observed_label`；Oracle 包不能读取二者，也不能导入 Adapter、Instrumentation、Runtime、Store 或 Observed Writer。
2. `benchmark/oracle_bridge.py` 是唯一协调边界，只把 Scenario、Manifest、Scripted action、Tool attempt 与 Receipt 的稳定字段单向投影给 sidecar，不传 Artifact 对象或标签。
3. Scenario asset 先成为 `asset:<id>` 真值根；Tool argument、File/Memory 输出、Receipt 值和 Skill output 再按实际稳定 Artifact ID机械传播 `GT_data`。
4. deny 动作仍有 Tool argument 真值和对齐 ID，但没有 Receipt、EffectRecord 或 `GT_effect`；只有强类型 Mock Receipt 能产生 `GT_effect=true`。
5. `OracleGrantResolver` 不接受 DecisionRecord 或 PolicyEngine 输入；`GT_auth` 由 Manifest + Grant 双钥匙、精确资源/scope、四值 Lifetime、时间窗和撤销 ID 独立计算。
6. `COPY | DERIVE | WRITE | LOAD | INVOKE` 是封闭父关系；当前 T06 输出关系，T07 才从 EventStore 构建 NetworkX 来源图和路径查询。
7. 两个 JSONL 都排除 Blob、任意 Event metadata、脚本输出和 fixture marker；Oracle 预期只校验机械结果，不反向填充真值。
8. 编程规范审计发现 Runner 超过 250 行后，按 `omo:refactor` 将 Manifest/动作/Receipt 投影抽到 Oracle Bridge；随后再次通过全部行为和静态门禁。
9. 最终规范复核发现新增 Oracle 测试文件超过 250 行并含过宽 JSON 类型；拆成授权/数据测试并使用 `JsonValue` 边界解析后，24 项 T06 测试保持通过。

### TDD 与验证

- 首轮红灯：T06 测试因 `skillflow.oracle` 不存在而在收集阶段失败。
- 第一轮绿灯：8 个核心测试通过；定向命令仅因全仓覆盖率门槛而非功能失败退出非零。
- 扩展后 T06 定向测试：24 项通过，覆盖独立授权、四值 Lifetime、五类 Tool、Memory WRITE/LOAD、双轨 E2E、丢标、deny attempt 和接口隔离。
- 全量 pytest：165 passed，分支覆盖率 88.48%。
- Ruff lint：PASS；format check：115 files already formatted。
- mypy strict：PASS，64 个源文件无类型问题。
- Python no-excuse：PASS，70 个本轮相关文件无违规。
- `skillflow doctor` 与 `pip check`：PASS；Git 状态和远端同步证据在提交后由最终汇报给出。

### 验收条件

- [x] 每次 Run 输出 `observed-trace.jsonl` 和 `oracle-trace.jsonl`。
- [x] 实际 Artifact/Effect 能按稳定 ID 在两条 Trace 中对齐；deny argument 也不丢失。
- [x] Scripted Oracle 路径从 asset 经 LOAD/INVOKE 到 Skill output 完整。
- [x] 删除 Observed origins 会降低手算 Recall，Oracle 逐条记录保持不变。
- [x] 修改策略结果不改变 Oracle authorization；Observed stub authorization 与 GT_auth 可明确不同。
- [x] Agent、Skill、Tool 和 Observed 运行组件无法取得或反向导入 Oracle 对象。
- [x] Oracle 与防御实现无循环依赖，默认 Trace 不包含测试秘密明文。

### 风险或遗留问题

- T06 Oracle 只实现当前 MVP 的精确 Resource/scope 覆盖；目录/模式 scope、稳定 reason code 和正式 monitor/enforce PolicyEngine 属于 T08。
- Resolver 已支持传入有效撤销 ID，但 Scenario 的 `AUTH_REVOKE` 运行编排和 EventStore Grant 视图仍属于 T08。
- T06 没有计算正式 Provenance Precision/Recall/F1；测试中的 Recall 只用于证明独立真值能观测丢标，正式指标属于 T09。
- 尚未构建 NetworkX 图或任何来源路径查询；本轮在 T06 停止，不进入 T07。

## T07：来源图与路径查询

- 状态：completed
- 日期：2026-08-25（Asia/Shanghai）
- 任务边界：只实现从 EventStore 重建的只读来源图、安全投影、研究查询、边界计数和脱敏 JSON；未实现 T08 正式授权匹配、T09 风险指标、T10 checkpoint 或 `INFLUENCE_CONFIRMED` 推断。

### 修改文件

- `src/skillflow/graph/`：新增强类型节点/边/路径合同、Artifact–Event 二部图、SecurityGraph 投影、事件与 Record 投影、路径枚举、路径指标和 JSON 导出。
- `src/skillflow/store/event_store.py`、`sqlite_store.py`：增加按 Run 读取 EffectRecord 的公共 EventStore 合同与 SQLite 实现。
- `src/skillflow/benchmark/runner.py`：每次 Scenario Run 从持久事实重建图，并以不可覆盖方式生成 `security-graph.json`。
- `pyproject.toml`：增加 NetworkX 运行依赖，以及兼容 Python 3.11 类型目标的 NetworkX/NumPy 开发类型依赖约束。
- `tests/unit/graph/`、`tests/integration/graph/`、`tests/e2e/test_t07_scenario_graph.py`：覆盖依赖隔离、环路、深度限制、七类查询、Golden 路径、脱敏导出、Runner 重启和 Session 重新进入。
- `README.md`、`docs/summaries/T07_Summary.md`：更新当前能力、查询用法、限制与中文验收总结。

### 关键设计决定

1. SQLite EventStore 继续是唯一事实源；图层只读取其公共合同，不读取 Oracle、Observed Trace、运行代理或 Blob 正文。
2. 来源核心严格保持 `Artifact --USED--> Event --GENERATED--> Artifact`；Principal、Grant、Decision 和 Effect 只存在于上层只读 SecurityGraph。
3. 对外语义边使用封闭枚举；普通事件最多生成 `INFLUENCE_CANDIDATE`，当前任何代码路径都不会生成 `INFLUENCE_CONFIRMED`。
4. 每条查询结果同时返回类型化节点、语义边、按路径顺序压缩的 Session 轨迹、证据 Event ID、边界深度和关联的 Grant/Skill/Tool ID。
5. Context、Memory、Skill、Tool 只在真实跨界结构边上逐次计数，不在同一 Event 的 Artifact 边和 Principal 边重复标记；Session 按实际路径转换计数，`A → B → A` 记为两次而不是全局去重后的一次。
6. 撤销是带事件时间的独立事实；历史节点和边不改写，只有撤销时间不晚于路径 Effect 时点的来源才标为 revoked origin。
7. 路径枚举维护逐路径 visited 集合，并同时提供默认最大深度 64 与最多 512 条返回路径的资源上限。
8. JSON 导出只由允许字段的 Pydantic 模型生成，排除 Blob、正文和任意 Event metadata；使用 exclusive-create 拒绝静默覆盖。
9. 如果 Tool 请求已有显式输入 Artifact，Skill→Tool 路径沿该 Artifact 传播；只有输入为空时才补 actor Skill→请求 Event 结构边，避免真实 Runner 断链同时也避免绕过 Golden 证据。

### TDD 与验证

- 首轮先写 T07 测试，因 `skillflow.graph` 尚不存在而在收集阶段红灯。
- Golden、七类查询、循环、最大深度、导出脱敏和隔离测试完成后，首轮定向测试 14/15 通过；真实 Runner 重启查询暴露 inputless Tool 请求与 actor Skill 断链。
- 脱敏运行图证明请求 Event 已能到达 Effect，但 `benign_reader` 不能到达请求；只在内存补一条 actor→request 边后 `nx.has_path` 从 False 变为 True。修复收紧为仅处理无显式输入 Artifact 的请求。
- no-excuse 审计发现事件投影和路径模块超过 250 行；按职责拆为 `special_event_projection.py` 与 `path_analysis.py`，公共接口和 T07 行为保持不变。
- 最终语义复核增加 `Session A → B → A` 回归测试，先因缺少顺序 Session 轨迹失败，再修正为两次穿越。
- 提交前逐边审计把 Golden 边界深度改为精确值：Context=1、Memory=2、Session=1、Skill=3、Tool=2、total=9；测试先暴露 Skill/Tool 重复标签，再移除重复计数。
- 二部图节点闭包测试先发现 Principal/Grant/Decision/Effect 被错误加入 provenance 核心，随后将它们限制在上层 SecurityGraph。
- T07 定向测试：17 passed；全量 pytest：182 passed，分支覆盖率 87.93%。
- Ruff lint/format、mypy strict（78 个源文件）、Python no-excuse、`skillflow doctor` 与 `pip check` 均通过；最终 Git 证据在提交推送后记录于汇报。

### 验收条件

- [x] 从 EventStore 重建冻结的 Artifact–Event 二部图和类型化 SecurityGraph。
- [x] 七类指定查询全部实现，并返回节点、边、Session、证据 Event、Grant、Skill、Tool 和边界深度。
- [x] Golden 路径识别 Skill A、Skill B、一次跨 Session、最终 Tool、撤销来源、关联 Grant 和全部因果 Event。
- [x] 环路在 visited/max-depth 约束下终止，Session 重新进入按每次穿越计数。
- [x] 普通轨迹不生成 `INFLUENCE_CONFIRMED`。
- [x] Runner 自动生成可由强类型模型读回且不含秘密哨兵的 JSON 图。
- [x] 图包不依赖 Oracle、Adapter、Instrumentation、Runtime 或 Trace Writer。

### 风险或遗留问题

- T07 只投影已经持久化的 Decision/Grant 引用，不判断 Manifest 与 Grant 是否真实覆盖 Effect；完整 matcher、reason code、monitor/enforce 和撤销授权执行属于 T08。
- `INFLUENCE_CANDIDATE` 只表示可达候选影响，不是因果确认；`INFLUENCE_CONFIRMED` 必须等待后续反事实证据。
- 简单路径枚举默认深度 64、最多返回 512 条；大图研究必须显式理解该资源边界，不能把截断结果误报为全图无路径。
- GraphML 未实现，按任务书只作为 T14 后的可选增强。
- 本轮在 T07 停止；T08 保持 pending，不自动开始。

## T08：授权匹配与策略决策

- 状态：completed
- 日期：2026-08-25（Asia/Shanghai）
- 任务边界：只实现 Manifest/Grant 双钥匙匹配、正式 PolicyEngine、Grant/撤销持久事实、决策真值表与 Benchmark 特权确认；未实现 T09 指标、T10 checkpoint 或真实平台 Adapter。

### 修改文件

- `src/skillflow/policy/`：新增 Manifest/Grant matcher、稳定 reason codes、来源检查、baseline 真值表、PolicyEngine 与 EventStore 运行适配器。
- `src/skillflow/models/`：把 Scope 收紧为封闭枚举，为 Decision 增加 Manifest 追踪，并允许 `user_confirm` 携带结构化 Grant。
- `src/skillflow/store/`：新增不可变 Grant 与撤销视图、SQLite 表和防改写触发器；Event、Grant/撤销继续原子追加。
- `src/skillflow/instrumentation/`、`adapters/`、`benchmark/`：ToolProxy 接入完整策略计划；Runner 注册初始 Grant，支持 USER/TRUSTED_POLICY 特权确认，并把最小结构化事实单向投影给 Oracle。
- `src/skillflow/runtime/contracts.py`、`store/envelope_validation.py`：把运行合同和跨事实校验按职责拆出，消除超过 250 行的源模块。
- `tests/unit/policy/`、`tests/integration/policy/`、`tests/e2e/test_t08_policy_modes.py`：覆盖双钥匙矩阵、四值 Lifetime、Scope、撤销、来源、monitor/enforce 和确认路径。
- `README.md`、`docs/security-semantics.md`、`docs/summaries/T08_Summary.md`：更新中文能力、冻结语义与验收总结。

### 关键设计决定

1. `authorized` 只由 Manifest 声明与有效结构化 Grant 共同决定；baseline、policy 和 executed 均不能改写它。
2. Lifetime 继续使用菱形偏序：`call < task < persistent` 与 `call < session < persistent`，其中 task/session 互不包含；匹配只检查当前 lifetime 对应的边界 ID。
3. 首版 Scope 固定为 `exact-file | exact-key | exact-sink | command` 的离散反链；资源只做规范化 URI 精确匹配，不接受字符串前缀。
4. baseline 按“结构无效 → 已有结构化确认 → auto approve → 相关文本开关 → confirm”的固定优先级计算；文本只可能影响 baseline，不创建 Grant。
5. policy 只有在双钥匙和来源检查全部通过时 ALLOW；只有 Manifest 已覆盖且单纯缺 Grant、策略又允许获取新授权时才 CONFIRM，否则 DENY。
6. monitor 仅在 baseline ALLOW 时执行 Mock Effect；enforce 还要求 policy ALLOW。两种模式不改变 policy 与 authorized 真值。
7. USER/TRUSTED_POLICY 确认通过 Skill 不可见的 `BenchmarkController` 生成 Grant；actor 必须与 `issuer_type` 一致，Skill actor 被显式拒绝。
8. AUTH_REVOKE 和 Skill Principal 撤销均是有时间戳的追加事实；后续请求读取 EventStore 计算，历史 Grant、Event 和 Effect 不回写。
9. Policy 运行面和 Oracle 双向静态隔离；Oracle 只接收 Benchmark 已实际执行的结构化确认，不读取 Policy 结果。

### TDD 与验证

- 首轮 policy 单元测试因 `skillflow.policy` 尚不存在而红灯；实现后 36 项 matcher/engine 测试通过。
- Runner 接入前，T08 E2E 的三条路径按预期失败；接入正式 provider 与特权确认后全部转绿。
- 全量回归首次暴露 T05 旧 fixture 未开启 baseline auto approve、T06 仍断言 Stub 授权值、Stub 兼容方法缺失和静态 Schema 未更新；逐项修正后没有改变 Oracle 真值。
- 新增特权边界测试，证明 Skill actor 不能签发 Grant，USER 可以签发并追加撤销；普通“用户已批准”文本不会产生 AUTH_GRANT。
- no-excuse 审计发现 `runtime/session.py`、`store/sqlite_writer.py` 和扩展后的 matcher 测试超长；分别按运行合同、Envelope 校验及 Manifest/Grant 测试职责拆分后，本轮相关文件无规则违规。
- 最终全量 pytest：236 passed，分支覆盖率 89.18%。
- Ruff lint：PASS；format check：158 files already formatted。
- mypy strict：PASS，88 个源文件无类型问题。
- T08 相关 Python no-excuse：PASS；`skillflow doctor`、CLI help 与 `pip check`：PASS。

### 验收条件

- [x] Manifest 与 Grant matcher 覆盖任务书指定维度，并返回稳定 reason codes。
- [x] 未知 Scope/Lifetime 被模型拒绝；Lifetime 不按枚举顺序比较，task/session 互不包含。
- [x] `baseline_result`、`policy_result`、`authorized`、`executed` 四事实同时持久化且可追踪到 Manifest、Grant 和来源 Artifact。
- [x] monitor/enforce 保持相同策略真值，只在实际执行上按规则分歧。
- [x] 过期 Grant、撤销 Grant、撤销来源、跨 call/task/session 和不可信/不完整来源均有稳定拒绝原因。
- [x] Skill 文本不能生成 Grant；只有 Benchmark USER/TRUSTED_POLICY 特权接口可以确认。
- [x] Policy 不读取 Oracle，Oracle 也不导入 Policy 或运行防御实现。

### 风险或遗留问题

- 首版 Scope 是精确离散反链，不支持目录、glob、域名层级或命令参数模式；不得把该限制误报为通用范围包含。
- 当前确认步骤由声明式 Benchmark 预注册结构化 Grant，不包含真实交互式 UI 或外部身份认证。
- T08 只产出逐 Effect 的完整 Decision 与证据，不计算 UEA、Precision、Recall、F1 或 Decay；这些属于 T09。
- 本轮在 T08 停止；T09 保持 pending，不自动开始。

## T09：基础指标 UEA 与 Provenance

- 状态：completed
- 日期：2026-08-25（Asia/Shanghai）
- 任务边界：只实现可由结构化真值直接计算的 UEA 与来源指标、逐场景报告和 micro 聚合；未实现 T10 Checkpoint、反事实重放、确认影响边或 T11 高级指标。

### 修改文件

- `src/skillflow/models/metrics.py`、`models/reports.py`：新增比例状态、原始计数、UEA 五元组、路径证据、逐深度来源指标与嵌套 Run 报告合同。
- `src/skillflow/analysis/`：新增双轨/图投影、UEA、Provenance、micro 聚合、Run 报告门面、Schema 复验和不可覆盖写入。
- `src/skillflow/benchmark/runner.py`：在 Observed/Oracle Trace 与 SecurityGraph 完成后自动写出 `risk-report.json`，并在结果中返回路径。
- `schemas/risk-report.schema.json`：由更新后的 Pydantic 判别联合确定性重生成。
- `tests/unit/analysis/`、`tests/unit/models/`、`tests/e2e/test_t09_risk_report.py`：覆盖 Golden 指标、N/A、重复去重、micro、双轨完整性、不可覆盖写入和真实 Run 报告。
- `pyproject.toml`：补充 `types-jsonschema` 开发依赖，使运行时 Schema 校验代码通过 mypy strict。
- `README.md`、`docs/summaries/T09_Summary.md`：更新中文能力、使用方法、验收证据与停止点。

### 关键设计决定

1. UEA 只认 Oracle 的 `GT_effect=true`、`GT_auth=false` 和真实 Receipt，不使用 baseline、policy 或模型文本猜测授权。
2. `UEA_count` 按 Effect/Receipt 实例计数；`UEA_type_count` 按规范化五元组全局去重；首版 `UEA_weight` 每个未授权已执行实例固定加 1。
3. 每个 UEA 实例输出 Manifest/Grant 缺失 reason codes，以及 SecurityGraph 中 Principal 到 Effect 的全部有限路径；路径只包含类型化 ID、边界深度和证据 Event ID，不复制正文或 Blob。
4. 来源指标逐 Artifact 比较 `Observed origins` 与 `Oracle GT_data`，先保留 TP/FP/FN，再计算 Precision、Recall 和 F1。所有比例都输出 numerator、denominator、value、status 与 evidence IDs。
5. 零分母不伪装为 0：完全无来源暴露时为 `0/0/null/not_applicable`；Oracle 非空而 Observed 为空时 Precision 为 N/A，Recall/F1 为 0。
6. Decay 固定为相邻总边界深度的 `Recall(d-1) - Recall(d)`；缺少前一深度或任一 Recall 无分母时为 N/A。
7. micro 聚合对 UEA 实例求和、对五元组全局去重，并汇总原始 TP/FP/FN 后重新计算比例；禁止平均场景百分比。
8. Oracle 的声明式 asset 根不要求进入 Observed；其余运行 Artifact 必须双轨完整对齐，任一侧整体缺失均拒绝计算，防止选择性漏记抬高指标。
9. `risk-report.json` 以 exclusive-create 写入，并在落盘前使用模型生成的 Draft 2020-12 Schema 复验；已有文件不会被覆盖。
10. Runner 的公开类和导入路径保持原位；T09 投影、计算和写入由 `analysis.run_reporting` 门面组合，Runner 保持 250 行有效代码。

### TDD 与验证

- 第一轮报告/聚合测试得到两个预期红灯：micro 聚合抛 `NotImplementedError`，Runner 结果缺少 `risk_report_path`。
- UEA 与来源 Golden 测试先以八个 `NotImplementedError` 红灯确认覆盖，再补纯计算实现转绿。
- 真实 Run 首次能写出报告后，静态 `risk-report.schema.json` 因仍为 T08 旧合同而失败；重生成 Schema 并迁移契约 fixture 后转绿。
- 完整性审查新增 Oracle-only 运行 Artifact 用例，现状按预期未抛错；加入非 asset 双轨集合保护后转绿，同时保留 Oracle-only 声明式 asset 根用例。
- 不可覆盖写入用 sentinel 文件验证：第二次写入抛 `RiskReportWriteError`，原字节保持不变。
- T05–T09 跨阶段定向回归：63 passed。
- 最终全量 pytest：254 passed，分支覆盖率 89.28%。
- Ruff lint：PASS；Ruff format：177 个文件格式一致。
- mypy strict：PASS，98 个源文件无类型问题。
- T09 相关 Python no-excuse：PASS；Runner 为 250 pure LOC。
- `skillflow doctor`、CLI help、`pip check`：PASS。

### 验收条件

- [x] UEA 实例数、类型数和固定权重只由 Oracle/Receipt 结构化事实计算。
- [x] 每个未授权已执行 Effect 都有稳定 reason codes、路径和证据 ID。
- [x] Golden P/R/F1、全缺失、空集合、多来源、重复事件与 Decay 用例通过。
- [x] 同时保留逐场景结果与从原始计数计算的 micro 聚合，不执行 macro 百分比平均。
- [x] 比例误差约束严于 `1e-9`，且零分母使用结构化 N/A。
- [x] Run 自动写出并可由静态 JSON Schema 验证的 `risk-report.json`。
- [x] 报告和图中不包含 fixture marker、Blob 正文或任意 Event metadata。

### 风险或遗留问题

- 当前 source-to-sink 证据是确定性 SecurityGraph 中的 Principal→Effect 候选路径；T10 之前不会把候选影响升级为因果确认。
- 边界深度使用每个 Artifact 可达祖先路径中的最大总深度；这是首版清晰规则，不代表所有路径分布统计。
- `RunRiskReport` 已从 T08 占位式平铺字段迁移为 T09 嵌套结构；当前仓库没有既有外部消费者，但后续公开发布前仍需冻结版本迁移策略。
- PowerShell 7.6.5 已设为 Windows Terminal 默认 Profile；仓库命令继续显式使用项目 `.venv-skillflow` 解释器。
- 本轮在 T09 完成后停止；T10 保持 pending，不自动开始。

## T10：Checkpoint 与反事实重放

- 状态：completed
- 日期：2026-08-25（Asia/Shanghai）
- 任务边界：只实现确定性 Scripted Backend 的完整 checkpoint/restore、Artifact identity/neutral 干预、成对 Replay、Effect Receipt 差异和 CI；未实现 T11 高级指标或真实平台 Pilot。

### 修改文件

- `src/skillflow/adapters/checkpoint.py`、`mock_checkpoint.py`、`mock_harness.py`：冻结并恢复 Store/Blob、Workspace、Context、Memory、Skill、Grant/撤销、Mock Tool、虚拟时间和 ID 计数，恢复后复验规范化哈希。
- `src/skillflow/store/checkpoint.py`、`runtime/workspace_checkpoint.py`：通过公开存储合同逻辑导出前缀，并导入新的空分支；源分支保持追加式不变。
- `src/skillflow/benchmark/scenario_execution.py`：把一次性循环重构为可在目标 Artifact alias 后暂停、快照、替换 Alias 并恢复后缀的 `ScenarioExecutor`。
- `src/skillflow/benchmark/harness_factory.py`：统一普通 Runner 与 Replay Runner 的确定性 Harness 装配，避免两套策略配置漂移。
- `src/skillflow/instrumentation/artifact_intervention.py`：新增 `identity | neutral` 的 `ARTIFACT_DERIVE`，保持 Artifact 类型、MIME、JSON 结构和精确长度。
- `src/skillflow/benchmark/replay*.py`：新增公共 checkpoint、original/neutral 隔离分支、控制条件摘要、Receipt 匹配、Effect diff、CI、报告和清单写入。
- `src/skillflow/models/reports.py`、`schemas/risk-report.schema.json`：新增强类型确认影响边和有符号 Replay 风险报告合同。
- `tests/unit/**/test_t10_*`、`tests/integration/harness/test_t10_checkpoint_restore.py`、`tests/e2e/test_t10_counterfactual_replay.py`：覆盖模型边界、输入绑定、确定性状态、完整恢复、正因果、负对照、泄漏和字节确定性。
- `README.md`、`docs/security-semantics.md`、`docs/summaries/T10_Summary.md`：更新中文能力、确认影响语义、验收证据和停止点。

### 关键设计决定

1. 最小 `HarnessAdapter` 保持不变；checkpoint/restore 只属于独立的 `CheckpointableHarnessAdapter` 扩展。
2. Checkpoint 只在没有活动 Skill 调用的 step 边界建立，并同时保存 Harness 状态和 Scenario 编排器游标；只恢复 Harness 而重跑前缀不算 T10 合格恢复。
3. `prefix_hash` 对分支 run ID 做规范化，`state_hash` 继续覆盖 Context、Memory、Skill、Tool、授权注册、时间、ID 和 Workspace；宿主路径、随机 Blob ID 和正文不进入哈希。
4. 每个 counterfactual 使用 source/original/neutral 三个独立 Run；original 与 neutral 从同一 checkpoint 恢复，run ID 和持久目录不同，但干预前哈希相同。
5. 原始分支也追加 identity `ARTIFACT_DERIVE`，使两边在干预点消耗相同的 Event/Artifact ID 序列；中和分支不能删除 Skill 或原地改写源 Artifact。
6. JSON neutral 保留键、容器和标量种类并精确补齐字节长度；文本和二进制采用等长中和值。无法定义中和形式时显式失败。
7. Scenario 的 `inputs` 只允许引用此前步骤产生的 Artifact alias；Scripted Backend 实际读取输入 Artifact ID/哈希来绑定 Tool source 和选择决策键，不能只在报告层伪造影响。
8. Replay 只认 selector 命中的已执行 Effect，且必须能对齐同分支 `ToolReceipt`；被拒请求、自然语言输出和图上游关系都不能计入 `y`。
9. Scripted CI 固定为 `int(y_original)-int(y_neutral)`；非零 CI 只能指向机械 removed/added Effect，零 CI 严禁确认边。
10. `replay-report.json` 与 `pair-manifest.json` 均独占创建，且不输出 Artifact 正文、Blob ID、Tool 参数正文或宿主路径。

### TDD 与验证

- Replay E2E 首先因 `skillflow.benchmark.replay` 不存在而红灯；实现不是对已有结果增加空断言。
- 完整恢复测试建立非空 Context、Memory、已加载 Skill、初始 Grant、Mock Shell、虚拟时间、ID 计数和 Workspace，再恢复到不同 run ID/根；两级哈希相同且源分支后续变化不污染恢复分支。
- 首轮正因果分支没有 Effect；读取真实 Decision 后确认是 enforce 正确拒绝 `UNTRUSTED_ORIGIN`。Golden fixture 改用 monitor 单独观察内容 gate，保留同一 Grant、Manifest 和 policy 拒绝事实，没有放宽正式策略。
- 正因果对照得到 `true → false, CI=1` 和一条确认边；无关内容负对照得到 `true → true, CI=0` 且无确认边。
- 两个不同的新输出根生成逐字节一致的 `replay-report.json` 和 `pair-manifest.json`；文件中不存在 fixture 正文或临时目录路径。
- T05–T09 端到端定向回归：13 passed。
- 整理后的 T10 单元、集成、端到端专项：21 passed。
- 最终全量 pytest：275 passed，分支覆盖率 89.39%。
- Ruff lint：PASS；format check：204 个 Python 文件格式一致。
- mypy strict：PASS，116 个源文件无类型问题。
- T10 变更 Python no-excuse：PASS，26 个文件无违规。
- `skillflow doctor`、CLI help、`pip check`：PASS。

### 验收条件

- [x] Checkpoint 保存任务书要求的 Context、Memory、Skill、授权、Tool、随机/ID 状态和虚拟时间。
- [x] 恢复到全新分支后，干预点之前的规范化 Trace 前缀哈希和完整状态哈希一致。
- [x] Artifact identity/neutral 都通过追加派生实现，保持类型、MIME、结构和精确长度，不删除 Skill。
- [x] 两分支共享 seed、时间、Script/Tool 返回、Manifest、Grant 和其他 checkpoint 输入。
- [x] 正因果中和后 Effect/Receipt 消失；无关输入中和后 Effect/Receipt 不变。
- [x] Replay 输出原始/中和 run、干预 Artifact、Effect diff、有符号 CI 和严格确认边。
- [x] 报告和证据清单不泄漏 Artifact 正文、Blob ID 或宿主路径，并可跨新根逐字节复现。

### 风险或遗留问题

- 当前确认影响只适用于确定性 Scripted Backend；真实 LLM 必须等待 T15 人工批准和预注册统计阈值。
- JSON 的“Schema 保持”指键、容器、标量种类和可解析性，不是任意外部 JSON Schema 的通用求解；无法保持时必须失败。
- Replay DSL 当前直接中和 Artifact alias；Memory 与授权状态虽然已进入 checkpoint，但专用 Memory/Grant 中和声明尚未扩展。
- 本轮在 T10 完成后停止；T11 保持 pending，不自动开始。

## T11：HIAA、ALR 与撤销残留影响

- 状态：completed
- 日期：2026-08-25（Asia/Shanghai）
- 任务边界：只实现 T11 的能力匹配四格实验设计、HIAA、授权洗白分类与 ALR、撤销后的 RIR 以及可复核 Experiment 风险报告；未创建 T12 场景库、最终实验矩阵或真实平台 Adapter。

### 修改文件

- `src/skillflow/models/matrix_design.py`、`models/matrix.py`：新增目标/中性 Skill 能力匹配合同、Harness 特性、四格定义与严格机械生成校验。
- `src/skillflow/models/advanced_metrics.py`、`models/residual_metrics.py`：新增有符号/N/A 指标、逐格原始事实、授权尝试分类、撤销记录及严格归因证据模型。
- `src/skillflow/analysis/effect_selection.py`、`hiaa.py`、`authorization_laundering.py`、`residual_influence.py`：分别实现共享 selector 的 HIAA、ALR 七条件分类和严格因果归因的 `RIR(k)` 纯计算。
- `src/skillflow/analysis/experiment_reporting.py`、`report_io.py`、`models/reports.py`：组合并复验 Experiment 风险报告，保留全部 outcome、Effect/Receipt ID、分类、计数、分母和值。
- `schemas/experiment-matrix.schema.json`、`schemas/risk-report.schema.json`：从 Pydantic 合同确定性重生成静态 Schema。
- `tests/unit/**/test_t11_*`、`tests/e2e/test_t11_experiment_report.py`：覆盖四格、正负/零分母 Golden、证据约束、分类排他性和 Schema 报告闭环。
- `README.md`、`docs/security-semantics.md`、`docs/summaries/T11_Summary.md`：更新中文能力、指标纪律和独立验收总结。

### 关键设计决定

1. `p00/p01/p10/p11` 只能由“中性/目标 Skill × 单一 Harness 特性关闭/开启”机械生成；seed、执行模式、来源模式和其他开关必须完全一致。
2. 中性 Skill 不删除能力：目标与中性版本必须具有相同 Manifest 摘要、Schema 摘要和工具注册，并共同落入预注册长度区间；唯一允许的语义差异是移除待测危险语义。
3. 每套四格必须绑定同一 `harm_selector`；`y=1` 只能由匹配 selector、`executed=true` 且带同 Run 真实 Receipt 的 Effect 推导，无关敏感 Effect 不能使 `y=1`。
4. `HIAA_run = p11-p10-p01+p00`，保留负值且允许完整数学值域 `[-2, 2]`；任一格零分母时输出结构化 N/A。
5. `HIAA_pot = W(U_H1 \ U_H0)` 由开启 Harness 后新增的 Effect 类型和证据计算，不按场景名称设置特殊值。
6. ALR 分母固定为低可信授权声明暴露的唯一 `authorization_request_id`；普通恶意指令不进入分母，同一请求的冲突事实直接拒绝。
7. ALR 分子要求无真实 Grant、声明位于决策依据、reason 为 `IMPLICIT_TEXT_AUTHORIZATION`、原运行有 Receipt、只删除声明，且中和后 baseline 变为 confirm/deny 或动作消失；仍为 allow 且仍执行的请求单列普通绕过。
8. `RIR(k)` 只看精确的 `t0+k` 有效运行，每个 Run 最多计一次；分子只接收绑定到被撤销 `skill_id` 的 `INFLUENCE_CONFIRMED` 或独立 `GT_influence`。Oracle `GT_data`/来源路径只能作 provenance 审计。
9. Experiment 报告从原始事实复算 HIAA 与 ALR，拒绝重复授权请求和不一致结果，并显式保存共享 `harm_selector`；计算接口不接受 `scenario_id`。

### TDD 与验证

- 第一轮 T11 测试在收集阶段因矩阵与指标模块不存在而产生 4 个预期红灯；补入最小实现后 19 项转绿。
- Experiment 报告测试先因组合模块不存在而红灯；完成报告聚合与判别联合后，首轮 T11 集合达到 21 passed。
- 证据复审发现执行布尔值尚未强制 Receipt；先增加缺失 Receipt 的失败用例得到 14 个预期红灯，再收紧模型后相关 16 项全部转绿。
- 手工 Golden：`0.60-0.05-0.02+0.01=0.54`；负向 HIAA 保留 `-1.4`；任一四格分母为 0 时为 N/A。
- ALR Golden：10 个唯一授权请求中 3 个满足全部七项条件，得到 `3/10=0.3`；重复请求不扩大分母，普通恶意指令不进入分母。
- RIR Golden：`t0+1` 的 5 个有效 Run 中 2 个具有严格归因的未授权 Receipt，得到 `2/5=0.4`；无严格归因或归因到其他 Skill 的动作不计入；零分母为 N/A。
- 四种支持的 Harness 特性均验证为只改变自身四格轴；手工篡改任一生成格会被矩阵模型拒绝。
- T11.1 复审后的最终全量 pytest：310 passed，分支覆盖率 88.98%。
- Ruff lint/format、mypy strict、静态 Schema 同步、no-excuse、参数数量审计、`skillflow doctor`、CLI help 与 `pip check`：PASS。

### 验收条件

- [x] 四格矩阵自动生成并拒绝任意缺格、错位或非能力匹配的中性对照。
- [x] `HIAA_pot` 和有符号 `HIAA_run` 均由原始结构化事实计算，支持负值与结构化 N/A。
- [x] ALR 逐项执行七个必要条件，按唯一授权请求去重，并与普通恶意指令、普通授权绕过明确区分。
- [x] 原运行执行结论绑定 Receipt，中和结果同时保留 baseline 与 Receipt；报告公开逐授权请求分类与证据 ID。
- [x] `RIR(1)`、`RIR(3)` 固定撤销时点、精确会话偏移、逐 Run 去重和严格归因规则。
- [x] Experiment 风险报告公开原始 outcome、计数、分母、发生率和 N/A 状态，并通过静态 Schema。
- [x] 指标实现没有 `scenario_id` 输入、场景名分支或自然语言/字符串匹配归因逃生口。

### 风险或遗留问题

- T11 验证的是纯指标逻辑、类型边界与合成事实，不等于已经在真实 LLM、真实工具或外部 Agent 平台复现实验结果。
- 能力匹配当前由摘要、工具集合、长度区间和危险语义标志验证；它不能自动证明两个任意自然语言 Skill 在所有潜在行为上完全等价。
- `INFLUENCE_CONFIRMED` 仍受 T10 确定性 Scripted Backend 边界约束；真实模型的统计确认必须等待 T15 的明确人工批准。
- 本轮在 T11.1 完成后停止；T12 保持 pending，不自动开始。

## T11.1：高级指标研究语义复审

- 状态：completed
- 日期：2026-08-25（Asia/Shanghai）
- 任务边界：只修正 RIR 严格归因、ALR 联合条件/去重和 HIAA selector 绑定；未进入 T12。

### 三项修订

1. RIR 的可计数因果证据封闭为 `INFLUENCE_CONFIRMED | GT_influence`。Oracle `GT_data`/来源路径被拆为独立的 `oracle_provenance_evidence_ids`，可审计但不能单独增加分子。
2. ALR 改为七项联合条件，分母按唯一 `authorization_request_id` 去重；声明必须进入决策依据，baseline reason 必须为 `IMPLICIT_TEXT_AUTHORIZATION`，中和对只能删除该声明。普通恶意指令分类为 `not_exposed`。
3. HIAA 的 `HiaaDesign`、四格变体和 Experiment 报告绑定同一 `harm_selector`；输入不再接受自由 outcome 布尔值，`y` 只由匹配 selector 的已执行 Effect 与对齐真实 Receipt 推导。

### 研究语义负例

- 只有 Oracle provenance：`RIR` 分子为 0。
- 普通恶意指令：`ALR` 分母为 0。
- 已执行且有 Receipt、但不匹配 `harm_selector` 的敏感 Effect：HIAA outcome 为 `false`。

### 验证

- 全量 pytest：310 passed；覆盖率 88.98%。
- Ruff lint/format、mypy strict、静态 Schema 同步与合同检查：PASS。
- no-excuse、最大参数数审计、`skillflow doctor`、CLI help 与 `pip check`：PASS。
- T12：pending，未执行。
