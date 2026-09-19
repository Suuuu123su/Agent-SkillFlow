# 冻结定义与论文主张边界审查

状态：`DEFINITION_REVIEW_BEFORE_RESULT_ACCESS`。本记录只读冻结代码、`FINAL_PLAN.json`、原生产合同和本轮 family registry。尚未读取留出 raw、oracle、预测结果或统计摘要；新增模型调用与沙箱执行均为 0。后续实际结果审查应追加到本文件，不能将当前状态提前写成结果通过。

## 1. 两个新合同不等于原生产合同

| 对象 | 本轮 `controlled-persistent-effect-v1` 实际实现 | 不能借此宣称 |
|---|---|---|
| UEA 执行事实 | 单个监督动作边界中的文件/SQLite 持久状态变化；完整 supervisor 优先于 ACK；没有变化且监测闭合时可判未发生违规执行 | 验证瞬时或随后回滚的外发、任意网络副作用；没有 ACK 就没有效果 |
| UEA 授权 | 动作与资源精确相等；固定 session 精确匹配；issued/expires/revoke 时点；闭合独立 Grant 表 | 验证生产完整的 Manifest+Grant 双钥匙、grantee/actor 匹配、source/sink、Scope 枚举及 Lifetime 的 call/task/session/persistent 菱形偏序 |
| UEA 统计 | 一次逻辑动作是否有未授权持久变化的布尔判断 | 与生产逐 Effect 权重和/类型分类的 UEA 数值口径等价 |
| TaskSuccess | 预注册文件 hash 或 SELECT 结果、任务/session/resource sidecar 绑定，以及每个家族都要求的持久变化 | 对合法只读、幂等无变化任务的普适成功定义；原 T17 所有 Artifact ID/版本、required Effect/Receipt、Run/Session 强绑定语义均已覆盖 |
| Receipt | 绑定 action/resource/effect/task/attempt/session 与时序的 worker ACK；完整 supervisor 可代替它建立执行事实 | 在生产仍要求 Tool Receipt 的旧合同里可以直接用任何 monitor 日志替换 Receipt |

以上差异可由 `experiments/evidence_contract_validation/{predictor,adapter,independent_oracle}.py` 与 `src/skillflow/oracle/grants.py`、`src/skillflow/experiment/t17/task_evidence.py`、`docs/security-semantics.md` 对照核查。旧 P3R 的 `METRIC_CONTRACTS_P3R.md` 明确要求完整原 Scope/Lifetime 和 Effect/Receipt 口径。本轮应一直带合同版本后缀；不能无后缀写“UEA/TaskSuccess 已在独立平台验证”。

## 2. failure 与 receipt 是不同来源的冗余执行证据

本轮 `failure` 不只是错误日志。它包含 supervisor 完整性、动作身份、实际变化路径和 effect ID；`receipt` 包含 worker ACK。`predictor._execution` 先使用完整 supervisor，再考虑有完整绑定的 ACK。

因此，“隐藏 receipt 后仍正确”本身不是非平凡的模型理解能力或最小证据发现：在大部分这类投影中，另一条能独立证明执行事实的 supervisor 通道仍可见。正确报告必须说明这种冗余，展示具体缺失组合，特别是 receipt 与 failure 同时缺失或故障相关遮蔽的结果。

源码实现/进程路径独立，不等于统计来源独立。两条记录仍来自同一受控工作负载、同一资源初始化与任务规格；oracle 与 adapter 也共享这些真实原始执行事实。独立 oracle 重新读实际保留的文件/DB，且不调用 predictor，是有价值的代码路径核对；不能称独立自然分布真值、独立人工标注或外部真实 agent 验证。

## 3. 成本是固定 padding 协议下的序列化负载

冻结规则为开发集每通道最大包的 2 倍安全余量、按 1 KiB 对齐并再加 1 KiB；每个通道有全局公开固定报价。初始头部、初始已可见通道包和后续返回包均计费，物理重传仍计费。局部 IPC 调度、CPU 缓存、处理时间、磁盘读取、网络握手和真实系统日志采集不在成本端点中。

这能保证当前协议内的公平字节比较和不通过隐藏包长窥视结果，但 padding 与固定包元数据可能占据主要成本。若观察到优势，只能写“在冻结的填充序列化负载协议中改善正确覆盖”，不能写减少自然日志量、真实网络字节、实际在线时延、token 或金额。不能从这个协议推出最小信息量或通用证据效率。

AUC 的共同区间在 `FINAL_PLAN.json` 冻结为 `[0, 76363]` 字节；0 预算与不足初始负载的行必须保留为不可行及共同分母。不能把不足预算的点悄悄移出主曲线，也不能在结果出来后换阈值或缩小积分区间。

## 4. 留出范围与小族统计

- 12 个具名任务族，每族 4 个实例；6 族开发、6 族留出。任务 operation 不同，开发/留出不是仅换 ID。
- 但双方共用同一 adapter/predictor、授权子合同、记录器和故障原型（normal、revoked/wrong_scope、no_commit、ack_lost 等）。这属于新任务操作上的冻结验证，不是未见故障机制、未见合同实现或跨 harness 泛化。
- 48 次初始化不等于 48 个独立同分布任务；query、通道 mask、budget、策略和随机 seed 均为重复测量。先在 query/condition 内平均 seed，再族内聚合、族间等权；六个留出族只支持描述性差异，不支持基于大行数的显著性或狭窄置信区间。
- `ALR`/`RIR` 族标签不表示这两个机制被证成。当前两个端点按预注册边界保持 unknown；无独立 reason、identity/neutral、污染前缀影响或因果撤销对照。CI 没有新增干预真值。

## 5. 案例与贡献的允许表述

| 可使用的表述 | 必须避免的升级 |
|---|---|
| 在受控 ACK 中断干预下，实际持久状态已经变化而 collector ACK 缺失；原始文件/DB 可核查 | 发现真实 agent 的自然攻击率、自然丢包率或未知生产漏洞 |
| 正确输出字节与错误任务绑定被独立任务要求分开核查 | 一般解决语义任务完成判定、LLM 裁判失效或跨用户授权 |
| 展示完整 monitor 能为 ACK 缺失提供替代执行依据 | 无需完整监测也能从缺失日志证明安全 |
| 冻结静态顺序在同一字节代理下优于全局顺序（仅结果满足时） | 提出新的通用主动获取算法或静态方法在真实系统中普适最优 |
| 动态对强静态无优势时保留阴性结果并删除动态贡献 | 通过改名、只选有利 budget/家族或重复测试留出来制造算法优势 |

任务/故障均由本轮脚本预设。即便实际状态落地与记录路径验证成立，这首先是框架合同与采集现象的受控验证；它不是意外发现的新攻击。若最后只有预设冗余与已知失败模式，不应仅因运行真实就宣称顶会核心新发现已成立。

## 6. 等结果封存后的复核项

收到主执行者明确确认后再打开结果：核对 Full 与独立 oracle 的分离、正确覆盖和错误确定率的两个分母、错误安全判断、未知真值、N/A、不可行行、逐族 AUC、实际沙箱次数与失败负例。检查摘要是否恰当使用本文件的版本与范围限定。这个结果复核不会修改冻结代码、策略或预算，也不会重新执行沙箱。
