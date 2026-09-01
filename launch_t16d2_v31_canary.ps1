$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv-skillflow\Scripts\python.exe'
$outputRoot = Join-Path $projectRoot 'runs\t16d2-v31-canary-live-20260830-01\attempt-01'

$env:SKILLFLOW_PROVIDER = 'openai'
$env:SKILLFLOW_MODEL_ID = 'gpt-5.6-luna'
$env:SKILLFLOW_MAX_USD = '0.25'
$env:SKILLFLOW_LIVE_APPROVED = '1'

Set-Location -LiteralPath $projectRoot
& $python -m skillflow.experiment.t16.task_success_canary_cli `
    --project-root $projectRoot `
    --output-root $outputRoot

$runExitCode = $LASTEXITCODE
Write-Host ""
Write-Host "T16-D.2 v3.1 Canary 进程已结束，退出码：$runExitCode"
Write-Host "可保留此窗口供结果核对。"
