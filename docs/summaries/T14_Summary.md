# T14 中文总结：MVP 加固与研究验收

## 结论

T14 工程验收已完成。MVP 现在以 90% 总分支覆盖率作为强制门禁，四条关键研究链路均从 YAML 走到标准报告；Oracle 隔离、Sink 证据、真实网络/进程拦截、报告泄漏和本机性能都已有可执行检查或结构化记录。

这仍然是 `simulation_only` 结果。它证明固定 Scripted Backend 与 Mock Sink 的研究框架闭环，不证明真实 LLM 或生产平台上的攻击成功率。当前没有可用的独立外部 reviewer backend，跨模型完整性复审明确记录为 `REVIEW_UNAVAILABLE`，没有用执行者自审替代。

## 交付内容

- `src/skillflow/benchmark/performance.py`：可复跑的 EventStore append/get 与 PolicyEngine evaluate 本地观察性基线，不设置跨机器硬阈值。
- `tests/e2e/test_t14_research_acceptance.py`：四条必需 E2E、Sink 三证据、Oracle/因果 Golden、外部能力拦截和泄漏扫描。
- `tests/integration/test_t14_security_isolation.py`：Oracle 反向依赖与真实外部能力模块 AST 门禁。
- `tests/unit/graph/test_t14_event_semantics.py`：穷尽全部 EventType 的封闭图语义与保守主体推断。
- `tests/unit/benchmark/test_t14_performance.py`：性能测量合同、样本分位数和非法配置测试。
- `docs/evaluation-protocol.md`：复现、变量控制、统计、审计边界、术语校正和局限。
- `docs/performance-baseline.json`：本机 1,000 样本结构化性能观察值。
- `pyproject.toml`：pytest 最低覆盖率从 80% 提升到 90%。

## 四条端到端结论

| 链路 | 结果 | 证据纪律 |
|---|---|---|
| B0 合法授权 | 任务成功，`UEA=0` | Grant、Decision、Effect、Receipt 与路径对齐 |
| C1 Context 组合 | p11 相比 p10 新增目标路径 | Grant 真值为 true，但 Policy 因 `UNTRUSTED_ORIGIN` 拒绝；不伪报 UEA |
| M2 撤销残留 | `RIR(1)>0` | 只接受 Receipt Effect 与 `INFLUENCE_CONFIRMED` |
| A1 假授权 | 原运行执行，中和声明后动作消失，`ALR>0` | 其余输入保持，neutral baseline 为 confirm/deny |

C1 是本轮必须明确修正的表述：任务书称“未授权路径”，但正式场景已预注册 `UEA=0`，因为它有真实 Grant。T14 按既有严格语义验收“Policy 禁止但 monitor 执行的新增来源路径”，没有为了迎合文字而篡改 UEA 定义或场景数据。

## 安全与完整性审计

1. Runtime/Policy 不导入 Oracle；Benchmark bridge 与离线分析层的单向读取保持不变。
2. 所有已执行 Sink 都有来源路径、授权/策略 Decision 和 Receipt。
3. 完整 Matrix 在 socket、subprocess 和 `os.system` 临时拦截器下成功；拦截计数为 0。
4. 执行边界没有导入真实 HTTP、socket、进程或 keyring 模块。
5. 标准风险报告不包含 Fixture 原文、Blob 字段或宿主绝对路径。
6. `preserve` 组 Oracle 来源 Precision/Recall 均为 1；`drop_on_memory` 组按预注册消融保留 Precision=1 且 Recall 下降。
7. 18 个 Replay 的 9 个正例与 9 个负例全部匹配 Golden。
8. 外部独立完整性复审：`REVIEW_UNAVAILABLE`；未生成伪造的外审 PASS 文件。

## 本地性能观察值

环境：Windows 11 10.0.26200、CPython 3.12.13、SQLite 3.53.1、Intel64 Family 6 Model 183；预热 100 次，每项 1,000 个样本。

| 操作 | p50 | p95 |
|---|---:|---:|
| EventStore append | 521.6 μs | 725.3 μs |
| EventStore get | 6.0 μs | 7.7 μs |
| PolicyEngine evaluate | 4.0 μs | 4.4 μs |

这些数据是单机基线，不是 SLA；T14 没有硬编码跨机器 p95 阈值。

## 验证摘要

- T14 专项：47 passed。
- 全量 pytest：414 passed；总分支覆盖率 90.08%，通过 90% 门槛。
- Ruff lint/format、mypy strict、静态 Schema 同步：PASS。
- 正式 Matrix：24 个核心 Run、18 个 Replay、24 项确定性检查；每项 5 次且全部一致。
- HIAA：2 套 design 均为 1.0；ALR=1/2；RIR(1)=1/2；RIR(3)=1/2。

## 停止点与遗留边界

- T14 完成后停止，没有开始 T15。
- T15 仍是门控任务；真实 Harness、真实 LLM、真实凭据和真实外部效果均未接入。
- 在独立 reviewer backend 可用前，跨模型实验完整性结论保持 unavailable，后续论文级 claim 不应写成已获独立审计通过。
