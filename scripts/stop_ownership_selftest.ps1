# ChakraOps R35.2 — stop_chakraops.ps1 self-test harness (LOCAL ONLY).
#
# Exercises the hardened stop logic against synthetic ownership records and benign
# spawned processes. Does NOT run in CI (CI is Linux/pytest). Requires a Windows
# host with python + node on PATH. Safe: only stops processes THIS harness spawns.
#
# Precondition: no ChakraOps ownership record may currently exist (the harness writes
# the shared record). If a recorded stack is live, refuse (do not clobber its record).
# A manually-started stack with NO record is unaffected: the harness uses its own
# ephemeral ports (18811/18812/18813) and never touches 18800/18873.

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = 'C:\Development\Workspace\ChakraOps-dev\chakraops'
$backendRoot = Join-Path $repo 'chakraops'
$stopScript = Join-Path $repo 'scripts\stop_chakraops.ps1'

Push-Location $backendRoot
$existing = python -c "from app.core.operations.process_ownership import read_record; print('YES' if read_record() else 'NO')"
Pop-Location
if ($existing -eq 'YES') {
    Write-Host "REFUSING: an ownership record already exists (a recorded stack may be running)." -ForegroundColor Yellow
    exit 2
}

$pass = 0; $fail = 0
function Assert([string]$label, [bool]$cond) {
    if ($cond) { Write-Host ("PASS  {0}" -f $label); $script:pass++ }
    else { Write-Host ("FAIL  {0}" -f $label) -ForegroundColor Red; $script:fail++ }
}

function Write-Record([int]$bpid, [int]$fpid, [int]$bport, [int]$fport, [string]$repoRoot) {
    $code = @"
from app.core.operations.process_ownership import write_record
write_record(backend_pid=$bpid, frontend_pid=$fpid, repo_root=r'''$repoRoot''',
             backend_cmd='uvicorn app.api.server:app', frontend_cmd='npm run dev',
             backend_port=$bport, frontend_port=$fport)
"@
    Push-Location $backendRoot
    python -c $code | Out-Null
    Pop-Location
}

function Clear-Record {
    Push-Location $backendRoot
    python -c "from app.core.operations.process_ownership import clear_record; clear_record()" | Out-Null
    Pop-Location
}

function Record-Exists {
    Push-Location $backendRoot
    $r = python -c "from app.core.operations.process_ownership import read_record; print('YES' if read_record() else 'NO')"
    Pop-Location
    return ($r -eq 'YES')
}

function Start-NodeListener([int]$Port) {
    $code = "require('net').createServer().listen($Port,'127.0.0.1'); setTimeout(function(){}, 120000);"
    $p = Start-Process node -ArgumentList '-e', $code -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    return $p
}

function Start-PyModuleListener([int]$Port) {
    # Mirrors `python -m uvicorn ...` command-line shape: `python -m <module> ...`.
    $p = Start-Process python -ArgumentList '-m', 'http.server', "$Port", '--bind', '127.0.0.1' -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    return $p
}

Write-Host "===== R35.2 stop-script self-test ====="

# --- Test 1: missing record -> nothing to stop (exit 0) ---
Clear-Record
& $stopScript | Out-Null
Assert "T1 missing-record exits cleanly (nothing to stop)" ($LASTEXITCODE -eq 0)

# --- Test 2: repo_root mismatch -> refuse (exit 1), record left as-is ---
Write-Record 0 0 0 0 'C:\Development\Workspace\ChakraOps'
& $stopScript | Out-Null
Assert "T2 repo_root mismatch refuses (exit 1)" ($LASTEXITCODE -eq 1)
Clear-Record

# --- Test 3: owned frontend (node/vite listener) IS stopped ---
$fe = Start-NodeListener 18811
$listening = [bool](Get-NetTCPConnection -LocalPort 18811 -State Listen -ErrorAction SilentlyContinue)
Assert "T3a node/vite listener came up on 18811" $listening
Write-Record 0 $fe.Id 0 18811 $repo
& $stopScript | Out-Null
Start-Sleep -Seconds 2
$alive = [bool](Get-Process -Id $fe.Id -ErrorAction SilentlyContinue)
Assert "T3b owned frontend (node) stopped" (-not $alive)
Assert "T3c port 18811 freed" (-not (Get-NetTCPConnection -LocalPort 18811 -State Listen -ErrorAction SilentlyContinue))
Assert "T3d ownership record cleared" (-not (Record-Exists))
if ($alive) { taskkill /PID $fe.Id /T /F 2>&1 | Out-Null }

# --- Test 4: foreign process on the port (wrong command identity) is REFUSED ---
$node = Start-NodeListener 18812
$nodeUp = [bool](Get-NetTCPConnection -LocalPort 18812 -State Listen -ErrorAction SilentlyContinue)
Assert "T4a node listener came up on 18812" $nodeUp
# Record claims backend on 18812 but backend cmd regex is uvicorn|python; node must be refused.
Write-Record 0 0 18812 0 $repo
& $stopScript | Out-Null
Start-Sleep -Seconds 2
$nodeAlive = [bool](Get-Process -Id $node.Id -ErrorAction SilentlyContinue)
Assert "T4b foreign node on backend port REFUSED (still alive)" $nodeAlive
taskkill /PID $node.Id /T /F 2>&1 | Out-Null
Clear-Record

# --- Test 5: idempotent second stop -> nothing to stop ---
& $stopScript | Out-Null
Assert "T5 idempotent second stop (exit 0)" ($LASTEXITCODE -eq 0)

# --- Test 6: explicit module-form (`python -m ...`) backend IS stopped ---
$pym = Start-PyModuleListener 18813
$pymUp = [bool](Get-NetTCPConnection -LocalPort 18813 -State Listen -ErrorAction SilentlyContinue)
Assert "T6a python -m listener came up on 18813" $pymUp
Write-Record $pym.Id 0 18813 0 $repo
& $stopScript | Out-Null
Start-Sleep -Seconds 2
$pymAlive = [bool](Get-Process -Id $pym.Id -ErrorAction SilentlyContinue)
Assert "T6b module-form (python -m) backend stopped" (-not $pymAlive)
Assert "T6c port 18813 freed" (-not (Get-NetTCPConnection -LocalPort 18813 -State Listen -ErrorAction SilentlyContinue))
if ($pymAlive) { taskkill /PID $pym.Id /T /F 2>&1 | Out-Null }
Clear-Record

Write-Host ("===== SELF-TEST SUMMARY: PASS={0} FAIL={1} =====" -f $pass, $fail)
if ($fail -gt 0) { exit 1 } else { exit 0 }
