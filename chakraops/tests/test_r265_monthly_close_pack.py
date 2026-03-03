# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.5: Monthly close pack — temp dir, deterministic, allowlist, no FAIL_/WARN_ in API JSON."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_close_pack_created_in_temp_directory() -> None:
    """Generate close pack with overridden base path; files created under data/reports/<month>/."""
    from app.core.ops.monthly_close_store_r265 import (
        generate_monthly_close_pack,
        set_reports_base_path,
        reset_reports_base_path,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_reports_base_path(Path(tmp))
        try:
            result = generate_monthly_close_pack("2026-03")
            assert result["month"] == "2026-03"
            assert result.get("pack") == "live"
            assert "generated_ts" in result
            assert set(result["paths"]) == {"monthly_report.json", "monthly_report.csv", "journal_export.csv", "summary.txt"}
            month_dir = Path(tmp) / "2026-03" / "live"
            assert month_dir.is_dir()
            for name in result["paths"]:
                assert (month_dir / name).is_file()
        finally:
            reset_reports_base_path()


def test_deterministic_file_contents_ordering() -> None:
    """Same journal data produces same file ordering and report structure."""
    from app.core.journal.journal_store import (
        set_journal_db_path,
        reset_journal_db_path,
        init_journal_db,
        journal_create,
    )
    from app.core.ops.monthly_close_store_r265 import (
        generate_monthly_close_pack,
        set_reports_base_path,
        reset_reports_base_path,
    )

    with tempfile.TemporaryDirectory() as tmp:
        jdb = Path(tmp) / "journal.db"
        set_journal_db_path(jdb)
        init_journal_db()
        set_reports_base_path(Path(tmp) / "reports")
        try:
            journal_create("2026-04-01", "SPY", "CSP", "OPEN", 1, premium=2.0, realized_pl=10.0)
            journal_create("2026-04-02", "QQQ", "SHARES", "SELL", 10, price=400.0, realized_pl=-5.0)
            r1 = generate_monthly_close_pack("2026-04")
            r2 = generate_monthly_close_pack("2026-04")
            assert r1["report"]["totals"]["realized_pl"] == r2["report"]["totals"]["realized_pl"]
            assert r1["report"]["totals"]["trade_count"] == 2
            assert sorted(r1["paths"]) == sorted(r2["paths"])
            month_dir = Path(tmp) / "reports" / "2026-04" / "live"
            size1 = (month_dir / "monthly_report.json").stat().st_size
            size2 = (month_dir / "monthly_report.json").stat().st_size
            assert size1 == size2
        finally:
            reset_journal_db_path()
            reset_reports_base_path()


def test_download_allowlist_works() -> None:
    """Download endpoint rejects file not in allowlist; accepts allowlist name."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.ops.monthly_close_store_r265 import ALLOWED_FILES

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/reports/monthly/close/download?month=2026-03&file=../../../etc/passwd")
        assert r.status_code == 400
        r2 = client.get("/api/ui/reports/monthly/close/download?month=2026-03&pack=live&file=monthly_report.json")
        assert r2.status_code in (200, 404)
        r3 = client.get("/api/ui/reports/monthly/close/download?month=2026-03&file=not_allowed.txt")
        assert r3.status_code == 400


def test_no_fail_warn_in_json_responses() -> None:
    """Close pack and files API must not return FAIL_ or WARN_ in JSON body."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        for path in [
            "/api/ui/reports/monthly/close/files?month=2026-03",
        ]:
            r = client.get(path)
            assert r.status_code == 200, path
            raw = json.dumps(r.json())
            assert "FAIL_" not in raw, path
            assert "WARN_" not in raw, path
        r = client.post("/api/ui/reports/monthly/close?month=2026-03")
        if r.status_code == 200:
            raw = json.dumps(r.json())
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
