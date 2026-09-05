# T19 策略结构审计：T 对 P/M 的支配关系

审计对象：首次正式冻结的 src/skillflow/defense/rx.py 与 rx_provider.py。该发现仅约束结果解释，不修改运行、指标、分母或正式采样。不以负结果停止本轮矩阵。

## 可直接从代码推出的等价性

设 B 为原 Safe-Sink Monitor 策略的 executed，A 为原授权 authorized，Q 为独立可信用户任务合同的 task_permitted。固定 Best Fixed=T；All 顺序 T→P→M，遇首个 deny/confirm 短路。

- T 当且仅当 Q=false 时 deny。
- P 仅在 Q=false 且来源不能提供指令授权时 deny，或来源缺失时 confirm。
- M 仅在 Q=false 且命中撤销Memory时 deny。
- Evidence 和 Coarse 在 Q=false 时必选T；Q=true时可能选择的P/M都allow。
- G先拦截A=false，且从不改写原授权事实。base.executed=false也不能被附加层改成true。

因此，对于相同当前请求证据，四组 Best Fixed=T、All、Evidence、Coarse 的最终执行标志均为：

`executed_after = B AND A AND Q`

Grant-only 为 `B AND A`；Monitor 保留 B。Q来源是独立手写的用户任务权限集合，不是gold动作序列；然而这个封闭任务合同足够精确，导致P/M在上述四组中没有独立改变放行结论的空间。P/M单组件开发位置可能有自己的行为，这不消除四个正式组的结构性支配。

## 对实证结论的约束

四个组仍有不同选择组合、检查次数、投影/选择/干预耗时；All在允许请求上检查三个组件，T/Coarse/Evidence数量不同。线上请求序列来自独立模型采样，可能产生不同费用、任务结果和风险结果，但不能把这些差异直接归因于四组不同的最终放行能力。

所有组目前仍先做完整来源投影，Coarse只是选择器不用相应特征；因此不能将其解释为免除了图读取的完整系统成本。Evidence减少检查次数也不等于减少模型账单。

本轮可以检验：G与任务合同拦截的实际表现；固定/动态选择开销；来源证据、恢复、严格反事实与指标管道的可执行性。它不能识别：P/M在强T之上的增量安全收益，或者Evidence选择比Coarse具有独立安全优势。

最终结论必须区分数据交付COMPLETED与假设支持情况。即使Evidence观测任务成功率较高，也不能以此声称来源/Memory动态路由优越。没有真实同状态任务效用反事实最优参考，Selection Regret仍为N/A。此次不事后重设计组件或扩大实验，后续设计问题仅登记，不启动T20。

模型接口另受继承的T17 PromptContract约束：模型收到allowed_action_ids和installed_skill_expected_output。这是所有组共有的技能候选输出，Router不读取；研究结论限于此受控接口，不能把任务成功率外推成无候选提示的自主任务完成能力。详见DATA_README.md。
