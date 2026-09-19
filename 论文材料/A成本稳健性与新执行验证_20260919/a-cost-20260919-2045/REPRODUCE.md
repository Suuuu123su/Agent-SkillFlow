# 只读复核与执行记录

以下从仓库根运行。已有 Python 3.12.14；复核只用标准库及仓库源码，不安装依赖、不调用模型、不启动业务沙箱、不重放策略子进程、不写实验产物。它读取保存的文件/SQLite状态，重算有限合同判定、账本、统计与Gate；请勿使用 Python `-O`（检查使用assert）。

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + (Join-Path (Get-Location) 'src')
$python = 'E:\Skill ＆ Harness\Agent\.venv-skillflow\Scripts\python.exe'
$out = '论文材料/A成本稳健性与新执行验证_20260919/a-cost-20260919-2045'
& $python -B -m experiments.evidence_cost_validation.verify_delivery --out $out
```

其他机器将`$python`替换为Python 3.12路径即可。期望JSON为`status=PASSED`，`campaign_executions=28`，`verification_new_executions=0`。核对内容：历史输入/源码SHA、原/新缺证manifest、候选96与静态选序、215040旧成本轨迹、92160新轨迹、28实际持久状态、五份新结果CSV逐字节相等、C0区间/分组和、Gate B重算及最终文件清单。只读核验仍包含纯函数预测器调用，它不是模型调用，也不是新增策略轨迹或业务执行。

## 本批实际执行阶段

这些是已完成的命令记录，**不需要再运行**。freeze/collect入口使用独占文件防止覆盖已有封存；正式数据仅采集一次。不应对旧目录重跑注册或报告；需新批次必须另行授权，不能借复现名义消耗剩余预算。

```powershell
& $python -B -m experiments.evidence_cost_validation.registration --out $out
& $python -B -m experiments.evidence_cost_validation.attribution --out $out
```

旧development静态选序与新成本轨迹通过相同函数入口执行（COMMANDS.jsonl保存各调用时间，部分通过编排函数直接调用，CLI是等价入口）：

```powershell
foreach ($cost in @('C1','C2')) {
    & $python -B -m experiments.evidence_cost_validation.sweep select --out $out --cost $cost
    & $python -B -m experiments.evidence_cost_validation.sweep replay --out $out --cost $cost --split development
    & $python -B -m experiments.evidence_cost_validation.sweep replay --out $out --cost $cost --split heldout
}
& $python -B -m experiments.evidence_cost_validation.report --out $out
```

Gate A PASS后才运行以下业务入口；sanity消耗4次，collect消耗24次，freeze消耗0次。程序内子进程只执行受控文件/SQLite操作，不是LLM推理。所有attempt先计账后初始化；未提交是预定业务结果，非可重试基础设施失败。

```powershell
& $python -B -m experiments.evidence_cost_validation.fresh sanity --out $out
& $python -B -m experiments.evidence_cost_validation.fresh freeze --out $out
& $python -B -m experiments.evidence_cost_validation.fresh collect --out $out
foreach ($cost in @('C1','C2')) {
    & $python -B -m experiments.evidence_cost_validation.sweep replay --out "$out/fresh" --cost $cost --split heldout
}
& $python -B -m experiments.evidence_cost_validation.fresh_report --out $out
& $python -B -m experiments.evidence_cost_validation.delivery --out $out
```

实现封存先于比较、新runner与Gate B源码封存先于新样本。DELIVERY_MANIFEST只是事后发布完整性清单，不冒充预登记。数据集派生绑定仅切换新输入路径、SHA与新缺证manifest，静态序列字节一致，成本/预测器/门槛不变。

测试记录：首次执行同一文件的7项测试通过，但默认全项目coverage不足退出1；日志保留在UNIT_TESTS.txt/XML。随后仅覆盖本分析变更的正确命令退出0：

```powershell
& $python -B -m pytest tests/unit/analysis/test_evidence_cost_validation.py -q -o addopts='' -p no:cacheprovider --basetemp "$out/temp/pytest-scoped" --junitxml "$out/UNIT_TESTS_SCOPED.xml"
```

测试命令为实际已完成记录，重新测试应使用新的临时目录和JUnit路径，避免覆盖已发布日志。没有声称全仓库测试、远端CI或Linux复核。

## 证据路径与计量

- DIAGNOSTIC_PLAN、COST_CONTRACTS、MASK_MANIFEST、IMPLEMENTATION_SEAL、FRESH_PLAN及各SHA：阶段冻结。
- C1/C2与fresh/C1/C2：逐预算预测、原协议字节、代理成本、可见投影与轨迹seal。
- EXECUTION_LEDGER：28次实际attempt；fresh/raw、sanity/raw：全部原件、独立oracle及持久文件/SQLite。SQLite文件必须随仓库保留。
- SOURCE_AUDIT是M0快照；SUMMARY/STATUS记录28次终值。预算是本批48上限，未续跑B。
- 随机缺证3种子先在query/condition内平均，再在族内计算、族间等权。未知、不可行与无真值另账。1,167,360次离线候选/轨迹试算不等于新独立样本量。
- 原协议wire bytes是序列化填充包字节，策略stdin另计；C1/C2均为代理量，不是账单、实网流量或时延。
- PARENT_READ_ONLY_VERIFICATION保留历史核查；READ_ONLY_VERIFICATION是本批完整复核；PUBLICATION记录分支与增量PR。
