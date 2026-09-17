# 精确缺口与论文可用边界

本地正式事实分卷无缺失；以下为语义、严格口径或核对范围限制，不因单项缺口中止其他指标。

|ID|项目|已定位缺口|当前可用性|证据|
|---|---|---|---|---|
|G01|HIAA_pot静态版本|F/G/H导出含观测Effect集合，没有完整冻结可达状态空间集合|原观测集合差可用；静态理论结论不可用|tables/HIAA_POTENTIAL_SETS.json|
|G02|ALR显式reason|F24/G15/H22暴露请求缺独立baseline_reason字段；原v2可由配置/决策推导|原v2点值加脚注；显式严格版缺证|tables/ALR_STRICT_CONTRACT.csv|
|G03|RIR合格队列|F30→13；G30→0；未另要求已确认污染前缀|0/13仅条件描述；G显示N/A|tables/RIR_SESSION_COHORTS.csv|
|G04|Replay identity稳定性|F5/G16/H1有效对与原核心终点不一致|保留原CI；稳定子集只描述敏感性|tables/CI_IDENTITY_SENSITIVITY.csv|
|G05|模型格式与任务独立性|G171/360含schema_rejection；每模型仅五表述簇重复|scheduled主值可用；不作纯模型因果排名|tables/FAILURE_BREAKDOWN.csv|
|G06|独立核对范围|图深度标签和授权真值仍信任本轮生产图/保存Oracle；区间原算法复现|来源集合与主汇总独立一致；不称完全独立实现|RECOMPUTE_CHECK.json|
|G07|公开导出信任边界|私有正文/服务端模型快照未导出；所有已登记字节与哈希一致|可验证公开结构事实链；不宣称私有语义复核|SOURCE_MANIFEST.json|
|G08|旧T19-R缺审计|历史报告核心1818可测+6未知；审计11可测+1技术失败+1140未到达，完整identity/neutral三联0/576|仅引用缺口，不恢复1824/1152计划、不重发未知|T19R_GAP_APPENDIX.md|
|G09|Evidence边界覆盖|只查同一保存任务的前六个initial_consume边界|证明局部输入/选择/消费链，不能代表所有commit/external边界|METRIC_TO_DECISION_MAP.md|
|G10|人工审查与发布|本轮没有人工审查，也未自动commit/push|可本地审阅，发表前需用户核对关键语义脚注|P3_STATUS.json|
|G11|T17→CT画像迁移|没有已证明兼容的桥梁/任务/合同开发画像|PROFILE_NOT_APPLICABLE；未来缺失回落Local-only|FUTURE_PLAN.md|
