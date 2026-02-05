#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Smoke test for position state machine transitions."""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
script_dir = Path(__file__).parent
repo_root = script_dir.parent
sys.path.insert(0, str(repo_root))

from app.core.models.position import Position
from app.core.state_machine.position_state_machine import (
    PositionState,
    transition_position,
    InvalidTransitionError,
)


def main() -> int:
    """Test state machine transitions with a sample position."""
    print("=" * 60, file=sys.stderr)
    print("ChakraOps State Machine Smoke Test", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    # Create a sample CSP position starting in OPEN state
    print("\n1. Creating sample position (AAPL CSP)...", file=sys.stderr)
    position = Position(
        id="smoke-test-001",
        symbol="AAPL",
        position_type="CSP",
        strike=150.0,
        expiry="2026-03-21",
        contracts=1,
        premium_collected=300.0,
        entry_date=datetime.now(timezone.utc).isoformat(),
        status="OPEN",
        state="OPEN",
        state_history=[],
    )
    print(f"   ✓ Position created: {position.symbol} {position.position_type} @ ${position.strike}", file=sys.stderr)
    print(f"   Initial state: {position.state}", file=sys.stderr)
    
    # Define transition sequence
    transitions = [
        (PositionState.HOLD, "Price above EMA200, holding position", "risk_engine"),
        (PositionState.ROLL_CANDIDATE, "Premium collected 75%, candidate for roll", "risk_engine"),
        (PositionState.ROLLING, "Initiating roll to new strike/expiry", "user"),
        (PositionState.OPEN, "Roll completed, new position opened", "system"),
        (PositionState.CLOSED, "Position closed at profit target", "user"),
    ]
    
    print(f"\n2. Executing {len(transitions)} state transitions...", file=sys.stderr)
    
    try:
        for i, (target_state, reason, source) in enumerate(transitions, start=1):
            current_state = position.state
            print(f"\n   Transition {i}: {current_state} -> {target_state.value}", file=sys.stderr)
            print(f"   Reason: {reason}", file=sys.stderr)
            print(f"   Source: {source}", file=sys.stderr)
            
            position = transition_position(
                position,
                target_state,
                reason,
                source=source,
            )
            
            print(f"   ✓ Transition successful", file=sys.stderr)
            print(f"   New state: {position.state}", file=sys.stderr)
            print(f"   History entries: {len(position.state_history)}", file=sys.stderr)
    
    except InvalidTransitionError as e:
        print(f"\n✗ ERROR: Invalid transition detected!", file=sys.stderr)
        print(f"   {e}", file=sys.stderr)
        return 1
    
    except Exception as e:
        print(f"\n✗ ERROR: Unexpected error during transition!", file=sys.stderr)
        print(f"   {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    # Verify final state
    print(f"\n3. Verifying final state...", file=sys.stderr)
    if position.state != "CLOSED":
        print(f"✗ ERROR: Expected final state CLOSED, got {position.state}", file=sys.stderr)
        return 1
    
    print(f"   ✓ Final state: {position.state}", file=sys.stderr)
    
    # Verify history count
    expected_history_count = len(transitions)
    actual_history_count = len(position.state_history)
    
    print(f"\n4. Verifying state history...", file=sys.stderr)
    if actual_history_count != expected_history_count:
        print(f"✗ ERROR: Expected {expected_history_count} history entries, got {actual_history_count}", file=sys.stderr)
        return 1
    
    print(f"   ✓ History entries: {actual_history_count}", file=sys.stderr)
    
    # Print history summary
    print(f"\n5. State History Summary:", file=sys.stderr)
    print(f"   {'From':<15} {'To':<15} {'Source':<15} {'Reason'}", file=sys.stderr)
    print(f"   {'-'*15} {'-'*15} {'-'*15} {'-'*40}", file=sys.stderr)
    for event in position.state_history:
        from_state = event.get('from_state', 'N/A') if isinstance(event, dict) else getattr(event, 'from_state', 'N/A')
        to_state = event.get('to_state', 'N/A') if isinstance(event, dict) else getattr(event, 'to_state', 'N/A')
        source = event.get('source', 'N/A') if isinstance(event, dict) else getattr(event, 'source', 'N/A')
        reason = event.get('reason', 'N/A') if isinstance(event, dict) else getattr(event, 'reason', 'N/A')
        reason_short = reason[:37] + "..." if len(reason) > 40 else reason
        print(f"   {from_state:<15} {to_state:<15} {source:<15} {reason_short}", file=sys.stderr)
    
    # Test invalid transition (should fail)
    print(f"\n6. Testing invalid transition (CLOSED -> OPEN)...", file=sys.stderr)
    try:
        transition_position(
            position,
            PositionState.OPEN,
            "Attempting invalid transition",
            source="test",
        )
        print(f"✗ ERROR: Invalid transition should have raised exception!", file=sys.stderr)
        return 1
    except InvalidTransitionError:
        print(f"   ✓ Invalid transition correctly rejected", file=sys.stderr)
    except Exception as e:
        print(f"✗ ERROR: Unexpected exception type: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    
    print(f"\n{'='*60}", file=sys.stderr)
    print("✓ All state machine tests passed!", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
