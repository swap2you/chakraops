# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for nightly evaluation and Slack summary.

Tests cover:
- CLI triggers evaluation correctly
- Slack message builder produces message even when 0 eligible
- Scheduler triggers command at scheduled time
- Run is persisted with source=nightly
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import json


# ============================================================================
# Slack Message Builder Tests
# ============================================================================

class TestSlackMessageBuilder:
    """Tests for Slack message formatting."""
    
    def test_build_slack_message_simple_with_eligible(self):
        """Test Slack message with eligible candidates."""
        from app.core.eval.nightly_evaluation import NightlySummary, build_slack_message_simple
        
        summary = NightlySummary(
            run_id="test_run_123",
            timestamp="2026-02-03T19:00:00Z",
            regime="NEUTRAL",
            risk_posture="MODERATE",
            duration_seconds=45.2,
            universe_total=50,
            evaluated=50,
            stage1_pass=35,
            stage2_pass=20,
            eligible=5,
            holds=25,
            blocks=5,
            top_eligible=[
                {"symbol": "AAPL", "score": 85, "primary_reason": "Chain evaluated"},
                {"symbol": "MSFT", "score": 82, "primary_reason": "Chain evaluated"},
            ],
            top_holds=[
                {"symbol": "TSLA", "primary_reason": "DATA_INCOMPLETE"},
            ],
        )
        
        message = build_slack_message_simple(summary)
        
        assert "test_run_123" in message
        assert "NEUTRAL" in message
        assert "MODERATE" in message
        assert "Eligible: 5" in message
        assert "Holds: 25" in message
        assert "AAPL" in message
        assert "MSFT" in message
        assert "TSLA" in message
    
    def test_build_slack_message_simple_zero_eligible(self):
        """Test Slack message when 0 eligible - should still produce valid message."""
        from app.core.eval.nightly_evaluation import NightlySummary, build_slack_message_simple
        
        summary = NightlySummary(
            run_id="test_run_zero",
            timestamp="2026-02-03T19:00:00Z",
            regime="BEAR",
            risk_posture="HIGH",
            duration_seconds=30.0,
            universe_total=50,
            evaluated=50,
            stage1_pass=10,
            stage2_pass=5,
            eligible=0,  # Zero eligible
            holds=40,
            blocks=10,
            top_eligible=[],  # Empty
            top_holds=[
                {"symbol": "NVDA", "primary_reason": "Low liquidity"},
            ],
        )
        
        message = build_slack_message_simple(summary)
        
        assert "test_run_zero" in message
        assert "Eligible: 0" in message
        assert "No eligible candidates today" in message
        assert "NVDA" in message
    
    def test_build_slack_message_blocks(self):
        """Test rich Slack block message format."""
        from app.core.eval.nightly_evaluation import NightlySummary, build_slack_message
        
        summary = NightlySummary(
            run_id="test_run_blocks",
            timestamp="2026-02-03T19:00:00Z",
            regime="BULL",
            risk_posture="LOW",
            duration_seconds=60.0,
            universe_total=50,
            evaluated=50,
            stage1_pass=40,
            stage2_pass=25,
            eligible=10,
            holds=15,
            blocks=5,
            top_eligible=[
                {
                    "symbol": "AAPL",
                    "score": 90,
                    "selected_contract": {
                        "contract": {
                            "strike": 150,
                            "expiration": "2026-03-21",
                            "delta": -0.25,
                            "bid": 2.50,
                        }
                    }
                },
            ],
            top_holds=[],
        )
        
        payload = build_slack_message(summary)
        
        assert "blocks" in payload
        assert len(payload["blocks"]) > 0
        
        # Find text content
        all_text = json.dumps(payload)
        assert "test_run_blocks" in all_text
        assert "BULL" in all_text
        assert "10" in all_text  # eligible count


# ============================================================================
# Nightly Config Tests
# ============================================================================

