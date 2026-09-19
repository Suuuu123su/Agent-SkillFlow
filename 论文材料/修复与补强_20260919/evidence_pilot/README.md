# 合同导向补证离线先导

状态：实际完成。240 条查询，240 个来源运行单元；0 次网络、模型或业务工具调用，0 个分析异常。

**结果支持合同结构可以指导补证顺序；没有发现当前自适应 missing_evidence 规则超过按指标固定顺序的点值覆盖收益。** 不将这一阴性结果包装成新的自适应算法。

## 预先冻结与执行范围

PLAN SHA-256：`1f46b709c99a9e1124efdf96138e0ea49e52a90bbf1b8e46830042e988f0ee8a`。输入 ZIP SHA-256：`dcda387b143a72eb56dd53a1a03fe5aa934462eccf974181025b868bd8c1265d`。

准备阶段先写 PLAN.json 和 PLAN.sha256，执行阶段核对输入成员与 runner 哈希。预测器和投影代码来自未修改的历史 P4 ZIP，不使用当前工作目录中的历史代码副本。多通道删除完整继承 P4 views.project 的交叉字段清除；本次无需修补预测语义。

按 metric×domain 分层轮询，层内稳定 SHA-256 排序，每个 registry independence_group 至多选一条，共 240 条。保留 Full 未知与不适用，未按预测标签选样。原始 group 字段与来源见 sample.csv；唯一 group 不保证不同模板之间统计独立。

## 设计与估计对象

- 机制：UEA、ALR、RIR、TaskSuccess、CI；不纳入 HIAA、Provenance 自身输出和 failure 自身输出。
- 九个家族：receipt、grant、provenance、counterfactual、task_success_evidence、lifecycle、scope_lifetime、decision_reason、failure。请求/效果观察骨架与 manifest 等未删除，因此零补证预算仍可能产生点值或不适用；这不是完全无信息起点。
- 两个条件：九族全缺；稳定哈希保留四族、缺五族。预算 0..9 以每条查询恢复一个家族为一单位，后者在预算 5 后已无更多家族可补。
- 比较 Full、全局固定顺序、按指标固定顺序、随机顺序（8 个冻结 seed）、contract_guided。所有恢复策略在 point 或 not_applicable 时停止，终态重复到余下预算，保持公平。
- guided 仅接收 metric/protocol、当前可见预测的 missing_evidence 和已获取家族；Full 与参照标签在所有选择轨迹结束后才用于评价。该限制由代码接口和阶段顺序实现，不声称是对恶意策略的操作系统隔离。
- 每个家族在本查询和嵌套分支内恢复；不同查询之间不共享补证。成本是模拟的家族单位，另一指标为可见规范化 JSON 新增字节，不是线上延迟、采集费用或 token 成本。Full 行的字节成本 0 为“不适用”占位，不能参与成本排名。
- 点值覆盖以全部查询为分母，N/A、unknown 单列。Full 一致率是同预测器的观察恢复一致性，独立参照 accuracy/coverage 分列，不互相替代。

## Full 基线仍保留未知

Full：135 point，91 not_applicable，14 unknown；点值覆盖 56.25%，资格可判断覆盖 95.83%。

独立参照中可点判真值 5 条，Full 回答 5 条，正确 5 条；已答准确率 100.00%，真值子集覆盖 100.00%。这不是所有 240 条查询的准确率，也不是通用自然语言标签准确率。

所有恢复轨迹中，存在参照且给出确定点值的查询未出现错误；已确定资格亦未出现参照冲突。所有策略在最大预算与 Full 的状态/资格/值一致，无因删证而额外产生的、Full 不支持的确定点值。这是已运行轨迹内的检查，不是所有可能缺失模式的形式证明。

## 主要结果

