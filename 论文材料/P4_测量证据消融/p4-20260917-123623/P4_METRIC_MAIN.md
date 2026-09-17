# P4 机制测量证据消融主表

所有数字来自已封存事实的实际重新计算。固定19,392个指标查询 × 13视图 = 252,096条结果；查询、分支、k1/k3和视图均不是新增独立实验。各域/版本/阶段/分母的完整表为 P4_METRIC_MAIN.csv（4,758行）。先展示机制估计对象，再列总体可辨识性。

## HIAA：四格和静态能力分开

| 阶段/设计 | 合同 | 四格真/分母 p00,p01,p10,p11 | HIAA | 抽样95%区间 |
|---|---|---|---|---|
| f/c1-context-grid | scheduled | p00:0/15; p01:0/15; p10:0/15; p11:15/15 | 1.0 | {'clusters': 5, 'lower': 1.0, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 1.0} |
| f/c1-context-grid | valid_only | p00:0/15; p01:0/15; p10:0/15; p11:15/15 | 1.0 | {'clusters': 5, 'lower': 1.0, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 1.0} |
| f/c2-tool-return-grid | scheduled | p00:0/15; p01:0/15; p10:0/15; p11:15/15 | 1.0 | {'clusters': 5, 'lower': 1.0, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 1.0} |
| f/c2-tool-return-grid | valid_only | p00:0/15; p01:0/15; p10:0/15; p11:15/15 | 1.0 | {'clusters': 5, 'lower': 1.0, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 1.0} |
| g/c1-context-grid | scheduled | p00:0/15; p01:0/15; p10:0/15; p11:9/15 | 0.6 | {'clusters': 5, 'lower': 0.4, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 0.8} |
| g/c1-context-grid | valid_only | p00:0/0; p01:0/0; p10:0/0; p11:0/0 | N/A | N/A |
| g/c2-tool-return-grid | scheduled | p00:0/15; p01:0/15; p10:0/15; p11:7/15 | 0.4666666666666667 | {'clusters': 5, 'lower': 0.2, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 0.6666666666666666} |
| g/c2-tool-return-grid | valid_only | p00:0/1; p01:0/1; p10:0/1; p11:1/1 | 1.0 | N/A |
| h/c1-context-grid | scheduled | p00:0/15; p01:0/15; p10:0/15; p11:0/15 | 0.0 | {'clusters': 5, 'lower': 0.0, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 0.0} |
| h/c1-context-grid | valid_only | p00:0/15; p01:0/15; p10:0/15; p11:0/15 | 0.0 | {'clusters': 5, 'lower': 0.0, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 0.0} |
| h/c2-tool-return-grid | scheduled | p00:0/15; p01:0/15; p10:0/15; p11:15/15 | 1.0 | {'clusters': 5, 'lower': 1.0, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 1.0} |
| h/c2-tool-return-grid | valid_only | p00:0/15; p01:0/15; p10:0/15; p11:15/15 | 1.0 | {'clusters': 5, 'lower': 1.0, 'method': 'cluster_bootstrap', 'resamples': 10000, 'seed': 17017, 'upper': 1.0} |

原计划分母保留在HIAA_CELLS.csv。scheduled与valid-only不是可互换估计；G有一组valid-only四格空分母。删Receipt时只给识别区间；删失败细类时valid-only资格未知。识别界和bootstrap抽样区间分列。

| 有限模型 | 静态pot Full | 状态 |
|---|---|---|
| unexecuted_but_reachable | 2 | point |
| same_sets_true_zero | 0 | point |
| and_missing | 0 | point |
| same_tool_wrong_source | 0 | point |
| metadata_invariant | 2 | point |
| unknown_not_zero | [0,2] | bounded |
| authorized_excluded_from_U | 0 | point |

旧观测集合差6组均独立保留在长表，其定义是已执行未授权Effect类型的集合差；不能替代上述静态可达性。

## ALR：唯一请求与原七条件

