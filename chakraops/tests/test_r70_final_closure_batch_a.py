# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 Final Closure Batch A — capital authority, account bridge, historicalize safety."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest

from app.core.broker.models import BrokerBalances, BrokerSnapshot, EquityPosition
from app.core.portfolio.capital_authority_r70 import (
    SOURCE_BROKER,
    STATE_FRESH,
    STATE_STALE,
    get_capital_snapshot,
    get_taxable_csp_capital,
    broker_share_quantities,
)
from app.core.portfolio.guardrails_r259 import build_guardrails_snapshot, get_guardrails_metrics_and_status
from app.core.portfolio.live_position_lenses_r70 import historicalize_orphan_unified_live_shares


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _snap(
    *,
    cash: float = 64000.0,
    buying_power: float = 128000.0,
    equity: float = 215000.0,
    stale: bool = False,
    age_minutes: float = 5.0,
    equities: Optional[List[EquityPosition]] = None,
    completeness: str = "complete",
) -> BrokerSnapshot:
    fetched = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    if equities is None:
        equities = [
            EquityPosition(symbol="NVDA", quantity=300.0, average_cost=157.0),
            EquityPosition(symbol="AMZN", quantity=25.0, average_cost=216.0),
            EquityPosition(symbol="SMCI", quantity=425.0, average_cost=30.0),
        ]
    return BrokerSnapshot(
        account_alias="acct_individual",
        fetched_at=fetched.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        balances=BrokerBalances(cash=cash, buying_power=buying_power, equity=equity),
        equity_positions=list(equities),
        option_positions=[],
        freshness="stale" if stale else "fresh",
        completeness=completeness,
        stale=stale,
        source="robinhood_mcp",
    )


def _patch_broker(monkeypatch: pytest.MonkeyPatch, snap: BrokerSnapshot, *, ready: bool = True) -> None:
    monkeypatch.setattr("app.core.broker.snapshot_store.load_snapshot", lambda _a: snap)
    monkeypatch.setattr(
        "app.core.broker.status.robinhood_mcp_read_only_status",
        lambda **_kw: {
            "status": "READ_ONLY_AVAILABLE" if ready else "UNAUTHENTICATED",
            "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": ready,
        },
    )


