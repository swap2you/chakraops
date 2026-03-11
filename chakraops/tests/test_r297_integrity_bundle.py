# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R29.7: Integrity bundle endpoint — ZIP contents, no forbidden tokens, deterministic, no decision write."""

from __future__ import annotations

import json
import re
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")

EXPECTED_ZIP_NAMES = [
    "manifest.json",
    "integrity_check.json",
    "reconcile_diff.json",
    "positions_db.json",
    "positions_computed.json",
    "system_health_subset.json",
]


@pytest.fixture
def positions_db_override(tmp_path):
    from app.core.portfolio.positions_unified_store_r279 import (
        set_positions_db_path,
        reset_positions_db_path,
        init_db,
    )
    db_path = tmp_path / "positions.db"
    set_positions_db_path(db_path)
    init_db()
    try:
        yield db_path
    finally:
        reset_positions_db_path()


def _fixed_integrity_result(*args, **kwargs):
    return {"status": "OK", "status_label": "OK", "last": None, "history": []}


def _fixed_reconcile_diff(*args, **kwargs):
    return {
        "status": "OK",
        "status_label": "OK",
        "missing_count": 0,
        "extra_count": 0,
        "mismatched_count": 0,
        "items": [],
    }


def _fixed_positions_db(*args, **kwargs):
    return {"status": "OK", "status_label": "OK", "count": 0, "items": []}


def _fixed_positions_computed(*args, **kwargs):
    """build_unified_positions returns a list of positions."""
    return []


def _fixed_health_block(name: str):
    if name == "rebuild":
        return {"status": "OK", "last_rebuild_at_utc": "2026-01-01T12:00:00Z"}
    if name == "reconcile":
        return {"status": "OK"}
    if name == "integrity_check":
        return {"last_status": "OK", "last_status_label": "OK"}
    return {}


def test_bundle_zip_contains_expected_files(positions_db_override) -> None:
    """GET /api/ui/positions/unified/integrity-bundle returns a ZIP with expected JSON files."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(
        "/api/ui/positions/unified/integrity-bundle",
        params={"include_paper": True, "limit": 200},
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    assert "attachment" in (r.headers.get("content-disposition") or "")
    assert "integrity_bundle_" in (r.headers.get("content-disposition") or "")
    z = zipfile.ZipFile(BytesIO(r.content), "r")
    names = set(z.namelist())
    for expected in EXPECTED_ZIP_NAMES:
        assert expected in names, f"Missing {expected}"
    z.close()


def test_bundle_contains_no_forbidden_tokens(positions_db_override) -> None:
    """All JSON file contents in the bundle contain no FAIL/WARN/PASS or FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(
        "/api/ui/positions/unified/integrity-bundle",
        params={"include_paper": True, "limit": 100},
    )
    assert r.status_code == 200
    z = zipfile.ZipFile(BytesIO(r.content), "r")
    for name in EXPECTED_ZIP_NAMES:
        if name not in z.namelist():
            continue
        raw = z.read(name).decode("utf-8")
        assert not FORBIDDEN.search(raw), f"{name} contained forbidden whole-word token: {raw[:200]}"
        assert not FORBIDDEN_UNDERSCORE.search(raw), f"{name} contained FAIL_/WARN_: {raw[:200]}"
    z.close()


def test_bundle_deterministic_for_fixed_fixture(positions_db_override) -> None:
    """Same inputs and mocked data yield identical JSON contents (deterministic)."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.core.portfolio.positions_unified_store_r279.get_positions_unified_integrity_check_result", side_effect=_fixed_integrity_result), \
         patch("app.core.portfolio.positions_unified_store_r279.get_reconcile_diff", side_effect=_fixed_reconcile_diff), \
         patch("app.core.portfolio.positions_unified_store_r279.read_positions_unified_from_db", side_effect=_fixed_positions_db), \
         patch("app.core.portfolio.positions_unified_store_r279.build_unified_positions", side_effect=_fixed_positions_computed), \
         patch("app.api.ui_routes._get_positions_unified_rebuild_health", return_value=_fixed_health_block("rebuild")), \
         patch("app.api.ui_routes._get_positions_unified_reconcile_health", return_value=_fixed_health_block("reconcile")), \
         patch("app.api.ui_routes._get_positions_unified_integrity_check_health", return_value=_fixed_health_block("integrity_check")):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r1 = client.get(
            "/api/ui/positions/unified/integrity-bundle",
            params={"include_paper": True, "limit": 200},
        )
        r2 = client.get(
            "/api/ui/positions/unified/integrity-bundle",
            params={"include_paper": True, "limit": 200},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    z1 = zipfile.ZipFile(BytesIO(r1.content), "r")
    z2 = zipfile.ZipFile(BytesIO(r2.content), "r")
    for name in EXPECTED_ZIP_NAMES:
        if name not in z1.namelist() or name not in z2.namelist():
            continue
        # Compare parsed JSON (manifest has generated_at_utc which may differ by second; exclude for strict determinism or accept)
        j1 = json.loads(z1.read(name).decode("utf-8"))
        j2 = json.loads(z2.read(name).decode("utf-8"))
        if name == "manifest.json":
            # generated_at_utc can differ; compare rest
            assert j1.get("include_paper") == j2.get("include_paper")
            assert j1.get("limit") == j2.get("limit")
            assert j1.get("counts") == j2.get("counts")
        else:
            assert j1 == j2, f"{name} differed between runs"
    z1.close()
    z2.close()


def test_bundle_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """GET integrity-bundle does not create or modify out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get(
            "/api/ui/positions/unified/integrity-bundle",
            params={"include_paper": True, "limit": 50},
        )
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'