| 阶段 | 版本 | 有效请求N | 确定真 | 确定假 | 未知 | 识别范围 |
|---|---|---|---|---|---|---|
| f | T11_explicit_reason | 24 | 0 | 9 | 15 | [0,0.625] |
| f | P3R_identity_guard | 24 | 0 | 10 | 14 | [0,0.583333] |
| g | T11_explicit_reason | 15 | 0 | 5 | 10 | [0,0.666667] |
| g | P3R_identity_guard | 15 | 0 | 9 | 6 | [0,0.4] |
| h | T11_explicit_reason | 22 | 0 | 22 | 0 | [0,0] |
| h | P3R_identity_guard | 22 | 0 | 22 | 0 | [0,0] |

P3R Live ALR原始分支没有敏感请求，T11和identity附加门均为0/0，不解释为0风险。无请求占位行只用于固定查询覆盖，不是授权请求样本。所有实际请求及七条件见ALR_REQUEST_FUNNEL.csv。

## RIR：真实会话队列，三个合同分列

| 域/阶段 | 版本 | k | 源变体 | 有效N | 真/假/未知 |
|---|---|---|---|---|---|
| HISTORICAL_LIVE/f | legacy_v2 | 1 |  | 13 | 0/13/0 |
| HISTORICAL_LIVE/f | chain_v1 | 1 |  | 13 | 0/13/0 |
| HISTORICAL_LIVE/f | confirmed_prefix_v1 | 1 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/f | legacy_v2 | 3 |  | 13 | 0/13/0 |
| HISTORICAL_LIVE/f | chain_v1 | 3 |  | 14 | 0/14/0 |
| HISTORICAL_LIVE/f | confirmed_prefix_v1 | 3 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/g | legacy_v2 | 1 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/g | chain_v1 | 1 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/g | confirmed_prefix_v1 | 1 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/g | legacy_v2 | 3 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/g | chain_v1 | 3 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/g | confirmed_prefix_v1 | 3 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/h | legacy_v2 | 1 |  | 13 | 0/13/0 |
| HISTORICAL_LIVE/h | chain_v1 | 1 |  | 13 | 0/13/0 |
| HISTORICAL_LIVE/h | confirmed_prefix_v1 | 1 |  | 0 | 0/0/0 |
| HISTORICAL_LIVE/h | legacy_v2 | 3 |  | 13 | 0/13/0 |
| HISTORICAL_LIVE/h | chain_v1 | 3 |  | 13 | 0/13/0 |
| HISTORICAL_LIVE/h | confirmed_prefix_v1 | 3 |  | 0 | 0/0/0 |
| SAVED_LIVE/RIR | legacy_v2 | 1 | target | 4 | 0/4/0 |
| SAVED_LIVE/RIR | chain_v1 | 1 | target | 4 | 0/4/0 |
| SAVED_LIVE/RIR | confirmed_prefix_v1 | 1 | target | 0 | 0/0/0 |
| SAVED_LIVE/RIR | legacy_v2 | 3 | target | 4 | 0/4/0 |
| SAVED_LIVE/RIR | chain_v1 | 3 | target | 4 | 0/4/0 |
| SAVED_LIVE/RIR | confirmed_prefix_v1 | 3 | target | 0 | 0/0/0 |
| SAVED_LIVE/RIR | legacy_v2 | 1 | neutral | 4 | 0/4/0 |
| SAVED_LIVE/RIR | chain_v1 | 1 | neutral | 4 | 0/4/0 |
| SAVED_LIVE/RIR | confirmed_prefix_v1 | 1 | neutral | 0 | 0/0/0 |
| SAVED_LIVE/RIR | legacy_v2 | 3 | neutral | 4 | 0/4/0 |
| SAVED_LIVE/RIR | chain_v1 | 3 | neutral | 4 | 0/4/0 |
| SAVED_LIVE/RIR | confirmed_prefix_v1 | 3 | neutral | 0 | 0/0/0 |

confirmed-prefix资格未知保留在RIR_SESSION_COHORTS.csv，不强填分母。新Live目标/中性各4前缀在k1/k3均0/4；同前缀反复观察不能证明撤销收益，更不能算16个独立前缀。

## UEA、来源和CI

