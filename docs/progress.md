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
