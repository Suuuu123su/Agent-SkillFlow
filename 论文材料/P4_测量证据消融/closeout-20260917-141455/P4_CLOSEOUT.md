# P4结项

管理状态：**CLOSED_WITH_DOCUMENTED_GAPS**。原P4仍为COMPLETED_WITH_DOCUMENTED_GAPS，原输入、预测、标签和状态未改动。

## 交付与研究结论

[三表](PAPER_TABLES.md)由同一份整理数据输出MD、UTF-8 CSV和LaTeX：表A 138行、表B 273行（完整4758层附表）、表C 130行并附13视图总体。[六张案例](PAPER_CASES.md)、[章节草稿](PAPER_P3_P4_SECTION.md)、[主张矩阵](CLAIM_EVIDENCE_MATRIX.csv)已完成。支持证据影响测量可辨识性的部分结论，未证明框架唯一必要性、通用自然语言准确性或Live撤销因果收益。独立人审仍0。

来源点值损失8166分为7472自身和694下游（ALR87、CI593、RIR14），不用于证据重要性排名。两种严格ALR合同分别保留；P4 E_STS仅显示为STS_target_contract。Full可判190/192，已答190/190与有限参照一致。

## 四层记录分开

- 原数据处理：固定19392查询×13视图，252096保存结果；原工程记录和研究限制均保留。
- 既有验证：作者便携832、作者ZIP832、外部报告832分别引用；不相加，不是本轮新增验证。外部报告为任务包提供的既有报告，不冒称本轮独立人审。
- 本轮检查：唯一一次读取保存预测并重聚合，4758层及参考计数一致；16项文档/数值/别名检查、61份使用来源哈希、原P4的184清单成员及原ZIP保全检查。没有新预测、原事实复算或64×13便携运行。链接与本包成员校验见[CLOSEOUT_CHECKS.json](CLOSEOUT_CHECKS.json)；最终ZIP字节回执单独在同目录ZIP_RECEIPT.json。
- 研究支持：有限参照314查询中308资格可知、192有确定适用真值；查询和会话相关，不是192独立任务。范围与抽样置信区间分开。

## 保留缺口

F/H ToolReturn valid_only四格在P3R各13、P4各15；点值均1不能合并分母。本轮记录[两个版本冲突](NUMERIC_CONFLICTS.csv)，不修原预测。旧CI有289/593中和破坏JSON、其余304语义未确认；新增Live ALR空分母、RIR零值无撤销收益证明、confirmed-prefix缺资格分母仍保留。完整限制见[RETAINED_LIMITATIONS.md](RETAINED_LIMITATIONS.md)。

## 归档边界

所有新增模型/业务/重放调用0。只追加本地论文入口和进度原文，保全记录在checks/ENTRY_UPDATES.json。未commit/push，[待提交清单](COMMIT_REVIEW_LIST.md)要求只选本次新增块。小型ZIP不内嵌旧大包，依赖准确路径与SHA256见[DEPENDENCIES.json](DEPENDENCIES.json)；[复现说明](REPRODUCE.md)明确文稿重建与原实验依赖。P1继续延期，P5/P6未开始。完成此结项即停止。
