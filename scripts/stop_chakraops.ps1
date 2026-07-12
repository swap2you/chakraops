# ChakraOps Windows shutdown — R35.2 operational hardening (owned processes only).
#
# Safely stops ChakraOps backend/frontend regardless of launch form
# (executable-form OR module-form such as `python -m uvicorn`).
#
# Ownership decision uses MULTIPLE signals and is fail-safe:
#   - The ownership record (out/process_ownership.json) is repo-scoped and is the
#     primary authorization artifact. If its repo_root does not match this checkout,
#     we refuse to stop anything.
#   - A candidate PID is only stopped when it presents >= 2 independent signals:
#       S_RECORD : PID == recorded role PID (or a descendant of it)
#       S_PORT   : PID is LISTENING on the role's expected port from the record
#       S_CMD    : command line matches the role command identity (uvicorn/python | vite/npm/node)
#     Rule: (S_RECORD OR S_PORT) AND S_CMD, with a PID-reuse age guard (S_AGE).
#   - Idempotent: not-running PID -> "already stopped"; missing record -> "nothing to stop".
#   - Never targets port 8000 (Docker); only the record's role ports (default 18800/18873).
#
# Canonical checkout: C:\Development\Workspace\ChakraOps-dev\chakraops
# (repo-root enforcement is inherited from chakraops_common.ps1 / process_ownership).

. "$PSScriptRoot\chakraops_common.ps1"

Set-Location -LiteralPath $script:ChakraOpsBackendRoot

Write-Host "=== ChakraOps Shutdown (R35.2) ===" -ForegroundColor Cyan

$pidPayload = python -c @"
from app.core.operations.process_ownership import read_record
import json
r = read_record()
if not r:
    print('')
elif r.get('repo_root') != r'''$($script:ChakraOpsRepoRoot)''':
    print('MISMATCH')
else:
    print(json.dumps({
        'backend_pid': r.get('backend_pid'),
        'frontend_pid': r.get('frontend_pid'),
        'backend_port': r.get('backend_port'),
        'frontend_port': r.get('frontend_port'),
        'created_at': r.get('created_at'),
    }))
"@

if (-not $pidPayload) {
    Write-Host "No ownership record found - nothing to stop."
    exit 0
}
if ($pidPayload -eq 'MISMATCH') {
    Write-Host "Ownership record repo_root mismatch - refusing to stop (fail-safe)." -ForegroundColor Yellow
    exit 1
}

$record = $pidPayload | ConvertFrom-Json

# Parse the record creation time for the PID-reuse age guard (with small negative skew).
$recordCreatedAt = $null
if ($record.created_at) {
    try { $recordCreatedAt = ([datetimeoffset]::Parse($record.created_at)).UtcDateTime.AddSeconds(-120) } catch { $recordCreatedAt = $null }
}

function Get-ListenerPidsOnPort([int]$Port) {
    if (-not $Port) { return @() }
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return @() }
    return ($conns | ForEach-Object { [int]$_.OwningProcess } | Sort-Object -Unique)
}

function Test-PidListensOnPort([int]$ProcessId, [int]$Port) {
    if (-not $Port -or -not $ProcessId) { return $false }
    return ((Get-ListenerPidsOnPort -Port $Port) -contains $ProcessId)
}

function Test-IsDescendantOf([int]$ProcessId, [int]$AncestorPid) {
    if (-not $ProcessId -or -not $AncestorPid) { return $false }
    $guard = 0
    $current = $ProcessId
    while ($current -and $guard -lt 12) {
        $guard++
        $wmi = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
        if (-not $wmi) { return $false }
        $parent = [int]$wmi.ParentProcessId
        if ($parent -eq $AncestorPid) { return $true }
        if ($parent -eq 0 -or $parent -eq $current) { return $false }
        $current = $parent
    }
    return $false
}

function Stop-ChakraOpsRole {
    param(
        [string]$Role,
        [int]$RecordPid,
        [int]$Port,
        [string]$CmdRegex
    )

    # Candidate PIDs: recorded role PID + whoever currently listens on the role's port.
    $candidates = New-Object System.Collections.Generic.List[int]
    if ($RecordPid) { [void]$candidates.Add($RecordPid) }
    foreach ($lp in (Get-ListenerPidsOnPort -Port $Port)) { if (-not $candidates.Contains($lp)) { [void]$candidates.Add($lp) } }

    if ($candidates.Count -eq 0) {
        Write-Host ("[{0}] nothing to stop (no recorded PID, no listener on port {1})." -f $Role, $Port)
        return
    }

    $stoppedAny = $false
    foreach ($procId in $candidates) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if (-not $proc) {
            Write-Host ("[{0}] PID {1} already stopped." -f $Role, $procId)
            continue
        }

        $wmi = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        $cmd = if ($wmi) { [string]$wmi.CommandLine } else { "" }

        $sPort   = Test-PidListensOnPort -ProcessId $procId -Port $Port
        $sCmd    = ($cmd -match $CmdRegex)
        $sRecord = ($procId -eq $RecordPid) -or (Test-IsDescendantOf -ProcessId $procId -AncestorPid $RecordPid)

        # PID-reuse age guard: if we know record time and process start time, the process
        # must have started at/after the record was written (with skew already applied).
        $sAge = $true
        if ($recordCreatedAt -and $proc.StartTime) {
            try { $sAge = ($proc.StartTime.ToUniversalTime() -ge $recordCreatedAt) } catch { $sAge = $true }
        }

        $safeToKill = (($sRecord -or $sPort) -and $sCmd -and $sAge)

        if ($safeToKill) {
            taskkill /PID $procId /T /F 2>&1 | Out-Null
            Write-Host ("[{0}] stopped PID {1} (record={2} port={3} cmd={4} age_ok={5})." -f $Role, $procId, $sRecord, $sPort, $sCmd, $sAge)
            $stoppedAny = $true
        } else {
            Write-Host ("[{0}] REFUSING PID {1} - ambiguous ownership (record={2} port={3} cmd={4} age_ok={5})." -f $Role, $procId, $sRecord, $sPort, $sCmd, $sAge) -ForegroundColor Yellow
        }
    }

    if (-not $stoppedAny) {
        Write-Host ("[{0}] no owned process required stopping." -f $Role)
    }
}

$backendPid  = if ($record.backend_pid)  { [int]$record.backend_pid }  else { 0 }
$frontendPid = if ($record.frontend_pid) { [int]$record.frontend_pid } else { 0 }
$backendPort  = if ($record.backend_port)  { [int]$record.backend_port }  else { 0 }
$frontendPort = if ($record.frontend_port) { [int]$record.frontend_port } else { 0 }

Stop-ChakraOpsRole -Role "backend"  -RecordPid $backendPid  -Port $backendPort  -CmdRegex 'uvicorn|python'
Stop-ChakraOpsRole -Role "frontend" -RecordPid $frontendPid -Port $frontendPort -CmdRegex 'vite|npm|node'

python -c "from app.core.operations.process_ownership import clear_record; clear_record()" | Out-Null
Write-Host "Ownership record cleared. Shutdown complete."
