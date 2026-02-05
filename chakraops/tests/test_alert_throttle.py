# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Alert Throttling & Signal De-duplication."""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.alert_throttle import (
    AlertSignature,
    should_emit_alert,
    clear_cache,
    get_cache_size,
)


class TestAlertSuppression:
    """Test alert suppression within cooldown period."""
    
    def test_suppress_duplicate_alert_within_cooldown(self):
        """Test that duplicate alerts are suppressed within cooldown."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert should be emitted
        assert should_emit_alert(signature, now=now, cooldown_minutes=30) is True
        
        # Second alert within cooldown should be suppressed
        assert should_emit_alert(signature, now=now + timedelta(minutes=15), cooldown_minutes=30) is False
    
    def test_suppress_multiple_duplicates(self):
        """Test that multiple duplicates are suppressed."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="MSFT",
            action="ROLL",
            confidence_level="MEDIUM",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert
        assert should_emit_alert(signature, now=now, cooldown_minutes=30) is True
        
        # Second alert (suppressed)
        assert should_emit_alert(signature, now=now + timedelta(minutes=10), cooldown_minutes=30) is False
        
        # Third alert (suppressed)
        assert should_emit_alert(signature, now=now + timedelta(minutes=20), cooldown_minutes=30) is False
    
    def test_suppress_at_cooldown_boundary(self):
        """Test that alerts are suppressed at cooldown boundary (just before expiry)."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="SPY",
            action="ALERT",
            confidence_level="HIGH",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert
        assert should_emit_alert(signature, now=now, cooldown_minutes=30) is True
        
        # Alert at 29 minutes 59 seconds (just before expiry) should be suppressed
        assert should_emit_alert(
            signature,
            now=now + timedelta(minutes=29, seconds=59),
            cooldown_minutes=30
        ) is False


class TestAlertEmission:
    """Test alert emission scenarios."""
    
    def test_emit_first_alert(self):
        """Test that first alert is always emitted."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        assert should_emit_alert(signature, cooldown_minutes=30) is True
    
    def test_emit_after_cooldown_expires(self):
        """Test that alert is emitted after cooldown expires."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="MSFT",
            action="ROLL",
            confidence_level="MEDIUM",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert
        assert should_emit_alert(signature, now=now, cooldown_minutes=30) is True
        
        # Alert after cooldown expires
        assert should_emit_alert(
            signature,
            now=now + timedelta(minutes=30, seconds=1),
            cooldown_minutes=30
        ) is True
    
    def test_emit_at_exact_cooldown_expiry(self):
        """Test that alert is emitted at exact cooldown expiry."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="NVDA",
            action="ALERT",
            confidence_level="LOW",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert
        assert should_emit_alert(signature, now=now, cooldown_minutes=30) is True
        
        # Alert at exact cooldown expiry
        assert should_emit_alert(
            signature,
            now=now + timedelta(minutes=30),
            cooldown_minutes=30
        ) is True


