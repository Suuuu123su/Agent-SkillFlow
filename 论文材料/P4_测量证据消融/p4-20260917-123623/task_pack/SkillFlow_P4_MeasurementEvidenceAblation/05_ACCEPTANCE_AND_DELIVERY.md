# 执行、定向验收与最终交付

## 1. 工作顺序

|阶段|实际实施|输出|
|---|---|---|
|S0 输入冻结|读相关AGENTS和当前工作区；定位P3/P3-R事实及必要原分卷；原件只读|SOURCE_MAP、QUERY_REGISTRY、LOCAL_BINDINGS|
|S1 合同与依赖|绑定每个指标的适用性/单位/分子/分母；把实际副本和派生答案标出来|METRIC_CONTRACTS、MASK_DEPENDENCY_MAP、GOLD_PROVENANCE|
|S2 投影与分析|生成13种隔离视图；同一算法在部分证据下三值/区间计算|分析代码、VIEW_MANIFESTS、READ_AUDIT|
|S3 小切片准入|用已有受控正负/缺证切片跑13视图；定向检查泄漏与负对照|验收明细、错误保留、通过范围|
|S4 全量离线|冻结后运行所有固定查询；各域和合同分层|逐查询预测、AGGREGATE_METRICS、TRANSITIONS|
|S5 论文与交付|独立聚合核对、至少6个实际案例、方法描述与局限；导出最小包|P4主表、报告、审查ZIP、提交清单|

全量只跑一次；程序Bug修复后仅重算受影响数据并保存前版差异。不将每次调试当独立实验，不追求大量重复测试数量。目标一工作日量级，原始数据大小/可得性导致延期时交付已完成范围和具体断点，不承诺后台继续。

## 2. 15项最低验收

1. 新模型/提供方/业务工具执行计数为0；无需读取Key或导入SDK。
2. 原输入和旧指标字节未改；工作输出新目录，不触碰旧STOP。
3. 固定查询去重；F/H、父子分支、k1/k3、多个profile不冒充独立任务。
4. 预测目录不含expected/gold/旧终点、scenario答案标签和语义提示ID。
5. 各家族所有副本/派生缓存纳入依赖映射；至少一个真实grant_snapshot旁路被测试阻止。
6. 没有只删最终指标列；实际可见输入哈希与读取日志对应。
7. Full→Mask与Mask→Full两种调用顺序产生相同语义结果；不存在缓存污染。
8. Receipt缺省不变成无执行，Grant缺省不变成无授权，scope缺省不变成无限许可。
9. 真假合取短路正确；已确定风险或业务失败不会被任务证书缺失洗掉。
10. 真实不适用、资格未知、技术分析异常、模型历史技术失败分别报告。
11. 至少一个真实可重建的命题删证后仍成立；无法找到则具体说明缺哪个事实，不捏造结果。
12. 无关元数据和一致ID重命名保持所测语义；不相关指标不应成批丢失。
13. HIAA区间负号、定比分母与未知资格处理通过独立小例核对；范围不叫置信区间。
14. 独立构念参考与生产预测分离；旧CI不被升级成控制语义gold，新Live ALR空分母不被填0。
15. 所有查询×13profile有结果/合理不适用/具体错误；结果长表能从最小包离线重算，不能只提供图或summary。

这些是准入要求，不是本包已执行通过的项目。存在研究负结果不阻止S4，工程隔离失败才需停止对应计算修复。

## 3. 最终目录

```
论文材料/P4_测量证据消融/<run_id>/
  P4_FINAL_REPORT.md
  P4_METRIC_MAIN.md
  P4_STATUS.json
  SOURCE_MAP.json
  QUERY_REGISTRY.jsonl
  METRIC_CONTRACTS.json
  MASK_DEPENDENCY_MAP.json
  GOLD_PROVENANCE.json
  VIEW_MANIFESTS.jsonl
  READ_AUDIT.jsonl
  results/QUERY_RESULTS.jsonl
  tables/METRIC_ABLATION.csv
  tables/ELIGIBILITY_AND_UNKNOWN.csv
  tables/FULL_TO_VIEW_TRANSITIONS.csv
  tables/REFERENCE_ERRORS.csv
  CASEBOOK.md
  IDENTIFIABILITY_WITNESSES.json
  LIMITATIONS_AND_GAPS.md
  checks/INDEPENDENT_RECOMPUTE.json
  checks/TARGETED_CHECKS.json
  code/...
  minimal_data/...
  REPRODUCE.md
  MANIFEST.json
  COMMIT_REVIEW_LIST.md
  p4-evidence-ablation-review.zip
```

CSV只是结果长表，可用标准库生成，不需要全套网页/Excel工具链。P4主表先列机制指标，错误率只在独立参照子集；实际样本和分析查询数量分别显示。至少6个源案例覆盖：失去点值、合理短路、不受影响、来源或时序、静态上下界、CI语义限制。找不到某类案例时不补假数据。

每条预测最少有：query_id、study、domain、protocol、unit_kind、native_unit_ref、view_id、eligibility、value或lower/upper、status、used_evidence、missing_evidence、minimal_proof、analysis_code_hash。value缺省不得用0占位。

P4_STATUS分别写输入覆盖、视图隔离、定向工程验证、实际计算完成度、独立参考覆盖、语义人审状态和研究结论。不是一个PASS概括全部。

## 4. 交付边界

审查包包含必要实际源码、未跟踪文件、最小输入和可从数据重建的结果；不包含Key、完整provider日志、无关私人内容或模型私有推理。仅报告源哈希不等于可复算，至少每个核心机制有真正可读切片。

不自动上传GitHub，不git add .，不force-push或删除旧结果。用户审核后再按明确提交范围发布；本轮只准备提交清单及论文材料入口的待合并文本。

## 5. 完成条件

可以以COMPLETED_WITH_DOCUMENTED_GAPS结束：全体预登记查询已处理，已有关键机制产生实际消融输出，证据不足及工程缺口分别列出，独立参照和负对照检查完成，科学结论不被夸大。

不能以COMPLETED结束：只有13个空配置、只复制P3汇总、所有缺证直接归零、所有项被程序硬编码unknown、预测器偷读gold、尚无源码或只给计划表。

P4完成后停止。P5的Live补证及Evidence画像路由仍不执行。无需等待或自动轮询下一轮授权。