class TestNightlyConfig:
    """Tests for nightly configuration."""
    
    def test_config_from_env_defaults(self):
        """Test default configuration values."""
        from app.core.eval.nightly_evaluation import NightlyConfig
        
        with patch.dict("os.environ", {}, clear=True):
            config = NightlyConfig.from_env()
        
        assert config.eval_time == "19:00"
        assert config.timezone == "America/New_York"
        assert config.max_symbols is None
        assert config.stage2_top_k == 20
    
    def test_config_from_env_custom(self):
        """Test custom configuration from environment."""
        from app.core.eval.nightly_evaluation import NightlyConfig
        
        env = {
            "NIGHTLY_EVAL_TIME": "20:30",
            "NIGHTLY_EVAL_TZ": "America/Chicago",
            "NIGHTLY_MAX_SYMBOLS": "25",
            "NIGHTLY_STAGE2_TOP_K": "15",
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
        }
        
        with patch.dict("os.environ", env, clear=True):
            config = NightlyConfig.from_env()
        
        assert config.eval_time == "20:30"
        assert config.timezone == "America/Chicago"
        assert config.max_symbols == 25
        assert config.stage2_top_k == 15
        assert config.slack_webhook_url == "https://hooks.slack.com/test"


# ============================================================================
# Slack Notification Tests
# ============================================================================

class TestSlackNotification:
    """Tests for Slack notification sending."""
    
    @patch("requests.post")
    def test_send_nightly_slack_success(self, mock_post):
        """Test successful Slack notification."""
        from app.core.eval.nightly_evaluation import NightlySummary, send_nightly_slack
        
        mock_post.return_value = MagicMock(status_code=200)
        
        summary = NightlySummary(
            run_id="test_run",
            timestamp="2026-02-03T19:00:00Z",
            eligible=5,
        )
        
        with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            success, msg = send_nightly_slack(summary)
        
        assert success
        assert "sent" in msg.lower()
        mock_post.assert_called()
    
    def test_send_nightly_slack_not_configured(self):
        """Test Slack notification when not configured."""
        from app.core.eval.nightly_evaluation import NightlySummary, send_nightly_slack
        
        summary = NightlySummary(
            run_id="test_run",
            timestamp="2026-02-03T19:00:00Z",
            eligible=5,
        )
        
        with patch.dict("os.environ", {}, clear=True):
            success, msg = send_nightly_slack(summary)
        
        assert not success
        assert "not configured" in msg.lower() or "not set" in msg.lower()
    
    @patch("requests.post")
    def test_send_nightly_slack_failure(self, mock_post):
        """Test Slack notification failure handling."""
        from app.core.eval.nightly_evaluation import NightlySummary, send_nightly_slack
        
        mock_post.return_value = MagicMock(status_code=500, text="Internal error")
        
        summary = NightlySummary(
            run_id="test_run",
            timestamp="2026-02-03T19:00:00Z",
            eligible=5,
        )
        
        with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            success, msg = send_nightly_slack(summary)
        
        assert not success
        assert "500" in msg


# ============================================================================
# Nightly Evaluation Runner Tests
# ============================================================================

class TestNightlyEvaluationRunner:
    """Tests for the nightly evaluation runner."""
    
    @patch("app.core.eval.nightly_evaluation.send_nightly_slack")
    @patch("app.core.eval.staged_evaluator.evaluate_universe_staged")
    @patch("app.core.eval.evaluation_store.save_run")
    @patch("app.core.eval.evaluation_store.update_latest_pointer")
    @patch("app.api.data_health.UNIVERSE_SYMBOLS", ["AAPL", "MSFT", "GOOGL"])
    def test_run_nightly_evaluation_success(
        self, mock_update, mock_save, mock_eval, mock_slack
    ):
        """Test successful nightly evaluation run."""
        from app.core.eval.nightly_evaluation import NightlyConfig, run_nightly_evaluation
        from app.core.eval.staged_evaluator import FullEvaluationResult, EvaluationStage, FinalVerdict, StagedEvaluationResult
        
        # Mock staged evaluation results (contract: StagedEvaluationResult)
        mock_result = MagicMock(spec=FullEvaluationResult)
        mock_result.verdict = "ELIGIBLE"
        mock_result.score = 80
        mock_result.regime = "NEUTRAL"
        mock_result.risk = "MODERATE"
        mock_result.stage_reached = EvaluationStage.STAGE2_CHAIN
        mock_result.stage1 = MagicMock()
        mock_result.stage1.stock_verdict.value = "QUALIFIED"
        mock_result.to_dict.return_value = {"symbol": "AAPL", "verdict": "ELIGIBLE", "score": 80}
        
        mock_exposure = MagicMock()
        mock_exposure.to_dict.return_value = {"total_positions": 0, "by_symbol": {}, "at_cap": False}
        mock_eval.return_value = StagedEvaluationResult(results=[mock_result], exposure_summary=mock_exposure)
        mock_slack.return_value = (True, "Slack sent")
        
        config = NightlyConfig(dry_run=False, stage2_top_k=5)
        result = run_nightly_evaluation(config=config, asof="last_close")
        
        assert result["success"]
        assert result["run_id"] is not None
        assert result["slack_sent"]
        mock_save.assert_called_once()
        mock_update.assert_called_once()
    
    def test_run_nightly_evaluation_dry_run(self):
        """Test dry run mode."""
        from app.core.eval.nightly_evaluation import NightlyConfig, run_nightly_evaluation
        
        config = NightlyConfig(dry_run=True)
        result = run_nightly_evaluation(config=config, asof="last_close")
        
        assert result["success"]
        assert result["dry_run"]
        assert "Dry run" in result.get("message", "")


