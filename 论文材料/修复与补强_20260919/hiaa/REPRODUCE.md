# 复现

在固定仓库 checkout 的根目录执行。需要 Python 3.11+，仅用标准库。

```bash
python -B experiments/hiaa_contract_repair/reproduce.py --out /tmp/skillflow-hiaa-reproduction
python -B tests/unit/analysis/test_hiaa_contract_repair.py
```

`--out` 必须是新目录，脚本拒绝覆盖。Windows 可换为一个尚不存在的本地目录。

第一次交付的命令为：

```bash
python -B experiments/hiaa_contract_repair/reproduce.py --out '论文材料/修复与补强_20260919/hiaa'
```

该目录现在已存在，请勿照抄旧输出路径覆盖结果。

复算依赖均在仓库：T17 F/G/H dataset manifests 和 core-trials 分表；P4 的归档 ZIP（从中读取 BASE_DOCUMENTS 与旧 results）、固定查询/注册表、冻结 predictor/views/ingest 源码；P3R legacy HIAA_CELLS。精确 SHA-256 见 INPUT_MANIFEST.json。无 task_pack 依赖，不调用历史 live launcher。

脚本只重新计算受影响的 HIAA_run 156 项；比较器在新结果封存之后读取历史结果。每个预测进程只允许访问自己的许可视图。输入的 status 归入 failure 通道；该通道被消融时连同 status 一起删除。

预期 SUMMARY：changed_predictions=24，changed_cell_rows=96，changed_top_level_point_values=0，p3r_exact_run_set_matches=48，main_summary_differences=0，negative_control_differences=0。模型请求、网络请求及业务工具调用均为 0。
