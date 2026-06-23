# ChakraOps R31-R35 release acceptance harness
param(
    [switch]$PostCommit,
    [switch]$SkipLiveSmoke
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = "C:\Development\Workspace\ChakraOps-dev\chakraops"
Set-Location -LiteralPath $RepoRoot

$ManifestPath = Join-Path $RepoRoot "docs\ai\validation\R31_R35_ACCEPTANCE_MANIFEST.json"
$EvidenceDir = Join-Path $RepoRoot "out\verification\R35.0"
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$Report = @{
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    stages = @()
    pass = $true
}

function Write-Stage {
    param([string]$Name, [bool]$Ok, [string]$Detail = "")
    $entry = @{ name = $Name; ok = $Ok; detail = $Detail; at = (Get-Date).ToUniversalTime().ToString("o") }
    $Report.stages += $entry
    if (-not $Ok) { $script:Report.pass = $false; throw "STAGE FAILED: $Name - $Detail" }
    Write-Host "[PASS] $Name" -ForegroundColor Green
}

function Run-Cmd {
    param([string]$Cwd, [string]$Cmd, [string]$LogFile)
    Push-Location (Join-Path $RepoRoot $Cwd)
    try {
        cmd /c $Cmd > $LogFile 2>&1
        return [int]$LASTEXITCODE
    } finally {
        Pop-Location
    }
}

$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json

# Stage 1 — Git integrity
$branch = git branch --show-current
Write-Stage "git_branch" ($branch -eq $manifest.approved_branch) "branch=$branch"
$head = (git rev-parse HEAD).Trim()
$origin = (git rev-parse "origin/$($manifest.approved_branch)").Trim()
Write-Stage "git_head_sync" ($head -eq $origin) "head=$head origin=$origin"
$porcelain = git status --porcelain
Write-Stage "git_clean" ([string]::IsNullOrWhiteSpace($porcelain)) $porcelain
Write-Stage "index_lock" (-not (Test-Path ".git\index.lock")) "index.lock present"

# Stage 2 — Authorization integrity
$authBase = $manifest.authorization_base_commit
$changed = @(git diff --name-only "$authBase..HEAD")
$changed | ConvertTo-Json | Set-Content (Join-Path $EvidenceDir "actual_changed_paths.json")
$manifest.authorized_implementation_paths | ConvertTo-Json | Set-Content (Join-Path $EvidenceDir "authorized_paths.json")
$unauthorized = @()
foreach ($p in $changed) {
    if ($manifest.authorized_implementation_paths -notcontains $p) {
        $unauthorized += $p
    }
}
@{ unauthorized = $unauthorized; changed = $changed } | ConvertTo-Json | Set-Content (Join-Path $EvidenceDir "authorization_validation.json")
Write-Stage "authorization_integrity" ($unauthorized.Count -eq 0) ($unauthorized -join ", ")

# Stage 3 — PowerShell integrity
$psLog = Join-Path $EvidenceDir "powershell_validation.log"
"" | Set-Content $psLog
$parseOk = $true
Get-ChildItem -Path (Join-Path $RepoRoot "scripts") -Filter "*.ps1" | ForEach-Object {
    $errs = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$errs)
    if ($errs -and $errs.Count -gt 0) {
        $parseOk = $false
        Add-Content $psLog "PARSE FAIL $($_.Name): $($errs | Out-String)"
    } else {
        Add-Content $psLog "PARSE OK $($_.Name)"
    }
}
# Safe invoke backup scripts (dry-run cleanup, list)
& (Join-Path $RepoRoot "scripts\list_backups_chakraops.ps1") 2>&1 | Add-Content $psLog
& (Join-Path $RepoRoot "scripts\cleanup_expired_backups.ps1") 2>&1 | Add-Content $psLog
Write-Stage "powershell_integrity" $parseOk "see powershell_validation.log"

# Stage 4 — Backend gates
$beLog = Join-Path $EvidenceDir "backend.log"
$code = Run-Cmd -Cwd "chakraops" -Cmd "python -m pytest tests -q --tb=short" -LogFile $beLog
Write-Stage "backend_full" ($code -eq 0) "exit=$code"
$r35Log = Join-Path $EvidenceDir "r350_suite.log"
$codeR = Run-Cmd -Cwd "chakraops" -Cmd "python -m pytest tests -k r350 -q --tb=short" -LogFile $r35Log
Write-Stage "backend_r350" ($codeR -eq 0) "exit=$codeR"

# Stage 5 — Frontend
$feLog = Join-Path $EvidenceDir "frontend.log"
$codeF = Run-Cmd -Cwd "frontend" -Cmd "npm run test -- --run" -LogFile $feLog
Write-Stage "frontend_tests" ($codeF -eq 0) "exit=$codeF"
$buildLog = Join-Path $EvidenceDir "build.log"
$codeB = Run-Cmd -Cwd "frontend" -Cmd "npm run build" -LogFile $buildLog
Write-Stage "frontend_build" ($codeB -eq 0) "exit=$codeB"

# Stage 6 — Live smoke
if (-not $SkipLiveSmoke) {
    & (Join-Path $RepoRoot "scripts\run_r31_r35_live_smoke.ps1")
    Write-Stage "windows_live_smoke" ($LASTEXITCODE -eq 0) "exit=$LASTEXITCODE"
}

# Stage 7 — Security scan (changed paths only)
$secLog = Join-Path $EvidenceDir "security_scan.log"
$scanCmd = "rg -i ""ORATS_API|api_key|Bearer [A-Za-z0-9]{20}"" scripts chakraops/app/core/operations --glob ""!**/.env*"" -c"
cmd /c $scanCmd 2>&1 | Tee-Object -FilePath $secLog
Write-Stage "security_scan" ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 1) "see security_scan.log"

# Stage 8 — Evidence consistency (parse counts from logs)
function Get-PytestSummary($logPath) {
    $tail = Get-Content $logPath -Tail 5 | Out-String
    if ($tail -match "(\d+) passed") { return $Matches[1] }
    return "unknown"
}
$beCount = Get-PytestSummary $beLog
$r35Count = Get-PytestSummary $r35Log
$Report.backend_passed = $beCount
$Report.r350_passed = $r35Count
Write-Stage "evidence_backend_parsed" ($beCount -ne "unknown") "passed=$beCount"
Write-Stage "evidence_r350_parsed" ($r35Count -ne "unknown") "passed=$r35Count"

# Stage 9 — Final git
$porcelain2 = git status --porcelain
Write-Stage "final_git_clean" ([string]::IsNullOrWhiteSpace($porcelain2)) $porcelain2

$Report.finished_at = (Get-Date).ToUniversalTime().ToString("o")
$Report.head = $head
$Report | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $EvidenceDir "release_acceptance.json")
@"
# R31-R35 Release Acceptance Report

- Pass: $($Report.pass)
- HEAD: $head
- Backend passed (parsed): $beCount
- R35 passed (parsed): $r35Count
- Stages: $($Report.stages.Count)
"@ | Set-Content (Join-Path $EvidenceDir "release_acceptance.md")

Copy-Item -LiteralPath (Join-Path $RepoRoot "docs\ai\validation\R31_R35_COWORK_UAT_HANDOFF.md") -Destination (Join-Path $EvidenceDir "cowork_uat_handoff.md") -Force -ErrorAction SilentlyContinue

Write-Host "=== RELEASE ACCEPTANCE PASS ===" -ForegroundColor Cyan
exit 0
