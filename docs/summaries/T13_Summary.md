# T13 中文总结：CLI、报告与端到端复现

## 结论

T13 已完成。研究者现在可以用一条离线命令从 `scenarios/matrix/mvp.yaml` 得到双轨 Trace、脱敏安全图、标准 Run/Replay 结果、HIAA/ALR/RIR 聚合、CSV 和 Experiment 报告；也可以用独立命令复算图、Run 报告、Replay 与聚合结果。

本轮没有进入 T14，没有新增真实 Harness Adapter。所有验收仍使用固定 `fixture://` Scripted Skill、合成 Oracle、进程内 Mock Tool 和 Run 独占 workspace；“完整成功”只指确定性研究框架闭环成功，不代表真实 LLM 或生产平台上的攻击效果。

## CLI 交付

| 命令 | 作用 | 关键边界 |
|---|---|---|
| `validate-manifest` | 校验 Manifest | 不加载或执行 Skill |
| `validate-scenario` | 校验 Scenario | 不运行 fixture |
| `run` | 运行一个 Scenario | 自动创建 single-run Experiment；默认脱敏 |
| `analyze` | 重算 Run 报告 | 从共享 SQLite、Blob 元数据和双轨 JSONL 恢复事实 |
| `graph` | 重建安全图 | MVP 只支持脱敏 JSON |
| `factorial` | 运行单一 Harness feature 的二水平实验 | 只接受预注册布尔轴和整数 seed |
| `matrix` | 执行完整 Matrix | 核心 Run、隔离复跑、Replay 和聚合一次完成 |
| `replay` | 中和一个已注册 Artifact | 从持久化 Run 找回 alias 并执行成对反事实 |
| `aggregate` | 重算 Experiment 指标 | 只读取标准 RunResult/ReplayResult |
| `export` | 导出 Run 或 Experiment 报告 | Schema 复验、默认脱敏、目标不可覆盖 |

已知命令错误使用结构化错误码和稳定退出码：输入错误为 2、资源不存在为 3、输出冲突为 4、执行失败为 5。错误正文不回显 Blob、fixture 原文或内部堆栈。

## 标准产物

```text
runs/<experiment_id>/
├── experiment-manifest.json
├── aggregate-metrics.json
├── summary.csv
├── experiment-report.json
├── state.sqlite
├── blobs/
│   └── determinism/...       # 只做一致性检查
├── runs/<run_id>/
│   ├── run-manifest.json
│   ├── observed-trace.jsonl
│   ├── oracle-trace.jsonl
│   ├── graph.json
│   └── run-report.json
└── replays/<replay_id>/
    ├── pair-manifest.json
    └── replay-report.json
```

`RunManifest` 保存相对 Scenario 引用、变体、seed、backend、角色、脱敏状态、任务结果和派生产物 SHA-256。`ExperimentManifest` 保存入口类型、核心 Run/Replay ID 及确定性指纹。标准报告不保存宿主绝对路径、Blob 正文、Tool 参数明文或 fixture marker。

## 报告契约

### RunResult

Run 报告保留：

- `run_id`、`experiment_id`、相对 Scenario、变体、seed、backend；
- `task_success`、selector 对齐的 `harm`；
- UEA 实例/类型/权重和来源 Precision/Recall/F1；
- Effect、授权真值、baseline/policy/executed Decision、Receipt；
- 决策依据 Artifact、证据 Event、来源到落点路径；
- Matrix 角色、四格/设计、授权条件和撤销后检查偏移。

顶层 Effect、Decision、执行布尔值与 Receipt 必须与结构化 Effect 结果逐项对齐；`harm=true` 必须有 selector 匹配的同 Run Effect/Receipt。

### ReplayResult

Replay 报告保留原始/中和 Run、干预 Artifact、两分支 Effect/Receipt、Effect diff、baseline 结果、同输入控制、CI 和确认影响边。CI 必须机械等于 `int(y_original)-int(y_neutral)`；确认边必须且只能指向对应差异 Effect。

