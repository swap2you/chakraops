# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-DEF-072: Windows startup must use npm.cmd and wait for LISTEN (no false ownership)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_startup_lib_exists_and_resolves_npm_cmd():
    text = _read("chakraops_startup.ps1")
    assert "function Resolve-ChakraOpsNpmLauncher" in text
    assert "function Wait-ChakraOpsPortListen" in text
    assert "function Stop-ChakraOpsStartedProcesses" in text
    assert "npm.cmd" in text
    # Must explicitly reject extensionless npm / Notepad class failure mode
    assert "Notepad" in text or "extensionless" in text.lower()


def test_start_script_uses_startup_lib_not_bare_npm():
    text = _read("start_chakraops.ps1")
    assert "chakraops_startup.ps1" in text
    assert "Resolve-ChakraOpsNpmLauncher" in text
    assert "Wait-ChakraOpsPortListen" in text
    assert re.search(r"Start-Process\s+npm\b", text) is None
    assert 'Start-Process -FilePath "npm"' not in text
    assert "Start-Process -FilePath 'npm'" not in text
    assert "cmd.exe" in text
    assert 'CHAKRAOPS_SCHEDULER_ENABLED = "false"' in text
    assert 'CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED = "false"' in text
    assert "Stop-ChakraOpsStartedProcesses" in text
    assert "write_record" in text
    # Ownership only after waits / inside success try
    assert "Wait-ChakraOpsHttpOk" in text
    assert "/api/healthz" in text


def test_start_script_does_not_trust_spawn_pid_as_listener():
    text = _read("start_chakraops.ps1")
    # Must record listen PIDs from Wait-ChakraOpsPortListen, not $frontendProc.Id alone
    assert "frontendListenPid" in text or "frontend_pid=$frontendListenPid" in text.replace(" ", "")
    assert "backendListenPid" in text or "backend_pid=$backendListenPid" in text.replace(" ", "")


def test_powershell_parses_startup_scripts():
    ps_exe = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if not ps_exe.exists():
        pytest.skip("PowerShell not available")
    for name in ("chakraops_startup.ps1", "start_chakraops.ps1", "start_chakraops_selftest.ps1"):
        fp = str((SCRIPTS / name).resolve()).replace("'", "''")
        ps = f"""
$errs = $null
$null = [Management.Automation.Language.Parser]::ParseFile('{fp}', [ref]$null, [ref]$errs)
if ($errs) {{ exit 1 }} else {{ exit 0 }}
"""
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0, f"parse failed for {name}: {r.stderr}"


@pytest.mark.skipif(
    not Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe").exists(),
    reason="PowerShell not available",
)
def test_start_chakraops_selftest_passes():
    script = SCRIPTS / "start_chakraops_selftest.ps1"
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "Failed=0" in r.stdout or "Passed=" in r.stdout
