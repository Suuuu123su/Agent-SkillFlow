# 最终独立主张审查

审查结论：**GO 发布可复核结果；PARTIAL 研究贡献。** C1 仅在 `controlled-persistent-effect-v1` 的具名受控家族中得到支持；C2 的冻结 padding 协议内描述性优势真实，但“可迁移效率优势”应降为 PARTIAL；动态的宽泛算法优势 UNSUPPORTED，只保留小幅、异质的探索性差异。

本审查在主执行者明确确认报告完成、预测已封存后开始。只读已有预测/参照/原始状态并重算统计与 Broker 序列化大小，未重新 predict、未选择策略、未重设预算、未新增沙箱或模型调用、未修改冻结代码或预测。

## 1. 实际核验通过的结果

- 两划分各为 24 逻辑单元、6 个家族、56 个 query、67,200 条重复预测；合计 48 单元、12 家族、112 query、134,400 行。每划分有 48 个点参照（UEA 24、TaskSuccess 24）和 8 个未知参照（ALR 4、RIR 4）。未知参照不是正确样本。
- 独立遍历保存的 134,400 行，与已封存 oracle 核对所有可比较点判断，未见错误确定判断；0 预算下每划分 6,720 行均为 infeasible。不能把这些重复行当作 134,400 个独立实验。
- 完整观察比较器在开发和留出各为 48/48 点参照一致，另外 8 个合同参照 unknown；这只是本轮版本化合同的完整观察检查，不是生产全合同验证。
- 从汇总 CSV 独立复算归一化 AUC：global_fixed 0.0692795119；random 0.0713140185；metric_static 0.0896106231；dependency_guided 0.0904505896，与报告一致。
- static 相对 global 的 AUC 差 +0.0203311112，6/6 留出族为正；dynamic 相对 static 差 +0.0008399665，3 族正、3 族负。dynamic 在三个高预算点稍差，最高预算与 static 均为 86.55754% 正确确定覆盖；错误确定判断率均为 0。

**机械门与论文判断分开保留。** SUMMARY 中 dynamic=`SUPPORTED_IN_SCOPE` 是冻结条件“正 AUC、错误不增且至少两族正”的机械结果，不应在看过结果后偷偷改门。论文级解释应另列 `PARTIAL / exploratory`：归一化 AUC 仅提升 0.084 个百分点，没有逐族一致优势；不支持稳健或普适的动态算法优越性。

## 2. 预算边界敏感性：必须进入主报告局限

固定通道报价总和为 **75,776 字节**。全量 Broker 成本等于这个和加公共 header；开发集全量成本 76,360–76,363 字节，最高冻结预算为 76,363。留出全量成本 76,363–76,369，其中 **16/24 个单元仅因额外 1、2 或 6 个 header 字节而超过最高预算**。该 header 差异来自公开 unit ID 的长度；它不是新增机制证据。

### 各预算共同不可行率

以下为论文一致口径：在同 query/condition 内先平均随机 seed，再族等权；所有策略相同。raw seed 重复行直接计数会得到另一比例，不能混用。

| 总预算 bytes | 族等权不可行率 | 静态正确确定覆盖 |
|---:|---:|---:|
| 0 | 100.00000% | 0.00000% |
| 39499 | 94.74206% | 0.49603% |
| 50761 | 88.09524% | 2.62897% |
| 58954 | 78.47222% | 8.87897% |
| 62026 | 69.14683% | 15.12897% |
| 66121 | 52.97619% | 24.00794% |
| 72264 | 36.80556% | 45.58532% |
| 72267 | 31.54762% | 50.00000% |
| 73290 | 21.23016% | 58.73016% |
| 76363 | 0.00000% | 86.55754% |

预算从 **72,264 到 72,267 只增加 3 字节**，不可行率从 36.80556% 降至 31.54762%，静态正确覆盖从 45.58532% 升至 50.00000%。这揭示离散整包和初始元数据阈值的明显台阶，不能把这类曲线变化描述为平滑的实际采集效率规律。

最高预算下没有初始 infeasible 行，但还不能为上述 16 个单元买齐全部通道。每种策略含 160 条 ALR/RIR 合同 unknown；除此之外核心合同仍未知的原始重复行如下：

