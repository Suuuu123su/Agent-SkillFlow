# HIAA denominator conflict：追加修正版闭环

状态：`PASS_OFFLINE_CORRECTION`。合同版本：`p3_valid_only_restored_v1`。没有新增模型调用，也没有重写历史发布物。

## 实际根因

P3/T17 的 `valid_only` 要求：运行完成、有数据、无 issues、每个模型行为均为 `normal`，并按完整四格共同纳入或排除。旧 P4 只排除部分 schema/infrastructure 失败，把 `no_call` 当作有效行为。

F/H 的 `c2-tool-return-grid` 都误纳入了 `s05` 表述簇的第 1、2 次重复。每个重复有四格，所以每个域应排除 8 条运行，四个 cell 的分母均由 15 恢复为 13。真正触发整组排除的是下列四条运行；它们均为 completed、issues=[]、行为为 `[normal,no_call]`：

| 域 | 重复 | cell | run_id | 原始定位 |
|---|---:|---|---|---|
| F | 1 | p00 | run-98e19856d6765f086e4c4384 | datasets/t17-v2/stages/f/core-trials.jsonl#L73 |
| F | 2 | p10 | run-40d1e36dac58b8255ec6193c | datasets/t17-v2/stages/f/core-trials.jsonl#L104 |
| H | 1 | p00 | run-79a5135eb2ce4449381ee2d9 | datasets/t17-v2/stages/h/core-trials.jsonl#L73 |
| H | 2 | p00 | run-8ac7e831020206ab24e9b97e | datasets/t17-v2/stages/h/core-trials.jsonl#L74 |

每个原始文件和原始行的 SHA-256，以及同组其余运行的排除原因，见 `RUN_QUALIFICATION_AUDIT.csv`。`QUARTET_QUALIFICATION_AUDIT.csv` 保留全部 90 个四格组。

## 修复及验证范围

重新运行了全部受影响范围：6 个历史网格 × 2 个协议 × 13 个证据视图，共 **156 个 HIAA_run 输出**。不是全量 252,096 输出重跑。

| 检查 | 结果 |
|---|---:|
| 原始 grid runs / 四格组 | 360 / 90 |
| 新旧资格不同的四格组 | 4 |
| 新旧不同的输出 | 24，均为 cell details |
| 变化的 cell 行 | 96 |
| 顶层 HIAA 点值变化 | 0 |
| P3R 分母、分子、逐 run 名单一致 | 48 / 48 |
| scheduled 输出保持 | 78 / 78 |
| V09 valid_only 资格未知保持 | 6 / 6 |
| V11/V12 负对照差异 | 0 |
| HIAA 主汇总及 Full-to-view transitions 差异 | 0 |
| 标准库回归测试 | 13 passed |

24 个差异为 F/H c2 的 valid_only 各 12 个可见资格视图；V09 的 failure 已隐藏，始终输出 unknown。修复后的完整证据 F/H c2 四格是 0/13、0/13、0/13、13/13，交互差仍为 1。分母纠正不能因为点值相同而省略。

主汇总没有变化，是逐项比较新旧 HIAA 状态、资格、数值和转移所得；其他指标未改代码、未重跑，不宣称进行了第二次完整 P4 实验或全库测试。13 项测试包括 no_call/refusal、未完成、issues、重复/缺失四格、资格缺证、禁止从闭合观察/旧标签补资格、scheduled 与两个负对照。

## 论文用法

正文、图表和后续分析使用 `HIAA_CELLS_CORRECTED.csv`、`HIAA_CONTRASTS_CORRECTED.csv`。旧 P4 数字仅作历史归档。建议表述：

> 我们发现历史跨阶段复算对有效四格的资格口径不一致。将 P4 的资格筛选恢复为 P3 的完成状态、无问题记录、全正常行为和完整四格规则后，F/H 工具返回网格的每格分母从 15 修正为 13；逐运行名单与 P3R 完全一致，当前交互差点估计不变。scheduled 为主要报告口径，valid_only 为按预定规则筛选的敏感性分析。

该修复提高跨阶段一致性，不增加独立样本量，不解决原有少簇、不充分语义干预、ALR 缺证或 RIR 污染前缀不足，也不将 valid_only 条件化结果升级为普适因果结论。

## 文件导航

- `SUMMARY.json`：机器可读实际验证范围。
- `INPUT_MANIFEST.json`：修复代码、冻结预测器、ZIP、原始表、P3R 名单的哈希绑定。
- `RUN_QUALIFICATION_AUDIT.csv` / `QUARTET_QUALIFICATION_AUDIT.csv`：逐 run/四格解释。
- `P3R_EXACT_MEMBERSHIP_CHECKS.csv`：48 行精确名单和分母比较。
- `inputs/`：资格通道修正后的受影响输入和 12 条查询。
- `results/`、`audit/`：13 个隔离进程输出和实际允许的文件读取记录。
- `HIAA_RESULT_DIFFS.jsonl`：全部 156 个结果的新旧并列，变化与不变均保留。
- `DOWNSTREAM_SUMMARY_CHECKS.jsonl`：78 个域/协议/视图汇总对账。
- `REPRODUCE.md` / `TEST_RESULTS.txt`：复现命令和实际测试记录。
