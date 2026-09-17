# P4：测量证据消融——只改变分析器视图，不改变已发生的事实

**阶段ID：`P4-MEASUREMENT-EVIDENCE-ABLATION-v1`。本包是待执行任务，不是实验结果。**

目标：用同一批P3/P3-R已保存事实，检验HIAA、ALR、RIR、UEA、Provenance、CI及任务完成判断分别依赖什么证据；证据不足时，分析器是否正确给出范围、未知或不适用，而非错误的确定结论。

本轮新增Actor、Router、Checker、Judge、攻击生成、本地模型、API和业务工具重放全部为0。不是对Evidence防御组件做消融，也不是删除Memory后重新让模型续跑。历史数据和旧指标不改。

## 阅读顺序

1. `01_CODEX_GOAL.md`：作为当前用户消息发给本地Codex，含授权、目标与停止边界。
2. `02_BACKGROUND_AND_INPUT_MAP.md`：新对话背景、确切输入与已知限制。
3. `03_ABLATION_PROTOCOL.md`：13个视图、实际隔离、独立参照与统计单位。
4. `04_METRICS_AND_EXAMPLES.md`：指标、三值逻辑与12组好坏例子。
5. `05_ACCEPTANCE_AND_DELIVERY.md`：实际实现顺序、必交结果、定向验收。

`plan.json`、`ablation_profiles.json`是配置规格，不包含已经绑定的本地结果。`contract_examples.json`是说明性测试向量，不是新增Live数据。`references/`是原报告只读副本，不能作为待测分析器的隐藏答案。

## 本轮应得到的主表

行是证据视图；列先HIAA/ALR/RIR/UEA/来源/CI，再任务与失败解释。每格报告固定查询数量、点值/区间/未知/不适用及适用性未知，受控独立参照上另报错误确定结论。

成功不要求Full每项都有值，也不要求删证后全变NA。发现冗余、负面对照不变、合理短路保留结论，都是有效结果。不能用大量unknown掩盖未实现，不能把缺证回零。

## 边界

P3/P3-R结项；P0不重做；P1继续延期；P2不重跑；Evidence画像路由不实现。允许必要分析代码、定向离线测试和本地论文材料，不自动commit/push，不全库或远端CI，不重开任何旧STOP/HOLD。