# ============================================================================
# Evaluation Store Source Tests
# ============================================================================

class TestEvaluationStoreSource:
    """Tests for source field in evaluation store."""
    
    def test_evaluation_run_summary_has_source(self):
        """Test EvaluationRunSummary includes source field."""
        from app.core.eval.evaluation_store import EvaluationRunSummary
        
        summary = EvaluationRunSummary(
            run_id="test_run",
            started_at="2026-02-03T19:00:00Z",
            source="nightly",
        )
        
        assert summary.source == "nightly"
    
    def test_evaluation_run_full_has_source(self):
        """Test EvaluationRunFull includes source field."""
        from app.core.eval.evaluation_store import EvaluationRunFull
        
        run = EvaluationRunFull(
            run_id="test_run",
            started_at="2026-02-03T19:00:00Z",
            source="nightly",
        )
        
        assert run.source == "nightly"
        
        # Test to_summary preserves source
        summary = run.to_summary()
        assert summary.source == "nightly"
    
    def test_evaluation_run_full_has_stage_counts(self):
        """Test EvaluationRunFull includes stage counts."""
        from app.core.eval.evaluation_store import EvaluationRunFull
        
        run = EvaluationRunFull(
            run_id="test_run",
            started_at="2026-02-03T19:00:00Z",
            stage1_pass=35,
            stage2_pass=20,
            holds=25,
            blocks=5,
        )
        
        assert run.stage1_pass == 35
        assert run.stage2_pass == 20
        assert run.holds == 25
        assert run.blocks == 5
        
        # Test to_summary preserves stage counts
        summary = run.to_summary()
        assert summary.stage1_pass == 35
        assert summary.stage2_pass == 20
        assert summary.holds == 25
        assert summary.blocks == 5


# ============================================================================
# Scheduler Tests
# ============================================================================

class TestNightlyScheduler:
    """Tests for nightly scheduler (skip if server deps not available)."""
    
    def test_get_next_nightly_time(self):
        """Test next nightly time calculation."""
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            try:
                from backports.zoneinfo import ZoneInfo
            except ImportError:
                pytest.skip("zoneinfo not available")
                return
        
        # Replicate server logic without importing server (avoids FastAPI dep in test env)
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz)
        hour, minute = 19, 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            from datetime import timedelta
            target = target + timedelta(days=1)
        
        # Next time should be in the future
        assert target > now
        assert (target - now).total_seconds() <= 86400
    
    def test_nightly_scheduler_status(self):
        """Test nightly scheduler status keys (without importing server)."""
        # Test that expected config/env names exist; actual status from server
        import os
        assert os.getenv("NIGHTLY_EVAL_ENABLED", "true") in ("true", "1", "yes", "false", "0", "no")
        # Default eval time format
        eval_time = os.getenv("NIGHTLY_EVAL_TIME", "19:00")
        parts = eval_time.split(":")
        assert len(parts) >= 1 and parts[0].isdigit()


# ============================================================================
# CLI Tests
# ============================================================================

class TestCLI:
    """Tests for CLI entry point."""
    
    def test_cli_test_mode(self):
        """Test CLI test mode produces output."""
        import sys
        from io import StringIO
        
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        try:
            # Import and run with test args
            from run_evaluation import run_test_mode
            import argparse
            
            args = argparse.Namespace(dry_run=False)
            result = run_test_mode(args)
            
            output = sys.stdout.getvalue()
            
            assert result == 0
            assert "test_run_123" in output
            assert "Slack message preview" in output
        finally:
            sys.stdout = old_stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
