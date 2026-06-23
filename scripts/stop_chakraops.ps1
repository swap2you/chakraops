# ChakraOps Windows shutdown — R35.0
$ErrorActionPreference = "SilentlyContinue"
Write-Host "=== ChakraOps Shutdown ===" -ForegroundColor Cyan

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match "uvicorn app.api.server:app" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "Stopped backend PID $($_.ProcessId)" }

Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -match "vite" -or $_.CommandLine -match "npm run dev" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "Stopped frontend PID $($_.ProcessId)" }

Write-Host "Shutdown complete."
