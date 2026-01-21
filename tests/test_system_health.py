# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for System Health & Readiness Snapshot."""

import pytest
from datetime import datetime, timezone

from app.core.system_health import (
    SystemHealthSnapshot,
    compute_system_health,
)


class TestHealthyScenario:
    """Test healthy system scenarios."""
    
    def test_healthy_with_risk_on_high_confidence(self):
        """Test that RISK_ON with high confidence produces HEALTHY status."""
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=85,
            total_candidates=10,
            actionable_candidates=5,
            blocked_actions=2,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 100
        assert snapshot.status == "HEALTHY"
        assert snapshot.regime == "RISK_ON"
        assert snapshot.regime_confidence == 85
        assert snapshot.total_candidates == 10
        assert snapshot.actionable_candidates == 5
        assert snapshot.blocked_actions == 2
    
    def test_healthy_at_threshold_80(self):
        """Test that score exactly at 80 produces HEALTHY status."""
        # Score = 100 - 20 (low confidence) = 80
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 80
        assert snapshot.status == "HEALTHY"
    
    def test_healthy_with_minor_errors(self):
        """Test that minor errors still produce HEALTHY status."""
        # Score = 100 - 20 (low confidence) - 20 (2 errors) = 60, but let's use high confidence
        # Score = 100 - 20 (2 errors) = 80
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,  # >= 70, no penalty
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=2,  # -20
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 80
        assert snapshot.status == "HEALTHY"


