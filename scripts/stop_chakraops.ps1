# ChakraOps Windows shutdown — R35.0 remediation (owned processes only)
. "$PSScriptRoot\chakraops_common.ps1"

function Stop-OwnedProcess {
    param(
        [int]$ProcessId,
        [string]$ExpectedFragment
    )
    if (-not $ProcessId) { return }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Host "PID $ProcessId not running"
        return
    }
    $wmi = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    $cmd = $wmi.CommandLine
    if ($ExpectedFragment -match "vite|npm") {
        if ($cmd -notmatch "vite|npm") {
            Write-Host "Refusing to stop PID $ProcessId - command identity mismatch" -ForegroundColor Yellow
            return
        }
        if ($cmd -notmatch [regex]::Escape($script:ChakraOpsRepoRoot)) {
            Write-Host "Refusing to stop PID $ProcessId - not ChakraOps-dev checkout" -ForegroundColor Yellow
            return
        }
    } else {
        if (-not $cmd -or $cmd -notmatch $ExpectedFragment) {
            Write-Host "Refusing to stop PID $ProcessId - command identity mismatch" -ForegroundColor Yellow
            return
        }
        if ($cmd -notmatch [regex]::Escape($script:ChakraOpsRepoRoot)) {
            Write-Host "Refusing to stop PID $ProcessId - not ChakraOps-dev checkout" -ForegroundColor Yellow
            return
        }
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped PID $ProcessId"
}

Set-Location -LiteralPath $script:ChakraOpsBackendRoot

Write-Host "=== ChakraOps Shutdown ===" -ForegroundColor Cyan

$pidPayload = python -c @"
from app.core.operations.process_ownership import read_record, clear_record
import json
r = read_record()
if not r:
    print('')
elif r.get('repo_root') != r'''$($script:ChakraOpsRepoRoot)''':
    print('MISMATCH')
else:
    print(json.dumps({'backend_pid': r['backend_pid'], 'frontend_pid': r['frontend_pid']}))
"@

if (-not $pidPayload) {
    Write-Host "No ownership record found - nothing to stop."
    exit 0
}
if ($pidPayload -eq 'MISMATCH') {
    Write-Host "Ownership record repo_root mismatch - refusing to kill." -ForegroundColor Yellow
    exit 1
}

$pidData = $pidPayload | ConvertFrom-Json
$backendPid = [int]$pidData.backend_pid
$frontendPid = [int]$pidData.frontend_pid

Stop-OwnedProcess -ProcessId $backendPid -ExpectedFragment "uvicorn"
Stop-OwnedProcess -ProcessId $frontendPid -ExpectedFragment "vite|npm"

python -c "from app.core.operations.process_ownership import clear_record; clear_record()" | Out-Null
Write-Host "Shutdown complete."
