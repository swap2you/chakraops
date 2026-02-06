# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1 Tests: Account model, store, service, and CSP sizing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.accounts.models import Account, generate_account_id, VALID_PROVIDERS, VALID_ACCOUNT_TYPES
from app.core.accounts.service import (
    validate_account_data,
    compute_csp_sizing,
    create_account,
    list_accounts,
    set_default,
    get_default_account,
    update_account,
)
from app.core.accounts import store as account_store


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_account_model_to_dict_from_dict() -> None:
    """Account round-trips through to_dict/from_dict."""
    acct = Account(
        account_id="test-1",
        provider="Robinhood",
        account_type="Taxable",
        total_capital=50000.0,
        max_capital_per_trade_pct=5.0,
        max_total_exposure_pct=30.0,
        allowed_strategies=["CSP", "CC"],
        is_default=True,
        active=True,
    )
    d = acct.to_dict()
    restored = Account.from_dict(d)
    assert restored.account_id == "test-1"
    assert restored.provider == "Robinhood"
    assert restored.total_capital == 50000.0
    assert restored.max_capital_per_trade_pct == 5.0
    assert restored.allowed_strategies == ["CSP", "CC"]
    assert restored.is_default is True


def test_generate_account_id() -> None:
    """Generated IDs have expected format."""
    aid = generate_account_id()
    assert aid.startswith("acct_")
    assert len(aid) > 5


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


def test_validate_create_valid() -> None:
    """Valid create payload passes validation."""
    data = {
        "provider": "Schwab",
        "account_type": "Roth",
        "total_capital": 25000,
        "max_capital_per_trade_pct": 5,
        "max_total_exposure_pct": 30,
        "allowed_strategies": ["CSP"],
    }
    errors = validate_account_data(data, is_create=True)
    assert errors == []


def test_validate_create_missing_fields() -> None:
    """Missing required fields produce errors."""
    errors = validate_account_data({}, is_create=True)
    assert len(errors) > 0
    assert any("provider" in e for e in errors)
    assert any("total_capital" in e for e in errors)


def test_validate_pct_out_of_range() -> None:
    """Percentages outside 1-100 produce errors."""
    data = {
        "provider": "Manual",
        "account_type": "Taxable",
        "total_capital": 10000,
        "max_capital_per_trade_pct": 0,  # too low
        "max_total_exposure_pct": 101,  # too high
    }
    errors = validate_account_data(data, is_create=True)
    assert any("max_capital_per_trade_pct" in e for e in errors)
    assert any("max_total_exposure_pct" in e for e in errors)


def test_validate_negative_capital() -> None:
    """Negative total_capital is rejected."""
    data = {
        "provider": "Manual",
        "account_type": "Taxable",
        "total_capital": -1000,
        "max_capital_per_trade_pct": 5,
        "max_total_exposure_pct": 30,
    }
    errors = validate_account_data(data, is_create=True)
    assert any("total_capital" in e for e in errors)


def test_validate_invalid_provider() -> None:
    """Invalid provider is rejected."""
    data = {"provider": "Crypto"}
    errors = validate_account_data(data, is_create=False)
    assert any("provider" in e for e in errors)


