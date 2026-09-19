# 来源和版本审计

从未合并PR #2最新be2bc1f接续，独立研究分支research/a-cost-robustness-pilot；origin正常fetch。旧317ff31实验与be2bc1f收口工作树均保留。原用户工作区diff/status基线单独封存，不执行stash/清理。

新任务ZIP和合并MD核心章节逐字节内容一致，重复计划/记录表一致；MANIFEST已读。M0只读重新验证旧48次执行、旧及修正各134400预测/费用对和80条ALL曲线；旧544文件及修正来源SHA检查通过。新DIAGNOSTIC_PLAN、COST_CONTRACTS和MASK_MANIFEST先冻结；实现与7项相关测试在任何新成本比较前另行封存。

ROW_CHANGES缺少family、unit、metric、condition、seed、首次分歧可见证据与oracle正确性，不能用于完整配对归因。因此E1从完整纠错预测重建22400配对，逐预算/族差与发布数字及面积和对账。所有旧留出已经看过，只能称探索性。

引用：[PR #1](https://github.com/Suuuu123su/Agent-SkillFlow/pull/1)、[PR #2](https://github.com/Suuuu123su/Agent-SkillFlow/pull/2)。本轮在线动作仅为Git同步/PR状态核实，未做新文献扫描或运行环境安装，不继续OpenClaw/B。

费用解释：wire_bytes是原padded-canonical-v1协议头部与恢复包的精确序列化字节，仍非线上通信或时延测量；决策报价另按C1/C2公开规则。实际本地policy stdin请求字节另外统计在各SELECTED_STATIC与TRAJECTORY_SEAL中，缓存命中不重复计入真实IPC。任何这些字节都不是模型token或付费API消耗。
