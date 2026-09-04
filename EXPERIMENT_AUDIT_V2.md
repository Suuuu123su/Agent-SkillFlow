# T17 第二版交付检查

日期：2026-09-04。结论：**本地数据闭环已完成，完整数据发布与 CI 验收仍待完成（`WARN_PUBLICATION_AND_CI_PENDING`）**。完整数据上传被自动安全检查拦截，已请求明确发布确认；当前 GitHub 只交付代码、汇总、指标和记录清单。这是对已有结果和实际检查的归档，不是新增独立审查；旧 `EXPERIMENT_AUDIT.md/json` 不改写。

| 项目 | 当前结果 | 证据 |
|---|---|---|
| E、F、G 预检、G 正式、H 新增阶段 | 均通过 | 公开集合五个阶段的终态、用量及阶段门 |
| 数量与失败保留 | 1038 个独立核心任务、846 个重放终态；各阶段分别报告 | `datasets/t17-v2/stages/`；不把 H 复用 F 再计一次 |
| 必需指标、任务证据、回执、观测与绑定 | 各阶段完整，指标只有实测／设计不适用 | 阶段及条件指标向量，原失败样本未删除 |
| 模型、防御与技能分层 | 242 组指标向量，25／22／20 份比较 | `datasets/t17-v2/reports.json` |
| 公开事实独立复算 | 已通过全部 JSON／CSV 比对，无新 API | `runs/t17-v2-recomputed-01/`；不使用私有模型正文 |
| 本地原始记录登记 | 59,739 个文件；复用 56,722 项，仅补登 3,017 项 | `docs/evidence/t17-v2-local-raw-inventory/` |
| 静态与格式检查 | 已通过；CI 修复只定向复查改动文件 | 源码、测试及交付脚本检查；400 行上限保留 |
| 严格类型、静态格式、依赖与环境 | 451 源文件、4 交付脚本、120 静态格式；依赖和离线环境通过 | 已执行的本地结果，不代替全量测试 |
| 隔离边界修复 | 5 项定向检查通过；未放开其他模块或能力 | `tests/integration/test_t14_security_isolation.py` |
| 当前完整 CI／覆盖率 | 未通过；首次在 15 分钟取消，修复待复验 | [首次 CI](https://github.com/Suuuu123su/Agent-SkillFlow/actions/runs/33874252249) |
| 独立审查 | `REVIEW_UNAVAILABLE`，运行前结论保留 `WARN` | `docs/evidence/T17_V2_PreLive_Review.md` |
| 全历史费用 | 已知估算 $15.3303527192，保守占用 $15.5443051756 | 14 次尝试已关闭；5 个未知响应使历史用量仍不完整，非账单 |

首次 CI 的实际注释为 “The job has exceeded the maximum execution time of 15m0s”。单个失败用例是旧静态隔离登记未包含已批准的新版入口，修复只允许 `v2/network.py` 导入 HTTP 客户端、`v2/campaign.py` 隐藏读取密钥；socket、环境密钥及其他运行模块的限制仍由反例检查覆盖。没有更改实验判定或原始数据。

CI 上限改为 45 分钟，增加逐例名称、失败简报、JUnit 与覆盖率 JSON 留档；综合覆盖率门仍为 90%，纯分支覆盖率单独输出。当前不得沿用历史 90.13%／75.89% 冒充本版结果。

后续仅处理实际 CI 结果和验收状态，不扩展实验。多攻击技能的真实排名与 SkillFlow-Rx 仍未开展／未实现。机器可读状态见 [EXPERIMENT_AUDIT_V2.json](EXPERIMENT_AUDIT_V2.json)。
