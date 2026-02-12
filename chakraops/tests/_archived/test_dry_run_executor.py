from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from app.execution.dry_run_executor import DryRunExecutionResult, execute_dry_run
from app.execution.execution_plan import ExecutionOrder, ExecutionPlan


def _make_order(
    symbol: str = "AAPL",
    strike: float = 150.0,
    expiry: str = "2026-02-20",
    option_right: str = "PUT",
    limit_price: float = 2.5,
) -> ExecutionOrder:
    """Helper to create a test ExecutionOrder."""
    return ExecutionOrder(
        symbol=symbol,
        action="SELL_TO_OPEN",
        strike=strike,
        expiry=expiry,
        option_right=option_right,
        quantity=1,
        limit_price=limit_price,
    )


def test_dry_run_blocked_case() -> None:
    """Dry-run should pass through blocked plan."""
    plan = ExecutionPlan(
        allowed=False,
        blocked_reason="NO_SELECTED_SIGNALS",
        orders=[],
    )

    result = execute_dry_run(plan)

    assert result.allowed is False
    assert result.blocked_reason == "NO_SELECTED_SIGNALS"
    assert len(result.orders) == 0
    assert result.executed_at is not None
    assert isinstance(result.executed_at, str)


def test_dry_run_allowed_case() -> None:
    """Dry-run should pass through allowed plan with orders."""
    order1 = _make_order("AAPL", 150.0, "2026-02-20", "PUT", 2.5)
    order2 = _make_order("MSFT", 400.0, "2026-02-20", "PUT", 3.0)

    plan = ExecutionPlan(
        allowed=True,
        blocked_reason=None,
        orders=[order1, order2],
    )

    result = execute_dry_run(plan)

    assert result.allowed is True
    assert result.blocked_reason is None
    assert len(result.orders) == 2
    assert result.orders[0].symbol == "AAPL"
    assert result.orders[1].symbol == "MSFT"
    assert result.executed_at is not None


def test_dry_run_deterministic_with_frozen_time() -> None:
    """Dry-run should be deterministic when time is frozen."""
    frozen_time = datetime(2026, 1, 22, 10, 0, 0)
    frozen_iso = frozen_time.isoformat()

    order = _make_order("AAPL", 150.0, "2026-02-20", "PUT", 2.5)
    plan = ExecutionPlan(allowed=True, blocked_reason=None, orders=[order])

    with patch("app.execution.dry_run_executor.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_time
        result1 = execute_dry_run(plan)
        result2 = execute_dry_run(plan)

    assert result1.executed_at == frozen_iso
    assert result2.executed_at == frozen_iso
    assert result1.allowed == result2.allowed
    assert result1.blocked_reason == result2.blocked_reason
    assert len(result1.orders) == len(result2.orders)


def test_dry_run_no_mutation() -> None:
    """Dry-run should not mutate input plan."""
    order = _make_order("AAPL", 150.0, "2026-02-20", "PUT", 2.5)
    plan = ExecutionPlan(allowed=True, blocked_reason=None, orders=[order])

    # Capture original state
    original_allowed = plan.allowed
    original_blocked_reason = plan.blocked_reason
    original_orders_count = len(plan.orders)

    result = execute_dry_run(plan)

    # Verify plan unchanged
    assert plan.allowed == original_allowed
    assert plan.blocked_reason == original_blocked_reason
    assert len(plan.orders) == original_orders_count

    # Verify result is separate
    assert result.allowed == plan.allowed
    assert result.orders is not plan.orders  # Different list objects (by identity)
    assert result.orders == plan.orders  # But same contents


def test_dry_run_json_serializable() -> None:
    """Dry-run result should be JSON-serializable."""
    import json
    from dataclasses import asdict

    order = _make_order("AAPL", 150.0, "2026-02-20", "PUT", 2.5)
    plan = ExecutionPlan(allowed=True, blocked_reason=None, orders=[order])

    result = execute_dry_run(plan)

    # Convert to dict and serialize to JSON
    result_dict = asdict(result)
    json_str = json.dumps(result_dict)

    # Parse back
    parsed = json.loads(json_str)

    assert parsed["allowed"] is True
    assert parsed["blocked_reason"] is None
    assert len(parsed["orders"]) == 1
    assert parsed["orders"][0]["symbol"] == "AAPL"
    assert parsed["orders"][0]["action"] == "SELL_TO_OPEN"
    assert parsed["executed_at"] is not None
    assert isinstance(parsed["executed_at"], str)


def test_dry_run_preserves_order_details() -> None:
    """Dry-run should preserve all order details."""
    order = _make_order(
        symbol="MSFT",
        strike=400.0,
        expiry="2026-03-20",
        option_right="CALL",
        limit_price=3.5,
    )

    plan = ExecutionPlan(allowed=True, blocked_reason=None, orders=[order])

    result = execute_dry_run(plan)

    assert len(result.orders) == 1
    result_order = result.orders[0]
    assert result_order.symbol == "MSFT"
    assert result_order.strike == 400.0
    assert result_order.expiry == "2026-03-20"
    assert result_order.option_right == "CALL"
    assert result_order.quantity == 1
    assert result_order.limit_price == 3.5
    assert result_order.action == "SELL_TO_OPEN"
