# ChakraOps R31-R35 live operational smoke (Windows only)
param(
    [switch]$SkipStartStop
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\chakraops_common.ps1"

$LogPath = Join-Path $script:ChakraOpsRepoRoot "out\verification\R35.0\windows_live_smoke.log"
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null
$script:SmokeLog = $LogPath

function Write-SmokeLog {
    param([string]$Message)
    $line = "[$(Get-Date -Format o)] $Message"
    Add-Content -LiteralPath $script:SmokeLog -Value $line
    Write-Host $line
}

function Assert-GitClean {
    Set-Location -LiteralPath $script:ChakraOpsRepoRoot
    $status = git status --porcelain
    if ($status) { throw "Repository not clean: $status" }
}

function Invoke-ChakraOpsStop {
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$script:ChakraOpsScriptsRoot\stop_chakraops.ps1"
}

function Invoke-ChakraOpsStart {
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$script:ChakraOpsScriptsRoot\start_chakraops.ps1"
}

function Clear-StaleChakraOpsPorts {
    foreach ($port in @($script:ChakraOpsBackendPort, $script:ChakraOpsFrontendPort)) {
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        foreach ($listener in $listeners) {
            $processId = [int]$listener.OwningProcess
            if (-not $processId) { continue }
            $wmi = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
            $cmd = $wmi.CommandLine
            if ($cmd -and $cmd -match [regex]::Escape($script:ChakraOpsRepoRoot)) {
                Write-SmokeLog "Clearing stale listener on port $port (PID $processId)"
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Invoke-Api {
    param([string]$Method, [string]$Path, [int[]]$AllowedStatus = @(200))
    try {
        $uri = "$($script:ChakraOpsBackendUrl)$Path"
        if ($Method -eq "GET") {
            $r = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 30
            return @{ status = 200; body = $r }
        }
        $r = Invoke-WebRequest -Uri $uri -Method Post -TimeoutSec 120 -UseBasicParsing
        return @{ status = [int]$r.StatusCode; body = $null }
    } catch {
        if ($_.Exception.Response) {
            return @{ status = [int]$_.Exception.Response.StatusCode.value__; body = $null }
        }
        throw
    }
}

$started = $false
try {
    Write-SmokeLog "=== R31-R35 live smoke start ==="
    Assert-GitClean

    if (-not $SkipStartStop) {
        Write-SmokeLog "Shutdown pass 1"
        Invoke-ChakraOpsStop | Out-Null
        Write-SmokeLog "Shutdown pass 2 (idempotent)"
        Invoke-ChakraOpsStop | Out-Null

        Clear-StaleChakraOpsPorts

        Write-SmokeLog "Starting ChakraOps"
        Invoke-ChakraOpsStart
        $started = $true
        $healthy = $false
        for ($i = 0; $i -lt 12; $i++) {
            Start-Sleep -Seconds 5
            & powershell -NoProfile -ExecutionPolicy Bypass -File "$script:ChakraOpsScriptsRoot\health_check_chakraops.ps1" | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $healthy = $true
                break
            }
        }
        if (-not $healthy) { throw "backend did not become healthy after startup" }
    }

    Write-SmokeLog "Health check"
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$script:ChakraOpsScriptsRoot\health_check_chakraops.ps1"
    if ($LASTEXITCODE -ne 0) { throw "health check failed" }

    $status = Invoke-Api -Method GET -Path "/api/operations/status"
    if ($status.body.scheduler.master_enabled -ne $false) {
        throw "scheduler master must be disabled"
    }
    Write-SmokeLog "Scheduler master disabled: OK"
    if ($status.body.trade_execution -ne $false) {
        throw "trade_execution must be false"
    }
    Write-SmokeLog "trade_execution false: OK"
    if ($status.body.manual_only -ne $true) {
        throw "manual_only must be true"
    }
    Write-SmokeLog "manual_only true: OK"
    $tokenPresent = [bool]$status.body.orats_token_present
    Write-SmokeLog "orats_token_present (boolean only): $tokenPresent"

    $enableNoConfirm = Invoke-Api -Method POST -Path "/api/operations/scheduler/enable" -AllowedStatus @(400, 422)
    if ($enableNoConfirm.status -notin 400, 422) {
        throw "scheduler enable without confirm must be rejected"
    }
    Write-SmokeLog "scheduler enable without confirm rejected: OK"

    $enableWrong = Invoke-Api -Method POST -Path "/api/operations/scheduler/enable?confirm=WRONG" -AllowedStatus @(400)
    if ($enableWrong.status -ne 400) {
        throw "scheduler enable wrong confirm must be rejected"
    }
    Write-SmokeLog "scheduler enable wrong confirm rejected: OK"

    Write-SmokeLog "Manual provider_health"
    $run = Invoke-Api -Method POST -Path "/api/operations/jobs/provider_health/run" -AllowedStatus @(200, 500)
    Write-SmokeLog "provider_health run status: $($run.status)"

    Write-SmokeLog "PowerShell backup create"
    & "$script:ChakraOpsScriptsRoot\backup_chakraops.ps1" -Label "smoke"
    if ($LASTEXITCODE -ne 0) { throw "backup create failed" }

    Write-SmokeLog "PowerShell list backups"
    & "$script:ChakraOpsScriptsRoot\list_backups_chakraops.ps1" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "list backups failed" }

    $latestId = python -c "from app.core.operations.backup_service import list_backups; b=list_backups(); print(b[0]['backup_id'] if b else '')"
    if (-not $latestId) { throw "no backup id" }
    Write-SmokeLog "Latest backup: $latestId"

    Write-SmokeLog "Verify backup"
    & "$script:ChakraOpsScriptsRoot\verify_backup_chakraops.ps1" -BackupId $latestId
    if ($LASTEXITCODE -ne 0) { throw "verify failed" }

    Write-SmokeLog "Restore to temp"
    & "$script:ChakraOpsScriptsRoot\restore_chakraops_validate.ps1" -BackupId $latestId
    if ($LASTEXITCODE -ne 0) { throw "restore validate failed" }

    Write-SmokeLog "Cleanup dry-run"
    & "$script:ChakraOpsScriptsRoot\cleanup_expired_backups.ps1"
    if ($LASTEXITCODE -ne 0) { throw "cleanup dry-run failed" }

    $brokerProbe = Invoke-WebRequest -Uri "$($script:ChakraOpsBackendUrl)/openapi.json" -UseBasicParsing -TimeoutSec 30
    $openapiDoc = $brokerProbe.Content | ConvertFrom-Json
    $apiPaths = @($openapiDoc.paths.PSObject.Properties.Name)
    foreach ($term in @("/broker", "/order", "place_order", "submit_order")) {
        foreach ($apiPath in $apiPaths) {
            if ($apiPath -match [regex]::Escape($term)) {
                throw "broker/order capability found in openapi path ${apiPath}: $term"
            }
        }
    }
    Write-SmokeLog "No broker/order openapi paths: OK"

    Write-SmokeLog "=== live smoke PASS ==="
    exit 0
} finally {
    if (-not $SkipStartStop) {
        Write-SmokeLog "Final shutdown pass 1"
        Invoke-ChakraOpsStop | Out-Null
        Write-SmokeLog "Final shutdown pass 2"
        Invoke-ChakraOpsStop | Out-Null
        Clear-StaleChakraOpsPorts
    }
    try {
        Assert-GitClean
        Write-SmokeLog "Repository clean after smoke"
    } catch {
        Write-SmokeLog "Repository clean check failed: $_"
        throw
    }
}
