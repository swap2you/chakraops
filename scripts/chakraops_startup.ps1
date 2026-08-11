# ChakraOps Windows startup helpers (R70-DEF-072)
# Dot-sourced by start_chakraops.ps1 and startup self-tests.
Set-StrictMode -Version Latest

function Resolve-ChakraOpsNpmLauncher {
    <#
    .SYNOPSIS
      Resolve a Win32-launchable npm entrypoint for Start-Process.

    Prefer npm.cmd beside node.exe (NVM-safe). Never return the extensionless
    `npm` shim — Start-Process treats it as a document and may open Notepad.
    #>
    $candidates = New-Object System.Collections.Generic.List[string]

    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCmd -and $nodeCmd.Source) {
        $nodeDir = Split-Path -Parent $nodeCmd.Source
        $candidates.Add((Join-Path $nodeDir "npm.cmd"))
    }

    $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npmCmd -and $npmCmd.Source) {
        $candidates.Add([string]$npmCmd.Source)
    }

    foreach ($whereLine in @(& where.exe npm.cmd 2>$null)) {
        if ($whereLine) { $candidates.Add([string]$whereLine.Trim()) }
    }

    foreach ($c in $candidates) {
        if ([string]::IsNullOrWhiteSpace($c)) { continue }
        if ($c -match '(?i)\\npm(\.cmd)?$' -and (Test-Path -LiteralPath $c)) {
            # Reject extensionless npm file even if where.exe listed it
            if ($c -match '(?i)\\npm$') { continue }
            return (Resolve-Path -LiteralPath $c).Path
        }
    }

    throw "npm.cmd not found beside node.exe / on PATH. Install Node.js (NVM) so npm.cmd is available. Do not use extensionless 'npm' with Start-Process."
}

function Wait-ChakraOpsPortListen {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$TimeoutSec = 90,
        [string]$BindHost = "127.0.0.1"
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Where-Object {
                -not $_.LocalAddress -or
                $_.LocalAddress -eq "0.0.0.0" -or
                $_.LocalAddress -eq "::" -or
                $_.LocalAddress -eq $BindHost -or
                $_.LocalAddress -eq "::1"
            })
        if ($listeners.Count -gt 0) {
            return [int]$listeners[0].OwningProcess
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Label did not enter LISTEN on ${BindHost}:$Port within ${TimeoutSec}s"
}

function Test-ChakraOpsHttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSec = 5,
        [string]$ContentRegex = ""
    )
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        if ($resp.StatusCode -ne 200) { return $false }
        if ($ContentRegex -and ($resp.Content -notmatch $ContentRegex)) { return $false }
        return $true
    } catch {
        return $false
    }
}

function Wait-ChakraOpsHttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$TimeoutSec = 90,
        [string]$ContentRegex = ""
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-ChakraOpsHttpOk -Url $Url -TimeoutSec 3 -ContentRegex $ContentRegex) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Label HTTP check failed for $Url within ${TimeoutSec}s"
}

function Stop-ChakraOpsStartedProcesses {
    param(
        [System.Diagnostics.Process]$BackendProc = $null,
        [System.Diagnostics.Process]$FrontendProc = $null,
        [int]$BackendPort = 0,
        [int]$FrontendPort = 0
    )
    foreach ($proc in @($FrontendProc, $BackendProc)) {
        if ($null -eq $proc) { continue }
        try {
            if (-not $proc.HasExited) {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
        } catch { }
    }
    foreach ($port in @($FrontendPort, $BackendPort)) {
        if ($port -le 0) { continue }
        $conns = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        foreach ($c in $conns) {
            try { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
}
