# ChakraOps Windows shutdown — R35.0 remediation (owned processes only)
. "$PSScriptRoot\chakraops_common.ps1"
Set-Location -LiteralPath $script:ChakraOpsBackendRoot

Write-Host "=== ChakraOps Shutdown ===" -ForegroundColor Cyan

$recordJson = python -c "from app.core.operations.process_ownership import read_record; import json; r=read_record(); print(json.dumps(r) if r else '')"
if (-not $recordJson) {
    Write-Host "No ownership record found — nothing to stop."
    exit 0
}

$record = $recordJson | ConvertFrom-Json
if ($record.repo_root -ne $script:ChakraOpsRepoRoot) {
    Write-Host "Ownership record repo_root mismatch — refusing to kill." -ForegroundColor Yellow
    exit 1
}

function Stop-OwnedProcess([int]$Pid, [string]$ExpectedFragment) {
    if (-not $Pid) { return }
    $proc = Get-Process -Id $Pid -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Host "PID $Pid not running"
        return
    }
    $wmi = Get-CimInstance Win32_Process -Filter "ProcessId=$Pid" -ErrorAction SilentlyContinue
    $cmd = $wmi.CommandLine
    if (-not $cmd -or $cmd -notmatch $ExpectedFragment) {
        Write-Host "Refusing to stop PID $Pid — command identity mismatch" -ForegroundColor Yellow
        return
    }
    if ($cmd -notmatch [regex]::Escape($script:ChakraOpsRepoRoot)) {
        Write-Host "Refusing to stop PID $Pid — not ChakraOps-dev checkout" -ForegroundColor Yellow
        return
    }
    Stop-Process -Id $Pid -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped PID $Pid"
}

Stop-OwnedProcess -Pid $record.backend_pid -ExpectedFragment "uvicorn"
Stop-OwnedProcess -Pid $record.frontend_pid -ExpectedFragment "vite|npm"

python -c "from app.core.operations.process_ownership import clear_record; clear_record()" | Out-Null
Write-Host "Shutdown complete."
