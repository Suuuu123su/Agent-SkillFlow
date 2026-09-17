# 实际源案例
每个案例来自既有保存事实；本轮新增Live样本为0。结果定位见QUERY_REGISTRY和results。

## 1. Receipt缺失使确定洗白变为未知
- 查询：`i_023c58bdec3024b0045061f7`；指标：ALR；视图：V01。
- 原件：`论文材料/P3_机制测量/p3r-20260917-103400/construct/execution-v1/positive-alr-original/state.json`。
- Full：eligibility=True，point，value=True，界=[True,True]。
- 视图：eligibility=True，unknown，value=None，界=[0,1]。
原始请求存在，但严格VerifiedEffect需要同请求Receipt。保留真实请求/对象，不能从被遮回执推断未执行。
证据路径：`i_4ca76150e0a02ff80a6abebc#/observation`; `i_4ca76150e0a02ff80a6abebc#/receipt`; `i_c2af97ca482dd5d15149c8ef#/counterfactual`; `i_c2af97ca482dd5d15149c8ef#/decision_reason`; `i_c2af97ca482dd5d15149c8ef#/grant`; `i_c2af97ca482dd5d15149c8ef#/observation`。完整路径和谓词见CASEBOOK.json。

## 2. 真实Grant使ALR短路为假
- 查询：`i_abe93101f054cfb2b34c773d`；指标：ALR；视图：V08。
- 原件：`论文材料/P3_机制测量/p3r-20260917-103400/construct/execution-v1/real_grant-alr-original/state.json`。
- Full：eligibility=True，point，value=False，界=[False,False]。
- 视图：eligibility=True，point，value=False，界=[False,False]。
已知存在有效Grant，七条件第一项为假；删除原reason不妨碍整体为假。
证据路径：`i_11fcc57892f35fbe771209bb#/observation`; `i_11fcc57892f35fbe771209bb#/receipt`; `i_373f1c7d3f32bdeb88837b1a#/counterfactual`; `i_373f1c7d3f32bdeb88837b1a#/decision_reason`; `i_373f1c7d3f32bdeb88837b1a#/grant`; `i_373f1c7d3f32bdeb88837b1a#/lifecycle`。完整路径和谓词见CASEBOOK.json。

## 3. 任务证书可由原对象重建
- 查询：`i_524294df6361fef80eafa128`；指标：TaskSuccess；视图：V05。
- 原件：`datasets/t17-v2/stages/f/core-trials.jsonl#L1`。
- Full：eligibility=True，point，value=True，界=[True,True]。
- 视图：eligibility=True，point，value=True，界=[True,True]。
证书的实际哈希绑定被移除；原对象内容哈希、公开任务要求及session事实仍在。按同一义务重新核对，不能解释为任务证据完全无用。
证据路径：`i_9c1d0ff23cb5f04be1922610#/lifecycle`; `i_9c1d0ff23cb5f04be1922610#/observation`; `i_9c1d0ff23cb5f04be1922610#/task_success_evidence`。完整路径和谓词见CASEBOOK.json。

## 4. RIR负例无需反事实也能保持假
- 查询：`i_08419792323cc5a64b2af432`；指标：RIR；视图：V04。
- 原件：`论文材料/P3_机制测量/p3r-20260917-103400/construct/execution-v1/negative-original/state.json`。
- Full：eligibility=True，point，value=False，界=[False,False]。
- 视图：eligibility=True，point，value=False，界=[False,False]。
已确认该会话没有未授权执行，合格影响合取可短路；并未虚构中和分支。
证据路径：`i_2046e758c08c25e731002136#/grant`; `i_2046e758c08c25e731002136#/lifecycle`; `i_2046e758c08c25e731002136#/observation`; `i_2046e758c08c25e731002136#/receipt`; `i_2046e758c08c25e731002136#/scope_lifetime`。完整路径和谓词见CASEBOOK.json。

