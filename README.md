# Agent-SkillFlow

SkillFlow研究Agent Skill与Harness交互中的安全机制，以统一运行证据连接实际Effect/Receipt、授权、来源、撤销与任务完成。

**论文主线：统一运行证据 → HIAA/ALR/RIR/UEA/Provenance/CI机制测量 → P3/P3R结果 → P4证据消融 → P0公开任务测量差异 → Evidence防御应用。**

## 当前阶段与结果

<!-- closeout-pilot:start -->

2026-09-19 收口与能力先导M0–M4完成：**A可信收口PASSED；B相对B1/B0为NO_GAIN**。A旧48次执行、134400对及80曲线核账通过；纠错重分析动态−静态AUC +0.001691（已公开留出，不是新盲测）。B单真实OpenClaw环境有效72场景，含资格/失败/重试累计83/96次，模型/Judge/付费API均0。三方法32留出预测一致；4/4族局部原生边界修复阻断越权且正常功能保留。00/10组合正常任务失败，第二环境BLOCKED_EXTERNAL，全部负结果保留；不继续扩样。

[最终中文报告](论文材料/补证收口与能力先导_20260919/closeout-pilot-20260919-1100/FINAL_REPORT_CN.md) · [机器摘要](论文材料/补证收口与能力先导_20260919/closeout-pilot-20260919-1100/SUMMARY.json) · [83次账本](论文材料/补证收口与能力先导_20260919/closeout-pilot-20260919-1100/ALL_ATTEMPTS.csv) · [复验/执行命令](论文材料/补证收口与能力先导_20260919/closeout-pilot-20260919-1100/REPRODUCE.md)。原工作区修改与旧封存保留。

<!-- closeout-pilot:end -->

<!-- evidence-strengthening-current:start -->

2026-09-19 新一轮证据合同补强：**M0–M3 已完成；研究验收 PARTIAL**。48个逻辑单元/12族，实际沙箱48/192，模型调用0；1087项新测试及HIAA13项回归通过。受控变体UEA/TaskSuccess留出48点参照与Full一致，缺证回放未见错误确定判断；静态对全局固定AUC +0.02033，动态对静态仅+0.00084且3族升3族降。16个留出完整包仅超最高预算1–6字节，故保留协议内覆盖前沿，**不宣称通用效率或强动态算法优势**。外部合格参照、完整生产合同及ALR/RIR/CI因果条件仍缺。原工作区和历史档案未变。

[最终中文验收](论文材料/证据合同补强_20260919/strengthening-20260919-085337/FINAL_REVIEWED_RESULTS.md) · [机器摘要](论文材料/证据合同补强_20260919/strengthening-20260919-085337/FINAL_REVIEWED_SUMMARY.json) · [独立全量核账](论文材料/证据合同补强_20260919/baseline-audit/DELIVERY_AUDIT.json) · [执行/复现入口](experiments/evidence_contract_validation/README.md)。下一步边界：本轮仅提交研究PR，不自动合并、扩样或新增模型调用。

<!-- evidence-strengthening-current:end -->

2026-09-19（修复与先导已上传至GitHub）：HIAA分母修复完成，F/H ToolReturn valid_only恢复每格13；48项逐格样本集合与P3R一致，156项离线修正版输出及13项针对性测试通过，点值不变。已完成240查询补证先导、235查询有限参照扩展及三对合成见证；动态策略未超过按指标固定顺序。新增模型、Judge、业务调用均为0。[修复与实验总览](论文材料/修复与补强_20260919/README.md) · [结果及论文措辞](论文材料/修复与补强_20260919/RESULTS_AND_PAPER_CLAIMS.md)。

本轮补强已在独立研究分支执行，当前状态见上方阶段记录：[本地Codex入口](docs/tasks/evidence-strengthening-20260919/CODEX_GOAL.md) · [实验计划](docs/tasks/evidence-strengthening-20260919/refine-logs/EXPERIMENT_PLAN.md)。重点是独立参照、按任务家族留出和统一字节预算；动态优势不作为预设结论。

P3/P3R与P4已完成并发布，研究缺口和不利结果保留。P4管理状态为`CLOSED_WITH_DOCUMENTED_GAPS`；完成实验与材料交付不等于全部研究主张成立。[当前状态](论文材料/metadata/current_state.json) · [论文材料](论文材料/README.md)。

