# T18 本地完整可复算数据

两个独立执行域：固定脚本 `scripted` 完成 264 个任务、16 对重放；模拟接口 `fake_reference` 完成 44 个任务、5 对重放。全部内容来自本地合成任务与受控执行器，真实 API 调用和费用均为 0。

## 直接查看

| 内容 | 固定脚本 | 模拟接口 |
|---|---|---|
| 全部指标、诊断与防御比较 | [JSON](scripted/reports/metrics.json) | [JSON](fake_reference/reports/metrics.json) |
| 可筛选的指标长表 | [CSV](scripted/reports/summary.csv) | [CSV](fake_reference/reports/summary.csv) |
| C1/C2 四格、两种分母与失败计数 | [CSV](scripted/reports/hiaa.csv) | [CSV](fake_reference/reports/hiaa.csv) |
| 文件清单及 SHA-256 | [清单](scripted/manifest.json) | [清单](fake_reference/manifest.json) |
| 固定阶段合同 | [合同](scripted/phase-contract.json) | [合同](fake_reference/phase-contract.json) |

每域还包含 `preregistration.json`、`matrix.json`、`catalog.json`，以及 `cores/` 的全部逐任务事实和 `replays/` 的全部成对事实。事实含事件、来源、授权、实际效果、回执、任务判定与诊断引用，不需要私有运行目录才能计算指标。

## 计划要求的明细表

根目录同时提供[逐任务](core-trials.jsonl)、[逐重放](replay-pairs.jsonl)、[逐请求诊断](diagnoses.jsonl)、[建议与实际防御](defense-plans.jsonl)、[配对结果](defense-outcomes.jsonl)、[诊断指标](diagnosis-metrics.json)、[单项防御表](defense-specificity.csv)、[路由比较表](router-comparison.csv)和[逐技能指标](skill-metrics.csv)。[明细清单](sha256-manifest.json)登记来源阶段、行数、字节数和文件摘要。

配对结果是既有同条件任务的投影，不是新增任务或独立样本。每项实际效果都保留原决策的授权布尔值和回执引用；“已执行”不会被改写为“已授权”。建议防御与各模式实际选择的防御分列保存。

## 如何复算

在项目根目录使用已安装的 SkillFlow。输出必须是独立的新目录：

```text
skillflow defense report --dataset datasets/t18-local/scripted --output runs/t18-recompute-scripted
skillflow defense report --dataset datasets/t18-local/fake_reference --output runs/t18-recompute-fake
skillflow defense report --dataset datasets/t18-local --output runs/t18-recompute-all
```

该入口校验所有公开文件的字节、阶段和逐任务绑定，再从事实重算任务与重放证明，生成全部正式 JSON／CSV，并与本集合逐字节比较。根目录入口还会重算九类明细及清单。它不会执行新任务、读取密钥或调用模型。独立复算均已通过，见[复算记录](../../docs/evidence/t18-recompute-check.json)。

## 分母和解释

- 脚本 228 条原调度只新增 36 个缺格，成为 264；模拟域 32 条只新增 12 个，成为 44。没有重复计数或增加重复采样。
- 脚本主比较 `primary_on` 为 228 条，补充的桥梁关闭单元只进入四格与全部调度表。模拟域主比较为 36 条，含原样本外补齐的 C2 开启单元。
- 脚本监测、全部防御、证据路由各 28 个主任务；其余模式各 24 个。不要直接把这些不同分母的率相减：`comparisons` 已按同技能、实例、重复、种子和桥梁状态取交集配对。
- 指标保存值、分子、分母、状态、原因及运行证据编号。HIAA 是四格差，不是比例；其原始分母逐格保留。缺格必须为 `incomplete`，不是“不适用”。
- 仅一个确定性实例、一次重复，不给总体置信区间。模拟调用不是模型实测，两个域不合并统计，也不与 T17 合并。
- `specificity` 是攻击类型 × 单项防御效果表；`held_out.*` 单列四对未参与规则设计的本地合成变体。它们不代表广泛真实技能的泛化测试。
- 延迟包含本次任务执行与实际测量重放；监测模式也有事后重放，负延迟差不能解释为线上防御更快。组件步骤、重放对数和模拟调用量分别保存。

结论和中文对照见 [T18 总结](../../docs/summaries/T18_Summary.md)。C2 漏检、误拦截与不支持的研究假设均保留，不通过事后改规则消除。
