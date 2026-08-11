# ChakraOps Robinhood MCP OAuth authorize (R70)
# Opens browser PKCE flow and stores tokens under C:\ChakraOpsSecrete\robinhood
# Cursor MCP OAuth ≠ ChakraOps app auth — this script never copies Cursor credentials.
param(
    [string]$RedirectUri = "http://127.0.0.1:8765/callback",
    [switch]$NoBrowser,
    [switch]$ForceDiscovery,
    [string]$Store = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $RepoRoot "chakraops"
$VenvPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"
$ScriptPy = Join-Path $BackendRoot "scripts\robinhood_mcp_authorize.py"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Missing venv python at $VenvPython. Create/activate chakraops/chakraops/.venv first."
}
if (-not (Test-Path -LiteralPath $ScriptPy)) {
    throw "Missing authorize script at $ScriptPy"
}

$argsList = @($ScriptPy, "--redirect-uri", $RedirectUri)
if ($NoBrowser) { $argsList += "--no-browser" }
if ($ForceDiscovery) { $argsList += "--force-discovery" }
if ($Store) { $argsList += @("--store", $Store) }

Write-Host "=== ChakraOps Robinhood MCP Authorize ===" -ForegroundColor Cyan
Write-Host "Python: $VenvPython"
Write-Host "Complete authorization in the browser when it opens, then return here."
Write-Host "Tokens are stored locally with restrictive ACL; values are never printed."

& $VenvPython @argsList
exit $LASTEXITCODE
