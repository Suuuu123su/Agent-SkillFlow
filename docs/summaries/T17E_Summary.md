# T17-E Summary

**状态：INCOMPLETE。** T17-E 的 24 core + 18 replay Canary 门未通过；T17-F、T17-G、T17-H 未启动，也不得标记完成。

## 阶段门结论

最新不可变 Attempt 完成了 16/24 core 与 12/18 replay；另有 1 个 M2 core 已获得 3/3 API 响应，但因模型没有产生后续步骤所需的 artifact:m2-memory-1，旧执行器以裸 KeyError 退出，未写终态。该行为已在提交 4d726b0 中改为可审计的 evidence_binding/failed 终态。

预注册规定确定性 no-call/缺失必需 Tool 结果不补采、不改 Prompt。因此本轮停止，不再发送付费请求；继续运行必须建立明确命名的 T17-v2 协议修订，不能伪装成原 T17 的重试。

## Immutable Attempt 记录

| Campaign | Core | Replay | API/响应 | 实际估算 | 保守占用 | 终止原因 |
|---|---:|---:|---:|---:|---:|---|
| t17-live-20260902-01 | 0 | 0 | 0/0 | $0 | $0 | 请求前取消 |
| t17-live-20260902-02 | 0 | 0 | 1/0 | $0 | $0.0009499 | Provider 400；Structured Output 使用了不支持的 uniqueItems |
| t17-live-20260902-03 | 16 | 12 | 81/81 | $0.0137336 | $0.0137336 | 512 输出上限被 42 visible + 470 reasoning token 用尽 |
| t17-live-20260902-04 | 3 | 3 | 17/17 | $0.0023986 | $0.0023986 | 有效 no-effect 路径触发过严 Oracle 断言 |
| t17-live-20260902-05 | 16 | 12 | 83/83 | $0.0157836 | $0.0157836 | M2 必需 Tool 结果缺失；Attempt 未终态化 |

OpenAI 官方 Responses 文档明确说明 max_output_tokens 同时包含可见输出与 reasoning token，并以 incomplete_details.reason=max_output_tokens 表示截断：[Create a model response](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)。

## 最新 Attempt 的 Partial 任务指标

这些值只描述 t17-live-20260902-05 已完成的 core，不发布为 scheduled 正式指标，也不与其他 Attempt micro 聚合。

| 指标 | 状态 | numerator / observed | scheduled | observed-only 点值 |
|---|---|---:|---:|---:|
| Completion | incomplete | 28 / 28 terminal | 42 | — |
| TSR | incomplete | 12 / 16 | 24 | 0.7500 |
| Safe TSR | incomplete | 7 / 16 | 24 | 0.4375 |
| Benign refusal | incomplete | 0 / 16 | 24 | — |
| Benign task failure | incomplete | 1 / 16 | 24 | — |
| Replay Influence coverage | incomplete | 12 / 12 terminal | 18 | — |
| Cluster bootstrap | not_applicable | — | 单 Canary cluster | — |

incomplete Ratio 的正式 value 与 Wilson 区间保持 null；上表点值仅是 observed-only 描述，不能替代 scheduled 估计。

## 完整指标组状态

| 指标组 | 状态 | 原因 |
|---|---|---|
| 证据完整性 | incomplete | 最新 Attempt 28/42 单元有不可变终态，另 1 core 仅有完整用量日志 |
| 任务效用 | incomplete | scheduled core 分母未闭合 |
| 操作与授权风险 | incomplete | 正式 Phase Report 被阶段门阻断 |
| 来源 Precision/Recall/F1 | incomplete | 正式 Phase Report 被阶段门阻断 |
| Replay CI、HIAA、ALR、RIR | incomplete | 12/18 replay，不能发布正式值 |
| Model1 稳定性 | incomplete | Canary 未闭合 |
| Model2 / 跨模型 | not_available | T17-G 未启动 |
| Defense Security Gain | not_available | T17-H 未启动 |
| 效率与费用 | measured | 五个 Campaign 的实际用量 Journal 可审计 |

## 累计效率与费用

- API 请求/响应：182 / 181
- Input / cached input / visible output / reasoning token：26,253 / 0 / 6,319 / 15,902
- 实际费用估算：$0.0319158
- 保守占用：$0.0328657
- 已批准 Campaign 总门：$0.25
- 剩余保守空间：$0.2171343

这些是 API 用量的工程费用估算，不等同于已确认账单。

## 修复与验证

- c7cb10c：移除 OpenAI strict JSON Schema 不支持的 uniqueItems，保留 Runtime 重复动作拒绝。
- 94f8720：识别 status=incomplete 与 max_output_tokens；统一 T17 输出上限为 2048。
- 22d36eb：允许 Reference no-effect 路径，同时保持实际 Effect/Artifact 来源校验。
- 4d726b0：把缺失必需 Scenario 输入转换为运行时安全的 typed failure，并由 Stage 记录为 evidence-binding 失败。
- 当前代码静态门：Ruff 通过；strict mypy 325 个源文件通过。
- 最新直接回归：3 passed。按用户指令，后续修复没有重跑全量测试。
- 较早完整基线为 873 passed、90.03% branch coverage；它不代表最后四个 Live 修复后的全量结果。

## 证据

- Partial 审计：docs/evidence/t17-e-canary-partial-audit.json
- Audit SHA-256：2dc31aa358128dac75eaa5366b5a86b41b66ae35445e8953beddced89069bcdb
- Raw 根目录：runs/t17-live-20260902-01 至 runs/t17-live-20260902-05
- 所有失败 Attempt、Journal、Trial 索引与 Raw 均保留本地，未改写、未合并、未删除。
