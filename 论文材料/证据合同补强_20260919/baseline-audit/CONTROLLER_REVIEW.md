# Controller / transport 独立复核

审查时间：2026-09-19。范围：`run.py`、`evaluation.py`、`transport.py`，并核查 `common.py`、`policy_worker.py`、`masks.py` 与报告聚合接口。此审查只读现有开发记录；未执行任何新增逻辑单元、未读取或生成留出结果、未修改 core。

## 实物核查

- 当前预算账本为 24 attempts / 24 unique execution units，全部 development，每个 unit 1 次；相对于 192 上限剩余 168。
- 审查时 `PLAN.json` 已存在，`heldout_COLLECTION_SEAL.json` 不存在。
- 24 个 development `record.json` 的 SHA256 均与 collection seal 一致。
- 每条开发记录的 `before.json`、`after.json`、`permission_schedule.json`、`task_requirements.json` 均与已封存 record 中重复字段一致：96 次内容比对，0 差异。
- 以上核查是当前一致性证据，不代表旧控制器已自动封存全部 oracle 输入。

## 实质发现（已即时发送主代理）

| 优先级 | 发现 | 影响 | 在留出前可完成的修正 |
|---|---|---|---|
| P1 | Collection seal 原先只锁定 `record.json` 和 licensed document；oracle 实际使用的 schedule / requirements / supervisor / before / after / retained sandbox 字节，以及 query registry 未全部锁定。 | 单独更改 sidecar 不会触发原有 record hash 检查，却可能改变独立参照或统计分母。当前未发现此类改动。 | 保留现有封存文件，追加不可覆盖的全输入 manifest，包含原始文件、独立 sidecar、真实产物、JSON/CSV query registry。replay 前和 oracle join 前核对；开发从已核对一致的 sealed-record 起点补齐。 |
| P2 | `choose_static` 按 20 个 mask 直接累积候选得分，其中随机缺证 3 seeds × 3 sizes = 9；主报告先平均 seeds 后只占 3 个 condition，总计 14 condition。 | 静态候选开发选择对随机缺证的相对权重为主结果的 3 倍；与共用测量合同要求的 seed 内平均不一致。 | 首选在显式 pre-heldout amendment 中将 random rows 权重设为 1/3，然后只重跑开发 CPU 选择；保留原 frozen PLAN 和旧候选结果。若不修，应明确限制“最佳静态”的目标口径，不能称按主报告指标挑选。 |

审查时上述两项尚待主代理处理。后续 amendment 及验证结果应另附记录，不能用本文件冒充修正完成。

## 已核对通过的控制路径

1. **实际执行预算**：控制器在调用 runner 与初始化前追加 ATTEMPTS；失败保留且计入总数。当前禁止自动重试，单次 `_collect` 只接受 24 个已预注册单位。检查总数不超过 192、每单位不超过 4；实际全部为每单位 1。没有从静态重放新增 sandbox 的代码路径。
2. **冻结与家族划分**：REGISTRATION 预先锁定 48 个 spec hashes、12 家族和开发/留出划分；PLAN 在开发候选选择后产生并锁 core hashes。heldout 收集先校验 PLAN/core，尚未收集留出时可以保留旧计划并追加带理由的 amendment，不能回写成仿佛最初即如此。
3. **一次留出**：已尝试过任一 unit 即拒绝自动再试；存在 heldout collection seal 时拒绝重新收集。预测或成本压缩文件已存在时 replay 拒绝重跑。重复运行不会悄悄覆盖结果。
4. **参照后置**：heldout collection 不生成 oracle / Full；`evaluate` 先运行全部冻结策略、写 prediction/cost 文件并生成 trajectory seal，再 `_reference(heldout)`。后者要求 trajectory seal 存在。开发参照在选策略前使用符合开发集用途。
5. **策略输入隔离**：worker 通过 stdin 只收到当前许可 document、metric、policy/order、acquired、公共 quotes 和 remaining budget。oracle、Full、raw 路径不进入消息。实现与文档均明确为合作式输入隔离，未声称 OS 权限隔离。
6. **费用守恒代码路径**：初始 public header + 每个初始许可包计入 `initial_bytes`；每个恢复包按真实 canonical UTF-8 padded packet 长度追加。超预算在访问 payload 前拒绝，报价溢出直接失败且不截断。memoization 缓存字节但每次重放仍追加相同收费事件，没有因缓存免费恢复。
7. **不可行预算**：预算小于共同初始负载时不请求 worker，记录 infeasible 与 required initial bytes，实际收费列为 0。报告保留该行的共同 oracle 分母；不把未发送的初始负载当已支付成本。
8. **停止规则**：每个 policy 在 point / not_applicable 时停止获取；unknown 可以继续。Full 不参与收费排名。

## 仍需最终结果阶段核验

- 对全部实际预测与成本 ledger 逐行核对 `sum(event.bytes) == charged_total_bytes <= budget`；不可行行应零计费且保留 required initial bytes。
- 按 unit/mask/budget 检查各策略共同 initial bytes；按 unit/mask 检查同一引用参照；验证报表先在 unit/query 内平均 seeds 再按 family 等权。
- 验证最终有效 PLAN/amendment 哈希、留出 collection seal、trajectory seal、oracle join 访问时间以及完整输入 manifest 的先后顺序。
- `evaluate_one` 对每个预算独立运行且允许跳过不可负担通道。不同预算路径可能不同；不得默认为单条嵌套轨迹或保证覆盖曲线单调。它仍是固定预算下的预注册策略评估。
- 控制器预算约束依赖本次单调度进程；当前没有多进程原子锁或掉电持久化声明。本轮观测到单进程、48以内执行时不构成已发生超额证据。
## 修正后复核与最终验收

主代理保留原 `PLAN.json` 和候选结果，追加 `FINAL_PLAN.json` 与 pre-heldout amendment：

- `seal_inputs` 对 raw 全部文件、licensed JSON 和 JSON/CSV query registry 建立不可覆盖 manifest；在重放前和 heldout oracle join 前检查全部哈希。
- 开发静态候选对随机缺证 seeds 使用 1/3 权重，family coverage 与 cost tie-break 均按同条件平均；开发 CPU 重选没有新增 sandbox。
- 最终 heldout 每条 attempt 绑定 FINAL_PLAN SHA，并且实际执行晚于最终冻结。

独立核验脚本 [verify_delivery.py](verify_delivery.py) 不 import 任何实验 core、不运行 sandbox/policy/predictor/oracle，仅使用标准库读取封存结果。完整输出见 [DELIVERY_AUDIT.json](DELIVERY_AUDIT.json)。

**最终结果 PASSED**：48 次实际执行、48 个逻辑单元、12 个 family；剩余执行预算 144。对 134,400 对 prediction/cost 行逐行检查 row_id、完整实验矩阵、所有共同 initial cost、每个收费事件与累计总额、冻结报价、预算上限、不可行零计费和空事件均通过。raw 产物、输入 manifest、FINAL_PLAN 与 core SHA 均通过。参照连接晚于两个 trajectory seals；独立重算的 family 等权覆盖/错误曲线、静态及动态 AUC 差与 SUMMARY 完全一致。

最初两项发现均已在 heldout 前修正并保留变更历史；没有更改或重跑留出以获得更好的结果。该核验只证明已声明的受控合同与记录一致性，不建立真实 agent/外部 harness 泛化或 OS 强隔离。
