from __future__ import annotations

from datetime import date, datetime

from app.execution.execution_gate import ExecutionGateResult
from app.execution.execution_plan import ExecutionOrder, ExecutionPlan, build_execution_plan
from app.signals.decision_snapshot import DecisionSnapshot


def _make_selected_signal_dict(
    symbol: str = "AAPL",
    strike: float = 150.0,
    expiry: date | str | None = None,
    option_right: str = "PUT",
    mid: float | None = 2.5,
    bid: float | None = 2.4,
) -> dict:
    """Helper to create a selected signal dict structure."""
    if expiry is None:
        expiry = date(2026, 2, 20)
    if isinstance(expiry, date):
        expiry_str = expiry.isoformat()
    else:
        expiry_str = expiry

    return {
        "scored": {
            "candidate": {
                "symbol": symbol,
                "signal_type": "CSP" if option_right == "PUT" else "CC",
                "as_of": datetime(2026, 1, 22, 10, 0, 0).isoformat(),
                "underlying_price": 150.0,
                "expiry": expiry_str,
                "strike": strike,
                "option_right": option_right,
                "bid": bid,
                "ask": 2.6 if bid else None,
                "mid": mid,
                "volume": 1000,
                "open_interest": 5000,
            },
            "score": {"total": 0.85, "components": []},
            "rank": 1,
        },
        "selection_reason": "SELECTED_BY_POLICY",
    }


def test_plan_blocked_when_gate_blocks() -> None:
    """Plan should be blocked when gate result blocks execution."""
    snapshot = DecisionSnapshot(
        as_of=datetime.now().isoformat(),
        universe_id_or_hash="test",
        stats={"symbols_evaluated": 1},
        candidates=[],
        scored_candidates=None,
        selected_signals=None,
        explanations=None,
    )

    gate_result = ExecutionGateResult(allowed=False, reasons=["NO_SELECTED_SIGNALS"])

    plan = build_execution_plan(snapshot, gate_result)

    assert plan.allowed is False
    assert plan.blocked_reason == "NO_SELECTED_SIGNALS"
    assert len(plan.orders) == 0


def test_plan_allowed_builds_orders() -> None:
    """Plan should build orders when gate allows execution."""
    selected1 = _make_selected_signal_dict("AAPL", 150.0, date(2026, 2, 20), "PUT", mid=2.5)
    selected2 = _make_selected_signal_dict("MSFT", 400.0, date(2026, 2, 20), "PUT", mid=3.0)

    snapshot = DecisionSnapshot(
        as_of=datetime.now().isoformat(),
        universe_id_or_hash="test",
        stats={"symbols_evaluated": 2},
        candidates=[],
        scored_candidates=None,
        selected_signals=[selected1, selected2],
        explanations=None,
    )

    gate_result = ExecutionGateResult(allowed=True, reasons=[])

    plan = build_execution_plan(snapshot, gate_result)

    assert plan.allowed is True
    assert plan.blocked_reason is None
    assert len(plan.orders) == 2

    # Verify first order
    order1 = plan.orders[0]
    assert order1.symbol == "AAPL"
    assert order1.action == "SELL_TO_OPEN"
    assert order1.strike == 150.0
    assert order1.expiry == "2026-02-20"
    assert order1.option_right == "PUT"
    assert order1.quantity == 1
    assert order1.limit_price == 2.5

    # Verify second order
    order2 = plan.orders[1]
    assert order2.symbol == "MSFT"
    assert order2.strike == 400.0
    assert order2.limit_price == 3.0


def test_plan_uses_bid_when_mid_missing() -> None:
    """Plan should use bid as fallback when mid is None."""
    selected = _make_selected_signal_dict("AAPL", 150.0, date(2026, 2, 20), "PUT", mid=None, bid=2.4)

    snapshot = DecisionSnapshot(
        as_of=datetime.now().isoformat(),
        universe_id_or_hash="test",
        stats={"symbols_evaluated": 1},
        candidates=[],
        scored_candidates=None,
        selected_signals=[selected],
        explanations=None,
    )

    gate_result = ExecutionGateResult(allowed=True, reasons=[])

    plan = build_execution_plan(snapshot, gate_result)

    assert plan.allowed is True
    assert len(plan.orders) == 1
    assert plan.orders[0].limit_price == 2.4


def test_plan_preserves_ordering() -> None:
    """Plan should preserve the ordering of selected signals."""
    selected1 = _make_selected_signal_dict("AAPL", 150.0, date(2026, 2, 20), "PUT", mid=2.5)
    selected2 = _make_selected_signal_dict("MSFT", 400.0, date(2026, 2, 20), "PUT", mid=3.0)
    selected3 = _make_selected_signal_dict("GOOGL", 200.0, date(2026, 2, 20), "CALL", mid=1.5)

    snapshot = DecisionSnapshot(
        as_of=datetime.now().isoformat(),
        universe_id_or_hash="test",
        stats={"symbols_evaluated": 3},
        candidates=[],
        scored_candidates=None,
        selected_signals=[selected1, selected2, selected3],
        explanations=None,
    )

    gate_result = ExecutionGateResult(allowed=True, reasons=[])

    plan = build_execution_plan(snapshot, gate_result)

    assert len(plan.orders) == 3
    assert plan.orders[0].symbol == "AAPL"
    assert plan.orders[1].symbol == "MSFT"
    assert plan.orders[2].symbol == "GOOGL"


def test_plan_deterministic() -> None:
    """Plan building should be deterministic."""
    selected = _make_selected_signal_dict("AAPL", 150.0, date(2026, 2, 20), "PUT", mid=2.5)

    snapshot = DecisionSnapshot(
        as_of=datetime.now().isoformat(),
        universe_id_or_hash="test",
        stats={"symbols_evaluated": 1},
        candidates=[],
        scored_candidates=None,
        selected_signals=[selected],
        explanations=None,
    )

    gate_result = ExecutionGateResult(allowed=True, reasons=[])

    plan1 = build_execution_plan(snapshot, gate_result)
    plan2 = build_execution_plan(snapshot, gate_result)

    assert plan1.allowed == plan2.allowed
    assert plan1.blocked_reason == plan2.blocked_reason
    assert len(plan1.orders) == len(plan2.orders)
    assert [o.symbol for o in plan1.orders] == [o.symbol for o in plan2.orders]
    assert [o.strike for o in plan1.orders] == [o.strike for o in plan2.orders]


def test_plan_no_mutation() -> None:
    """Plan building should not mutate input snapshot or gate_result."""
    selected = _make_selected_signal_dict("AAPL", 150.0, date(2026, 2, 20), "PUT", mid=2.5)

    snapshot = DecisionSnapshot(
        as_of=datetime.now().isoformat(),
        universe_id_or_hash="test",
        stats={"symbols_evaluated": 1},
        candidates=[],
        scored_candidates=None,
        selected_signals=[selected],
        explanations=None,
    )

    gate_result = ExecutionGateResult(allowed=True, reasons=[])

    # Capture original state
    original_selected_count = len(snapshot.selected_signals) if snapshot.selected_signals else 0
    original_reasons = list(gate_result.reasons)

    plan = build_execution_plan(snapshot, gate_result)

    # Verify inputs unchanged
    assert len(snapshot.selected_signals) == original_selected_count if snapshot.selected_signals else True
    assert gate_result.reasons == original_reasons
    assert plan.allowed is True
