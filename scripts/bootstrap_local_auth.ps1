# ChakraOps AUTH-001 — bootstrap local Argon2id admin hashes + session secret.
# Writes ONLY under C:\ChakraOpsSecrete (or -SecretRoot). Never echoes the password.
# Fixed admins: swap2you, swapnilpatil, daudada, admin. No signup/register.

param(
    [string]$SecretRoot = "C:\ChakraOpsSecrete",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

$admins = @("swap2you", "swapnilpatil", "daudada", "admin")
$usersFile = Join-Path $SecretRoot "chakraops_auth_users.json"
$secretFile = Join-Path $SecretRoot "chakraops_session_secret"

if (-not $PythonExe) {
    $venvPy = Join-Path $PSScriptRoot "..\chakraops\.venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        $PythonExe = (Resolve-Path -LiteralPath $venvPy).Path
    } else {
        $PythonExe = "python"
    }
}

Write-Host "ChakraOps local auth bootstrap" -ForegroundColor Cyan
Write-Host "Secret root: $SecretRoot"
Write-Host "Users file:  $usersFile"
Write-Host "Session:     $secretFile"
Write-Host "Admins:      $($admins -join ', ')"
Write-Host "Password will NOT be printed or logged." -ForegroundColor Yellow

$secure = Read-Host -AsSecureString "Enter password for all four fixed admins"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null
}

if ([string]::IsNullOrWhiteSpace($plain)) {
    throw "Password must not be empty."
}
if ($plain.Length -lt 12) {
    $plain = $null
    throw "Password must be at least 12 characters."
}

New-Item -ItemType Directory -Force -Path $SecretRoot | Out-Null

# Pass password via env var to a short-lived Python process; clear immediately after.
# Do not Write-Host / log the value.
$env:CHAKRAOPS_BOOTSTRAP_PASSWORD = $plain
$plain = $null
$secure = $null

$py = @"
import json, os, secrets, sys
from pathlib import Path

try:
    from argon2 import PasswordHasher
except ImportError:
    print("ERROR: argon2-cffi not installed. Run: pip install argon2-cffi", file=sys.stderr)
    sys.exit(2)

password = os.environ.get("CHAKRAOPS_BOOTSTRAP_PASSWORD") or ""
os.environ.pop("CHAKRAOPS_BOOTSTRAP_PASSWORD", None)
if not password or len(password) < 12:
    print("ERROR: bootstrap password missing/too short", file=sys.stderr)
    sys.exit(1)

root = Path(r'''$SecretRoot''')
root.mkdir(parents=True, exist_ok=True)
users_path = root / "chakraops_auth_users.json"
secret_path = root / "chakraops_session_secret"

ph = PasswordHasher()
admins = ["swap2you", "swapnilpatil", "daudada", "admin"]
payload = {"users": {u: {"password_hash": ph.hash(password), "role": "admin"} for u in admins}}
# Clear local password reference ASAP
password = None

tmp = users_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
tmp.replace(users_path)

if (not secret_path.is_file()) or len(secret_path.read_text(encoding="utf-8").strip()) < 32:
    secret_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")

print("Wrote hashes for", len(admins), "admins")
print("Users path:", str(users_path))
print("Session secret path:", str(secret_path))
print("OK")
"@

try {
    & $PythonExe -c $py
    if ($LASTEXITCODE -ne 0) {
        throw "Bootstrap Python failed with exit $LASTEXITCODE"
    }
} finally {
    Remove-Item Env:CHAKRAOPS_BOOTSTRAP_PASSWORD -ErrorAction SilentlyContinue
}

Write-Host "Bootstrap complete. Set CHAKRAOPS_AUTH_MODE=required to enforce login." -ForegroundColor Green
Write-Host "Never commit $usersFile or $secretFile to Git." -ForegroundColor Yellow
