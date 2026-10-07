# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.7: Portfolio enrichment cc_eligible, pct_return, days_held; CC_ELIGIBLE notification dedupe; no FAIL_/WARN_ in payloads."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


def test_enrich_shares_cc_eligible_and_reason() -> None:
    """Enrichment sets cc_eligible True when quantity >= 100; reason is safe label only (no FAIL_/WARN_)."""
    from app.core.portfolio.live_shares_mark_r274 import enrich_live_shares_positions_with_mark, CC_MIN_SHARES

    assert CC_MIN_SHARES == 100
    # No price -> still get cc_eligible and cc_eligible_reason
    positions = [
        {"symbol": "AAPL", "quantity": 150, "avg_cost": 180.0, "opened_at": None},
        {"symbol": "NVDA", "quantity": 50, "avg_cost": 400.0, "opened_at": None},
    ]
    out = enrich_live_shares_positions_with_mark(positions, {}, None)
    assert len(out) == 2
    out_by_sym = {p["symbol"]: p for p in out}
    assert out_by_sym["AAPL"]["cc_eligible"] is True
    assert "100" in (out_by_sym["AAPL"].get("cc_eligible_reason") or "")
    assert "FAIL" not in (out_by_sym["AAPL"].get("cc_eligible_reason") or "")
    assert "WARN" not in (out_by_sym["AAPL"].get("cc_eligible_reason") or "")
    assert out_by_sym["NVDA"]["cc_eligible"] is False
    assert "Fewer" in (out_by_sym["NVDA"].get("cc_eligible_reason") or "")
    assert "FAIL" not in (out_by_sym["NVDA"].get("cc_eligible_reason") or "")
    assert "WARN" not in (out_by_sym["NVDA"].get("cc_eligible_reason") or "")


def test_enrich_shares_pct_return_days_held_and_sorted() -> None:
    """Enrichment adds pct_return, days_held; result sorted by symbol for determinism."""
    from app.core.portfolio.live_shares_mark_r274 import enrich_live_shares_positions_with_mark

    now = datetime.now(timezone.utc)
    opened = (now.replace(hour=0, minute=0, second=0, microsecond=0)).isoformat().replace("+00:00", "Z")
    positions = [
        {"symbol": "ZZZ", "quantity": 100, "avg_cost": 10.0, "opened_at": opened},
        {"symbol": "AAA", "quantity": 100, "avg_cost": 10.0, "opened_at": opened},
    ]
    out = enrich_live_shares_positions_with_mark(positions, {"AAA": 11.0, "ZZZ": 12.0}, None)
    assert [p["symbol"] for p in out] == ["AAA", "ZZZ"]
    assert out[0].get("pct_return") == 10.0  # (11-10)/10*100
    assert out[1].get("pct_return") == 20.0  # (12-10)/10*100
    assert out[0].get("days_held") is not None
    assert out[1].get("days_held") is not None


def test_cc_eligible_notification_dedupe_by_symbol() -> None:
    """CC_ELIGIBLE notification: at most one active (NEW/ACKED) per symbol; append only when none."""
    from app.api.notifications_store import (
        maybe_append_cc_eligible_notification,
        CC_ELIGIBLE,
        load_notifications,
        append_archive,
    )
    from app.core.eval.evaluation_store_v2 import get_decision_store_path, set_output_dir, reset_output_dir

    with __import__("tempfile").TemporaryDirectory() as tmp:
        out_path = Path(tmp)
        set_output_dir(out_path)
        try:
            path = get_decision_store_path().parent / "notifications.jsonl"
            if path.exists():
                path.unlink()
            # First append for NVDA -> True
            assert maybe_append_cc_eligible_notification("NVDA") is True
            # Second append for NVDA while first still NEW -> False (deduped)
            assert maybe_append_cc_eligible_notification("NVDA") is False
            # Different symbol -> True
            assert maybe_append_cc_eligible_notification("AAPL") is True
            recs = load_notifications(limit=10, state_filter=None)
            cc_nvda = [r for r in recs if r.get("type") == CC_ELIGIBLE and (r.get("symbol") or "").upper() == "NVDA"]
            assert len(cc_nvda) == 1
            # Archive NVDA; then append again for NVDA -> True (re-trigger allowed)
            if cc_nvda:
                append_archive(cc_nvda[0]["id"])
            assert maybe_append_cc_eligible_notification("NVDA") is True
        finally:
            reset_output_dir()


def test_portfolio_shares_payload_no_fail_warn_substrings() -> None:
    """GET /portfolio shares_positions must not contain FAIL_ or WARN_ in any field (R27.7)."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir
    from app.core.accounts import holdings_db

    prev_env = os.environ.get("CHAKRAOPS_OUT")
    with __import__("tempfile").TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        os.environ["CHAKRAOPS_OUT"] = str(out_dir)
        set_output_dir(out_dir)
        try:
            holdings_db.init_db()
            holdings_db.upsert_share_position("default", "SPY", 100, avg_cost=450.0)
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.get("/api/ui/portfolio")
            assert r.status_code == 200
            data = r.json()
            raw = json.dumps(data)
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
            for pos in data.get("shares_positions") or []:
                assert "FAIL_" not in json.dumps(pos)
                assert "WARN_" not in json.dumps(pos)
        finally:
            reset_output_dir()
            if prev_env is not None:
                os.environ["CHAKRAOPS_OUT"] = prev_env
            else:
                os.environ.pop("CHAKRAOPS_OUT", None)