class TestSignatureChange:
    """Test that signature changes allow alert emission."""
    
    def test_emit_when_symbol_changes(self):
        """Test that alert is emitted when symbol changes."""
        clear_cache()
        
        signature1 = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        signature2 = AlertSignature(
            symbol="MSFT",  # Different symbol
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert for AAPL
        assert should_emit_alert(signature1, now=now, cooldown_minutes=30) is True
        
        # Alert for MSFT (different symbol) should be emitted even within cooldown
        assert should_emit_alert(signature2, now=now + timedelta(minutes=5), cooldown_minutes=30) is True
    
    def test_emit_when_action_changes(self):
        """Test that alert is emitted when action changes."""
        clear_cache()
        
        signature1 = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        signature2 = AlertSignature(
            symbol="AAPL",
            action="ROLL",  # Different action
            confidence_level="HIGH",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert for CLOSE
        assert should_emit_alert(signature1, now=now, cooldown_minutes=30) is True
        
        # Alert for ROLL (different action) should be emitted even within cooldown
        assert should_emit_alert(signature2, now=now + timedelta(minutes=5), cooldown_minutes=30) is True
    
    def test_emit_when_confidence_changes(self):
        """Test that alert is emitted when confidence level changes."""
        clear_cache()
        
        signature1 = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        signature2 = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="MEDIUM",  # Different confidence
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert with HIGH confidence
        assert should_emit_alert(signature1, now=now, cooldown_minutes=30) is True
        
        # Alert with MEDIUM confidence (different confidence) should be emitted
        assert should_emit_alert(signature2, now=now + timedelta(minutes=5), cooldown_minutes=30) is True
    
    def test_suppress_when_all_fields_match(self):
        """Test that alerts are suppressed when all signature fields match."""
        clear_cache()
        
        signature1 = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        signature2 = AlertSignature(
            symbol="AAPL",  # Same
            action="CLOSE",  # Same
            confidence_level="HIGH",  # Same
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert
        assert should_emit_alert(signature1, now=now, cooldown_minutes=30) is True
        
        # Second alert with identical signature should be suppressed
        assert should_emit_alert(signature2, now=now + timedelta(minutes=5), cooldown_minutes=30) is False


class TestCooldownVariations:
    """Test different cooldown periods."""
    
    def test_custom_cooldown_5_minutes(self):
        """Test with custom 5-minute cooldown."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="SPY",
            action="ALERT",
            confidence_level="HIGH",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert
        assert should_emit_alert(signature, now=now, cooldown_minutes=5) is True
        
        # Suppressed at 4 minutes
        assert should_emit_alert(signature, now=now + timedelta(minutes=4), cooldown_minutes=5) is False
        
        # Emitted at 6 minutes
        assert should_emit_alert(signature, now=now + timedelta(minutes=6), cooldown_minutes=5) is True
    
    def test_custom_cooldown_60_minutes(self):
        """Test with custom 60-minute cooldown."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="NVDA",
            action="ROLL",
            confidence_level="MEDIUM",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert
        assert should_emit_alert(signature, now=now, cooldown_minutes=60) is True
        
        # Suppressed at 45 minutes
        assert should_emit_alert(signature, now=now + timedelta(minutes=45), cooldown_minutes=60) is False
        
        # Emitted at 61 minutes
        assert should_emit_alert(signature, now=now + timedelta(minutes=61), cooldown_minutes=60) is True
    
    def test_zero_cooldown_allows_all(self):
        """Test that zero cooldown allows all alerts."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        now = datetime.now(timezone.utc)
        
        # All alerts should be emitted with zero cooldown
        assert should_emit_alert(signature, now=now, cooldown_minutes=0) is True
        assert should_emit_alert(signature, now=now + timedelta(seconds=1), cooldown_minutes=0) is True
        assert should_emit_alert(signature, now=now + timedelta(seconds=2), cooldown_minutes=0) is True


class TestAlertSignatureStructure:
    """Test AlertSignature dataclass structure."""
    
    def test_alert_signature_has_all_required_fields(self):
        """Test that AlertSignature has all required fields."""
        signature = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        assert hasattr(signature, "symbol")
        assert hasattr(signature, "action")
        assert hasattr(signature, "confidence_level")
        
        assert signature.symbol == "AAPL"
        assert signature.action == "CLOSE"
        assert signature.confidence_level == "HIGH"
    
    def test_alert_signature_is_frozen(self):
        """Test that AlertSignature is frozen (immutable)."""
        signature = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        # Should raise AttributeError when trying to modify
        with pytest.raises(AttributeError):
            signature.symbol = "MSFT"
    
    def test_alert_signature_string_representation(self):
        """Test that AlertSignature has proper string representation."""
        signature = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        signature_str = str(signature)
        assert "AAPL" in signature_str
        assert "CLOSE" in signature_str
        assert "HIGH" in signature_str


class TestCacheManagement:
    """Test cache management functions."""
    
    def test_cache_size_tracks_signatures(self):
        """Test that cache size tracks number of unique signatures."""
        clear_cache()
        
        assert get_cache_size() == 0
        
        signature1 = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        signature2 = AlertSignature(
            symbol="MSFT",
            action="ROLL",
            confidence_level="MEDIUM",
        )
        
        now = datetime.now(timezone.utc)
        
        # Add first signature
        should_emit_alert(signature1, now=now, cooldown_minutes=30)
        assert get_cache_size() == 1
        
        # Add second signature
        should_emit_alert(signature2, now=now, cooldown_minutes=30)
        assert get_cache_size() == 2
        
        # Same signature doesn't increase cache size
        should_emit_alert(signature1, now=now + timedelta(minutes=5), cooldown_minutes=30)
        assert get_cache_size() == 2
    
    def test_clear_cache_removes_all_signatures(self):
        """Test that clear_cache removes all signatures."""
        clear_cache()
        
        signature1 = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        signature2 = AlertSignature(
            symbol="MSFT",
            action="ROLL",
            confidence_level="MEDIUM",
        )
        
        now = datetime.now(timezone.utc)
        
        # Add signatures
        should_emit_alert(signature1, now=now, cooldown_minutes=30)
        should_emit_alert(signature2, now=now, cooldown_minutes=30)
        assert get_cache_size() == 2
        
        # Clear cache
        clear_cache()
        assert get_cache_size() == 0
        
        # After clearing, first alert should be emitted again
        assert should_emit_alert(signature1, now=now + timedelta(minutes=1), cooldown_minutes=30) is True


class TestDeterministicOutput:
    """Test that alert throttling is deterministic."""
    
    def test_same_inputs_produce_same_output(self):
        """Test that same inputs produce same output."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="AAPL",
            action="CLOSE",
            confidence_level="HIGH",
        )
        
        now = datetime.now(timezone.utc)
        
        # First call
        result1 = should_emit_alert(signature, now=now, cooldown_minutes=30)
        
        # Clear and repeat
        clear_cache()
        result2 = should_emit_alert(signature, now=now, cooldown_minutes=30)
        
        assert result1 == result2
    
    def test_deterministic_with_time_progression(self):
        """Test deterministic behavior with time progression."""
        clear_cache()
        
        signature = AlertSignature(
            symbol="MSFT",
            action="ROLL",
            confidence_level="MEDIUM",
        )
        
        now = datetime.now(timezone.utc)
        
        # First alert
        assert should_emit_alert(signature, now=now, cooldown_minutes=30) is True
        
        # At 15 minutes: suppressed
        assert should_emit_alert(signature, now=now + timedelta(minutes=15), cooldown_minutes=30) is False
        
        # At 30 minutes: emitted
        assert should_emit_alert(signature, now=now + timedelta(minutes=30), cooldown_minutes=30) is True
        
        # At 45 minutes: suppressed again (new cooldown started at 30 minutes)
        assert should_emit_alert(signature, now=now + timedelta(minutes=45), cooldown_minutes=30) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
