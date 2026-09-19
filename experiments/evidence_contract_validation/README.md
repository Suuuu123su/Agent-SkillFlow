# 证据合同补强：可执行入口与边界

本实现只调用本地 Python 标准库执行文件/SQLite 任务；模型、Judge、付费 API 调用为 0。历史 P4/HIAA、原始 ZIP 与旧预测不被修改。

本轮结果目录：`论文材料/证据合同补强_20260919/strengthening-20260919-085337/`。实际执行记录、冻结计划与最终结果以该目录为准。

## 分阶段入口

在仓库根目录、PowerShell 7 下使用现有 Python 3.12 环境：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$studyPython='E:\Skill ＆ Harness\Agent\.venv-skillflow\Scripts\python.exe'
$studyOut='论文材料/证据合同补强_20260919/<新的run_id>'
& $studyPython -B -m experiments.evidence_contract_validation.run prepare --out $studyOut
& $studyPython -B -m experiments.evidence_contract_validation.run check-contract --out $studyOut
& $studyPython -B -m experiments.evidence_contract_validation.run collect-development --out $studyOut
& $studyPython -B -m experiments.evidence_contract_validation.run freeze --out $studyOut
& $studyPython -B -m experiments.evidence_contract_validation.run revise-freeze --out $studyOut
& $studyPython -B -m experiments.evidence_contract_validation.run collect-heldout --out $studyOut
& $studyPython -B -m experiments.evidence_contract_validation.run evaluate --out $studyOut
& $studyPython -B -m experiments.evidence_contract_validation.run report --out $studyOut
```

以上是完整新实验的复现接口，会产生实际执行，**本轮没有授权再运行第二批48单元**。复查已有结果应只验证哈希、重算统计，不调用两个 collect 阶段。所有测试数据及临时文件仅写 E 盘。本轮原始输出不可覆盖；自动重试被禁用。

`REGISTRATION.json` 保存执行前的家族/实例、种子和上限。`PLAN.json` 保留初次开发冻结；`FINAL_PLAN.json` 是留出前最终修订冻结，记录父计划 SHA。修订只发生在留出执行前，用于封存所有独立参照输入，并把开发候选选择的随机seed平均口径与报告对齐。旧候选和冻结都保留。后续阶段自动验证最终源码哈希。

## 合同和来源分层

| 本轮指标 | 实际验证范围 | 未验证范围 |
|---|---|---|
| UEA / `controlled-persistent-effect-v1` | 单个受监督动作的实际持久状态变化；精确动作/资源、session、授予/过期/撤销时间表 | 生产 Scope/Lifetime 全部规则、manifest历史原字节、瞬时后回滚效果、真实 agent 行为 |
| TaskSuccess / 同版本 | 实际文件hash、SQL结果、task/session/resource绑定及持久效果 | 自然语言业务语义、外部任务普适成功 |
| ALR、RIR | 预注册家族存在；参照及预测保持未知 | 原因、合格identity/neutral干预、已确认污染前缀与因果撤销收益 |
| 历史CI/HIAA | 原合同的只读回归和依赖审计 | 新CI语义中和真值或新增HIAA研究结论 |

collector ACK 与独立 supervisor 状态区间是不同采集证据；后者可在 ACK 丢失时提供实际落地事实。`failure` 通道因此包含独立监测的完整性及变化事件，不只是退出码。原始前后字节、SQL表和hash保留在 raw 中；策略只接触该次获准的投影，不能读取 oracle/Full。此隔离是合作式输入隔离，同用户进程不构成操作系统权限边界。

## 成本与统计

固定公共通道报价由开发集计算并填充到真实 canonical UTF-8 字节包；初始头部、初始包和每次补证包均收费。缓存仅减少CPU重复编码，每次回放仍按完整包计费。代理量的边界是 broker 序列化包，不含本地分析 IPC、系统调度或真实线上采集时延。

预算不可行时不向策略交付观察，计费为0并保留共同分母；该行 `required_initial_bytes` 与可见结构大小描述需要提供的初始包，不代表已交付。不同预算独立重放，允许跳过买不起的通道，因此不能默认获得同一条嵌套轨迹。

48逻辑实例来自12个共享构造家族；开发/留出各6族。策略、20种缺证配置、10个预算及随机种子是重复测量。先平均同query/condition的随机seed，再族内汇总、族间等权；不把预测行数作为独立样本量。字节阈值与策略均在留出前冻结；记录器/预测器/oracle采用不同代码路径，但受控任务定义仍共享研究合同。
