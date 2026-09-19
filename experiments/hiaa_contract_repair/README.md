# HIAA 历史合同修复

修复版本：`p3_valid_only_restored_v1`。仅修复 P4 对历史 T17 四格的 `valid_only` 资格规则；原始运行、P3/P3R/P4 冻结发布包和生产 T17 实现均不改写。

`src/skillflow/experiment/t17/v2/hiaa_metrics.py::_valid_four_cells` 和 `analysis_context.py::behavior_valid` 本身正确：运行完成、有数据、无 issues、所有行为为 normal，且配对内恰有四个不同 cell。P4 的发布后分析器遗漏了部分条件，实际 F/H 差异由 `no_call` 引起。

## 执行

Python 3.11+ 标准库即可，无 Key、SDK、模型请求或网络。

```bash
python -B experiments/hiaa_contract_repair/reproduce.py --out /tmp/skillflow-hiaa-reproduction
python -B tests/unit/analysis/test_hiaa_contract_repair.py
```

输出目录必须尚不存在。复算从仓库原始 T17 表及 P4 ZIP 输入开始。`reproduce.py` 生成资格证据后，把每个投影视图交给独立 `predict.py` 进程；预测进程文件审计只允许读该视图的 DOCUMENTS/QUERIES，禁止网络、子进程和读取旧结果。全部新预测落盘后，父进程才打开旧输出及 P3R 名单比较。

## 修复规则

- `contract.py` 只覆盖 `HIAA_run / valid_only` 的四格资格筛选。端点、四格差和 cluster bootstrap 沿用冻结 P4 代码。
- 从原始 run 绑定 `failure.run_status`，不使用历史 `behavior_valid` 或旧资格标签；steps/issues 必须与归档规范化输入逐项相等。
- `failure` 缺失时保留资格未知；不从 `observation.closed`、缓存标签或正文猜测补回。V09 会同时删除新增的 `failure.run_status`。
- scheduled、完整四格检查、V11/V12 负对照和其他指标保持原合同。缺数据的原始运行不能凭空加入网格；本次 360 条网格成员均有已绑定原始数据。
- Full 四格的分母、分子和逐 run 名单必须与 P3R 对应 48 行完全一致。

当前结果见 `论文材料/修复与补强_20260919/hiaa/README.md`。这是追加修正版入口；继续执行旧 P4 冻结入口仍会复现其历史发布结果，包括已定位的 13/15 差异。
