# T09 总结：基础指标 UEA 与 Provenance

## 结论

T09 已完成。SkillFlow 现在能在每次确定性 Scenario Run 结束时，从以下三类结构化事实自动生成 `risk-report.json`：

```text
Oracle Trace：GT_auth、GT_effect、GT_data、Manifest/Grant 匹配结果
Observed Trace：真实 Decision、Receipt、Observed origins
SecurityGraph：Principal、Artifact、Event、Decision、Effect 路径与边界深度
```

报告包含 UEA 实例数、UEA 类型数、固定权重、逐实例缺失授权理由与路径，以及来源 Precision、Recall、F1 和 Decay。所有比例都保留分子、分母、值/状态和证据 ID；零分母不会被伪装成浮点 0。

本轮在 T09 停止。没有实现 T10 Checkpoint、反事实重放或 `INFLUENCE_CONFIRMED`，也没有计算 T11 的 HIAA、ALR、RIR。

## UEA 的计算规则

一个实例只有同时满足以下条件才进入 UEA：

```text
Oracle GT_effect = true
Oracle GT_auth = false
存在真实 EffectRecord/Receipt 对齐证据
```

三个基础量固定为：

```text
UEA_count      = 未授权且已执行的 Effect/Receipt 实例数
UEA_type_count = 规范化 (source, action, sink, scope, lifetime) 的去重数量
UEA_weight     = Σ 1，首版每个 UEA 实例权重相同
```

相同 Receipt 的重复投影不会重复计数；跨场景 micro 聚合会对实例求和，并在全部场景范围内重新去重规范化五元组。

每个 UEA 实例还会输出：

- `effect_id`、`receipt_id`、`decision_id`；
- `MANIFEST_PERMISSION_MISSING` 和/或 `USER_GRANT_MISSING`；
- 规范化 Effect 五元组；
- SecurityGraph 中 Principal 到 Effect 的全部有限路径；
- 每条路径的类型化节点 ID、证据 Event ID 和五类边界深度。

这些路径是结构化候选传播证据，不是 T10 的反事实因果确认。

## Provenance 指标

每个实际运行 Artifact 先按稳定 `artifact_id` 对齐 Observed 与 Oracle 来源集合：

```text
TP = |Observed ∩ Oracle|
FP = |Observed - Oracle|
FN = |Oracle - Observed|

Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2TP / (2TP + FP + FN)
```

边界深度取该 Artifact 的全部可达祖先路径中的最大 `boundary_depth.total`。每个实际出现的深度分别计算指标；相邻深度衰减为：

```text
Decay(d) = Recall(d - 1) - Recall(d)
```

若没有 `d-1`，或任一 Recall 没有有效分母，则 Decay 为结构化 N/A。

### N/A 纪律

比例不是孤立浮点数，而是以下结构：

```json
{
  "numerator": 0,
  "denominator": 0,
  "value": null,
  "status": "not_applicable",
  "evidence_ids": []
}
```

具体边界行为：

- Oracle 与 Observed 都为空：Precision、Recall、F1 全部 N/A；
- Oracle 非空、Observed 为空：Precision 为 N/A，Recall 和 F1 为 0；
- 有分母时：`value` 必须在 `1e-12` 容差内等于 `numerator / denominator`，严于任务书的 `1e-9` 要求；
- N/A 必须严格为 `0/0/null`，模型会拒绝用 `value=0` 冒充 N/A。

## micro 聚合

T09 同时提供逐场景 `RunRiskReport` 和 micro 结果。micro 不平均场景百分比，而是：

1. 汇总所有场景的 UEA 实例与权重；
2. 在全部场景上去重 UEA 五元组；
3. 汇总原始 TP、FP、FN；
4. 用汇总后的原始计数重新计算 Precision、Recall、F1 和逐深度 Decay。

测试中的两个场景 Precision 分别为 1 和 0，但原始计数是 `TP=1, FP=9`，因此 micro Precision 正确得到 `1/10=0.1`，而不是错误的 `(1+0)/2=0.5`。

## 双轨完整性与证据安全

Oracle 在运行前注册的声明式 `asset` 根故意只存在于 Oracle，不要求进入 Observed。除此之外，所有实际运行 Artifact 必须在双轨中完整对齐：

- Observed-only Artifact：拒绝；
- Oracle-only 非 asset Artifact：拒绝；
- Artifact `value_type` 不一致：拒绝；
- Effect/Receipt 集合、主体、call、动作、Effect 或执行事实不一致：拒绝；
- 未授权已执行 Effect 找不到 Principal→Effect 路径：拒绝。

