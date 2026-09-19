# 主张—证据矩阵

| 主张 | 状态 | 当前证据与限制 |
|---|---|---|
| C1：有限合同下独立受控执行记录的可靠判断 | SUPPORTED_IN_SCOPE | 两个可独立参照的合同是 UEA 与 TaskSuccess；所有缺证/不可行分母保留。只适用于具名家族和许可接口，不是一般 soundness。 |
| C2：指标静态在同总字节预算下优于全局固定顺序 | SUPPORTED_IN_SCOPE | 留出正确覆盖 AUC 差 0.02033；完整逐族差异在 PAIRED_FAMILY_AUC.csv。不能外推在线时延或经济节省。 |
| 动态策略优于强指标静态 | SUPPORTED_IN_SCOPE | 留出 AUC 差 0.00084。不支持时删除动态算法优势，保留负结果。 |
| 跨真实 agent / 外部 harness 泛化 | UNSUPPORTED | 本轮 source 为标准库受控程序；历史 ClawTrojan/OpenClaw 记录不满足本轮独立合同参照要求。 |
| ALR/RIR/CI 新机制真值或因果主张 | UNSUPPORTED | ALR/RIR 独立 reason/prefix/intervention 条件缺失；CI 仅保留历史依赖回归，没有新语义中和真值。 |

Full 只作为完整观察比较器，单列 [FULL_INDEPENDENT_ORACLE.csv](FULL_INDEPENDENT_ORACLE.csv)，不作为免费补证策略或真值。unknown、bounded、N/A、error 和未知参照均未计入正确回答。

统计单位为 12 个家族、48 个独立初始化的逻辑单元；只有 6 个留出家族，不给 query 独立 Bernoulli 区间、不报显著性。随机 seed、budget、mask、policy 是重复测量。成本仅为包含初始头部、许可初始包、补证包及 padding 的规范化序列化负载代理。

## 可直接使用的保守措辞

- 若 C1 在本轮范围内成立：“在六个留出任务家族和声明的受控持久效果合同中，我们同时报告正确确定判断覆盖与错误确定判断率；结论限于这些程序、记录器和许可观察接口，不表示真实 agent 平台的普适正确性。”
- 阴性结果：“在预先冻结的共同字节阈值及相同初始证据下，动态策略未获支持的优势不作为贡献；强静态方案与全部失败、未知及不可行行一并保留。”
- 来源不足：“本地存在外部 harness 历史轨迹，但它们缺乏本轮所需的独立结构化授权或任务参照。新增验证因此定位为受控程序执行与独立代码路径验证。”
