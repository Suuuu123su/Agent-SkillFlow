$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'E:\Skill ＆ Harness\Agent'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = 'E:\Skill ＆ Harness\Agent\.tmp\t19-host'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
& '.\.venv-skillflow\Scripts\python.exe' -m skillflow.experiment.t19.host --root 'E:\Skill ＆ Harness\Agent' --live-root 'E:\Skill ＆ Harness\Agent\runs\t19-live-20260905-01'
Read-Host 'Host exited. Press Enter to close'