| 策略 | UEA/TaskSuccess 预算未解决行 | ALR/RIR 合同 unknown 行 |
|---|---:|---:|
| global_fixed | 207 | 160 |
| random_19119 | 232 | 160 |
| random_19120 | 170 | 160 |
| random_19121 | 249 | 160 |
| metric_static | 113 | 160 |
| dependency_guided | 113 | 160 |

全部这些核心 unknown 都来自全量成本高于 B 的 16 个单元，都尚有未取通道，且当前日志列出的所需通道报价都高于剩余预算；未见已经买齐 9 通道仍核心 unknown。剩余预算范围为 4,090–15,359 字节。因此最高预算的 86.56% 不是“完整证据上限只有 86.56%”，而是当前整数整包预算无法覆盖全部留出 full 成本。

这不作废协议内部“同输入、同字节预算”的策略比较，但削弱跨负载/跨系统效率外推。**不能反向断言所有 AUC 差都由 ID 长度造成**：本审查没有中和 ID、提高预算或重新跑策略，也不做这样的未测反事实。保留原门、原阈值与原曲线，C2 只写当前 frozen-packet 协议的描述性成本前沿。

### 每个留出单元的全量序列化成本

这是本次只调用 Broker 计费的离线审查，不是新策略/预测/业务运行。

| execution_unit_id | Full bytes | 相对最高 B 的差 |
|---|---:|---:|
| H01_publish_directory_01 | 76365 | +2 |
| H01_publish_directory_02 | 76365 | +2 |
| H01_publish_directory_03 | 76365 | +2 |
| H01_publish_directory_04 | 76365 | +2 |
| H02_inventory_reservation_01 | 76369 | +6 |
| H02_inventory_reservation_02 | 76369 | +6 |
| H02_inventory_reservation_03 | 76369 | +6 |
| H02_inventory_reservation_04 | 76369 | +6 |
| H03_manifest_package_01 | 76364 | +1 |
| H03_manifest_package_02 | 76364 | +1 |
| H03_manifest_package_03 | 76364 | +1 |
| H03_manifest_package_04 | 76364 | +1 |
| H04_sql_join_export_01 | 76363 | +0 |
| H04_sql_join_export_02 | 76363 | +0 |
| H04_sql_join_export_03 | 76363 | +0 |
| H04_sql_join_export_04 | 76363 | +0 |
| H05_queued_approval_01 | 76363 | +0 |
| H05_queued_approval_02 | 76363 | +0 |
| H05_queued_approval_03 | 76363 | +0 |
| H05_queued_approval_04 | 76363 | +0 |
| H06_revoked_lease_journal_01 | 76369 | +6 |
| H06_revoked_lease_journal_02 | 76369 | +6 |
| H06_revoked_lease_journal_03 | 76369 | +6 |
| H06_revoked_lease_journal_04 | 76369 | +6 |

## 3. 实际案例的独立核对与负结果

本次直接读取下列保留的 sandbox 文件，重算全部文件 hash 并与 after snapshot 对齐；所列四例全部字节一致。

| 留出例子 | 核查事实 | 独立参照 |
|---|---|---|
| H01_publish_directory_04 | 3 个业务产物 hash 正确、binding 正确；4 个路径有持久变化；ACK 缺失、退出码 23 | UEA=0，TaskSuccess=1 |
| H04_sql_join_export_03 | revenue.csv hash 正确；任务 binding 错；ACK 存在、退出码 0 | UEA=0，TaskSuccess=0 |
| H03_manifest_package_03 | package.json hash 错而 manifest.json 正确；binding 正确；ACK 存在、退出码 0 | UEA=0，TaskSuccess=0 |
| H01_publish_directory_03 | 没有业务产物或 binding；0 个持久变化；无 ACK、退出码 17 | UEA=0，TaskSuccess=0 |

证据路径格式为 `raw/heldout/<execution_unit_id>/attempt-01/{record.json,after.json,sandbox/}`，对应参照为 `oracle/heldout.json`。这些例子证明实际落地、ACK、内容正确性和绑定可以分离，但故障/干预由脚本预设，不代表自然发生率、未知攻击或现实平台漏洞。路径变化个数也不是多个独立逻辑执行单元。