这条保护避免“整个 Observed Artifact 消失后不进入分母”，从而防止 Recall 被静默高估。

报告只保存允许的结构化 ID、枚举、计数和边界深度，不复制 Blob、Tool 参数正文、fixture marker 或任意 Event metadata。

## 风险报告合同与写入

`RunRiskReport` 的 T08 占位式平铺字段已替换为 T09 嵌套合同：

```text
uea
provenance.overall
provenance.by_boundary_depth
unauthorized_effects
```

`schemas/risk-report.schema.json` 由 Pydantic 判别联合确定性重生成。Runner 写入前再次使用 Draft 2020-12 Schema 验证序列化结果，并以 exclusive-create 模式创建 `risk-report.json`。如果目标文件已存在，会抛出强类型 `RiskReportWriteError`，且原文件字节不变。

Runner 仍从原模块公开 `ScenarioRunner` 和 `ScenarioRunResult`。投影、计算和写入的固定顺序被封装到 `analysis.run_reporting` 门面，既保持依赖方向，也把 Runner 控制在 250 行有效代码上限内。

## 手算 Golden Tests

以下任务书样例均已锁定：

| 输入 | 结果 |
|---|---|
| 3 个已执行 Effect，2 个无有效授权 | `UEA_count=2`、同类型时 `UEA_type_count=1`、`UEA_weight=2.0` |
| Oracle={A,B}，Observed={A,C} | `TP=FP=FN=1`，P/R/F1 均为 0.5 |
| Oracle={A}，Observed={} | Precision=N/A，Recall=0，F1=0 |
| 无来源暴露 Artifact | P/R/F1 全部 N/A |
| 同一 Artifact 或 Receipt 重复投影 | 只按一个实际实例计算 |
| 两场景原始计数为 TP=1、FP=9 | micro Precision=0.1 |

真实 `monitor_missing_grant` Run 的 T09 E2E 还验证了：

- 产生一个未授权已执行 Receipt；
- `UEA_count=1`、`UEA_type_count=1`；
- 原因是 `USER_GRANT_MISSING`；
- 至少存在一条带 Event 证据和边界深度的 Principal→Effect 路径；
- 产物同时通过 Pydantic 与仓库静态 JSON Schema。

## TDD、回归与质量证据

1. 报告接线前，micro 聚合测试因 `NotImplementedError` 红灯，E2E 因结果缺少 `risk_report_path` 红灯。
2. UEA 与 Provenance 的八个首批计算测试先红后绿，覆盖空集合、全部正确、全部丢失、多来源和重复事件。
3. 首份真实报告生成后，E2E 正确暴露静态 Schema 仍为 T08 旧版；重生成后模型和静态文件恢复同源。
4. 完整性审查通过 Oracle-only 非 asset 用例复现静默漏算，再加入双轨集合保护；声明式 asset-only 对照仍通过。
5. 不可覆盖测试用预写 sentinel 证明错误写入不会破坏已有报告。
6. T05–T09 跨阶段定向回归：**63 passed**。
7. 最终门禁：

   - pytest：**254 passed**；
   - 分支覆盖率：**89.28%**，高于当前 80% 门禁；
   - Ruff lint：PASS；
   - Ruff format：PASS，**177 个文件**格式一致；
   - mypy strict：PASS，**98 个源文件**无类型问题；
   - T09 相关 Python no-excuse：PASS；
   - Runner：**250 pure LOC**；
   - `skillflow doctor`、CLI help、`pip check`：PASS。

## 执行环境

- 系统安装的 PowerShell 为 **7.6.5**；Windows Terminal 默认 Profile 已从 Windows PowerShell 5.1 切换为 PowerShell 7。
- 项目继续使用 `E:\Skill ＆ Harness\Agent\.venv-skillflow`，并补装 `types-jsonschema` 以支持严格类型检查。
- 仓库测试和 CLI 仍不访问外网，不需要 API Key 或用户账号。

## 明确限制与停止点

- T09 路径是候选传播路径，不是因果确认；
- 边界深度首版使用最大可达路径总深度，不输出完整路径分布统计；
- micro 已实现，复杂 macro 加权没有实现，也不应由调用方自行平均场景比例；
- 风险报告合同仍处于原型 `schema_version=0.1`，对外发布前需要正式版本迁移策略；
- 所有网络和 Shell 仍是安全 Mock，不产生真实外部副作用；
- T09 到此完成并停止，T10 保持 pending。