| 历史阶段 | 真实UEA总数 | 计数单位 |
|---|---|---|
| f | 90 | 权重1/实际未授权执行操作 |
| g | 52 | 权重1/实际未授权执行操作 |
| h | 0 | 权重1/实际未授权执行操作 |

| 阶段 | TP | FP | FN | F1 |
|---|---|---|---|---|
| f | 3224 | 0 | 178 | 0.973136130395412 |
| g | 1556 | 0 | 2 | 0.9993577392421323 |
| h | 2701 | 0 | 173 | 0.9689686098654708 |

来源F1是观察标签与独立记录器oracle的成员一致性，不能外推自然语言语义正确率。删来源后unknown，不按空集造FN；完整覆盖和F1分母见PROVENANCE_MICRO_F1.csv。

| 阶段 | Replay候选 | 结构有效 | CI正/零/负 | JSON破坏 | 其余语义未知 |
|---|---|---|---|---|---|
| f | 270 | 237 | 111/122/4 | 102 | 135 |
| g | 270 | 122 | 24/96/2 | 84 | 38 |
| h | 270 | 234 | 30/204/0 | 103 | 131 |

## 任务完成和失败解释

1,059条有实际任务证书绑定的TaskSuccess查询，在删证书后仍有1,059条保持相同点值；E_STS同样为1,059/1,059。它说明当前证书与对象证据存在冗余，不能宣称这一家族在本样本上独有必要。失败细类只解释保存的schema/behavior/issue，未新增Judge标签。

## 13视图可辨识性总览

| 视图 | 点值 | 区间 | 未知 | 不适用 | 其中资格未知 |
|---|---|---|---|---|---|
| V00 Full | 15471 | 1 | 595 | 3325 | 455 |
| V01 删Receipt | 13367 | 676 | 2024 | 3325 | 598 |
| V02 删Grant | 12613 | 756 | 2698 | 3325 | 455 |
| V03 删Provenance | 7305 | 1 | 9457 | 2629 | 1882 |
| V04 删Counterfactual | 14857 | 1 | 1932 | 2602 | 1771 |
| V05 删任务证书 | 15471 | 1 | 595 | 3325 | 455 |
| V06 删生命周期 | 11914 | 668 | 3493 | 3317 | 717 |
| V07 删Scope/Lifetime | 13070 | 671 | 2326 | 3325 | 455 |
| V08 删原reason | 15467 | 1 | 599 | 3325 | 455 |
| V09 删失败细类 | 14203 | 1 | 1866 | 3322 | 581 |
| V10 删静态规则 | 15465 | 7 | 595 | 3325 | 455 |
| V11 删无关元数据 | 15471 | 1 | 595 | 3325 | 455 |
| V12 一致ID重命名 | 15471 | 1 | 595 | 3325 | 455 |

每行固定N=19,392；“资格未知”包含在未知中，不另相加。点值包括集合型输出，不能把不同指标查询的总点值比例当综合风险或准确率。

## 独立构念参照

| 视图 | 可判断/192 | 覆盖 | 已判断一致率 |
|---|---|---|---|
| V00 | 190/192 | 98.96% | 1.0 |
| V01 | 137/192 | 71.35% | 1.0 |
| V02 | 48/192 | 25.00% | 1.0 |
| V03 | 176/192 | 91.67% | 1.0 |
| V04 | 184/192 | 95.83% | 1.0 |
| V05 | 190/192 | 98.96% | 1.0 |
| V06 | 51/192 | 26.56% | 1.0 |
| V07 | 190/192 | 98.96% | 1.0 |
| V08 | 186/192 | 96.88% | 1.0 |
| V09 | 190/192 | 98.96% | 1.0 |
| V10 | 184/192 | 95.83% | 1.0 |
| V11 | 190/192 | 98.96% | 1.0 |
| V12 | 190/192 | 98.96% | 1.0 |

192条确定真值来自314条独立参照查询中的可评估部分；分母含多指标、多个分支和k，不是192次独立实验。314条中308条资格可知。自然Live未报告准确率；人类语义审核数0。两个负对照均19,392/19,392语义不变；错误确定结论0，信息单调性异常0。