### ExperimentReport

Experiment 报告保留核心 Run/Replay ID、原始计数、两套独立 HIAA 四格、ALR 分类与唯一授权请求、撤销事实、RIR₁/RIR₃ 分子分母和值。三个层级以 `report_scope=run | replay | experiment` 形成判别联合，并共同通过静态 `risk-report.schema.json`。

## 聚合纪律

### 确定性重复

Matrix 的 24 个核心配置各运行 5 次：第一次是核心 Run，其余 4 次是隔离副本。副本沿用相同 run ID、seed、虚拟时间和规范化报告角色，比较 Observed Trace、Oracle Trace、Graph 与 RunResult 指纹；副本只位于 `blobs/determinism/`，不进入 Experiment `run_ids`、CSV 或任何指标分母。

### HIAA

聚合器先按 `hiaa_design_id` 分组，再要求整套四格只有一个 `harm_selector`。每格 outcome 只读取 RunResult 中 selector 匹配且有同 Run Receipt 的 harm Effect。C1、C2 两套正式矩阵结果均为 `(0,0,0,1)`，所以两套 `HIAA_run=1.0`。

### ALR

聚合器从 RunResult 读取真实 Grant、声明 trust、决策依据、baseline reason 与原 Receipt，从 ReplayResult 读取“只删除声明”、其余输入保持、neutral baseline 和 neutral Receipt。只有七项条件联合成立才算授权洗白，分母按唯一 `authorization_request_id` 去重。正式 Matrix 结果为 `ALR=1/2`：一个请求为洗白，另一个结构化确认暴露不进入分子。

### RIR

聚合器只把 ReplayResult 中 `CI=1` 且存在 `INFLUENCE_CONFIRMED` 的 selector alias，与撤销后精确 `t0+k` Session 的未授权 Receipt Effect 对齐。Oracle `GT_data` 和来源路径不会单独增加分子。正式 Matrix 结果为 `RIR_1=1/2`、`RIR_3=1/2`，分母同时保留攻击与能力匹配控制。

## 任务书原样验收

以下命令在离线环境中完整成功：

```powershell
skillflow matrix scenarios\matrix\mvp.yaml --backend scripted --output runs\mvp
```

逐项检查结果：

| 项目 | 实测 |
|---|---:|
| 核心 Run | 24 |
| Replay | 18 |
| 确定性检查 | 24 |
| 每项重复次数 | 5 |
| 一致检查 | 24/24 true |
| 隔离重复副本 | 96 |
| CSV 核心数据行 | 24 |
| HIAA design | 2，均为 1.0 |
| ALR | 1/2 |
| RIR₁ | 1/2 |
| RIR₃ | 1/2 |

24 个 Run 子目录和 18 个 Replay 子目录均按标准文件白名单检查，没有缺失或额外文件。根目录恰有 5 个标准文件和 `blobs/`、`runs/`、`replays/` 三个标准子目录。

## 测试与质量门禁

- 全量 pytest：**366 passed**；
- 总覆盖率（含分支）：**89.58%**，高于当前 80% 门槛；
- T13/T10 定向回归：**17 passed**；
- Ruff lint：PASS；Ruff format：PASS；
- mypy strict：PASS，**161 个源文件**无类型问题；
- 静态 Schema 确定性重生成与同步测试：PASS；
- no-excuse：本轮新增/显著修改模块均低于 250 个非空非注释行；最大参数数审计：PASS；
- `skillflow doctor`、根 CLI help、`pip check`：PASS。

## 已知边界与停止点

- 当前 backend 只允许 `scripted`，不应把固定合成实验的比率外推为现实攻击成功率。
- GraphML/HTML 是任务书明确允许的可选增强，T13 MVP 只实现 JSON。
- 派生产物可由持久化事实复算，但 Blob 内容本身仍是受控运行态输入，不属于公开报告。
- 本轮到 T13 为止。T14 保持 `pending`，未执行。
