# ChakraOps dedicated local dev ports (avoid Docker/Vite defaults on 8000/5173).
#
# Single source of truth for the PowerShell layer. Mirrors the resolution rules in
# chakraops/app/core/chakraops_ports.py and frontend/vite.config.*:
#   - Unset/empty env var -> default.
#   - Env var set -> must be an integer in [1, 65535], else fail clearly.
#   - Backend and frontend ports must differ.

$script:ChakraOpsMinPort = 1
$script:ChakraOpsMaxPort = 65535
$script:ChakraOpsDefaultBackendPort = 18800
$script:ChakraOpsDefaultFrontendPort = 18873

function Resolve-ChakraOpsPort {
    param(
        [Parameter(Mandatory = $true)][string]$EnvName,
        [Parameter(Mandatory = $true)][int]$Default
    )
    $raw = [Environment]::GetEnvironmentVariable($EnvName)
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $Default
    }
    $raw = $raw.Trim()
    $parsed = 0
    if (-not [int]::TryParse($raw, [ref]$parsed)) {
        throw "$EnvName='$raw' is not a valid port (must be an integer $($script:ChakraOpsMinPort)-$($script:ChakraOpsMaxPort))"
    }
    if ($parsed -lt $script:ChakraOpsMinPort -or $parsed -gt $script:ChakraOpsMaxPort) {
        throw "$EnvName=$parsed is out of range ($($script:ChakraOpsMinPort)-$($script:ChakraOpsMaxPort))"
    }
    return $parsed
}

$script:ChakraOpsBackendPort = Resolve-ChakraOpsPort -EnvName 'CHAKRAOPS_BACKEND_PORT' -Default $script:ChakraOpsDefaultBackendPort
$script:ChakraOpsFrontendPort = Resolve-ChakraOpsPort -EnvName 'CHAKRAOPS_FRONTEND_PORT' -Default $script:ChakraOpsDefaultFrontendPort

if ($script:ChakraOpsBackendPort -eq $script:ChakraOpsFrontendPort) {
    throw "Backend and frontend ports must differ (both=$($script:ChakraOpsBackendPort)); set distinct CHAKRAOPS_BACKEND_PORT/CHAKRAOPS_FRONTEND_PORT"
}

$script:ChakraOpsBackendUrl = "http://127.0.0.1:$($script:ChakraOpsBackendPort)"
$script:ChakraOpsFrontendUrl = "http://127.0.0.1:$($script:ChakraOpsFrontendPort)"
