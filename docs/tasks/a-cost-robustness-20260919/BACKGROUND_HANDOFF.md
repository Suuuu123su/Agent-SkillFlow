# 新会话背景：为什么只继续 A

## 主线与概念

用户研究 agent skill 投毒与安全，希望以 SkillFlow 描述 skill 与运行环境的权限、来源、生命周期和实际效果关系，并进行统一测量。Evidence 防御用于验证框架，不以最强防御排行榜为目标。

A 研究的是：证据缺失时，怎样在有限资源下补齐支持可靠判断的记录。静态策略按某指标固定顺序取证；动态策略根据当前缺少的前提改变顺序。例如拿到执行回执后仍缺 session 绑定，应该补 lifecycle 通道。point 表示可确定判断；unknown 是证据不足，不能算安全或正确。Full 是完整观察比较器，不等于独立真值。

B 是另一个“事前预测失效与局部干预”的先导。它在一个真实 OpenClaw 环境中完成，但三种方法表现相同，NO_GAIN，第二环境阻塞。本轮不继续 B。

## 已有事实

1. HIAA 分母名单修复已经完成：P4 对齐 P3 valid_only 成组合同，48项名单、156项派生输出、13项针对性测试核对，顶层点值不变。原 P3/P4 的 ALR/RIR/CI 语义限制仍保留。
2. PR #1 使用48次真实本地文件/SQLite执行、12任务族；development/heldout各24单元、6族。134400条预测/费用行是缺证、预算、策略的重复测量，不是独立样本。0新增模型调用。
3. PR #2 的 A 已修复便携路径读取、ACK隐藏session时遗漏lifecycle提示、静态选择目标与梯形AUC不一致。旧数据与源码封存不改，另做一次纠错重分析，新增业务执行0。
4. 修正版动态/静态族等权归一化AUC为 `0.09130200476774569 / 0.0896106231015644`，差 `+0.0016913816661812964`，旧差约`+0.0008399665`。六族均正，旧版3正3负；静态最终选序不变，各预算错误确定判断未增加。
5. 中间预算50761/58954 bytes的动态覆盖优势约0.496个百分点；最高76363 bytes约0.0496个百分点。说明不只最高预算端点有差异，但不能排除封包成本定义的整体影响。
6. 原完整包16/24仅因公开头部多1–6字节无法在最高预算买齐。原通道quote含固定padding，是序列化负载代理。原AUC结果不能直接外推线上采集效率。
7. 独立真值主要覆盖 `controlled-persistent-effect-v1` 的UEA和TaskSuccess：受监督动作的持久文件/SQL变化、精确授权/资源/session/时间。生产完整Manifest/Grant双重授权、全部Scope/Lifetime、瞬时回滚效果、只读/幂等任务成功均未完整验证。

目前判断是：A 有有限、方向一致的小增益，值得一次有上限的稳健性检查；尚未支持强动态算法或通用效率贡献。用户要求先验证有没有希望，不为正结果不断换题或扩跑。

## 本地必须读的证据和代码

路径相对仓库根：

- 旧数据根 `论文材料/证据合同补强_20260919/strengthening-20260919-085337/`：`FINAL_PLAN.json`、开发/留出查询、raw、oracle、licensed_source、封存及历史预测；`PLAN.json`只是旧父计划。
- 收口根 `论文材料/补证收口与能力先导_20260919/closeout-pilot-20260919-1100/`：`FINAL_REPORT_CN.md`、`SUMMARY.json`、`REPRODUCE.md`、`CLAIM_EVIDENCE_MATRIX.md`。
- 收口 `closeout/`：`CLOSEOUT_PLAN.json`、`CLOSEOUT_RESULTS.json`、`AGGREGATE_CURVES.csv`、`ROW_CHANGES.csv.gz`、预测/费用记录、只读核账。
- 最新修订实现：`experiments/closeout_pilot/evaluation.py`、`predictor.py`、`reanalysis.py`、`audit.py`、`paths.py`。
- 原冻结支撑：`experiments/evidence_contract_validation/transport.py`、`policy.py`、`dependencies.py`、`masks.py`、`sandbox.py`、`adapter.py`、`independent_oracle.py`、`family_registry.json`、`reporting.py`。

冻结入口检查源码哈希且拒绝覆盖；新任务应另建版本化模块和输出目录，不能向旧run再次运行collect/evaluate/reanalysis，也不能重签旧SHA以掩盖改动。

## 实施时已经知道的坑

- `padded_packet(bundle, quote)` 把quote当真实字节长度。C2的“每通道1单位”不能直接传入它；决策成本与真实传输字节必须分账。
- 最新 `orders_for()` 给动态与静态相同的已选基础顺序，动态只根据missing_channels重排；应保留这个公平比较。
- 新成本需要重选静态，但选择只能使用旧development和原有限候选集，动态规则不调。
- 旧sandbox的单个variant同时控制授权安排和执行故障，不能假定它已支持“无效授权×不提交”四格。必要时新增轻量版本化runner，把授权条件和执行条件分开，保持预测器、证据合同与独立oracle语义不变。
- 实验场景标签只能给调度/评估层，不能通过unit_id、文件名、fault字段、免费包形状或报价泄漏给补证策略。代理读取已许可投影，不能访问真实状态或oracle。

GitHub证据：[PR #1](https://github.com/Suuuu123su/Agent-SkillFlow/pull/1)、[PR #2](https://github.com/Suuuu123su/Agent-SkillFlow/pull/2)。本任务只做研究价值筛查；已有材料不等于完成新颖性认证。