| 阅读目的 | 入口 |
|---|---|
| 框架实现与合同 | [核心代码](src/skillflow/) · [安全语义](docs/security-semantics.md) · [Schema](schemas/) · [测试](tests/) |
| 当前HIAA修正 | [修复报告](论文材料/修复与补强_20260919/hiaa/README.md) · [修正版四格表](论文材料/修复与补强_20260919/hiaa/HIAA_CELLS_CORRECTED.csv) · [复现](论文材料/修复与补强_20260919/hiaa/REPRODUCE.md) |
| 机制测量 | [P3主表](论文材料/P3_机制测量/p3-20260916-232018/P3_METRIC_MAIN.md) · [P3R主表](论文材料/P3_机制测量/p3r-20260917-103400/P3R_METRIC_MAIN.md) · [指标合同](论文材料/P3_机制测量/p3r-20260917-103400/METRIC_CONTRACTS_P3R.md) |
| 测量证据消融 | [P4主表](论文材料/P4_测量证据消融/p4-20260917-123623/P4_METRIC_MAIN.md) · [结项](论文材料/P4_测量证据消融/closeout-20260917-141455/P4_CLOSEOUT.md) · [表格数据册](论文材料/P4_测量证据消融/closeout-20260917-141455/PAPER_TABLES.md) · [六案例](论文材料/P4_测量证据消融/closeout-20260917-141455/PAPER_CASES.md) |
| 测量差异与防御应用 | [P0结项](论文材料/P0/CLOSEOUT.md) · [P0指标与措辞](论文材料/P0/PAPER_METRICS.md) · [P2 Luna All](论文材料/P2/luna-all/CURRENT_STATUS.md) · [三模型五方法历史结果](benchmarks/clawtrojan/results/three-models-20260915/README.md) |
| 已发布事实与复现 | [T17分卷与索引](datasets/t17-v2/README.md) · [T18独立构念验证](datasets/t18-local/README.md) · [四份原始审查ZIP](论文材料/发布记录/p3-p4-20260917/README.md) |

## 结论边界

- HIAA按target/neutral×单bridge四格计算；F/H ToolReturn的历史13/15冲突已由追加修正版解决为每格13，旧P4原件保留历史身份。修复不改变点值，不把Evidence-All的ASR差当HIAA。
- ALR保留合同区别、reason缺证与空分母；空分母不是零风险。RIR零值不证明撤销的因果收益。
- 旧CI的593对中289对破坏JSON结构，另304对中和语义未确认；正、零、负结果保留。
- P4有限独立参照覆盖190/192，已答一致190/190，不是通用100%准确率，也不证明框架唯一必要性。表格数据册含541行，不是三张已排版正文表。
- P0辅助标签人审0、unknown及原`PROCESSED_WITH_GAPS`保留；业务违规V不等同UEA。DS混合版本、GLM预算、Luna传输及个人上下文差异未消除。P2历史比较均为`HISTORY_ONLY`。
- 当前事件证据已被防御路径使用，不等于聚合HIAA/ALR/RIR已驱动在线Router。

P0已结项，P1因资源延期，P2已完成；P5画像接口可选且未启动，P6全文未完成。9月17日目录发布本身不授权继续研究实验；9月19日用户另行授权本轮修复与对应实验。

## 历史与仓库布局

源码、测试、Schema及数据保留开发路径。历史审计已移至[docs/history/audits](docs/history/audits/)，早期规范移至[docs/history/specs](docs/history/specs/)，P2旧任务入口归入[历史任务](docs/history/tasks/P2_Luna_All_Completion.md)，两个旧T16启动器位于[scripts/legacy/t16](scripts/legacy/t16/)；历史运行标记不是当前执行授权。

9月17日重组实际迁移16项、将52个与原ZIP逐字节一致的展开任务包文件改为archive-only，根目录文件由14个降至6个。原四ZIP、T17分卷、冻结组件、失败与未知证据保留；Git历史不改写。迁移后位置、哈希、还原方法及冻结旧链接解释见[迁移说明](docs/releases/repo-restructure-20260917.md)与[机器映射](docs/releases/repo-restructure-20260917.json)。

9月17日重组验证仅覆盖受影响路径、链接、Git索引字节、只读定位与发布树；未执行Live启动器、P3/P4复算、全量测试或自愿远端CI。新增模型、Judge、业务工具、反事实执行均为0，算法、指标和原分数不改。独立工作树完成整理，原工作区未提交修改不纳入发布。
