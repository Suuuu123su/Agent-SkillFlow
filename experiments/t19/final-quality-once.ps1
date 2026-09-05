$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'E:\Skill ＆ Harness\Agent'
$check = Get-Content -LiteralPath 'experiments/t19/independent-recompute-check.json' -Raw | ConvertFrom-Json
if ($check.status -ne 'passed') { throw 'independent_recompute_not_passed' }
$quality = 'experiments/t19/quality/final-v1'
if (Test-Path -LiteralPath $quality) { throw 'one_shot_quality_already_exists_do_not_repeat' }
New-Item -ItemType Directory -Path $quality | Out-Null
$tempRoot = 'E:\Skill ＆ Harness\Agent\runs\t19-quality-final-v1'
if (Test-Path -LiteralPath $tempRoot) { throw 'quality_temp_already_exists_do_not_delete' }
New-Item -ItemType Directory -Path "$tempRoot/temp" -Force | Out-Null
$env:TEMP = "$tempRoot/temp"
$env:TMP = $env:TEMP
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:COVERAGE_FILE = (Join-Path (Resolve-Path $quality).Path '.coverage')
$python = (Resolve-Path '.venv-skillflow/Scripts/python.exe').Path
@{ started_utc=[DateTime]::UtcNow.ToString('o'); full_suite_attempt=1; temporary_archive_exclusion='.tmp'; coverage_threshold=90 } | ConvertTo-Json | Set-Content -LiteralPath "$quality/started.json" -Encoding utf8
& $python --version *> "$quality/python-version.log"
$results = [System.Collections.Generic.List[object]]::new()
function Invoke-QualityGate {
    param([string]$Name, [string[]]$Arguments)
    $began = [DateTime]::UtcNow
    & $python @Arguments *> "$quality/$Name.log"
    $code = $LASTEXITCODE
    $results.Add(@{ gate=$Name; exit_code=$code; duration_seconds=([DateTime]::UtcNow-$began).TotalSeconds })
    Write-Output "$Name exit_code=$code"
}
Invoke-QualityGate -Name 'pytest-full' -Arguments @('-m','pytest','-vv','--tb=short','--durations=15',"--basetemp=$tempRoot/pytest", "--junitxml=$quality/test-results.xml", "--cov-report=json:$quality/coverage.json", "--cov-report=xml:$quality/coverage.xml")
Invoke-QualityGate -Name 'ruff-check' -Arguments @('-m','ruff','check','.','--extend-exclude','.tmp')
Invoke-QualityGate -Name 'ruff-format' -Arguments @('-m','ruff','format','--check','.','--extend-exclude','.tmp')
Invoke-QualityGate -Name 'mypy' -Arguments @('-m','mypy','src/skillflow')
Invoke-QualityGate -Name 'cli-help' -Arguments @('-m','skillflow.cli','--help')
$failures = @($results | Where-Object { $_.exit_code -ne 0 })
@{ status= $(if ($failures.Count) { 'failed' } else { 'passed' }); finished_utc=[DateTime]::UtcNow.ToString('o'); gates=$results.ToArray(); full_suite_attempt=1; scope='local_existing_project_quality_not_remote_GitHub_CI' } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$quality/result.json" -Encoding utf8
if ($failures.Count) { exit 1 }