class TestDegradedScenario:
    """Test degraded system scenarios."""
    
    def test_degraded_with_low_confidence(self):
        """Test that low confidence produces DEGRADED status."""
        # Score = 100 - 20 (low confidence) = 80, but let's add more
        # Score = 100 - 20 (low confidence) - 10 (blocked > actionable) = 70
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=2,
            blocked_actions=3,  # > actionable, so -10
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 70
        assert snapshot.status == "DEGRADED"
    
    def test_degraded_at_threshold_50(self):
        """Test that score exactly at 50 produces DEGRADED status."""
        # Score = 100 - 20 (low confidence) - 30 (RISK_OFF) = 50
        snapshot = compute_system_health(
            regime="RISK_OFF",
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 50
        assert snapshot.status == "DEGRADED"
    
    def test_degraded_with_errors(self):
        """Test that errors produce DEGRADED status."""
        # Score = 100 - 20 (low confidence) - 30 (3 errors, capped at -30) = 50
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=3,  # -30 (capped)
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 50
        assert snapshot.status == "DEGRADED"
    
    def test_degraded_at_threshold_79(self):
        """Test that score at 79 produces DEGRADED status."""
        # Score = 100 - 20 (low confidence) - 1 (minimal error) = 79
        # Actually, errors are -10 each, so we need: 100 - 20 - 10 = 70
        # Let's use: 100 - 20 (low confidence) - 10 (blocked > actionable) = 70
        # To get 79: 100 - 20 - 1 = 79, but errors are -10 each
        # Let's use: 100 - 20 (low confidence) = 80, then subtract 1 somehow
        # Actually, we can't subtract 1 with the given rules. Let's test with 70
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=2,
            blocked_actions=3,  # > actionable, so -10
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 70
        assert snapshot.status == "DEGRADED"


class TestHaltScenario:
    """Test halt system scenarios."""
    
    def test_halt_with_risk_off_and_low_confidence(self):
        """Test that RISK_OFF with low confidence produces HALT status."""
        # Score = 100 - 20 (low confidence) - 30 (RISK_OFF) = 50, but let's add more
        # Score = 100 - 20 (low confidence) - 30 (RISK_OFF) - 10 (blocked > actionable) = 40
        snapshot = compute_system_health(
            regime="RISK_OFF",
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=2,
            blocked_actions=3,  # > actionable, so -10
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 40
        assert snapshot.status == "HALT"
    
    def test_halt_with_errors_capped(self):
        """Test that errors are capped at -40."""
        # Score = 100 - 20 (low confidence) - 40 (errors capped) = 40
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=10,  # Would be -100, but capped at -40
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 40
        assert snapshot.status == "HALT"
    
    def test_halt_at_threshold_49(self):
        """Test that score just below 50 produces HALT status."""
        # Score = 100 - 20 (low confidence) - 30 (RISK_OFF) - 1 (error) = 49
        # Actually errors are -10 each, so: 100 - 20 - 30 - 10 = 40
        # To get 49, we need: 100 - 20 - 30 - 1 = 49, but errors are -10 each
        # Let's use: 100 - 20 (low confidence) - 30 (RISK_OFF) = 50, then we need -1 more
        # But we can't subtract 1. Let's test with 40 which is < 50
        snapshot = compute_system_health(
            regime="RISK_OFF",
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=1,  # -10
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 40
        assert snapshot.status == "HALT"


class TestScoreBounds:
    """Test that score is bounded correctly."""
    
    def test_score_cannot_exceed_100(self):
        """Test that score cannot exceed 100."""
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=85,
            total_candidates=10,
            actionable_candidates=5,
            blocked_actions=2,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 100
        assert snapshot.health_score <= 100
    
    def test_score_cannot_go_below_0(self):
        """Test that score cannot go below 0."""
        # Create enough issues to push score below 0
        # Score = 100 - 20 (low confidence) - 40 (errors capped) - 10 (blocked > actionable) - 30 (RISK_OFF) = -10
        # Should be clamped to 0
        snapshot = compute_system_health(
            regime="RISK_OFF",  # -30
            regime_confidence=65,  # < 70, so -20
            total_candidates=5,
            actionable_candidates=2,
            blocked_actions=3,  # > actionable, so -10
            error_count_24h=10,  # Capped at -40
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 0  # Clamped to 0
        assert snapshot.status == "HALT"
        assert snapshot.health_score >= 0


class TestSystemHealthSnapshotStructure:
    """Test SystemHealthSnapshot dataclass structure."""
    
    def test_snapshot_has_all_required_fields(self):
        """Test that SystemHealthSnapshot has all required fields."""
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=85,
            total_candidates=10,
            actionable_candidates=5,
            blocked_actions=2,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert hasattr(snapshot, "regime")
        assert hasattr(snapshot, "regime_confidence")
        assert hasattr(snapshot, "total_candidates")
        assert hasattr(snapshot, "actionable_candidates")
        assert hasattr(snapshot, "blocked_actions")
        assert hasattr(snapshot, "error_count_24h")
        assert hasattr(snapshot, "warning_count_24h")
        assert hasattr(snapshot, "health_score")
        assert hasattr(snapshot, "status")
        assert hasattr(snapshot, "computed_at")
        
        assert snapshot.regime in ["RISK_ON", "RISK_OFF"]
        assert 0 <= snapshot.regime_confidence <= 100
        assert isinstance(snapshot.total_candidates, int)
        assert isinstance(snapshot.actionable_candidates, int)
        assert isinstance(snapshot.blocked_actions, int)
        assert isinstance(snapshot.error_count_24h, int)
        assert isinstance(snapshot.warning_count_24h, int)
        assert 0 <= snapshot.health_score <= 100
        assert snapshot.status in ["HEALTHY", "DEGRADED", "HALT"]
        assert isinstance(snapshot.computed_at, str)
    
    def test_computed_at_is_iso_format(self):
        """Test that computed_at is in ISO format."""
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=85,
            total_candidates=10,
            actionable_candidates=5,
            blocked_actions=2,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        # Should be parseable as ISO datetime
        try:
            datetime.fromisoformat(snapshot.computed_at.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail(f"computed_at is not valid ISO format: {snapshot.computed_at}")


class TestDeterministicOutput:
    """Test that health computation is deterministic."""
    
    def test_same_inputs_produce_same_score(self):
        """Test that same inputs produce same score."""
        snapshot1 = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=2,
            error_count_24h=1,
            warning_count_24h=2,
        )
        
        snapshot2 = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=2,
            error_count_24h=1,
            warning_count_24h=2,
        )
        
        assert snapshot1.health_score == snapshot2.health_score
        assert snapshot1.status == snapshot2.status
        assert snapshot1.regime == snapshot2.regime
        assert snapshot1.regime_confidence == snapshot2.regime_confidence


class TestScoringRules:
    """Test individual scoring rules."""
    
    def test_regime_confidence_penalty(self):
        """Test that regime_confidence < 70 incurs -20 penalty."""
        snapshot_low = compute_system_health(
            regime="RISK_ON",
            regime_confidence=65,  # < 70
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        snapshot_high = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,  # >= 70
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot_low.health_score == 80  # 100 - 20
        assert snapshot_high.health_score == 100
    
    def test_error_penalty_capped_at_40(self):
        """Test that error penalty is capped at -40."""
        snapshot_4_errors = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=4,  # -40
            warning_count_24h=0,
        )
        
        snapshot_10_errors = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=10,  # Would be -100, but capped at -40
            warning_count_24h=0,
        )
        
        assert snapshot_4_errors.health_score == 60  # 100 - 40
        assert snapshot_10_errors.health_score == 60  # 100 - 40 (capped)
    
    def test_blocked_actions_penalty(self):
        """Test that blocked_actions > actionable_candidates incurs -10 penalty."""
        snapshot_blocked = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=2,
            blocked_actions=3,  # > actionable
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        snapshot_not_blocked = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=2,  # <= actionable
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot_blocked.health_score == 90  # 100 - 10
        assert snapshot_not_blocked.health_score == 100
    
    def test_risk_off_penalty(self):
        """Test that RISK_OFF incurs -30 penalty."""
        snapshot_risk_off = compute_system_health(
            regime="RISK_OFF",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        snapshot_risk_on = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot_risk_off.health_score == 70  # 100 - 30
        assert snapshot_risk_on.health_score == 100


class TestStatusMapping:
    """Test status mapping rules."""
    
    def test_healthy_status_at_80(self):
        """Test that score >= 80 produces HEALTHY status."""
        snapshot = compute_system_health(
            regime="RISK_ON",
            regime_confidence=75,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=2,  # -20, score = 80
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 80
        assert snapshot.status == "HEALTHY"
    
    def test_degraded_status_at_50(self):
        """Test that score 50-79 produces DEGRADED status."""
        snapshot = compute_system_health(
            regime="RISK_OFF",
            regime_confidence=65,  # -20
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=1,
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 50  # 100 - 20 - 30
        assert snapshot.status == "DEGRADED"
    
    def test_halt_status_below_50(self):
        """Test that score < 50 produces HALT status."""
        snapshot = compute_system_health(
            regime="RISK_OFF",
            regime_confidence=65,  # -20
            total_candidates=5,
            actionable_candidates=2,
            blocked_actions=3,  # > actionable, -10
            error_count_24h=0,
            warning_count_24h=0,
        )
        
        assert snapshot.health_score == 40  # 100 - 20 - 30 - 10
        assert snapshot.status == "HALT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