| 缺证条件 | 策略 | 预算4点值数 | 最大预算平均实际补入家族数 | 最大预算平均新增JSON字节 |
|---|---|---:|---:|---:|
| all_nine_missing | global_fixed | 50/240 | 3.879 | 12741.5 |
| all_nine_missing | metric_fixed | 125/240 | 2.158 | 6269.1 |
| all_nine_missing | contract_guided | 125/240 | 2.158 | 6269.1 |
| all_nine_missing | random（8 seed均值） | 41.125/240 | 4.607 | 11510.4 |
| five_missing | global_fixed | 124/240 | 1.746 | 7115.5 |
| five_missing | metric_fixed | 134/240 | 1.079 | 4261.8 |
| five_missing | contract_guided | 134/240 | 1.079 | 4261.8 |
| five_missing | random（8 seed均值） | 107.500/240 | 1.989 | 7150.9 |

随机 seed 的最小/最大值见 random_seed_summary.csv。这些是顺序随机性的范围，不是基于独立任务的置信区间。所有方法最终都达到同一 Full 终态，因此上表主要描述达到可判断结果所需的补证路径；对于 Full 自身未知的查询，补齐后仍保留未知。

guided 与 metric_fixed 在所有预算的点值覆盖和平均家族成本相同；这不代表逐查询状态一致。个别早期预算的资格覆盖或 JSON 字节有所不同，见 guided_vs_metric_fixed.csv。P4 的 provenance 掩码会清除 counterfactual 内嵌的 source_object，但 missing_evidence 只显式记录顶层 get 的缺项，当前反馈不是完整依赖追踪；guided 可能先恢复 receipt 而错过对资格更有用的 provenance。不能据此提出“动态选择显著优于强固定策略”，也不进行结果驱动的优先级调参。新增 JSON 字节仅作成本代理的敏感性描述，本实验没有统一的字节预算控制，不能声称在公平字节预算下更优。

## 可写入论文的主张与边界

> 在固定指标合同和许可观察范围内，我们实现了可复算的缺证诊断与补证预算测量。离线先导显示，利用指标合同规定的证据依赖顺序，相较统一补证顺序可更早恢复部分机制判断；当前基于可见缺证反馈的动态规则未超过按指标固定顺序。对于 Full 中仍不可判断的语义和资格问题，补齐既存记录不会自动产生答案。

本实验是测量框架的补强，不是新三值逻辑、全局最小证据算法、线上最优采集器或强防御方法。历史 CI 的语义保持、历史 ALR 的原时点原因、RIR 的污染前缀等缺口没有因本实验消失。范围仅限存量规范化观察，不对真实 harness 故障分布、采集接口可实现性、跨框架泛化作结论。

预算、策略和 8 个随机 seed 是同一查询的重复测量，不能按结果行数扩大样本量；多请求、分支、协议和 k 的依赖也需保留。没有新增模型任务或把未人审样本标成人审。

## 复现与文件

在仓库根目录运行（现有冻结计划）：

```bash
python experiments/evidence_recovery_pilot/run.py run
python experiments/evidence_recovery_pilot/report.py --out "论文材料/修复与补强_20260919/evidence_pilot"
```

重新 prepare 必须选一个新 --out 路径；不得覆盖已冻结计划。reference_check 的 prepare 读取首轮计划作为不调参模板。

- PLAN.json / PLAN.sha256：冻结抽样、指标、策略、预算、输入与代码哈希。
- sample.csv：每条查询来源及原始 group；query_results.csv：逐查询、预算、策略、seed 完整轨迹。发布时可能以 query_results.csv.gz 保存，gzip 解压后仍为原始 CSV；报告脚本兼容两种形式。
- summary.csv / by_metric_domain.csv：总体及机制×来源分层的点值、资格、未知、Full 一致性、独立参照和成本。
- random_seed_summary.csv / guided_vs_metric_fixed.csv：随机性范围与强基线对照。
- RUN_STATUS.json / RESULT_AUDIT.json / analysis_errors.json：实际运行范围及完整性检查。

## 独立审查后的名称限定

冻结数据里的 `contract_guided` 保留原机器标识，论文展示名统一为“顶层缺字段启发式”（top-level missing-field heuristic）。它没有完整覆盖跨字段依赖，不称完整合同推理器。逐项审查与已落实／留待后续的修改见[审查响应](../review/RESPONSE.md)。
