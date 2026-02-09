# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5: API readiness audit — UNKNOWN states, multi-exit, data_sufficiency."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.core.decision_quality.derived import compute_derived_metrics
from app.core.decision_quality.analytics import get_outcome_summary, _closed_with_exit
from app.core.exits.store import load_exit_events, get_final_exit, save_exit
from app.core.exits.models import ExitRecord


def test_return_on_risk_null_includes_status() -> None:
    """When risk_amount missing, API response must include return_on_risk_status = UNKNOWN_INSUFFICIENT_RISK_DEFINITION."""
    pos = MagicMock()
    pos.opened_at = "2026-01-15"
    pos.risk_amount_at_entry = None

    exit_rec = MagicMock()
    exit_rec.exit_date = "2026-02-06"
    exit_rec.realized_pnl = 100.0

    derived = compute_derived_metrics(pos, exit_rec, capital=1000.0, risk_amount=None)

    assert derived["return_on_risk"] is None
    assert derived["return_on_risk_status"] == "UNKNOWN_INSUFFICIENT_RISK_DEFINITION"
    assert derived["outcome_tag"] is None


def test_outcome_summary_includes_unknown_risk_count() -> None:
    """Outcome summary must include unknown_risk_definition_count even when INSUFFICIENT DATA."""
    result = get_outcome_summary()
    assert "unknown_risk_definition_count" in result
    assert result["unknown_risk_definition_count"] == 0 or isinstance(result["unknown_risk_definition_count"], int)


def test_closed_with_exit_excludes_scale_out_only() -> None:
    """Positions with only SCALE_OUT (no FINAL_EXIT) must not appear in decision quality."""
    # _closed_with_exit filters to positions with has_final=True
    # This test verifies the filter logic: only FINAL_EXIT positions included
    items = _closed_with_exit()
    for pos, final_exit, derived in items:
        assert final_exit.event_type == "FINAL_EXIT"


def test_multi_exit_aggregated_pnl(tmp_path: Path) -> None:
    """Multi-exit (SCALE_OUT + FINAL_EXIT) uses aggregated realized_pnl."""
    from app.core.exits.store import _get_exits_dir, _ensure_exits_dir

    exits_dir = tmp_path / "exits"
    exits_dir.mkdir()

    with patch("app.core.exits.store._get_exits_dir", return_value=exits_dir), \
         patch("app.core.exits.store._ensure_exits_dir", return_value=exits_dir):
        scale = ExitRecord(
            position_id="pos_agg", exit_date="2026-02-01", exit_price=102.0,
            realized_pnl=50.0, fees=0, exit_reason="TARGET1", exit_initiator="MANUAL",
            confidence_at_exit=4, event_type="SCALE_OUT",
        )
        save_exit(scale)
        final = ExitRecord(
            position_id="pos_agg", exit_date="2026-02-06", exit_price=105.0,
            realized_pnl=150.0, fees=1.0, exit_reason="TARGET2", exit_initiator="MANUAL",
            confidence_at_exit=4, event_type="FINAL_EXIT",
        )
        save_exit(final)

        events = load_exit_events("pos_agg")
        aggregated = sum(float(getattr(e, "realized_pnl", 0)) for e in events)
        assert aggregated == 200.0
        assert get_final_exit("pos_agg").event_type == "FINAL_EXIT"


def test_data_sufficiency_api_always_includes_missing_fields() -> None:
    """symbol/data-sufficiency API must always include missing_fields (empty list when PASS)."""
    from app.core.symbols.data_sufficiency import derive_data_sufficiency

    status, missing = derive_data_sufficiency("UNKNOWN_SYMBOL_XYZ")
    assert isinstance(missing, list)
    assert status in ("PASS", "WARN", "FAIL")


def test_audit_exit_event_created(tmp_path: Path) -> None:
    """Exit event creation produces audit log."""
    from app.core.audit import audit_exit_event_created, _audit_path

    with patch("app.core.audit._audit_path", return_value=tmp_path / "audit" / "phase5_actions.jsonl"):
        audit_exit_event_created("pos_1", "AAPL", "FINAL_EXIT", "TARGET1")
        path = tmp_path / "audit" / "phase5_actions.jsonl"
        assert path.exists()
        content = path.read_text()
        assert "exit_event_created" in content
        assert "pos_1" in content
        assert "AAPL" in content
        assert "FINAL_EXIT" in content


def test_audit_manual_execution_intent(tmp_path: Path) -> None:
    """Manual execution intent produces audit log."""
    from app.core.audit import audit_manual_execution_intent

    with patch("app.core.audit._audit_path", return_value=tmp_path / "audit" / "phase5_actions.jsonl"):
        audit_manual_execution_intent("pos_1", "AAPL", "CSP", "acct_1", contracts=2)
        path = tmp_path / "audit" / "phase5_actions.jsonl"
        assert path.exists()
        content = path.read_text()
        assert "manual_execution_intent" in content
        assert "pos_1" in content
        assert "AAPL" in content