def test_validate_invalid_strategies() -> None:
    """Invalid strategies are rejected."""
    data = {"allowed_strategies": ["CSP", "IRON_CONDOR"]}
    errors = validate_account_data(data, is_create=False)
    assert any("strategies" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Store tests (using temp directory)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_accounts_dir(tmp_path: Path):
    """Redirect accounts store to temp directory."""
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()
    with patch.object(account_store, "_get_accounts_dir", return_value=accounts_dir):
        with patch.object(account_store, "_ensure_accounts_dir", return_value=accounts_dir):
            yield accounts_dir


def test_store_create_and_list(tmp_accounts_dir: Path) -> None:
    """Create and list accounts via store."""
    acct = Account(
        account_id="store-test-1",
        provider="Manual",
        account_type="Taxable",
        total_capital=10000.0,
        max_capital_per_trade_pct=5.0,
        max_total_exposure_pct=30.0,
        allowed_strategies=["CSP"],
        is_default=True,
    )
    account_store.create_account(acct)
    result = account_store.list_accounts()
    assert len(result) == 1
    assert result[0].account_id == "store-test-1"


def test_store_default_enforcement(tmp_accounts_dir: Path) -> None:
    """Only one default account at a time."""
    acct1 = Account(
        account_id="a1", provider="Manual", account_type="Taxable",
        total_capital=10000, max_capital_per_trade_pct=5,
        max_total_exposure_pct=30, allowed_strategies=["CSP"],
        is_default=True,
    )
    acct2 = Account(
        account_id="a2", provider="Schwab", account_type="Roth",
        total_capital=20000, max_capital_per_trade_pct=5,
        max_total_exposure_pct=30, allowed_strategies=["CSP"],
        is_default=True,
    )
    account_store.create_account(acct1)
    account_store.create_account(acct2)

    accounts = account_store.list_accounts()
    defaults = [a for a in accounts if a.is_default]
    assert len(defaults) == 1
    assert defaults[0].account_id == "a2"


def test_store_set_default(tmp_accounts_dir: Path) -> None:
    """set_default_account switches default correctly."""
    acct1 = Account(
        account_id="a1", provider="Manual", account_type="Taxable",
        total_capital=10000, max_capital_per_trade_pct=5,
        max_total_exposure_pct=30, allowed_strategies=["CSP"],
        is_default=True,
    )
    acct2 = Account(
        account_id="a2", provider="Manual", account_type="Roth",
        total_capital=20000, max_capital_per_trade_pct=5,
        max_total_exposure_pct=30, allowed_strategies=["CSP"],
    )
    account_store.create_account(acct1)
    account_store.create_account(acct2)

    account_store.set_default_account("a2")
    accounts = account_store.list_accounts()
    defaults = [a for a in accounts if a.is_default]
    assert len(defaults) == 1
    assert defaults[0].account_id == "a2"


# ---------------------------------------------------------------------------
# CSP Sizing tests (CRITICAL)
# ---------------------------------------------------------------------------


def test_csp_sizing_basic() -> None:
    """Basic CSP sizing: 50k capital, 5% max, $500 strike = 5 contracts."""
    acct = Account(
        account_id="test", provider="Manual", account_type="Taxable",
        total_capital=50000.0, max_capital_per_trade_pct=5.0,
        max_total_exposure_pct=30.0, allowed_strategies=["CSP"],
    )
    result = compute_csp_sizing(acct, strike=500.0)
    # max_capital = 50000 * 5% = 2500
    # csp_notional = 500 * 100 = 50000
    # recommended = floor(2500 / 50000) = 0 -> insufficient
    assert result["recommended_contracts"] == 0
    assert result["eligible"] is False
    assert "Insufficient" in result["reason"]


def test_csp_sizing_affordable() -> None:
    """CSP sizing where contracts are affordable."""
    acct = Account(
        account_id="test", provider="Manual", account_type="Taxable",
        total_capital=100000.0, max_capital_per_trade_pct=10.0,
        max_total_exposure_pct=30.0, allowed_strategies=["CSP"],
    )
    result = compute_csp_sizing(acct, strike=50.0)
    # max_capital = 100000 * 10% = 10000
    # csp_notional = 50 * 100 = 5000
    # recommended = floor(10000 / 5000) = 2
    assert result["recommended_contracts"] == 2
    assert result["eligible"] is True
    assert result["capital_required"] == 10000  # 5000 * 2


def test_csp_sizing_single_contract() -> None:
    """CSP sizing where exactly one contract is affordable."""
    acct = Account(
        account_id="test", provider="Manual", account_type="Taxable",
        total_capital=50000.0, max_capital_per_trade_pct=5.0,
        max_total_exposure_pct=30.0, allowed_strategies=["CSP"],
    )
    result = compute_csp_sizing(acct, strike=25.0)
    # max_capital = 50000 * 5% = 2500
    # csp_notional = 25 * 100 = 2500
    # recommended = floor(2500 / 2500) = 1
    assert result["recommended_contracts"] == 1
    assert result["eligible"] is True


def test_csp_sizing_insufficient_capital() -> None:
    """CSP sizing: small account cannot afford any contracts at high strike."""
    acct = Account(
        account_id="test", provider="Manual", account_type="Taxable",
        total_capital=5000.0, max_capital_per_trade_pct=5.0,
        max_total_exposure_pct=30.0, allowed_strategies=["CSP"],
    )
    result = compute_csp_sizing(acct, strike=100.0)
    # max_capital = 5000 * 5% = 250
    # csp_notional = 100 * 100 = 10000
    # recommended = floor(250 / 10000) = 0
    assert result["recommended_contracts"] == 0
    assert result["eligible"] is False
    assert result["verdict_override"] == "HOLD"
