# 零新增调用的复现说明

需要已有 `datasets/t17-v2`、`datasets/t18-local`、相同哈希的原分析源码和本地Python环境；完整来源版本见SOURCE_MANIFEST与audit/ANALYSIS_CODE_MANIFEST。静态Evidence映射另需清单列出的父目录冻结源码和所选保存边界。因此 `requires_existing_public_collection=true`。

所有脚本仅作本轮分析源码，未作为Skill/实验启动器使用。主入口recover.py阻止网络/子进程/凭据文件与输出目录外写入；使用现有Python的 `-B`。独立器不导入生产指标函数。review ZIP可以直接检查中间表和最终值；验证原事实需要上述源集合。

不要在原交付目录重跑覆盖审查记录。需要重算时，在同一级P3_机制测量下创建另一个新run目录，复制analysis和audit/head.txt等版本记录，保持`analysis/<script>.py`的相对层级。按顺序运行recover.py → independent.py → supplement.py → t18_refine.py → finalize_tables.py → write_reports.py。当前independent.py已修正单位权重；correct_weight.py仅用于保留本次首次错误与定向修正的历史，不需在已修正版再次调用。

recover.py生成FRESH_VECTORS与首次封存后，supplement.py才读取历史报告。新复现目录里的SOURCE_MANIFEST和初始HEAD记录应由执行者在运行前从真实只读工作区生成，不能直接把本目录旧HEAD当新环境事实。不要运行旧launcher、导入/初始化SemanticReviewer或Provider、恢复任何Replay/模型队列。

包内小型定向验证见audit/DELIVERY_VALIDATION.json。这里没有授权未来P4/P5/RX或发布操作。
