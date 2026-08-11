# ChakraOps Windows operations common foundation (R35.0 release acceptance)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\chakraops_ports.ps1"

$script:ChakraOpsRepoRoot = "C:\Development\Workspace\ChakraOps-dev\chakraops"
$script:ChakraOpsStaleRoot = "C:\Development\Workspace\ChakraOps"
$script:ChakraOpsBackendRoot = Join-Path $script:ChakraOpsRepoRoot "chakraops"
$script:ChakraOpsFrontendRoot = Join-Path $script:ChakraOpsRepoRoot "frontend"
$script:ChakraOpsScriptsRoot = Join-Path $script:ChakraOpsRepoRoot "scripts"

function Initialize-ChakraOpsCheckout {
    if (-not (Test-Path -LiteralPath $script:ChakraOpsRepoRoot)) {
        throw "Repository not found: $($script:ChakraOpsRepoRoot)"
    }
    $cwd = (Get-Location).Path
    if ($cwd -eq $script:ChakraOpsStaleRoot -or $cwd.StartsWith($script:ChakraOpsStaleRoot + [char]92)) {
        throw "Stale checkout detected. Use $($script:ChakraOpsRepoRoot)"
    }
    Set-Location -LiteralPath $script:ChakraOpsBackendRoot
    $py = Get-ChakraOpsPythonPath
    & $py -c "from app.core.operations.process_ownership import validate_repo_root; validate_repo_root(r'$($script:ChakraOpsRepoRoot)')" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "validate_repo_root failed"
    }
}

function Invoke-ChakraOpsPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Code
    )
    $py = Get-ChakraOpsPythonPath
    & $py -c $Code
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Get-ChakraOpsPythonPath {
    # Prefer project venv so startup matches tested deps (argon2, mcp, etc.).
    # Bare `python` on PATH may be a system install missing ChakraOps packages.
    $venvPy = Join-Path $script:ChakraOpsBackendRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        return $venvPy
    }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        throw "python not found on PATH and venv missing at $venvPy"
    }
    return $py.Source
}
