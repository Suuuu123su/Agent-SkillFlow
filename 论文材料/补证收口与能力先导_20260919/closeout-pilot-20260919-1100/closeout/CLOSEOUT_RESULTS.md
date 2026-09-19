# A：可信收口结果

状态：**CLOSED_EXPLORATORY_REANALYSIS**。三项修复完成，完整性门通过；本阶段新增业务执行、模型/Judge/API 调用均为 0。

旧48个单元/12族不变。旧与修正版各134400对重复预测/费用记录；各80条ALL曲线经独立算术核账。1111项相关测试通过，1项符号链接创建因Windows权限跳过；另实际Windows目录junction越界拒绝通过。只声称便携解析测试，不声称Windows/Linux双系统实测。

## old → corrected

|策略|旧留出AUC|修正AUC|最高预算正确覆盖|
|---|---:|---:|---:|
|dependency_guided|0.09045059|0.09130200|86.607143%|
|global_fixed|0.06927951|0.06927951|78.521825%|
|metric_static|0.08961062|0.08961062|86.557540%|
|random|0.07131402|0.07131402|79.150132%|

所有修正后的确定判断错误数为0；缺证、不可行预算与未知参照仍留在分母。每划分48个核心点真值、8个ALR/RIR未知真值；N/A记录数0不等于这些机制已获验证。详见PER_FAMILY、AGGREGATE_CURVES和CLOSEOUT_RESULTS的原始计数。

## 修正归因

路径reader只改变定位方式，不修改原路径串、seal或原SHA。ACK只缺session时补报lifecycle，保留错误session、effect、task、attempt及过期回执的拒绝。已知H01样例从unknown恢复为point true，其完整记录见LIFECYCLE_KNOWN_CASE.json。没有按ID特判。
静态选择改为原候选集内的族等权、seed平均、归一化梯形AUC，保留错误优先/成本/候选序号平局规则。最终选中顺序与旧顺序完全相同，因此本批覆盖变化来自生命周期提示修复；不是重新挑数据、加预算或增加候选。完整候选评分另存STATIC_CANDIDATES.json。

动态对静态差从+0.00083997变为+0.00169138，6族均正，但绝对差仍小且原留出早已公开。这是探索性纠错，不是新的盲测或稳健算法结论。最高预算16/24完整包仍超限1–6字节；padding与header阈值敏感性、有限合同、ALR/RIR/CI限制不变。

## 每族动态减静态AUC

|任务族|差值|
|---|---:|
|H01_publish_directory|+0.00059870|
|H02_inventory_reservation|+0.00229471|
|H03_manifest_package|+0.00121728|
|H04_sql_join_export|+0.00303303|
|H05_queued_approval|+0.00280505|
|H06_revoked_lease_journal|+0.00019951|

完整old→corrected所有汇总指标见OLD_VS_CORRECTED.csv；逐行发生变化的状态/费用/缺证/获取顺序见ROW_CHANGES.csv.gz，未变行可通过配对row_id复验。原始历史文件完全保留。
