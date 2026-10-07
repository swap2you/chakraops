# ChakraOps root command surface. Recurring jobs stay disabled.
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("setup", "start", "stop", "test", "status")]
    [string]$Command
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"

function Ensure-LocalDirs {
    foreach ($name in @("runtime", "00_inbox", "deliverables", "99_archive")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Root $name) | Out-Null
    }
}

switch ($Command) {
    "setup" {
        Ensure-LocalDirs
        if (-not (Test-Path -LiteralPath $Py)) {
            $base = Get-Command python -ErrorAction SilentlyContinue
            if (-not $base) { throw "python not found; install Python 3.13 and rerun setup" }
            & $base.Source -m venv (Join-Path $Backend ".venv")
        }
        & $Py -m pip install --upgrade pip
        & $Py -m pip install -r (Join-Path $Backend "requirements.txt")
        Push-Location $Frontend
        try { npm ci } finally { Pop-Location }
        Write-Host "Setup complete. Recurring jobs were not registered."
    }
    "start" {
        & powershell -NoProfile -File (Join-Path $Root "scripts\start_chakraops.ps1")
    }
    "stop" {
        & powershell -NoProfile -File (Join-Path $Root "scripts\stop_chakraops.ps1")
    }
    "test" {
        if (-not (Test-Path -LiteralPath $Py)) { throw "venv missing; run: .\chakra.ps1 setup" }
        Push-Location $Backend
        try { & $Py -m pytest tests -q --tb=short; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
        finally { Pop-Location }
        Push-Location $Frontend
        try {
            npm run typecheck
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            npm run test -- --run
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            npm run build
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        finally { Pop-Location }
    }
    "status" {
        foreach ($url in @("http://127.0.0.1:18800/health", "http://127.0.0.1:18873/api/healthz")) {
            try {
                $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
                Write-Host "$url $($resp.StatusCode) $($resp.Content)"
            }
            catch {
                Write-Host "$url down"
            }
        }
        Write-Host "Recurring jobs: disabled"
    }
}
