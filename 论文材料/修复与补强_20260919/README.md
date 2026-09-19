# HIAA修复与贡献补强

状态：`COMPLETED_WITH_RESEARCH_LIMITS`。基于 `ff6241c402a97e61f23b51d3aa1e863131c2477f`，按用户新授权完成修复、查新和对应离线实验。完整判断与可直接使用的段落见[结果及论文措辞](RESULTS_AND_PAPER_CLAIMS.md)。

| 内容 | 入口 | 实际结果 |
|---|---|---|
| HIAA修复 | [报告](hiaa/README.md)、[复现](hiaa/REPRODUCE.md) | 每格15→13；48项名单一致；156输出、13项测试通过；点值不变 |
| 候选贡献查新 | [查新报告](NOVELTY.md) | 收窄为特定合同下的缺证判断边界及补证成本，保留核验限制 |
| 补证先导 | [240查询](evidence_pilot/README.md) | 预算4，指标固定／诊断导向125点值，全局顺序50点值 |
| 有限参照扩展 | [235查询](evidence_pilot_reference/README.md) | 36 unit、9构念家族；独立真值覆盖126/128，已答126/126一致 |
| 合成不可辨识见证 | [三对见证](witnesses/README.md) | 同观察异真值3/3；缺证6/6未知、恢复6/6正确 |

**当前动态策略没有超过按指标固定顺序的总体点值覆盖。** 各预算与seed是重复测量，不增加独立任务数；Full一致性不代替独立真值。有限构念准确性不代表通用自然语言安全准确性，家族单位和JSON字节代理不代表线上成本。历史ALR/RIR/CI/manifest限制仍保留。

所有历史ZIP、原始输入和旧预测保持原字节。本轮仅追加修正版；新增模型、Judge、业务执行均为0。两份较大的逐查询CSV确定性压缩为 `query_results.csv.gz`，回读逐字节一致，原始／压缩SHA256见各目录RESULT_ARCHIVE.json；脚本可重新生成CSV，报告器兼容两种形式。

下一步如继续强化贡献，应获得其他harness的独立证据与真实成本测量；本轮没有把未执行的扩展写成完成。

[原生交叉模型审查](review/REVIEW.md)与[逐项响应](review/RESPONSE.md)：候选方向PROCEED WITH CAUTION；当前方法不支持新动态算法优势。代码标识contract_guided保留，正文称“顶层缺字段启发式”。

最终交付核对见[DELIVERY_CHECKS.json](DELIVERY_CHECKS.json)。只读复核：`python -B experiments/evidence_recovery_pilot/verify_delivery.py`，验证31项HIAA输入绑定、两份冻结计划、压缩结果逐字节回读及当前文档链接，不重复实验。

交付状态：代码与结果已在本地提交。Git推送缺少写入凭据，GitHub连接器建分支操作返回aborted且无具体原因；未确认任何成功远端发布，也未创建PR。交付包提供相对基准提交的二进制补丁、全部变更文件及应用说明。
