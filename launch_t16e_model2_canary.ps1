$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv-skillflow\Scripts\python.exe'
$outputRoot = Join-Path $projectRoot 'runs\t16e-model2-gpt55-live-20260831-01\attempt-01'

$env:SKILLFLOW_SECOND_PROVIDER = 'openai'
$env:SKILLFLOW_SECOND_MODEL_ID = 'gpt-5.5-2026-04-23'
$env:SKILLFLOW_MAX_USD = '1'
$env:SKILLFLOW_LIVE_APPROVED = '1'

Set-Location -LiteralPath $projectRoot
& $python -m skillflow.experiment.t16.t16e_cli `
    --project-root $projectRoot `
    --output-root $outputRoot

$runExitCode = $LASTEXITCODE
Write-Host ""
Write-Host "T16-E Model2 Canary 进程已结束，退出码：$runExitCode"
Write-Host "可保留此窗口供结果核对。"
