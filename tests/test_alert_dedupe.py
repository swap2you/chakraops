# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for alert deduplication engine."""

import pytest
from datetime import datetime, timedelta

from app.core.engine.alert_dedupe import AlertDedupeEngine
from app.core.engine.actions import (
    ActionType,
    Urgency,
    ActionDecision,
    RollPlan,
)


class TestAlertDedupeEngine:
    """Test alert deduplication and cooldown logic."""
    
    def test_first_notification_always_allowed(self):
        """Test that first notification for a symbol is always allowed."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["No action required"],
            next_steps=[],
            computed_at=datetime.now(),
        )
        
        assert engine.should_notify("AAPL", decision) is True
    
    def test_low_urgency_duplicate_suppressed(self):
        """Test that duplicate LOW urgency notifications are suppressed."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["No action required"],
            next_steps=[],
            computed_at=datetime.now(),
        )
        
        # First notification allowed
        assert engine.should_notify("AAPL", decision) is True
        engine.record_notification("AAPL", decision)
        
        # Duplicate notification suppressed
        assert engine.should_notify("AAPL", decision) is False
    
    def test_medium_urgency_duplicate_suppressed(self):
        """Test that duplicate MEDIUM urgency notifications are suppressed."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.CLOSE,
            urgency=Urgency.MEDIUM,
            reasons=["Premium >= 65% captured"],
            next_steps=["Consider closing position"],
            computed_at=datetime.now(),
        )
        
        # First notification allowed
        assert engine.should_notify("MSFT", decision) is True
        engine.record_notification("MSFT", decision)
        
        # Duplicate notification suppressed
        assert engine.should_notify("MSFT", decision) is False
    
    def test_high_urgency_allowed_within_cooldown_first_time(self):
        """Test that HIGH urgency notification is allowed on first occurrence."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
        )
        
        assert engine.should_notify("NVDA", decision) is True
    
    def test_high_urgency_suppressed_within_cooldown(self):
        """Test that HIGH urgency duplicate is suppressed within cooldown period."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
        )
        
        # First notification
        assert engine.should_notify("NVDA", decision) is True
        engine.record_notification("NVDA", decision)
        
        # Immediately after (within cooldown) - should be suppressed
        assert engine.should_notify("NVDA", decision, cooldown_minutes=60) is False
    
    def test_high_urgency_allowed_after_cooldown(self):
        """Test that HIGH urgency notification is allowed after cooldown period."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.ALERT,
            urgency=Urgency.HIGH,
            reasons=["RISK_OFF regime detected"],
            next_steps=["Reduce exposure"],
            computed_at=datetime.now(),
        )
        
        # First notification
        assert engine.should_notify("SPY", decision) is True
        engine.record_notification("SPY", decision)
        
        # Manually set last_sent_at to 61 minutes ago
        fingerprint = engine._compute_fingerprint("SPY", decision)
        engine._decision_cache["SPY"] = (
            fingerprint,
            datetime.now() - timedelta(minutes=61)
        )
        
        # Should be allowed after cooldown
        assert engine.should_notify("SPY", decision, cooldown_minutes=60) is True
    
    def test_different_decisions_allowed(self):
        """Test that different decisions for same symbol are allowed."""
        engine = AlertDedupeEngine()
        
        decision1 = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["No action required"],
            next_steps=[],
            computed_at=datetime.now(),
        )
        
        decision2 = ActionDecision(
            action=ActionType.CLOSE,
            urgency=Urgency.MEDIUM,
            reasons=["Premium >= 65% captured"],
            next_steps=["Consider closing"],
            computed_at=datetime.now(),
        )
        
        # First decision
        assert engine.should_notify("AAPL", decision1) is True
        engine.record_notification("AAPL", decision1)
        
        # Different decision should be allowed
        assert engine.should_notify("AAPL", decision2) is True
    
    def test_different_symbols_independent(self):
        """Test that deduplication is per-symbol."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["No action required"],
            next_steps=[],
            computed_at=datetime.now(),
        )
        
        # First symbol
        assert engine.should_notify("AAPL", decision) is True
        engine.record_notification("AAPL", decision)
        
        # Same decision for different symbol should be allowed
        assert engine.should_notify("MSFT", decision) is True
    
    def test_fingerprint_includes_roll_plan(self):
        """Test that roll plan is included in fingerprint calculation."""
        engine = AlertDedupeEngine()
        
        roll_plan = RollPlan(
            roll_type="defensive",
            suggested_expiry=datetime.now().date() + timedelta(days=35),
            suggested_strike=200.0,
            notes=["Defensive roll"],
        )
        
        decision1 = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
            roll_plan=roll_plan,
        )
        
        # Different roll plan should create different fingerprint
        roll_plan2 = RollPlan(
            roll_type="out",
            suggested_expiry=datetime.now().date() + timedelta(days=40),
            suggested_strike=210.0,
            notes=["Out roll"],
        )
        
        decision2 = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
            roll_plan=roll_plan2,
        )
        
        # First decision
        assert engine.should_notify("AAPL", decision1) is True
        engine.record_notification("AAPL", decision1)
        
        # Different roll plan should be allowed
        assert engine.should_notify("AAPL", decision2) is True
    
    def test_record_notification_updates_cache(self):
        """Test that record_notification updates the cache."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["No action required"],
            next_steps=[],
            computed_at=datetime.now(),
        )
        
        # Record notification
        engine.record_notification("AAPL", decision)
        
        # Should have cached entry
        last_sent = engine.get_last_sent_at("AAPL")
        assert last_sent is not None
        assert isinstance(last_sent, datetime)
        
        # Duplicate should be suppressed
        assert engine.should_notify("AAPL", decision) is False
    
    def test_get_last_sent_at_nonexistent_symbol(self):
        """Test that get_last_sent_at returns None for unknown symbol."""
        engine = AlertDedupeEngine()
        
        assert engine.get_last_sent_at("UNKNOWN") is None
    
    def test_clear_cache(self):
        """Test that clear_cache removes all entries."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["No action required"],
            next_steps=[],
            computed_at=datetime.now(),
        )
        
        # Record notification
        engine.record_notification("AAPL", decision)
        assert engine.get_last_sent_at("AAPL") is not None
        
        # Clear cache
        engine.clear_cache()
        
        # Should be empty
        assert engine.get_last_sent_at("AAPL") is None
        assert engine.should_notify("AAPL", decision) is True
    
    def test_fingerprint_stable_across_reasons_order(self):
        """Test that fingerprint is stable regardless of reasons order."""
        engine = AlertDedupeEngine()
        
        decision1 = ActionDecision(
            action=ActionType.ALERT,
            urgency=Urgency.HIGH,
            reasons=["Reason A", "Reason B"],
            next_steps=["Step 1"],
            computed_at=datetime.now(),
        )
        
        decision2 = ActionDecision(
            action=ActionType.ALERT,
            urgency=Urgency.HIGH,
            reasons=["Reason B", "Reason A"],  # Different order
            next_steps=["Step 1"],
            computed_at=datetime.now(),
        )
        
        # Fingerprints should be the same (reasons are sorted)
        fp1 = engine._compute_fingerprint("AAPL", decision1)
        fp2 = engine._compute_fingerprint("AAPL", decision2)
        
        assert fp1 == fp2
    
    def test_custom_cooldown_period(self):
        """Test that custom cooldown period is respected."""
        engine = AlertDedupeEngine()
        
        decision = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
        )
        
        # First notification
        assert engine.should_notify("AAPL", decision, cooldown_minutes=30) is True
        engine.record_notification("AAPL", decision)
        
        # Set last_sent_at to 31 minutes ago (past 30-minute cooldown)
        fingerprint = engine._compute_fingerprint("AAPL", decision)
        engine._decision_cache["AAPL"] = (
            fingerprint,
            datetime.now() - timedelta(minutes=31)
        )
        
        # Should be allowed with 30-minute cooldown
        assert engine.should_notify("AAPL", decision, cooldown_minutes=30) is True
        
        # But still suppressed with 60-minute cooldown
        assert engine.should_notify("AAPL", decision, cooldown_minutes=60) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
