# T16-B 中文总结：Fake Provider 全量实验演练

## 结论

T16-B 已完成。两个逻辑 Fake Model Slot 按 T16-A 冻结的 12 个条件、10 个语义实例和 3 次重复，完整调度并保存了 720 条实验链。所有运行均满足 `simulation_only=true`，Fake Provider 实际计费为 0 美元；本阶段没有读取 API Key、调用真实 LLM、访问真实网络或执行 T16-C。

必须先明确结论边界：本轮 `harm=180`、`completed_without_harm=540` 只是确定性 Fake 规则为验证保存、分类和聚合管线而产生的操作性计数，不是现实攻击成功率，不能用于评价任何真实模型的安全性。两个 Fake Slot 和三次 Fake 重复也不是独立统计样本。

## 720 条运行结果

运行公式为：

```text
12 个条件 × 10 个语义实例 × 3 次采样 × 2 个 Fake Slot = 720 条
```

正式运行结果：

- 已调度 720 条，唯一 `trial_id` 为 720 个；重复 `trial_id` 在进入统计前直接拒绝。
- 共产生 960 次本地 Fake Provider 调用；M2 每条链使用 3 次调用，其余条件每条链使用 1 次。
- 模拟用量合计为 input 158,400、cached input 33,600、output 52,800、reasoning 13,200 token；Fake 账单费用仍为 0。
- 720 条 provenance 全部为结构化 `not_available`，`metric_value=null`；没有把缺失 Hook 记成安全值 0，也没有接受模型自报来源。
- 完整 JSONL 保存在 `runs/t16b-fake-20260826-01/trial-results.jsonl`，共 720 行；SHA-256 为 `7433c1a5ce9d94e9d53ade63cd4a5cb69ba8c5af4920a2247d5c75ac49079fc3`。

## Matrix 完整性

- 12 个条件、每条件 10 个唯一语义实例、每实例 3 个 repeat、2 个 Fake Slot 均完整。
- target/neutral/control 在相同槽位、配对组、语义实例和 repeat 下共享唯一 `pair_id`。
- C1 四格共享 `effect-selector:context-harm`，没有让无关 Effect 改写四格结果。
- M2 target/control 的每条链都同时生成 Session 1、3 的结构化观察；target 的已执行 Effect 分别绑定 Receipt，control 保持未执行。
- 60 条 A1 neutralized 链的干预审计都只删除 `authorization_claim`，并显式保持 Tool、Skill、Manifest、授权结构、数据格式、长度区间和任务模板。
- 统计分母按预注册唯一单位去重：唯一 condition-instance 为 120，唯一 pair-instance 为 70；Slot 与 repeat 不扩大这两个分母。

## 失败注入

10 类必需失败和 2 类分类对照全部被安全收敛：

| 类别 | 结果 |
|---|---|
| Provider timeout、rate limit、Gateway crash | 结构化为 `invalid_other` |
| 缺少 Receipt、缺少 Token 使用信息 | Schema 拒绝 |
| 超过单 Run 费用、总费用 | 调用前停止 |
| 超过最大 Agent Step | `agent_turns` 上限停止 |
| 第二次重试（配置只允许一次） | `retries` 上限停止 |
| 意外网络访问 | 硬失败保护层拦截；测试中的 socket 原语未建立真实连接 |
| refusal、no-call | 都属于原有 `invalid` 三分类，但保留为两个不同的操作性子类 |

故障注入与正式 720 条正常演练分开保存和汇总，不污染 Matrix 分母。

## 费用模拟

以下价格只是假设费率，用于验证算式和停止逻辑，不是任何厂商的现实价格：

| 链长 | 正常费用 | 最坏费用 |
|---|---:|---:|
| 短链 | $0.00190 | $0.00760 |
| 普通链 | $0.00595 | $0.01680 |
| M2 多 Session 长链 | $0.02764 | $0.07800 |

单 Run、总费用、Agent Step 和重试上限均通过。总预算演练在尝试第 3 条结果时停止，停止前 2 条已经逐行 flush 并保留在 `budget-stop-results.jsonl`；其 SHA-256 为 `9e691c0bf47e819b60ab88826f116f389ff0fbe519b024c3a27ba74f67764c89`。

## 交付物

- `experiments/t16/t16b_fake_dry_run.yaml`
- `src/skillflow/experiment/t16/dry_run*.py`
- `schemas/t16b-dry-run-summary.schema.json`
- `docs/evidence/t16b-fake-run-summary.json`
- `docs/evidence/t16b-matrix-integrity.json`
- `docs/evidence/t16b-failure-injection.json`
- `docs/evidence/t16b-cost-simulation.json`
- T16-B 单元、集成、端到端与拒绝路径测试

## 正式验证

- 全量 pytest：508 passed；总分支覆盖率 90.25%，通过 90% 门槛。
- Ruff lint：PASS；Ruff format：306 个 Python 文件格式一致。
- mypy strict：PASS，191 个源文件无类型问题。
- 静态 Schema 与禁网安全定向检查：11 passed。
- `pip check`：PASS。
- 正式 Fake 运行：720/720 可调度，720 个 `trial_id` 唯一，12/12 故障/分类注入安全收敛，6/6 费用画像完成。

## 局限与停止点

- Fake 行为由预注册结构因素机械产生，不包含真实模型生成、拒绝倾向、工具选择或跨模型差异。
- Fake `harm` 和完成计数只能证明数据路径与分类器工作，不能写成真实 ASR 或模型安全结论。
- 假设价格只能验证费用公式和上限，不代表 T16-C 的实际供应商价格。
- 本阶段没有平台 provenance Hook 或独立 Oracle，因此 720 条来源结果全部是结构化 N/A。
- 按本阶段禁网约束，独立外部模型复审记为 `REVIEW_UNAVAILABLE`；没有生成伪造的审计 PASS。
- T16-C 保持 pending。只有用户明确授权真实费用后才能开始；本轮停止于 T16-B，没有自动 Git push。
