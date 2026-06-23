# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 Windows backup PowerShell script tests."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_backup_script_dot_sources_common():
    text = _read("backup_chakraops.ps1")
    assert "chakraops_common.ps1" in text
    assert "$StaleRoot" not in text or "ChakraOpsStaleRoot" in _read("chakraops_common.ps1")


def test_common_defines_required_variables():
    text = _read("chakraops_common.ps1")
    assert "ChakraOpsRepoRoot" in text
    assert "ChakraOpsStaleRoot" in text
    assert "ChakraOpsBackendRoot" in text
    assert "Set-StrictMode" in text


def test_all_backup_scripts_dot_source_common():
    for name in (
        "backup_chakraops.ps1",
        "list_backups_chakraops.ps1",
        "verify_backup_chakraops.ps1",
        "restore_chakraops_validate.ps1",
        "cleanup_expired_backups.ps1",
    ):
        assert "chakraops_common.ps1" in _read(name)


def test_cleanup_defaults_to_dry_run():
    text = _read("cleanup_expired_backups.ps1")
    assert "dry_run=True" in text.replace(" ", "")
    assert "DELETE-EXPIRED-BACKUPS" in text


def test_powershell_parser_accepts_scripts():
    if not Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe").exists():
        pytest.skip("PowerShell not available")
    for name in SCRIPTS.glob("*.ps1"):
        fp = str(name.resolve()).replace("'", "''")
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
        assert r.returncode == 0, f"parse failed for {name.name}: {r.stderr}"


def test_runbook_references_exist():
    runbook = (REPO / "chakraops" / "docs" / "RUNBOOK_BACKUP_RESTORE.md").read_text(encoding="utf-8")
    for script in (
        "backup_chakraops.ps1",
        "list_backups_chakraops.ps1",
        "verify_backup_chakraops.ps1",
        "restore_chakraops_validate.ps1",
        "cleanup_expired_backups.ps1",
    ):
        assert script in runbook
        assert (SCRIPTS / script).exists()


def test_historical_undefined_stale_root_fixed():
    """backup_chakraops.ps1 must not reference bare $StaleRoot before definition."""
    text = _read("backup_chakraops.ps1")
    assert not re.search(r'"\$StaleRoot', text)
    assert "$Backend" not in text or "Initialize-ChakraOpsCheckout" in text
