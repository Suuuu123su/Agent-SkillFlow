# 仓库实体整理与保全记录（2026-09-17）

基准：[`99fc346b4daca9405078555110a09796cb991567`](https://github.com/Suuuu123su/Agent-SkillFlow/tree/99fc346b4daca9405078555110a09796cb991567)。本次为REPO-RESTRUCTURE-PUBLISH-v2，实际迁移16项，52个冗余展开任务包文件改为archive-only；逐文件旧/新路径、Git blob及SHA256见[机器清单](repo-restructure-20260917.json)。根文件14→6，原位置不留转发副本。当前入口为[项目README](../../README.md)与[论文材料README](../../论文材料/README.md)。

| 归类 | 实际位置 | 数量 |
|---|---|---:|
| 历史审计 | [docs/history/audits](../history/audits/) | 4 |
| 早期规范 | [docs/history/specs](../history/specs/) | 2 |
| 旧T16启动器 | [scripts/legacy/t16](../../scripts/legacy/t16/) | 2 |
| P0汇总与表格 | [论文材料/P0](../../论文材料/P0/) | 4 |
| P0旧元数据 | [历史发布metadata](../../论文材料/发布记录/p0-20260915/metadata/) | 3 |
| 已结束P2任务 | [P2_Luna_All_Completion.md](../history/tasks/P2_Luna_All_Completion.md) | 1 |

## 去重后的获取与依赖

P3R任务包19个、P4任务包17个、收尾任务包16个文件均与各自继续公开保留的原ZIP成员逐字节相同。只移除这些展开副本；四份完整审查ZIP、原结果、T17分卷、冻结组件库、失败与未知记录均保留。去重不会缩减Git历史下载体积。没有删除唯一研究证据，也没有整理原工作区未跟踪内容。

[四份ZIP与原SHA256](../../论文材料/发布记录/p3-p4-20260917/README.md)继续是完整布局入口。机器清单的每条`archive_only`记录提供`retained_archive`和`retained_member`，不是不可获取的哈希占位。

需要离线复核时，先在仓库根核对ZIP的SHA256，再解包到**新的E盘目录**。例如P3R：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '论文材料/P3_机制测量/p3r-20260917-103400/p3r-completion-review.zip'
Expand-Archive -LiteralPath '论文材料/P3_机制测量/p3r-20260917-103400/p3r-completion-review.zip' -DestinationPath 'E:/SkillFlow-review/P3R-20260917'
```

P4与收尾包同理使用各自ZIP与不同的新目录。成员`task_pack/...`会恢复在解包根下的原相对位置。P3R便携入口为`review_slice/recompute.py`，P4为`code/reproduce_offline.py`，收尾文稿为`code/render_tables.py`；依各包原REPRODUCE说明操作，本轮未执行这些复算器。

历史生成/审计源码仍有PACK依赖：P3R的`capacity_slots.csv`、`plan.json`及任务manifest，P4的源构建/准入脚本，收尾的外部评审引用与manifest遍历。不要直接从缺少task_pack的展开目录运行这些历史生成器；还原相应完整ZIP后才具备原任务文件布局。跨阶段历史构建器仍须按原DEPENDENCIES准备依赖，当前发布不声称单包可重建所有实验。不执行包内task_pack工具、Live启动器或恢复流程。

## 历史身份与必要例外

- P0旧manifest的原相对根为`论文材料/`，十项在`caad8858cad5cdf9e8be3f0c7bf28eca00d0ad44`全部按Git blob长度和SHA256匹配；没有修改旧清单来适配新树。原P0状态中的“下一步P2”是历史文本，当前状态另见[唯一状态入口](../../论文材料/metadata/current_state.json)。
- 冻结的审计Markdown保留原字节。`EXPERIMENT_AUDIT_V2.md`中的两个`docs/evidence/...`相对链接仍按旧根解释；[固定提交的原版](https://github.com/Suuuu123su/Agent-SkillFlow/blob/99fc346b4daca9405078555110a09796cb991567/EXPERIMENT_AUDIT_V2.md)可正确浏览，机器清单明确列出这两条例外。没有把冻结历史链接计为当前链接全通过。
- 冻结P0报告和旧PUBLICATION_MAP中的路径是原发布身份；旧P0报告中的`P0/ALL_METHODS.md`/`metadata/sources.json`等文字路径通过迁移映射和旧相对根解释。实际当前链接由两级README提供，不回写原分数、报告、状态或哈希。
- T17历史校验器仅对两个精确的旧审计键增加只读位置兼容：原位置存在时仍校验原位置；不存在时定位`docs/history/audits/`。原清单键、字节漂移拒绝和越界检查不变。其他加载器、实验算法、指标合同、冻结源码副本不改。
- `experiments/`及`runs/`保留既有布局和依赖，没有为了减少目录数移动冻结组件；P0三个来源原件公开缺口、HIAA 13/15、ALR/RIR/CI语义限制继续保留。

## 本次验证与发布范围

两个旧启动器只修项目根表达式；仅静态解析与独立路径表达式检查，未运行脚本或其帮助入口。对Git暂存区逐blob确认纯移动字节不变、删除项均有原ZIP成员；新增属性覆盖迁移后的冻结JSON/CSV。普通文档链接修订记录前后身份，当前导航及所有受影响可编辑链接作路径检查，旧已有断链和冻结引用单列。

新增模型、Actor、Checker、Judge、业务工具、反事实、P3/P4复算均为0。不更改Evidence、原结果或分母，不启动P1/P5/P6。不运行全库测试、自愿远端CI，不改变CI或分支保护。正常fast-forward发布；不force-push、不改写历史。发布后重新读取GitHub提交树与README，最终提交SHA及远端结果以实际Git记录和交付回执为准。