def test_fresh_broker_cash_drives_sizing(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap(cash=64000.0, buying_power=200000.0, equity=215000.0)
    _patch_broker(monkeypatch, snap)
    monkeypatch.setattr(
        "app.core.accounts.holdings_db.get_account_summary",
        lambda: {"cash": 0.0, "total_capital": 0.0, "buying_power": 0.0},
    )
    cap = get_capital_snapshot("acct_individual")
    assert cap["state"] == STATE_FRESH
    assert cap["source"] == SOURCE_BROKER
    assert cap["cash"] == 64000.0
    assert cap["buying_power"] == 200000.0
    assert cap["cash"] != cap["buying_power"]
    assert cap["sizing_blocked"] is False

    gsnap = build_guardrails_snapshot()
    assert gsnap["cash"] == 64000.0
    metrics = get_guardrails_metrics_and_status(gsnap)
    assert metrics["metrics"]["available_budget_usd"] > 0
    assert metrics["metrics"]["capital_source"] == SOURCE_BROKER


def test_roth_not_pooled_into_taxable_csp(monkeypatch: pytest.MonkeyPatch) -> None:
    ind = _snap(cash=10000.0)
    roth = _snap(cash=50000.0)
    roth.account_alias = "acct_ira_roth"

    def _load(alias: str):
        return roth if alias == "acct_ira_roth" else ind

    monkeypatch.setattr("app.core.broker.snapshot_store.load_snapshot", _load)
    monkeypatch.setattr(
        "app.core.broker.status.robinhood_mcp_read_only_status",
        lambda **_kw: {"status": "READ_ONLY_AVAILABLE", "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True},
    )
    taxable = get_taxable_csp_capital()
    assert taxable["account_alias"] == "acct_individual"
    assert taxable["cash"] == 10000.0
    assert taxable["pooled_from_roth"] is False
    roth_cap = get_capital_snapshot("acct_ira_roth", allow_manual_fallback=False)
    assert roth_cap["taxable_csp_eligible"] is False
    assert roth_cap["csp_cash_eligible"] == 0.0


def test_stale_broker_blocks_sizing(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap(stale=True, age_minutes=5.0)
    _patch_broker(monkeypatch, snap)
    cap = get_capital_snapshot("acct_individual")
    assert cap["state"] == STATE_STALE
    assert cap["sizing_blocked"] is True
    metrics = get_guardrails_metrics_and_status()
    assert metrics["metrics"]["available_budget_usd"] == 0.0
    assert metrics["metrics"]["csp_cash_available_usd"] == 0.0


def test_age_exceeded_blocks_sizing(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap(age_minutes=200.0)
    _patch_broker(monkeypatch, snap)
    cap = get_capital_snapshot("acct_individual")
    assert cap["state"] == STATE_STALE
    assert cap["sizing_blocked"] is True


def test_broker_zero_cash_stays_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap(cash=0.0, buying_power=0.0, equity=100.0, equities=[])
    _patch_broker(monkeypatch, snap)
    cap = get_capital_snapshot("acct_individual")
    assert cap["cash"] == 0.0
    assert cap["state"] == STATE_FRESH


def test_cc_eligibility_uses_broker_shares(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap(equities=[EquityPosition(symbol="NVDA", quantity=300.0)])
    _patch_broker(monkeypatch, snap)
    shares = broker_share_quantities("acct_individual")
    assert shares.get("NVDA") == 300
    from app.core.accounts.holdings_db import get_holdings_for_evaluation

    monkeypatch.setattr(
        "app.core.accounts.holdings_db.get_total_shares_for_evaluation",
        lambda _aid: {"SPY": 100},
    )
    out = get_holdings_for_evaluation()
    assert out.get("NVDA") == 300
    assert "SPY" not in out  # manual SPY must not create live CC while broker fresh


def test_historicalize_defaults_dry_run_and_protects_broker_holding(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    snap = _snap(equities=[EquityPosition(symbol="NVDA", quantity=300.0)])
    _patch_broker(monkeypatch, snap)

    # Default dry_run True
    out = historicalize_orphan_unified_live_shares()
    assert out["dry_run"] is True
    assert out.get("refused") is False or "candidates" in out

    # Destructive without confirm refused
    out2 = historicalize_orphan_unified_live_shares(dry_run=False, confirm=False)
    assert out2.get("refused") is True
    assert out2["orphan_live_shares_moved"] == 0

    # Stale broker refused
    stale = _snap(stale=True)
    _patch_broker(monkeypatch, stale)
    out3 = historicalize_orphan_unified_live_shares(dry_run=False, confirm=True)
    assert out3.get("refused") is True
    assert out3["orphan_live_shares_moved"] == 0


def test_account_bridge_creates_aliases(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from app.core.accounts import store as accounts_store
    from app.core.accounts.account_bridge_r70 import ensure_broker_accounts_bridged, list_accounts_enriched

    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    accounts_store._save_all([])  # type: ignore[attr-defined]
    snap = _snap()
    _patch_broker(monkeypatch, snap)
    result = ensure_broker_accounts_bridged()
    assert "acct_individual" in (result["created"] + [result.get("default_account_id")])
    enriched = list_accounts_enriched()
    ids = {a["account_id"] for a in enriched}
    assert "acct_individual" in ids
    assert "acct_ira_roth" in ids
    assert "acct_agentic" in ids
    default = next(a for a in enriched if a.get("is_default"))
    assert default["account_id"] == "acct_individual"
    agentic = next(a for a in enriched if a["account_id"] == "acct_agentic")
    assert agentic.get("execution_eligible") is False