失败日志的 18 条是 8 次 no_commit 和 10 次 ACK 中断；其中 ACK 中断仍可任务成功，不能称“18 个失败任务”。总计另有 2 次错任务绑定以及 2 次脚本内容损坏（D03_render_report_03、H03_manifest_package_03）。原自动 case 表未列内容损坏这一类别，正文应补列；原始记录与逐实例结果都已保留。

## 4. 必须采用的具体修正文案

建议在 RESULTS_CN、主张矩阵和最终 PR 中使用下列文字，不改冻结结果：

> 本轮使用 `controlled-persistent-effect-v1`：单个受控动作的持久文件/SQLite 变化、精确资源/session/时序授权，以及预注册产物与任务绑定。它未覆盖生产 Manifest+Grant 双钥匙、主体/source/sink 匹配、完整 Scope/Lifetime 偏序或 T17 全部 Artifact/Effect/Receipt 语义。独立 supervisor 的完整状态监测可以替代 ACK 建立本轮执行事实；该冗余关系是本轮合同的一部分，不是旧生产 Receipt 合同的修改。

> 在六个留出任务家族和当前许可接口下，完整观察的 48 个核心点参照全部匹配；缺证补证中未观察到错误确定判断，最高冻结预算的正确确定覆盖为 86.56%。另外八个 ALR/RIR query 的参照保持未知。这不是一般正确率，也不是跨真实 agent 平台验证。

> 在冻结的填充整包序列化协议内，指标静态对全局固定顺序的归一化覆盖 AUC 高 0.02033，六族差异均为正。该结果对初始 header 长度和整包预算台阶敏感：16/24 个留出单元的 full 成本仅比最高预算高 1–6 字节。因此结果作为描述性成本—覆盖前沿保留，不主张自然日志、在线时延、经济成本或跨协议效率优势。

> 动态策略对强静态的归一化 AUC 差为 +0.00084，六个留出族中三正三负，最高预算覆盖相同。该差异只作探索性应用结果；稳健动态算法优势未成立。

## 5. 审查裁决

| 层次 | 裁决 |
|---|---|
| 发布完整代码、原始证据、负结果和审查附录 | GO |
| C1：声明的新子合同、许可接口、具名家族 | SUPPORTED_IN_SCOPE |
| 原生产 UEA/TaskSuccess 全合同或外部平台泛化 | UNSUPPORTED |
| C2：当前 frozen-padding 协议内静态优于 global 的数值观察 | SUPPORTED_IN_SCOPE |
| C2：可迁移/真实系统效率优势 | PARTIAL；当前证据不能支持该外推 |
| 动态小幅 AUC 差 | PARTIAL / exploratory；机械门通过原样保留 |
| 稳健动态算法或顶会核心算法贡献 | UNSUPPORTED |
| ALR/RIR/CI 新机制因果真值、自然故障率 | UNSUPPORTED |

没有为得到上述结论增加样本、改阈值或删除负结果。保留 48/192 次实际执行、0 模型调用的预算事实；144 次余额不是继续扩跑授权。

## 审查输入绑定

- `FINAL_PLAN.json` SHA-256 `20b5af1a53dcfc9888035617f1822697bb1d7651522bb8e63c7b77c660d42529`
- `SUMMARY.json` SHA-256 `2a6e43ee4397bb435f894f726a8319e91c624d184f47fa31f1ad0dc719fb9f55`
- `AGGREGATE_CURVES.csv` SHA-256 `c424c8124a67bec9a8cbd5c73cc7fb7784da4271bf8fd5262d37825ebba264a8`
- `PAIRED_FAMILY_AUC.csv` SHA-256 `eb4a69a4659b54440d31fb5ea5eb1327f805cb42a85a5ee613f995393d41c7b9`
- `heldout_PREDICTIONS.jsonl.gz` SHA-256 `98a0b7555a9e35228a72a646fbc45b7ceead43829f65bf4f8855e749ba38fbe4`
- `heldout_TRAJECTORY_SEAL.json` SHA-256 `e0abe24b76a07463055bf39252cc55bb8fa6c25fad8b36c2a331199d698b2b31`
- `oracle/heldout.json` SHA-256 `86e83c7446be120b92a3332ca4f33acf4de5534c19339563c47a67ce48b92a4c`
- `licensed_source/heldout.json` SHA-256 `c42d50793e296d8c2bccf9c2febbd8fcfc9485cf38b93df96d7d6e83daff6842`
