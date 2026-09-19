# 复现边界与环境

本目录包含冻结 PLAN、预测封存、独立 oracle、原始执行和计费账本。应先核对 SUMMARY.json 的 input_sha256，再复算统计；不得为复算图表重新执行业务沙箱或调用模型。

已有环境：PowerShell 7，Python 3.12.14；代码以标准库运行，使用工作区 E 盘的临时目录和 PYTHONDONTWRITEBYTECODE=1。报告入口为 `experiments.evidence_contract_validation.reporting.report(output_directory)`。

报告拒绝覆盖已经存在的 SUMMARY.json。若要独立复算，请把已封存输入复制到一个新的 E 盘输出目录，然后运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
& 'E:\Skill ＆ Harness\Agent\.venv-skillflow\Scripts\python.exe' -B -c "from experiments.evidence_contract_validation.reporting import report; report(r'E:\已复制的本轮封存输入目录')"
```

需复制的输入：PLAN.json、ATTEMPTS.jsonl、FAILURES.jsonl（存在时）、两划分 QUERY_REGISTRY.csv、PREDICTIONS.jsonl.gz、COST_LEDGER.jsonl.gz、TRAJECTORY_SEAL.json，以及 oracle/、evaluation_only/ 和本轮原始 raw 记录目录。保留目录相对结构。不要复制 SUMMARY.json 或其它生成报告以免混淆。

模型调用始终为 0。完整实验从开发冻结到留出的实际命令和偏差以同目录阶段日志及根 README 为准；报告程序不承担新增实验调度。
