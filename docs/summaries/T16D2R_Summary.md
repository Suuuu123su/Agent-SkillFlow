# T16-D.2R：v3.1 最小修复总结

## 阶段结论

- T16-D.2R：`COMPLETED`。
- 本阶段真实 API 调用数：0；新增真实模型费用：`$0`。
- 原 T16-D.2 Attempt、Raw Records、预算日志、阶段门、报告和全部 SHA-256 均保持不可变。
- 没有从旧第 8 条 Trial 继续，没有创建或执行新 Canary，没有运行 48 条真实链，没有进入 T16-E，也没有 git push。
- 下一步仍是使用全新的 v3.1 Attempt 重新运行 Canary；本阶段未执行。

## 新协议与配置

| 项目 | 值 |
|---|---|
| protocol ID | `t16-task-success-bridge-preregistration-v3.1` |
| protocol version | `3.1` |
| preregistration schema | `0.3.1` |
| protocol SHA-256 | `9ad38f19e1e9ba87d6c863c988af14b4a6e145338a2f9a79ee4a0b2a489deca4` |
| live config ID | `t16d2r-v3.1-gpt-5.6-luna` |
| live config schema | `0.2` |
| canonical config SHA-256 | `6eedc1313c8ed84d39a7e5788746912ea36dac94c22f29f3331851a6e6c3fe56` |
| max Agent Step | `16` |

新文件为 `experiments/t16/preregistration_task_success_v3_1.yaml`。与 v3 相比，只允许以下变化：

1. preregistration schema/version；
2. protocol ID/version；
3. `budget.max_agent_turns: 8 -> 16`。

测试会把 v3.1 规范化回 v3 后做完整结构比较。Prompt Contract、48 条 Matrix、Scenario、Tool、Manifest、TaskSuccess evaluator、condition/pair、模型、temperature、reasoning effort、输出上限、费用上限和重试上限均未改变。原 Matrix SHA-256 仍为 `695560d3494ca037fa19b84b2bcb9daa5f4f74016da4396ac450f07538e54b56`。

## 为什么是 16 步

- 用户最后明确更正为 16，而不是 12；本实现没有保留隐藏的 12-step 截断。
- 旧真实 Attempt 已证明 8 步不足：`m2-target` 完成前已收到 8 个响应，下一次调用在请求前被拒绝。
- 16 是对旧上限的有限倍增，为四个 M2 Session、Tool 循环及最终结构化结果保留有界余量，同时仍由硬上限阻止无限循环。
- 离线 Mock 已证明 M2 target 能在 16 步内完成；但本阶段禁止真实 API，因此尚不能声称真实模型一定能在 16 步内完成。该结论必须由下一次全新 v3.1 Canary 验证。

## 用量异常保存

新增 `actual-usage-journal.jsonl` 及对应严格 Schema，和原调用前 `budget-journal.jsonl` 并行工作：

1. 每次 Client 调用前，原 Budget Journal 继续先 fsync 保守费用预留；
2. 每次 API 响应返回后，立即累计并 fsync 调用数、已观察 Token 和按冻结费率计算的费用，不等待 Session/Trial 完成；
3. Runner 在 `finally` 中写 Trial 终态：`completed`、`step_limit_exhausted` 或 `partial`；
4. Provider error、Gateway crash、Step 上限和其他异常均保留已发生的累计状态；
5. 没有实际响应时，Token 和费用保存为 JSON `null`，状态为 `not_available`，绝不写成 0；
6. 部分调用有响应、部分调用缺 usage 时，保存已观察小计并标记 `partial`，不把小计冒充完整总量；
7. 日志不保存 Prompt、模型响应正文、API Key 或其他凭据。

网络硬阻断的手工离线复现得到：Client 调用 16 次，第 17 次调用前停止；终态 `step_limit_exhausted`；16 个响应全部保存，input Token 1,600，已观察估算费用 `$0.0004928`，调用前保守预留 `$0.03269415`。这些数字只来自脚本 Client，不是供应商账单或真实模型结果。

## v3 与 v3.1 隔离

- v3 和 v3.1 使用不同 protocol/config ID、preregistration SHA-256、phase contract 与未来 Attempt 目录。
- v3.1 preflight 把完整 live config 纳入 phase contract。
- 阶段门新增 `phase_contract_mismatch`：同一统计输入中出现两个不同 phase contract 时立即拒绝，因此旧 v3 与新 v3.1 Raw Records 不能合并。
- 没有修改研究指标或旧 Trial 的实验结果。

## 原 Attempt 不可变性

目录：`runs/t16d2-v3-live-20260829-01/attempt-01/`

| 文件 | 修复后复核 SHA-256 |
|---|---|
| `bridge-report.json` | `79af70b489dce77d1d45c30e9da012ef74c4124963be17e41c4e84064245c124` |
| `budget-journal.jsonl` | `bbd31d17e0d9f60e0b2cf5623cf64d81a6dd7540d4373d316041156cf86767e2` |
| `checkpoint-007.json` | `14cca080112bf406023f7cf5b93f48d174eb6b9457296abb9d20d941dbaa6806` |
| `preflight.json` | `7b46d8c75e752aa7ef7007079fd26459da0131f77eadecdc4c192a7b4d3cc50c` |
| `raw-trials.jsonl` | `911158a920488c50cd9676ede396e30c8c88d90f05e882e7efce8025613c34d6` |
| `run-summary.json` | `a9b24ae89ba0a5abe17c8eff9948baeb7e9be4260332f4b8fae5e608e8595348` |
| `stage-gate-canary.json` | `9ec886d238089b41ed5390f8271f9b62edbc313ee3b8fa0502789f184e02c009` |

7/7 文件均与修复前冻结值逐字节一致。

## 测试与质量门槛

- 红阶段：新增测试首先因缺少 `live_usage_store` 导入失败，证明测试在实现前确实为红。
- 最终修复/回归测试：21 passed；覆盖 16 步 M2、17 步前拒绝、逐响应用量、Step/Provider/Gateway finally、N/A/partial、日志完整性、禁网、旧哈希和跨协议拒绝合并。
- 最终全量 pytest：`800 passed in 240.00s`。
- 最终分支覆盖率：`90.15%`，通过 90% 门槛。
- JUnit：`.tmp/t16d2r-full-final-01/junit.xml`。
- Coverage XML：`.tmp/t16d2r-full-final-01/coverage.xml`。
- Ruff lint：PASS；Ruff format：409 个 Python 文件一致。
- mypy strict：262 个源文件 PASS。
- 静态 Draft 2020-12 Schema 检查：PASS；新增 `schemas/t16d2r-usage-event.schema.json`。
- `pip check`：PASS。
- 全部测试只使用 Fake/Mock/脚本 Client；意外网络路径被测试硬失败。

第一次全量回归虽然 789 项功能测试全部通过，但覆盖率为 89.97%，未达到门槛，因此没有把该运行记为 PASS。补充 N/A、partial、重复终态和损坏 sequence 边界测试后，最终独立全量运行达到上述 800/800 与 90.15%。

## 已知限制与下一步

- 本阶段没有真实模型证据；不能据此判断 v3.1 Canary 会完成，也不能形成任何新的 HIAA、ALR、RIR、UEA 或 TaskSuccess 研究结果。
- `gpt-5.6-luna` 仍只有公开 alias，没有不可变 Provider revision snapshot。
- 下一步：全新目录、全新 Attempt 的 v3.1 Canary，保持 pending，未执行；必须由用户另行明确启动。
