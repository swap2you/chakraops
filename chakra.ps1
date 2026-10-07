# ChakraOps root command surface. Recurring jobs stay unregistered.
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("setup", "start", "stop", "test", "status")]
    [string]$Command
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$ArgumentList
    )
    & $FilePath @ArgumentList
    $code = $LASTEXITCODE
    if ($null -ne $code -and $code -ne 0) {
        exit $code
    }
}

function Ensure-LocalDirs {
    foreach ($name in @("runtime", "00_inbox", "deliverables", "99_archive")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Root $name) | Out-Null
    }
}

function Get-ObservedSchedules {
    $tasks = @()
    try {
        $tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
            $_.TaskName -match 'chakra|ChakraOps' -or $_.TaskPath -match 'chakra|ChakraOps'
        })
    } catch {
        $tasks = @()
    }
    if ($tasks.Count -eq 0) {
        Write-Host "Scheduled tasks: none observed for ChakraOps"
    } else {
        foreach ($task in $tasks) {
            Write-Host "Scheduled task: $($task.TaskPath)$($task.TaskName) state=$($task.State)"
        }
    }
    $wfDir = Join-Path $Root ".github\workflows"
    if (Test-Path -LiteralPath $wfDir) {
        Get-ChildItem -LiteralPath $wfDir -Filter *.yml | ForEach-Object {
            $text = Get-Content -Raw -LiteralPath $_.FullName
            if ($text -match '(?m)^on:\s*$[\s\S]*?^\s*schedule:') {
                Write-Host "Workflow $($_.Name): schedule trigger observed"
            } else {
                Write-Host "Workflow $($_.Name): no schedule trigger observed"
            }
        }
    }
}

if ($env:CHAKRAOPS_EXIT_PROBE -eq "1") {
    Invoke-Native cmd.exe /c exit 9
}

switch ($Command) {
    "setup" {
        Ensure-LocalDirs
        if (-not (Test-Path -LiteralPath $Py)) {
            $base = Get-Command python -ErrorAction SilentlyContinue
            if (-not $base) { throw "python not found; install Python 3.13 and rerun setup" }
            Invoke-Native $base.Source -m venv (Join-Path $Backend ".venv")
        }
        Invoke-Native $Py -m pip install --upgrade pip
        Invoke-Native $Py -m pip install -r (Join-Path $Backend "requirements.txt")
        Push-Location $Frontend
        try { Invoke-Native npm.cmd ci } finally { Pop-Location }
        Write-Host "Setup complete. No scheduled task was registered."
    }
    "start" {
        Invoke-Native powershell -NoProfile -File (Join-Path $Root "scripts\start_chakraops.ps1")
    }
    "stop" {
        Invoke-Native powershell -NoProfile -File (Join-Path $Root "scripts\stop_chakraops.ps1")
    }
    "test" {
        if (-not (Test-Path -LiteralPath $Py)) { throw "venv missing; run: .\chakra.ps1 setup" }
        Push-Location $Backend
        try { Invoke-Native $Py -m pytest tests -q --tb=short }
        finally { Pop-Location }
        Push-Location $Frontend
        try {
            Invoke-Native npm.cmd run typecheck
            Invoke-Native npm.cmd run test -- --run
            Invoke-Native npm.cmd run build
        }
        finally { Pop-Location }
    }
    "status" {
        foreach ($url in @("http://127.0.0.1:18800/health", "http://127.0.0.1:18873/api/healthz")) {
            try {
                $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
                Write-Host "$url $($resp.StatusCode)"
            }
            catch {
                Write-Host "$url down"
            }
        }
        Get-ObservedSchedules
    }
}
