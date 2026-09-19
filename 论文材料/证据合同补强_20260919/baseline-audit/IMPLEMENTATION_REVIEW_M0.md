# M0 独立实现审查记录

审查方式：只读源码和纯内存接口反例；新增模型调用 0、沙箱执行 0。没有查看留出执行结果。本记录是冻结前开发审查，不是留出后调参。

| 问题 | 实测或源码证据 | 开发处理 |
|---|---|---|
| 新 grant 副本未纳入依赖闭包 | adapter 使用 `scope_lifetime.limits`、`lifecycle.grant_times`；旧 `_rule` 只匹配 `grant_limits` 等旧字段。纯内存遮蔽 grant 后仍出现 `limits.g` 与 `grant_times.g` | 已通知依赖模块负责人修复并加入实际新 schema 的 mask 检查 |
| 产物 hash 在其它通道有副本 | 遮蔽 task_success_evidence 后 `receipt.ack.artifact_hashes` 仍保留实际 hash；failure.changes 原有 before/after hash | 主执行者已从 adapter 的许可 receipt 移除 artifact_hashes，并将 failure 改为效果路径/ID；原始证据保持 |
| 强静态候选截断偏倚 | UEA 的 5 通道排列有 120 种，直接截前 24 种全部 receipt-first；额外 cheapest 至多增加一种首通道，且原实现无开发 greedy | 已加入开发集正确覆盖 greedy、按字节收益 greedy，并按首通道轮询填足最多 24 候选；已读到代码修复 |
| 陈旧/错任务 ACK 优先于完整监测 | 纯内存输入 `monitor_closed=True, changes=[]`，ACK action/resource 相同而 task/session 错误，既有正确产物及绑定；旧 predictor 返回 TaskSuccess point=True，违反 requires_committed_effect | 主执行者接手修复 ACK effect/task/session 绑定及完整 monitor 优先规则；不能把该内存反例声称为新 48 单元中已观测自然错误 |
| 不可行预算账本不守恒 | B=0 时 public header 必需 487 字节；旧 ledger 仍有 487 字节 events，结果 charged_total_bytes 却为 0 | 主执行者接手将未发送的初始需求与实际计费事件分开 |

已检查的正面边界：policy_worker 仅接收 metric、许可投影、策略公开顺序/报价和余额；未 import oracle、未获取 raw 路径，broker 的隐藏文档不传给 worker。封存函数先写预测和成本摘要后才允许后续 join。这里仍是合作式输入隔离，绝非 OS 文件读取隔离。

family registry 是 6 开发族/6 留出族，不同 operation，未见单纯换 ID 的开发/留出复制。代码定义可见不等于看过留出结果；是否按顺序冻结和只评估一次，须由 driver/PLAN/访问与封存记录进一步证实，本次未据未完成 driver 宣称已通过。

额外边界：当前 oracle 和 predictor 只覆盖声明的持久效果合同；ALR/RIR 固定 unknown，CI 没有新语义真值。SQLite adapter 使用已预注册的全列 SELECT 子集，不能外推任意 SQL 顺序/列选择。固定 padding 成本是序列化负载代理，未测在线时延或真实网络经济成本。

本表记录发现与开发修复，不替代冻结后测试；最终交付应以根 README、门检查、冻结哈希和阶段结果为准。
