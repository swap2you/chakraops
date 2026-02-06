# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1 Tests: Manual execution — position creation and validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.positions.models import Position, generate_position_id, VALID_STATUSES, VALID_STRATEGIES
from app.core.positions import store as position_store
from app.core.positions.service import validate_manual_execute, manual_execute
from app.core.accounts.models import Account
from app.core.accounts import store as account_store


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_position_model_round_trip() -> None:
    """Position round-trips through to_dict/from_dict."""
    pos = Position(
        position_id="pos_test_1",
        account_id="acct_1",
        symbol="SPY",
        strategy="CSP",
        contracts=2,
        strike=500.0,
        expiration="2026-03-21",
        credit_expected=2.50,
        status="OPEN",
        notes="Test position",
    )
    d = pos.to_dict()
    restored = Position.from_dict(d)
    assert restored.position_id == "pos_test_1"
    assert restored.symbol == "SPY"
    assert restored.strategy == "CSP"
    assert restored.contracts == 2
    assert restored.strike == 500.0
    assert restored.status == "OPEN"
    assert restored.notes == "Test position"


def test_generate_position_id() -> None:
    """Generated IDs have expected format."""
    pid = generate_position_id()
    assert pid.startswith("pos_")
    assert len(pid) > 4


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_accounts_and_positions(tmp_path: Path):
    """Set up temp dirs for both accounts and positions stores."""
    accounts_dir = tmp_path / "accounts"
    positions_dir = tmp_path / "positions"
    accounts_dir.mkdir()
    positions_dir.mkdir()

    # Create a test account
    acct = Account(
        account_id="test-acct",
        provider="Manual",
        account_type="Taxable",
        total_capital=50000.0,
        max_capital_per_trade_pct=5.0,
        max_total_exposure_pct=30.0,
        allowed_strategies=["CSP", "CC"],
        is_default=True,
        active=True,
    )

    with patch.object(account_store, "_get_accounts_dir", return_value=accounts_dir), \
         patch.object(account_store, "_ensure_accounts_dir", return_value=accounts_dir), \
         patch.object(position_store, "_get_positions_dir", return_value=positions_dir), \
         patch.object(position_store, "_ensure_positions_dir", return_value=positions_dir):
        account_store.create_account(acct)
        yield {"accounts_dir": accounts_dir, "positions_dir": positions_dir, "account": acct}


def test_validate_manual_execute_valid(tmp_accounts_and_positions) -> None:
    """Valid manual execution payload passes validation."""
    data = {
        "account_id": "test-acct",
        "symbol": "SPY",
        "strategy": "CSP",
        "contracts": 2,
        "strike": 500.0,
        "expiration": "2026-03-21",
    }
    errors = validate_manual_execute(data)
    assert errors == []


def test_validate_manual_execute_missing_account() -> None:
    """Missing account_id fails validation."""
    data = {
        "symbol": "SPY",
        "strategy": "CSP",
        "contracts": 1,
    }
    errors = validate_manual_execute(data)
    assert any("account_id" in e for e in errors)


def test_validate_manual_execute_invalid_strategy() -> None:
    """Invalid strategy fails validation."""
    data = {
        "account_id": "test-acct",
        "symbol": "SPY",
        "strategy": "IRON_CONDOR",
        "contracts": 1,
    }
    with patch.object(account_store, "get_account", return_value=Account(
        account_id="test-acct", provider="Manual", account_type="Taxable",
        total_capital=50000, max_capital_per_trade_pct=5,
        max_total_exposure_pct=30, allowed_strategies=["CSP"],
        active=True,
    )):
        errors = validate_manual_execute(data)
    assert any("strategy" in e for e in errors)


def test_validate_manual_execute_stock_needs_quantity() -> None:
    """STOCK strategy requires positive quantity."""
    data = {
        "account_id": "test-acct",
        "symbol": "AAPL",
        "strategy": "STOCK",
        "quantity": 0,
    }
    with patch.object(account_store, "get_account", return_value=Account(
        account_id="test-acct", provider="Manual", account_type="Taxable",
        total_capital=50000, max_capital_per_trade_pct=5,
        max_total_exposure_pct=30, allowed_strategies=["STOCK"],
        active=True,
    )):
        errors = validate_manual_execute(data)
    assert any("quantity" in e for e in errors)


# ---------------------------------------------------------------------------
# Store tests
# ---------------------------------------------------------------------------


def test_store_create_and_list_positions(tmp_accounts_and_positions) -> None:
    """Create and list positions via store."""
    pos = Position(
        position_id="pos_test_1",
        account_id="test-acct",
        symbol="SPY",
        strategy="CSP",
        contracts=1,
        strike=500.0,
        expiration="2026-03-21",
        status="OPEN",
    )
    position_store.create_position(pos)
    result = position_store.list_positions()
    assert len(result) == 1
    assert result[0].position_id == "pos_test_1"
    assert result[0].symbol == "SPY"


def test_store_filter_by_status(tmp_accounts_and_positions) -> None:
    """List positions filtered by status."""
    pos1 = Position(
        position_id="pos_1", account_id="test-acct", symbol="SPY",
        strategy="CSP", contracts=1, status="OPEN",
    )
    pos2 = Position(
        position_id="pos_2", account_id="test-acct", symbol="QQQ",
        strategy="CSP", contracts=1, status="CLOSED",
    )
    position_store.create_position(pos1)
    position_store.create_position(pos2)

    open_positions = position_store.list_positions(status="OPEN")
    assert len(open_positions) == 1
    assert open_positions[0].symbol == "SPY"

    closed_positions = position_store.list_positions(status="CLOSED")
    assert len(closed_positions) == 1
    assert closed_positions[0].symbol == "QQQ"


# ---------------------------------------------------------------------------
# Manual execution end-to-end
# ---------------------------------------------------------------------------


def test_manual_execute_creates_position(tmp_accounts_and_positions) -> None:
    """Manual execute creates a position with status=OPEN."""
    data = {
        "account_id": "test-acct",
        "symbol": "SPY",
        "strategy": "CSP",
        "contracts": 2,
        "strike": 500.0,
        "expiration": "2026-03-21",
        "credit_expected": 2.50,
        "notes": "Testing manual execution",
    }
    position, errors = manual_execute(data)
    assert errors == []
    assert position is not None
    assert position.status == "OPEN"
    assert position.symbol == "SPY"
    assert position.contracts == 2
    assert position.strike == 500.0
    assert position.notes == "Testing manual execution"

    # Verify persisted
    stored = position_store.list_positions()
    assert len(stored) == 1
    assert stored[0].position_id == position.position_id


def test_manual_execute_invalid_data_returns_errors(tmp_accounts_and_positions) -> None:
    """Invalid manual execute data returns errors without creating position."""
    data = {
        "account_id": "nonexistent",
        "symbol": "SPY",
        "strategy": "CSP",
        "contracts": 1,
    }
    position, errors = manual_execute(data)
    assert position is None
    assert len(errors) > 0

    # No positions created
    stored = position_store.list_positions()
    assert len(stored) == 0
