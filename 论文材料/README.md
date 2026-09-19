# 论文材料

按“统一证据 → 核心机制测量 → 测量正确性与证据消融 → 公开任务测量差异 → 防御应用”阅读。[当前状态](metadata/current_state.json)是导航汇总；各阶段原状态与清单保持历史身份。

## 2026-09-19修复与补强

[总览](修复与补强_20260919/README.md) · [HIAA修正版](修复与补强_20260919/hiaa/README.md) · [查新](修复与补强_20260919/NOVELTY.md) · [补证先导](修复与补强_20260919/evidence_pilot/README.md) · [有限参照扩展](修复与补强_20260919/evidence_pilot_reference/README.md) · [论文措辞](修复与补强_20260919/RESULTS_AND_PAPER_CLAIMS.md)。

F/H ToolReturn有效四格恢复13，HIAA点值不变。补证实验支持按指标合同排序相对全局顺序的有限收益，当前动态规则没有超过强静态基线；结果不代表通用准确率或线上成本。

## 机制结果与证据消融

- [P3核心指标恢复](P3_机制测量/p3-20260916-232018/P3_METRIC_MAIN.md) · [P3R补全主表](P3_机制测量/p3r-20260917-103400/P3R_METRIC_MAIN.md) · [指标合同](P3_机制测量/p3r-20260917-103400/METRIC_CONTRACTS_P3R.md)。
- [P4证据消融主表](P4_测量证据消融/p4-20260917-123623/P4_METRIC_MAIN.md) · [结项报告](P4_测量证据消融/closeout-20260917-141455/P4_CLOSEOUT.md)。
- [541行表格数据册](P4_测量证据消融/closeout-20260917-141455/PAPER_TABLES.md) · [章节草稿](P4_测量证据消融/closeout-20260917-141455/PAPER_P3_P4_SECTION.md) · [六案例](P4_测量证据消融/closeout-20260917-141455/PAPER_CASES.md)。不是三张已排版正文主表，也不代表P6全文完成。

HIAA历史13/15原结果保留，新修正版已闭环该冲突；ALR不同合同与空分母、RIR零值的因果限制、旧CI中和语义仍保留。P4有限参照覆盖190/192和已答一致190/190分开报告，不能解释为通用100%准确率或框架唯一必要性。

## 公开任务测量差异与防御应用

- [P0结项](P0/CLOSEOUT.md) · [P0指标及限定措辞](P0/PAPER_METRICS.md) · [全部五方法](P0/ALL_METHODS.md)。
- [原生历史15组](P0/tables/native_history15.csv) · [P0端点](P0/tables/p0_endpoints.csv) · [30分层](P0/tables/p0_30_strata.csv)。
- [P2 Luna All最终报告](P2/luna-all/P2_FINAL_REPORT.md) · [P2状态与复现](P2/luna-all/CURRENT_STATUS.md) · [三模型历史应用](../benchmarks/clawtrojan/results/three-models-20260915/README.md)。

P0辅助标签人审0、unknown与原PROCESSED_WITH_GAPS保留；V不是UEA。DS混合版本、GLM预算、Luna传输与个人上下文限制保留；P2历史对照均为HISTORY_ONLY。当前事件证据消费不等于聚合指标驱动Router。

## 归档与复现边界

[四份完整原审查包](发布记录/p3-p4-20260917/README.md)原字节保留；本轮去掉52个重复展开任务包文件，包内成员、保留位置与提取方式见[迁移说明](../docs/releases/repo-restructure-20260917.md)及[逐文件映射](../docs/releases/repo-restructure-20260917.json)。已有离线复算器需要完整长表或task_pack时，先在新目录还原对应ZIP布局，不执行包内Live启动器。

旧P0的[来源](发布记录/p0-20260915/metadata/sources.json)、[状态](发布记录/p0-20260915/metadata/status.json)与[manifest](发布记录/p0-20260915/metadata/manifest.json)已归档；原相对根为`论文材料/`，十项manifest精确对应`caad8858cad5cdf9e8be3f0c7bf28eca00d0ad44`，不是当前文件树清单。P0三个来源原件未见于公开树/包，不能据公开汇总声称完整逐观测资料可得。

P1延期；P5未启动；P6未完成。9月17日发布仅作目录迁移与导航修复；9月19日新增修正分析版本和离线先导，原归档及其状态不回写，新增模型调用0。
