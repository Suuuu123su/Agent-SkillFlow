$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'E:\Skill ＆ Harness\Agent'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = 'E:\Skill ＆ Harness\Agent\runs\t19-finalization\temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$python = (Resolve-Path '.venv-skillflow/Scripts/python.exe').Path
$stateRoot = 'runs/t19-finalization'
$terminal = 'runs/t19-live-20260905-01/formal-v1/host-result-formal-01.json'
if (Test-Path -LiteralPath "$stateRoot/started.json") { throw 'finalization_already_started' }
@{ status='waiting_for_formal'; started_utc=[DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath "$stateRoot/started.json" -Encoding utf8
while (-not (Test-Path -LiteralPath $terminal)) { Start-Sleep -Seconds 30 }
$hostResult = Get-Content -LiteralPath $terminal -Raw | ConvertFrom-Json
if ($hostResult.status -ne 'completed') { throw 'formal_worker_not_completed' }
& $python "$stateRoot/prepare-cli.py" *> "$stateRoot/freeze-and-cli.log"
if ($LASTEXITCODE -ne 0) { throw 'freeze_or_cli_failed' }
function Invoke-OfflineStep {
    param([string]$Name, [string[]]$Arguments)
    & $python @Arguments *> "$stateRoot/$Name.log"
    if ($LASTEXITCODE -ne 0) { throw "$Name failed" }
    Write-Output "$Name completed"
}
Invoke-OfflineStep -Name 'export' -Arguments @('-m','skillflow.cli','defense','t19','export','--phase','runs/t19-phases/formal-v1','--campaign','runs/t19-live-20260905-01/formal-v1','--live-root','runs/t19-live-20260905-01','--output','experiments/t19/public-data/formal-v1')
Invoke-OfflineStep -Name 'recompute-primary' -Arguments @('-m','skillflow.cli','defense','t19','recompute','--source','experiments/t19/public-data/formal-v1','--output','experiments/t19/reports/formal-v1')
Invoke-OfflineStep -Name 'recompute-independent' -Arguments @('-m','skillflow.cli','defense','t19','recompute','--source','experiments/t19/public-data/formal-v1','--output','runs/t19-recompute/formal-v1-independent')
Invoke-OfflineStep -Name 'compare-independent' -Arguments @('-m','skillflow.cli','defense','t19','check','--left','experiments/t19/reports/formal-v1','--right','runs/t19-recompute/formal-v1-independent','--output','experiments/t19/independent-recompute-check.json')
@{ status='offline_delivery_checked'; completed_utc=[DateTime]::UtcNow.ToString('o'); full_quality_run=$false } | ConvertTo-Json | Set-Content -LiteralPath "$stateRoot/completed.json" -Encoding utf8
Write-Output 'Offline delivery complete. Full quality still requires the final one-shot invocation.'
