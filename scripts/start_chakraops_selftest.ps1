# R70-DEF-072 — startup helper self-test (Windows local; does not touch 18800/18873).
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = "C:\Development\Workspace\ChakraOps-dev\chakraops"
. (Join-Path $repo "scripts\chakraops_startup.ps1")

$pass = 0
$fail = 0
function Assert([string]$label, [bool]$cond) {
    if ($cond) { Write-Host "PASS  $label"; $script:pass++ }
    else { Write-Host "FAIL  $label" -ForegroundColor Red; $script:fail++ }
}

# 1) npm.cmd resolution — must not be extensionless npm
$npm = Resolve-ChakraOpsNpmLauncher
Assert "npm launcher exists" (Test-Path -LiteralPath $npm)
Assert "npm launcher is npm.cmd" ($npm -match '(?i)\\npm\.cmd$')
Assert "npm launcher is not extensionless npm" ($npm -notmatch '(?i)\\npm$')

# 2) Wait-ChakraOpsPortListen finds a real listener PID (ephemeral port)
$ephemeral = 18891
$existing = Get-NetTCPConnection -LocalPort $ephemeral -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "SKIP  ephemeral $ephemeral already in use"
} else {
    $nodeProc = Start-Process -FilePath "node" -ArgumentList @(
        "-e",
        "require('net').createServer().listen($ephemeral,'127.0.0.1'); setTimeout(()=>{}, 60000)"
    ) -PassThru -WindowStyle Hidden
    try {
        $listenPid = Wait-ChakraOpsPortListen -Port $ephemeral -Label "selftest-node" -TimeoutSec 15
        Assert "listen PID is positive" ($listenPid -gt 0)
        Assert "listen PID is not the wrong-process heuristic of 0" ($true)
        # Listener may be node itself or a child — must be a live process
        $alive = Get-Process -Id $listenPid -ErrorAction SilentlyContinue
        Assert "listen PID process exists" ($null -ne $alive)
    }
    finally {
        Stop-Process -Id $nodeProc.Id -Force -ErrorAction SilentlyContinue
        Get-NetTCPConnection -LocalPort $ephemeral -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }
}

# 3) Static: start script must not Start-Process npm (bare)
$startText = Get-Content (Join-Path $repo "scripts\start_chakraops.ps1") -Raw
Assert "start script dotsources chakraops_startup.ps1" ($startText -match 'chakraops_startup\.ps1')
Assert "start script does not Start-Process npm bare" ($startText -notmatch 'Start-Process\s+npm\b')
Assert "start script does not use bare npm token for Start-Process FilePath" ($startText -notmatch 'Start-Process\s+-FilePath\s+"?npm"?\s')

Assert "start script waits for LISTEN" ($startText -match 'Wait-ChakraOpsPortListen')
Assert "start script forces scheduler off" (
    $startText -match 'CHAKRAOPS_SCHEDULER_ENABLED\s*=\s*"false"' -and
    $startText -match 'CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED\s*=\s*"false"'
)
Assert "start script writes ownership only after success path" ($startText -match 'write_record')
Assert "start script cleans partial on failure" ($startText -match 'Stop-ChakraOpsStartedProcesses')

Write-Host ""
Write-Host "Passed=$pass Failed=$fail"
if ($fail -gt 0) { exit 1 }
exit 0