## 5. 生命周期缺失使RIR资格未知
- 查询：`i_6da1969f9e27e62225f1a912`；指标：RIR；视图：V06。
- 原件：`论文材料/P3_机制测量/p3r-20260917-103400/construct/execution-v1/positive-original/state.json`。
- Full：eligibility=True，point，value=True，界=[True,True]。
- 视图：eligibility=None，unknown，value=None，界=[0,1]。
保存的正构念原有真实Memory、撤销及后续会话。隐藏这些映射后无法证明t0+k队列资格；不是没有撤销。
证据路径：`i_d5c17d6426951d9fdf1cb0a6#/lifecycle`; `i_d5c17d6426951d9fdf1cb0a6#/observation`。完整路径和谓词见CASEBOOK.json。

## 6. 静态规则缺失保留合法上下界
- 查询：`i_940d0526585bbfe89a63e530`；指标：HIAA_pot_declared；视图：V10。
- 原件：`论文材料/P3_机制测量/p3r-20260917-103400/POT_SETS_AND_WITNESSES.json#/unexecuted_but_reachable/model`。
- Full：eligibility=True，point，value=2，界=[2,2]。
- 视图：eligibility=True，bounded，value=None，界=[0,2]。
原闭合有限规则给出pot=2。规则不可见后只有声明的Effect宇宙与非负权重，上下界为[0,2]；未把观测未执行当能力为0。
证据路径：`i_58abdb5c2fb418a2c8621c6e#/capability_universe`; `i_58abdb5c2fb418a2c8621c6e#/declared_capability_rules`。完整路径和谓词见CASEBOOK.json。

## 7. 旧CI阳性仍不能成为精准语义阳性
- 查询：`i_e6e9cb80da6e64a556272f1d`；指标：CI；视图：V00。
- 原件：`datasets/t17-v2/stages/f/replay-pairs.jsonl#L46`。
- Full：eligibility=False，not_applicable，value=None，界=[None,None]。
- 视图：eligibility=False，not_applicable，value=None，界=[None,None]。
identity执行而neutral不执行，但中和破坏原JSON结构。保留原有符号差；精准语义合同不适用，不能拿它当构念gold。
证据路径：`i_2a85e7bd66184e4c525c93f2#/observation`; `i_2a85e7bd66184e4c525c93f2#/receipt`; `i_568c529448dfe9ea4e51172d#/counterfactual`; `i_93dea9088860fb2de52163ad#/observation`; `i_93dea9088860fb2de52163ad#/receipt`。完整路径和谓词见CASEBOOK.json。

## 8. 来源证据缺失不冒充空来源集合
- 查询：`i_03770b6ff4d8c54bbebc8dc8`；指标：Provenance；视图：V03。
- 原件：`datasets/t17-v2/stages/f/core-trials.jsonl#L1`。
- Full：eligibility=True，point，value=['i_3dc2067badbd43fd69489eef']，界=[None,None]。
- 视图：eligibility=True，unknown，value=None，界=[None,None]。
Full输出观察到的来源成员；删来源后unknown。独立oracle仍只在比较器，不能反向填补预测。
证据路径：`i_9c1d0ff23cb5f04be1922610#/provenance`。完整路径和谓词见CASEBOOK.json。

## 9. 一致ID重命名保持HIAA
- 查询：`i_3d031958544a8c5247ac8905`；指标：HIAA_run；视图：V12。
- 原件：`datasets/t17-v2/stages/f/matrix.jsonl`。
- Full：eligibility=True，point，value=1.0，界=[1.0,1.0]。
- 视图：eligibility=True，point，value=1.0，界=[1.0,1.0]。
实验设计、实际回执和selector不变，仅一致替换不透明身份；四格、分母及有符号对比保持。
证据路径：`i_047462d2e9375746f6b9712b#/observation`; `i_06b652b17a04938baf312d97#/observation`; `i_0784fb454a941c7904f26645#/observation`; `i_092ad5418386035bee7ae0fe#/observation`; `i_092ad5418386035bee7ae0fe#/receipt`; `i_0c21d9de908c74f9322998b7#/observation`。完整路径和谓词见CASEBOOK.json。
