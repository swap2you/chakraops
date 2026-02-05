# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Action Engine."""

import pytest
from datetime import date, datetime, timedelta

from app.core.action_engine import ActionDecision, evaluate_position_action
from app.core.models.position import Position


class TestCloseAction:
    """Test CLOSE action rules."""
    
    def test_premium_70_percent_triggers_close(self):
        """Test that premium_collected_pct >= 70 triggers CLOSE."""
        position = Position(
            id="test-1",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=1050.0,  # $10.50 per share = 7% of strike = 70% of $15 max premium
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        market_context = {
            "price": 155.0,
            "EMA50": 152.0,
            "EMA200": 150.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 70.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action == "CLOSE"
        assert decision.urgency == "MEDIUM"
        assert "PREMIUM_70_PCT" in decision.reason_codes
        assert "70" in decision.explanation
    
    def test_premium_70_exact_threshold(self):
        """Test that premium_collected_pct == 70.0 triggers CLOSE."""
        position = Position(
            id="test-2",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=1400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        market_context = {
            "price": 205.0,
            "EMA50": 202.0,
            "EMA200": 200.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 70.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action == "CLOSE"
        assert decision.urgency == "MEDIUM"
    
    def test_premium_69_does_not_trigger_close(self):
        """Test that premium_collected_pct == 69.9 does NOT trigger CLOSE (premium rule)."""
        position = Position(
            id="test-3",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=2097.0,  # 69.9%
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 305.0,
            "EMA50": 302.0,
            "EMA200": 300.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 69.9,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action != "CLOSE"  # Should be HOLD or other
    
    def test_dte_3_and_premium_50_triggers_close(self):
        """Test that DTE <= 3 AND premium_collected_pct >= 50 triggers CLOSE."""
        position = Position(
            id="test-4",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=3)).isoformat(),
            contracts=1,
            premium_collected=800.0,  # $8 per share = 2% of strike = 50% of $16 max premium
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 405.0,
            "EMA50": 402.0,
            "EMA200": 400.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 50.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action == "CLOSE"
        assert decision.urgency == "HIGH"
        assert "DTE_LE_3" in decision.reason_codes
        assert "PREMIUM_50_PCT" in decision.reason_codes
    
    def test_dte_3_and_premium_49_does_not_trigger_close(self):
        """Test that DTE <= 3 but premium < 50 does NOT trigger CLOSE."""
        position = Position(
            id="test-5",
            symbol="TSLA",
            position_type="CSP",
            strike=180.0,
            expiry=(date.today() + timedelta(days=2)).isoformat(),
            contracts=1,
            premium_collected=176.4,  # 49%
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 185.0,
            "EMA50": 182.0,
            "EMA200": 180.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
        }
        
        decision = evaluate_position_action(position, market_context)
        
        # Should not be CLOSE (might be ROLL if other conditions met)
        assert decision.action != "CLOSE" or decision.reason_codes != ["DTE_LE_3", "PREMIUM_50_PCT"]


class TestRollAction:
    """Test ROLL action rules."""
    
    def test_dte_7_premium_lt_50_price_gt_ema50_triggers_roll(self):
        """Test that DTE <= 7, premium < 50, and price > EMA50 triggers ROLL."""
        position = Position(
            id="test-6",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=7)).isoformat(),
            contracts=1,
            premium_collected=450.0,  # 30%
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 155.0,
            "EMA50": 152.0,
            "EMA200": 150.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action == "ROLL"
        assert decision.urgency == "HIGH"
        assert "DTE_LE_7" in decision.reason_codes
        assert "PREMIUM_LT_50" in decision.reason_codes
        assert "PRICE_GT_EMA50" in decision.reason_codes
    
    def test_dte_7_but_premium_50_does_not_trigger_roll(self):
        """Test that DTE <= 7 but premium >= 50 does NOT trigger ROLL."""
        position = Position(
            id="test-7",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=6)).isoformat(),
            contracts=1,
            premium_collected=1000.0,  # 50%
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 205.0,
            "EMA50": 202.0,
            "EMA200": 200.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 50.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        # Should not be ROLL (might be CLOSE if DTE <= 3)
        assert decision.action != "ROLL" or "PREMIUM_LT_50" not in decision.reason_codes
    
    def test_dte_7_premium_lt_50_but_price_lt_ema50_does_not_trigger_roll(self):
        """Test that DTE <= 7 and premium < 50 but price <= EMA50 does NOT trigger ROLL."""
        position = Position(
            id="test-8",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=5)).isoformat(),
            contracts=1,
            premium_collected=450.0,  # 30%
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 298.0,  # Below EMA50
            "EMA50": 302.0,
            "EMA200": 300.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        # Should not be ROLL (might be ALERT if price < EMA200)
        assert decision.action != "ROLL" or "PRICE_GT_EMA50" not in decision.reason_codes


class TestAlertAction:
    """Test ALERT action rules."""
    
    def test_price_lt_ema200_triggers_alert(self):
        """Test that price < EMA200 triggers ALERT."""
        position = Position(
            id="test-9",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=600.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 390.0,  # Below EMA200
            "EMA50": 395.0,
            "EMA200": 400.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action == "ALERT"
        assert decision.urgency == "HIGH"
        assert "PRICE_LT_EMA200" in decision.reason_codes
    
    def test_price_eq_ema200_does_not_trigger_alert(self):
        """Test that price == EMA200 does NOT trigger ALERT."""
        position = Position(
            id="test-10",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 150.0,  # Equal to EMA200
            "EMA50": 152.0,
            "EMA200": 150.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        # Should not be ALERT for price < EMA200
        assert decision.action != "ALERT" or "PRICE_LT_EMA200" not in decision.reason_codes
    
    def test_regime_risk_off_triggers_alert(self):
        """Test that regime == RISK_OFF triggers ALERT."""
        position = Position(
            id="test-11",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=600.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 205.0,
            "EMA50": 202.0,
            "EMA200": 200.0,
            "ATR_pct": 0.03,
            "regime": "RISK_OFF",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action == "ALERT"
        assert decision.urgency == "HIGH"
        assert "REGIME_RISK_OFF" in decision.reason_codes


class TestHoldAction:
    """Test HOLD action (default)."""
    
    def test_default_hold(self):
        """Test that default case returns HOLD."""
        position = Position(
            id="test-12",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 155.0,
            "EMA50": 152.0,
            "EMA200": 150.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action == "HOLD"
        assert decision.urgency == "LOW"
        assert "DEFAULT" in decision.reason_codes
    
    def test_hold_when_no_matching_rules(self):
        """Test HOLD when no other rules match."""
        position = Position(
            id="test-13",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=20)).isoformat(),  # DTE > 7
            contracts=1,
            premium_collected=450.0,  # < 70%
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 305.0,  # > EMA200
            "EMA50": 302.0,
            "EMA200": 300.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert decision.action == "HOLD"
        assert decision.urgency == "LOW"


class TestRulePriority:
    """Test that rules are evaluated in priority order (first match wins)."""
    
    def test_close_takes_priority_over_roll(self):
        """Test that CLOSE rule takes priority over ROLL."""
        position = Position(
            id="test-14",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=7)).isoformat(),  # DTE <= 7
            contracts=1,
            premium_collected=1050.0,  # 70%
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        market_context = {
            "price": 155.0,  # > EMA50 (would trigger ROLL)
            "EMA50": 152.0,
            "EMA200": 150.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 70.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        # CLOSE should win (premium >= 70)
        assert decision.action == "CLOSE"
        assert "PREMIUM_70_PCT" in decision.reason_codes
    
    def test_close_takes_priority_over_alert(self):
        """Test that CLOSE rule takes priority over ALERT."""
        position = Position(
            id="test-15",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=1120.0,  # 70%
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        market_context = {
            "price": 390.0,  # < EMA200 (would trigger ALERT)
            "EMA50": 395.0,
            "EMA200": 400.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 70.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        # CLOSE should win
        assert decision.action == "CLOSE"
    
    def test_roll_takes_priority_over_alert(self):
        """Test that ROLL rule takes priority over ALERT."""
        position = Position(
            id="test-16",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=6)).isoformat(),  # DTE <= 7
            contracts=1,
            premium_collected=400.0,  # 20% (< 50)
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 205.0,  # > EMA50 (triggers ROLL), but also > EMA200
            "EMA50": 202.0,
            "EMA200": 200.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 20.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        # ROLL should win
        assert decision.action == "ROLL"
    
    def test_alert_takes_priority_over_hold(self):
        """Test that ALERT rule takes priority over HOLD."""
        position = Position(
            id="test-17",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=20)).isoformat(),  # DTE > 7
            contracts=1,
            premium_collected=450.0,  # 30% (< 70)
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 290.0,  # < EMA200 (triggers ALERT)
            "EMA50": 295.0,
            "EMA200": 300.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        # ALERT should win
        assert decision.action == "ALERT"


class TestEdgeCases:
    """Test edge cases and exact thresholds."""
    
    def test_premium_70_exact(self):
        """Test exact threshold: premium_collected_pct == 70.0."""
        position = Position(
            id="test-18",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=1050.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        market_context = {
            "price": 155.0,
            "EMA50": 152.0,
            "EMA200": 150.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 70.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        assert decision.action == "CLOSE"
    
    def test_premium_50_exact(self):
        """Test exact threshold: premium_collected_pct == 50.0 with DTE <= 3."""
        position = Position(
            id="test-19",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=3)).isoformat(),
            contracts=1,
            premium_collected=1000.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 205.0,
            "EMA50": 202.0,
            "EMA200": 200.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 50.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        assert decision.action == "CLOSE"
        assert "DTE_LE_3" in decision.reason_codes
        assert "PREMIUM_50_PCT" in decision.reason_codes
    
    def test_dte_7_exact(self):
        """Test exact threshold: DTE == 7."""
        position = Position(
            id="test-20",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=7)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 305.0,
            "EMA50": 302.0,
            "EMA200": 300.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        assert decision.action == "ROLL"
        assert "DTE_LE_7" in decision.reason_codes
    
    def test_dte_3_exact(self):
        """Test exact threshold: DTE == 3."""
        position = Position(
            id="test-21",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=3)).isoformat(),
            contracts=1,
            premium_collected=800.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 405.0,
            "EMA50": 402.0,
            "EMA200": 400.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 50.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        assert decision.action == "CLOSE"
        assert "DTE_LE_3" in decision.reason_codes
    
    def test_missing_market_data_graceful(self):
        """Test that missing market data doesn't crash."""
        position = Position(
            id="test-22",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        # Missing EMA50, EMA200
        market_context = {
            "price": 155.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        # Should not crash, should return HOLD
        decision = evaluate_position_action(position, market_context)
        assert decision is not None
        assert decision.action in ["HOLD", "CLOSE", "ROLL", "ALERT"]


class TestActionDecisionStructure:
    """Test ActionDecision dataclass structure."""
    
    def test_action_decision_has_all_fields(self):
        """Test that ActionDecision has all required fields."""
        position = Position(
            id="test-23",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_context = {
            "price": 155.0,
            "EMA50": 152.0,
            "EMA200": 150.0,
            "ATR_pct": 0.03,
            "regime": "RISK_ON",
            "premium_collected_pct": 30.0,
        }
        
        decision = evaluate_position_action(position, market_context)
        
        assert hasattr(decision, "symbol")
        assert hasattr(decision, "action")
        assert hasattr(decision, "urgency")
        assert hasattr(decision, "reason_codes")
        assert hasattr(decision, "explanation")
        assert hasattr(decision, "allowed_next_states")
        
        assert decision.symbol == "AAPL"
        assert decision.action in ["HOLD", "CLOSE", "ROLL", "ALERT"]
        assert decision.urgency in ["LOW", "MEDIUM", "HIGH"]
        assert isinstance(decision.reason_codes, list)
        assert isinstance(decision.explanation, str)
        assert isinstance(decision.allowed_next_states, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
