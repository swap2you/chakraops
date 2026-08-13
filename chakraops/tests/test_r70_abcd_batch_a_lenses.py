# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-ABCD Batch A — live position lenses + integrity NOT_RUN."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.core.broker.models import BrokerBalances, BrokerSnapshot, EquityPosition, OptionPosition
from app.core.portfolio.live_position_lenses_r70 import (
    LENS_LIVE_TOTAL,
    build_live_position_lenses,
    historicalize_orphan_unified_live_shares,
    unmirror_live_shares_open_by_symbol,
)
from app.core.portfolio.positions_unified_store_r279 import (
    get_positions_unified_integrity_check_health,
    get_positions_unified_integrity_check_result,
)


def _snap(*, stale: bool = False, equities: Optional[List[EquityPosition]] = None, age_minutes: float = 5.0) -> BrokerSnapshot:
    from datetime import datetime, timedelta, timezone

    if equities is None:
        equities = [
            EquityPosition(symbol="NVDA", quantity=300.0, average_cost=157.0),
            EquityPosition(symbol="AMZN", quantity=25.0, average_cost=216.0),
            EquityPosition(symbol="SMCI", quantity=425.0, average_cost=30.0),
        ]
    fetched = (datetime.now(timezone.utc) - timedelta(minutes=age_minutes)).isoformat().replace("+00:00", "Z")
    return BrokerSnapshot(
        account_alias="acct_individual",
        fetched_at=fetched,
        balances=BrokerBalances(cash=1.0, buying_power=1.0, equity=1.0),
        equity_positions=list(equities),
        option_positions=[],
        freshness="fresh",
        completeness="complete",
        stale=stale,
        source="robinhood_mcp",
    )


def test_integrity_never_run_is_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.portfolio.positions_unified_store_r279.load_integrity_check_state",
        lambda: None,
    )
    health = get_positions_unified_integrity_check_health()
    assert health["last_status"] == "NOT_RUN"
    assert health["last_checked_at_utc"] is None
    result = get_positions_unified_integrity_check_result()
    assert result["status"] == "NOT_RUN"


def test_live_lenses_fresh_broker_equals_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap()
    monkeypatch.setattr(
        "app.core.broker.snapshot_store.load_snapshot",
        lambda _alias: snap,
    )
    monkeypatch.setattr(
        "app.core.broker.status.robinhood_mcp_read_only_status",
        lambda **_kw: {
            "status": "READ_ONLY_AVAILABLE",
            "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True,
        },
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._manual_recovery_positions",
        lambda: [{"symbol": "AAPL", "quantity": 10, "authority": "manual_holdings"}],
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._paper_open_positions",
        lambda: [],
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._historical_closed_count",
        lambda: 5,
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._unified_open_diagnostic",
        lambda: {"open_live_count": 81, "open_paper_count": 186},
    )
    out = build_live_position_lenses()
    assert out["live_state"] == "FRESH"
    assert out["live_open_count"] == 3
    assert out["live_equity_count"] == 3
    assert out["live_option_count"] == 0
    assert out["manual_open_count"] == 1
    assert out["lenses"][LENS_LIVE_TOTAL]["count"] == 3
    # Unified orphans must not inflate LIVE
    assert out["lenses"]["UNIFIED_STORE_OPEN_POSITIONS"]["count"] == 81
    assert out["live_open_count"] != 81


def test_live_lenses_broker_zero_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap(equities=[])
    snap.balances = BrokerBalances(cash=0.0, buying_power=0.0, equity=0.0)
    monkeypatch.setattr("app.core.broker.snapshot_store.load_snapshot", lambda _a: snap)
    monkeypatch.setattr(
        "app.core.broker.status.robinhood_mcp_read_only_status",
        lambda **_kw: {"status": "READ_ONLY_AVAILABLE", "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True},
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._manual_recovery_positions",
        lambda: [],
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._paper_open_positions",
        lambda: [],
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._historical_closed_count",
        lambda: 0,
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._unified_open_diagnostic",
        lambda: {"open_live_count": 0, "open_paper_count": 0},
    )
    out = build_live_position_lenses()
    assert out["live_open_count"] == 0
    assert out["sizing_blocked"] is False


def test_live_lenses_stale_blocks_sizing(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap(stale=True)
    monkeypatch.setattr("app.core.broker.snapshot_store.load_snapshot", lambda _a: snap)
    monkeypatch.setattr(
        "app.core.broker.status.robinhood_mcp_read_only_status",
        lambda **_kw: {"status": "STALE", "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True},
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._manual_recovery_positions",
        lambda: [],
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._paper_open_positions",
        lambda: [],
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._historical_closed_count",
        lambda: 0,
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._unified_open_diagnostic",
        lambda: {"open_live_count": 0, "open_paper_count": 0},
    )
    out = build_live_position_lenses()
    assert out["live_state"] == "STALE"
    assert out["sizing_blocked"] is True
    assert out["live_open_count"] == 3  # last-good still visible


def test_live_lenses_age_exceeded_is_stale_not_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Age-based freshness must match capital authority (boolean stale=False is insufficient)."""
    snap = _snap(stale=False, age_minutes=200.0)
    monkeypatch.setattr("app.core.broker.snapshot_store.load_snapshot", lambda _a: snap)
    monkeypatch.setattr(
        "app.core.broker.status.robinhood_mcp_read_only_status",
        lambda **_kw: {"status": "READ_ONLY_AVAILABLE", "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True},
    )
    monkeypatch.setattr("app.core.portfolio.live_position_lenses_r70._manual_recovery_positions", lambda: [])
    monkeypatch.setattr("app.core.portfolio.live_position_lenses_r70._paper_open_positions", lambda: [])
    monkeypatch.setattr("app.core.portfolio.live_position_lenses_r70._historical_closed_count", lambda: 0)
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._unified_open_diagnostic",
        lambda: {"open_live_count": 0, "open_paper_count": 0},
    )
    from app.core.portfolio.capital_authority_r70 import get_capital_snapshot, get_broker_freshness_view

    lenses = build_live_position_lenses()
    cap = get_capital_snapshot("acct_individual")
    view = get_broker_freshness_view("acct_individual")
    assert lenses["live_state"] == "STALE"
    assert lenses["sizing_blocked"] is True
    assert cap["state"] == "STALE"
    assert view["state"] == "STALE"
    assert lenses["live_state"] == cap["state"] == view["state"]


def test_paper_excluded_from_live(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap(equities=[EquityPosition(symbol="NVDA", quantity=1.0)])
    monkeypatch.setattr("app.core.broker.snapshot_store.load_snapshot", lambda _a: snap)
    monkeypatch.setattr(
        "app.core.broker.status.robinhood_mcp_read_only_status",
        lambda **_kw: {"status": "READ_ONLY_AVAILABLE", "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True},
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._manual_recovery_positions",
        lambda: [],
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._paper_open_positions",
        lambda: [{"symbol": "PAPER", "quantity": 99, "is_paper": True}],
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._historical_closed_count",
        lambda: 0,
    )
    monkeypatch.setattr(
        "app.core.portfolio.live_position_lenses_r70._unified_open_diagnostic",
        lambda: {"open_live_count": 0, "open_paper_count": 1},
    )
    out = build_live_position_lenses()
    assert out["live_open_count"] == 1
    assert out["paper_open_count"] == 1
