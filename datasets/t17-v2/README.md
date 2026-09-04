# T17 第二版完整分层数据

本集合包含 E、F、G 预检、G 正式和 H 新增部分。各自完整的任务、重放、回执、来源、用量、格式及原始记录清单在 `stages/e`、`stages/f`、`stages/g_canary`、`stages/g`、`stages/h`。阶段清单登记所有数据分卷，不能仅读首卷。

顶层长表保留分子、分母、证据、区间和状态；模型分别报告，不跨模型、预检或协议计算总体比例。模型比较为 F 与 G；防御比较复用 F 加 H，共 630 个任务和 540 组重放。H 子目录只有新增的 270/270，不重复保存 F 样本。

`model-pair-contract.json` 保留两侧原配置及阶段身份，列出接口、推理档位和批准修订的解释限制。比较描述模型及服务配置组合，不声称仅识别模型权重效应。同点值不证明统计等价，跨零区间记不确定。

重算：从项目根目录运行 `.venv-skillflow/Scripts/python.exe scripts/t17_delivery/t17_collection.py --from-collection datasets/t17-v2 --output runs/t17-v2-recomputed-01`。仅读取公开事实，无需密钥或私有正文。阶段单独重算仍使用 `skillflow t17 v2 report --dataset <阶段目录> --output <新目录>`。技能比较使用 `skillflow compare-skills` 指向阶段目录；尚未开展不同攻击技能的实证排名。

费用按冻结费率估算，不是账单；已撤回及失败尝试费用不计入实验分母，另见总费用表。独立审查状态为 REVIEW_UNAVAILABLE；本数据集合不单独宣告项目质量验收通过。
