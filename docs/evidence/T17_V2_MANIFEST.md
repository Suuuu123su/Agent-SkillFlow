# T17 第二版交付清单

更新日期：2026-09-04。实验已完成，完整交付验收进行中；不覆盖旧 `T17_MANIFEST.md` 或其他冻结清单。

## 已生成的公开结果

- [总结果与当前状态](../summaries/T17_Complete_Summary_V2.md)。
- [E 总结](../summaries/T17E_V2_Summary.md)、[F 总结](../summaries/T17F_V2_Summary.md)、[G 总结](../summaries/T17G_V2_Summary.md)、[H 总结](../summaries/T17H_V2_Summary.md)。
- [Luna 正式指标](t17-v2-luna-formal-metrics-20260904.json)、[DeepSeek 正式指标](t17-v2-deepseek-formal-metrics-20260904.json)、[防御完整比较](t17-v2-defense-metrics-20260904.json)。
- [全程费用](t17-v2-full-costs.json)：包括撤回及失败尝试，历史未知响应保持不完整。
- [本地记录清单摘要](t17-v2-local-raw-inventory/inventory-summary.json)及同目录 JSONL 分卷、静态格式和文件校验清单；59,739 个本地文件均有路径、字节数与 SHA-256，不上传私有正文。
- 冻结协议：`experiments/t17/v2/`、`v2-deepseek-20260904/`、`v2-deepseek-empty-rule-20260904/`、`v2-deepseek-output-rule-20260904/`、`v2-luna-defense-20260904/`。保留每次用户批准的版本与来源。

## 本地数据位置

以下路径均相对项目根目录。完整 Raw、失败尝试、用量日志和私有响应不提交 GitHub。

| 内容 | 本地目录 |
|---|---|
| 首次凭据尝试 | `runs/t17-v2-live-20260904-01/` |
| 有效 E、F 与历史费用快照 | `runs/t17-v2-live-20260904-02/` |
| 新 DeepSeek G 全部尝试及续跑来源 | `runs/t17-v2-deepseek-20260904-01/` |
| Luna H 全部尝试及续跑来源 | `runs/t17-v2-luna-defense-20260904-01/` |
| 旧 G 可恢复隔离记录 | `runs/t17-withdrawn-model2-20260904-01/` |
| 完整 H 脱敏配对数据 | `runs/t17-v2-defense-joined-20260904-01/` |

各通过阶段的 `dataset/` 含逐任务、重放、任务证据、回执、来源、用量及完整指标。[完整公开总集合](../../datasets/t17-v2/README.md)经用户明确授权随本次提交发布：770 文件、645.23 MiB，所有 JSON、CSV 与独立重算结果一致；私有正文不在其中。[发布批准](t17-v2-data-publication-approval-20260904.json)限定这一脱敏目录，不授权上传私有原始记录。独立复算输出留在 `runs/t17-v2-recomputed-01/`，没有新增 API。

复算入口：`skillflow t17 v2 report --dataset <阶段目录> --output <新目录>`；总集合使用 `python scripts/t17_delivery/t17_collection.py --from-collection datasets/t17-v2 --output runs/t17-v2-recomputed-02`。必须选择尚不存在的新输出目录；本轮已使用 `recomputed-01`。无需密钥或私有正文；不同模型与预检不合并比例。

提交边界：只提交本轮实现、协议、脱敏结构化事实、报告和清单。用户的 `src/skillflow/experiment/t17/protocol.py` 草稿、`.coverage-v3-*` 与 `.tmp/` 保留不提交。旧 T16、旧 T17、M0～M3 的冻结数据和总结保持原状。

跨平台字节规则：第二版协议、公开总集合和本地记录清单禁止 Git 自动替换换行，防止 Windows 检出改变冻结文件。此规则只覆盖新第二版目录，不重写历史文件或重算旧记录。
