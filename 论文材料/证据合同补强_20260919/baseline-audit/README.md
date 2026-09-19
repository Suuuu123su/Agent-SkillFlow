# R001 历史回归与外部来源盘点

状态：`PASS_BASELINE_REGRESSION`；外部独立参照：`NOT_AVAILABLE`。本目录实跑没有新增模型、网络或业务沙箱执行，没有改写任何历史结果。

## 实际验证

| 项目 | 本轮实际结果 | 证据 |
|---|---:|---|
| HIAA 定向回归 | 13/13 通过 | [HIAA_TEST_RESULTS.txt](HIAA_TEST_RESULTS.txt) |
| 原始 HIAA 资格重算 | 360 条运行、90 个四格组 | [SUMMARY.json](SUMMARY.json) |
| 与 P3R 精确名单核对 | 48/48，包含实际 run IDs 与源行 | [HIAA_P3R_48_MEMBERSHIP_CHECKS.csv](HIAA_P3R_48_MEMBERSHIP_CHECKS.csv) |
| F/H ToolReturn valid_only | 8 个 cell 分母均为 13 | 同上 |
| 历史 CI 回放 | 30 个 CI query，120 条策略终点与原 CSV 状态、资格、获取顺序、缺失列表一致 | [CI_8_PLUS_2_REPLAY.jsonl](CI_8_PLUS_2_REPLAY.jsonl) |
| all-nine-missing / budget 2 差异 | 8 条 | 同上 |
| five-missing / budget 1 差异 | 2 条 | 同上 |

这 10 条差异中，`metric_fixed` 均为 `bounded` 且资格明确；`contract_guided` 均为 `unknown` 且资格未知。静态策略恢复 provenance，旧启发式优先恢复 receipt。历史投影删除 provenance 时会递归清除嵌套 `source_object`，旧 `missing_evidence` 没有登记这个依赖。本轮复现不能补齐旧 CI 中和的语义真值，也不能变成动态策略优势。

HIAA 验证重新从原始运行计算资格，未仅复读已保存的 48 条通过标签。没有重跑完整 P4，也没有重算非 HIAA 指标。

## 外部来源的实际可用边界

本地并非没有外部材料。实际读取 ClawTrojan P0 的 585 条事实和 39 张任务义务卡，重数得到 4,744 次调用；同时盘点原生 ZIP、固定上游版本、MIT 许可证及 OpenClaw T15 记录。逐源文件、哈希、schema 与排除理由见 [EXTERNAL_SOURCE_INVENTORY.json](EXTERNAL_SOURCE_INVENTORY.json) 和 [INPUT_MANIFEST.json](INPUT_MANIFEST.json)。

- **ClawTrojan P0**：实际本地写入、文件 delta 和模拟消息记录可用；没有真实结构化 Grant，不能生成 UEA 独立真值。任务义务与 U/V 语义判断来自历史 Codex 辅助标注、人审 0，部分前像、政策边界及唯一物理响应绑定不完整；不能将其升级为本轮独立 TaskSuccess oracle。
- **ClawTrojan 原生快照**：上游 `9566637c9af3f7b05e576d09b45de489bf9fec9d`，4 个适配文件；不是未修改上游。原生 C/P/S 判分与调用轨迹不能代替结构化权限和独立任务真值。
- **OpenClaw T15**：历史真实 Gateway 使用假 provider 和 SkillFlow safe sink；缺等价 Grant matcher、撤销 hook 和独立来源图，不能仅凭 safe-sink Receipt 声称外部授权真值。

因此 `external_source=NOT_AVAILABLE` 的准确含义是“本轮所需的独立 UEA 与 TaskSuccess 合同参照不可得”，不是“外部日志不存在”。主实验应继续执行独立本地沙箱，结论限定为受控程序执行及独立代码路径验证。没有启动外部 harness、安装依赖或读取凭据/API 原始请求。

## 复现

在仓库根目录使用 PowerShell 7；解释器实测 Python 3.12.14。输出目录需使用未完成审计的新目录，避免覆盖本轮证据：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=Join-Path (Get-Location) 'src'
$auditTemp=Join-Path (Get-Location) '论文材料/证据合同补强_20260919/baseline-audit/temp'
New-Item -ItemType Directory -Force -Path $auditTemp | Out-Null
$env:TEMP=$auditTemp
$env:TMP=$auditTemp
& 'E:\Skill ＆ Harness\Agent\.venv-skillflow\Scripts\python.exe' -B experiments/evidence_contract_validation/audit_baseline.py --out '论文材料/证据合同补强_20260919/baseline-audit-reproduction'
```

外部 P0 路径默认为 `E:\Skill ＆ Harness\ClawTrojan-P0-measurement-audit-20260915-v1`；可使用 `--external-root` 指定其父目录。哈希记录绑定实际读取文件，不声称恢复了历史原始生成时未绑定的字节。
