# T18 开始审计（2026-09-04）

状态：准备完成，实现与实验尚未完成。原计划为 228 个脚本任务、32 个模拟接口任务；用户要求补齐 HIAA 后，冻结前机械修正为 264／44，重放上限仍为 20／8 对，真实 API 与费用均为 0。

- T17 第二版已完成，保留独立审查不可用及历史费用警告。基线提交为 `707cf07`，当前 `e54f7d0` 只增加 T18 计划；T17 冻结数据、配置、指标、总结和原始记录不改写。本次尚未声称重新核验全部旧文件哈希。
- 已完整阅读 README、进度、T17 完成总结、公开数据说明、论文主线、研究设想及 T18 计划；已核对技能目录、能力指纹、技能比较、可信运行环境、任务证据、防御比较和检查点重放实现。
- 既有目录有 15 个物理技能包、24 个配置；`catalog_models.py` 检查身份与能力配对，`skill_comparison.py` 按技能和相同环境比较，`dataset_io` 支持独立复算。现有控制的授权、会话等可能不同，不能直接宣称全部满足 T18 的同能力、同授权配对。
- 最小新增区域为 `src/skillflow/defense/`（可信信号与四种防御）、`src/skillflow/experiment/t18/`（目录、执行与复算）、对应测试、`experiments/t18/`、`schemas/t18-*`、`datasets/t18-local/` 和 T18 文档。根命令只注册新入口；旧公开 Harness 接口不改。
- 复用事件库、精确授权检查、安全接收端、任务证据和隔离重放。基础授权计算始终执行；监测模式允许的越权 Mock 效果仍计风险，附加防御只能收紧，不能更改授权真值。
- 官方来源核对：ACL Anthology 的 [Task Shield](https://aclanthology.org/2025.acl-long.1435/)／[IPIGuard](https://aclanthology.org/2025.emnlp-main.53/)、NeurIPS 的 [DRIFT](https://proceedings.neurips.cc/paper_files/paper/2025/hash/77f3b26c7907aa27b207df9b9d43f29a-Abstract-Conference.html)、USENIX 的 [AttriGuard](https://www.usenix.org/conference/usenixsecurity26/presentation/he-yu)。只作本地机制适配，不运行作者代码，不声称完整复现。StruQ 的专门训练不在范围内。
- 原 228 个任务遗漏 C1/C2 完整四格；此前“设计不适用”的解释已由用户指出并撤回。正式冻结前补齐 72 个脚本四格单元（36 个原调度单元、36 个缺格），并在模拟接口域补齐两种模式的 16 个单元（4 个原调度、12 个缺格）。缺格必须是 `incomplete`，不借用 T17 数字。单次确定性实验不做总体显著性推断。
- 先冻结无标签路由规则，再建立留出技能；公开标签只进入离线评分或明确标记的理想路由基线。必要重放按实际需求计数，达到上限不得继续运行。

全项目质量检查只在最终进行一次；期间只执行短批次定向验证。用户的 T12 README 修改、草稿、旧覆盖率及临时目录保留，不纳入本轮提交。
