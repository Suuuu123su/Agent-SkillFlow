# 可信收口与外部能力资格验证

A 的实现位于此新增目录，旧 `evidence_contract_validation` 的冻结源码不变。
`predictor.py`/`evaluation.py` 是可追溯的追加版本；`audit.py` 从旧独立核账器派生，只修相对路径读取及显式旧源码根目录。

## 只读复验（0业务执行，0新增预测）

```powershell
& 'E:\Skill ＆ Harness\Agent\.venv-skillflow\Scripts\python.exe' -B -m experiments.closeout_pilot.verify_closeout --old '论文材料/证据合同补强_20260919/strengthening-20260919-085337' --out '论文材料/补证收口与能力先导_20260919/closeout-pilot-20260919-1100/closeout' --source-snapshot 'E:\Skill ＆ Harness\publication\evidence-strengthening-20260919'
```

在其他位置克隆时，可将 `--source-snapshot` 指向包含317ff31旧源码的独立checkout；所有冻结相对路径支持Windows/POSIX分隔符，拒绝盘符、绝对路径、`..`与解析后越界。只在Windows实测。

## 一次离线纠错（0业务执行）

```powershell
& 'E:\Skill ＆ Harness\Agent\.venv-skillflow\Scripts\python.exe' -B -m experiments.closeout_pilot.reanalysis --old '论文材料/证据合同补强_20260919/strengthening-20260919-085337' --out '论文材料/补证收口与能力先导_20260919/<new-run>/closeout' --source-snapshot 'E:\Skill ＆ Harness\publication\evidence-strengthening-20260919'
```

不会调用旧collect。入口拒绝覆盖，原候选集/预算/报价不变；开发真值选序，轨迹先封存后连既有参照。原留出已公开，不能称新的盲测。现存run已执行一次，无需重复。

## 外部资格检查（会实际启动真实Gateway并计数）

`gateway_probe`检查HTTP直接工具入口；`gateway_agent_probe`检查官方脚本provider驱动的完整agent工具路径。二者不请求模型，所有动作限定E盘独占目录；第二个的本地HTTP协议请求不是模型推理调用。运行前需检查本轮ledger与环境资格，不能把资格检查当正式留出。
