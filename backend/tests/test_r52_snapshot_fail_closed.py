# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52: snapshot store fail-closed — never wipe last-good with zeros."""

from __future__ import annotations

from pathlib import Path

from app.core.broker.models import BrokerBalances, BrokerSnapshot, EquityPosition
from app.core.broker.snapshot_store import (
    init_snapshot_store,
    load_snapshot,
    persist_sync_result,
    reset_snapshot_store_dir,
    save_snapshot,
    set_snapshot_store_dir,
)


def _good_snap(alias: str = "acct_individual") -> BrokerSnapshot:
    return BrokerSnapshot(
        account_alias=alias,
        fetched_at="2026-08-10T12:00:00+00:00",
        balances=BrokerBalances(
            cash=50000.0,
            buying_power=80000.0,
            equity=100000.0,
            market_value=50000.0,
        ),
        equity_positions=[
            EquityPosition(symbol="NVDA", quantity=10.0, average_cost=100.0, market_value=1500.0),
        ],
        option_positions=[],
        completeness="full",
        stale=False,
        errors=[],
    )


def test_failure_keeps_last_good(tmp_path: Path):
    set_snapshot_store_dir(tmp_path)
    try:
        init_snapshot_store()
        good = _good_snap()
        save_snapshot(good)
        loaded = load_snapshot("acct_individual")
        assert loaded is not None
        assert loaded.balances.equity == 100000.0

        meta = persist_sync_result("acct_individual", None, failed=True)
        assert meta.get("has_last_good") is True
        assert meta.get("stale") is True

        after = load_snapshot("acct_individual")
        assert after is not None
        assert after.balances.equity == 100000.0
        assert after.stale is True
    finally:
        reset_snapshot_store_dir()


def test_zero_wipe_rejected(tmp_path: Path):
    set_snapshot_store_dir(tmp_path)
    try:
        init_snapshot_store()
        save_snapshot(_good_snap())
        wipe = BrokerSnapshot(
            account_alias="acct_individual",
            fetched_at="2026-08-10T13:00:00+00:00",
            balances=BrokerBalances(cash=0.0, buying_power=0.0, equity=0.0, market_value=0.0),
            equity_positions=[],
            option_positions=[],
            completeness="empty",
            stale=False,
            errors=[],
        )
        meta = save_snapshot(wipe)
        assert meta.get("saved") is False
        assert meta.get("reason") == "zero_wipe_rejected"
        after = load_snapshot("acct_individual")
        assert after is not None
        assert after.balances.equity == 100000.0
    finally:
        reset_snapshot_store_dir()


def test_good_sync_replaces(tmp_path: Path):
    set_snapshot_store_dir(tmp_path)
    try:
        init_snapshot_store()
        save_snapshot(_good_snap())
        newer = _good_snap()
        newer.fetched_at = "2026-08-10T14:00:00+00:00"
        newer.balances.cash = 51000.0
        meta = persist_sync_result("acct_individual", newer, failed=False)
        assert meta.get("saved") is True
        after = load_snapshot("acct_individual")
        assert after is not None
        assert after.balances.cash == 51000.0
    finally:
        reset_snapshot_store_dir()
