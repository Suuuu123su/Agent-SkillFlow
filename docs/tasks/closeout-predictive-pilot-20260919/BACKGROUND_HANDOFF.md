# 新会话背景：为什么先收口，再做预测与干预先导

## 1. 研究主线

用户研究 agent skill 投毒与安全，目标是系统性、可量化的 SkillFlow 框架。Skill 可以包含说明、资源和流程；harness 是连接模型、工具、权限、记忆与执行控制的运行环境。同一个 skill 的风险，可能取决于这些环节如何交互。

已有论文叙事：统一运行证据 → HIAA/ALR/RIR/UEA/Provenance/CI 机制测量 → P3/P3R → P4 证据消融 → P0 公开任务测量差异 → Evidence 针对性防御应用。框架是主线，防御用于验证。新先导应检验框架是否能在结果出现前指出失效条件，并通过干预检验原因。

术语简释：Grant 是实际授权；Scope 是授权的动作和资源范围；Lifetime 是有效时间/会话。Receipt 是执行回执，不能单独保证动作落地。Provenance 是数据来源和传递关系，不等于授权。独立真值来自授权要求和外部状态检查，不能由被测预测器自己生成。unknown 表示证据不足，不能算安全或正确。

## 2. 已完成与不可混淆的结果

- HIAA 分母修复已在提交 `4ba3aaf5e53b17733e0858b5394ec153c03998b4` 落地：P4 恢复与 P3 的 valid_only 成组名单一致，F/H ToolReturn 每格 15→13；48 项名单、156 项派生输出与 13 项针对性测试已核对，顶层 HIAA 点值不变。不要重新打开全量 P3/P4。
- 早期 240 查询补证先导、235 查询扩展及 3 对合成见证已经看过，属于开发/回归材料。两批查询有重叠，不是 475 个独立任务。动态补证未显示稳定总体优势。
- 随后 PR #1 完成 48 次真实本地沙箱执行，12 个任务族，开发与留出各 24 单元/6 族；新增模型调用 0。1087 项测试不是 1087 个独立任务；134400 行预测/费用是重复测量。
- 留出中，受控持久效果合同的 UEA/TaskSuccess 共 48 个点真值与完整观察一致；8 个 ALR/RIR 查询仍未知。缺证回放未观察到错误确定判断，不等于所有查询都正确回答。
- 原族等权覆盖 AUC：global 0.06927951，random 0.07131402，metric_static 0.08961062，dynamic 0.09045059。动态比静态约 +0.00084，6 族中 3 正 3 负，最高预算二者均约 86.56%。这些是旧结果，修后需另报。
- 16/24 留出完整包只因头部多 1–6 字节超过最高预算。成本是特定 padding/封包协议的序列化负载代理，未测真实线上成本。留出的是新任务操作，仍共享合同、adapter 和故障原型。
- 生产完整 Manifest/Grant 双重授权、完整 Scope/Lifetime、瞬时后回滚效果未覆盖；TaskSuccess 变体不覆盖只读/幂等成功。ALR 原因、RIR 污染前缀、CI 语义中和限制继续保留。

## 3. 本轮必须阅读的仓库证据

所有路径相对仓库根目录：

1. `docs/security-semantics.md`；`论文材料/P3_机制测量/p3r-20260917-103400/METRIC_CONTRACTS_P3R.md`。
2. `论文材料/修复与补强_20260919/RESULTS_AND_PAPER_CLAIMS.md`。
3. `论文材料/证据合同补强_20260919/strengthening-20260919-085337/FINAL_REVIEWED_RESULTS.md`、`FINAL_REVIEWED_SUMMARY.json`、`FINAL_PLAN.json`、`COMMANDS.jsonl`。
4. `论文材料/证据合同补强_20260919/baseline-audit/CLAIM_SCOPE_REVIEW.md`、`FINAL_CLAIM_REVIEW.md`、`verify_delivery.py`。
5. `experiments/evidence_contract_validation/README.md`、`dependencies.py`、`predictor.py`、`policy.py`、`evaluation.py`、`reporting.py`、`run.py`。
6. `docs/openclaw-adapter-design.md`、`src/skillflow/adapters/live_reference_harness.py` 及实际 OpenClaw adapter/runner。

## 4. 完成报告之后发现的三个缺口

旧封存路径用了 Windows 反斜杠，Linux 原核账脚本无法解析；只在内存中做相对路径兼容后，旧 48 次执行、134400 对预测/成本行与 80 条 ALL 聚合曲线能通过核对。这不等于原脚本已经修好。

ACK 的 session 绑定会被 lifecycle 投影隐藏，但 `_execution()` 某些缺证分支只请求 receipt/failure；动态策略因而可能漏补 lifecycle。已知例：`H01_publish_directory_02:UEA / random_3 / seed=19121 / budget=66121`。静态 `heldout:0003465` 用 63053 bytes 得到 point true；动态 `heldout:0003475` 用 62029 bytes 后仍缺 lifecycle。它是回归样例，不是整体优劣证明。

`choose_static()` 按离散预算点等权平均选择候选，而最终报告按不等间隔预算计算梯形 AUC。应统一选择目标，仍只用开发真值、原候选集和原预算。

旧 CLI 会检查冻结源码哈希，replay 不许覆盖，旧 report 还依赖原 Windows 工作区路径。因此须新增版本化纠错入口，不能改源码后直接对旧目录跑 evaluate/report，不能修改或重签旧 FINAL_PLAN。当前原留出已被研究人员看过，纠错结果必须称“已公开留出上的修订重分析”。

## 5. 新颖性与外部验证边界

[Skill-Use](https://arxiv.org/abs/2608.04828) 已研究不同 harness 下的 skill 表现；[VIGIL](https://arxiv.org/abs/2606.26524) 已研究跨调用时序、参数和值流约束的运行时检查。因此“关系检查”或“环境不同结果不同”本身不够。当前候选只通过有限近邻检查，尚未获得完整新颖性认证。

候选增量是：冻结交互规则，在未见配置组合上预测真实失效；预先指定单处修改，验证它是否消除副作用并保留正常任务。不要宣称已有工作没有此能力，除非进一步核实原文。

仓库的 MockPilotAdapter 不是第二真实环境；`live_reference_harness.py` 继承 MockHarnessAdapter，名字中的 live 不能作为资格证明。更换模型也不构成第二环境。OpenClaw 的某些 origin_ids 来自假 Provider 注入并回传，不能自称独立来源证据；只返回 receipt 的安全 Sink 也不能充当实际落地真值。先查真实执行路径，再决定可做的范围。
