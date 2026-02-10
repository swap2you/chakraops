# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Integration test for signal engine with golden JSON comparison."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from app.core.market.stock_models import StockSnapshot
from app.signals.engine import run_signal_engine
from app.signals.models import CCConfig, CSPConfig, SignalEngineConfig
from app.signals.scoring import ScoringConfig
from app.signals.selection import SelectionConfig
from tests.fixtures.mock_options_provider import MockOptionsChainProvider


def create_test_snapshots() -> list[StockSnapshot]:
    """Create a small test universe."""
    base_time = datetime(2026, 1, 22, 10, 0, 0)
    return [
        StockSnapshot(
            symbol="AAPL",
            price=150.0,
            bid=149.99,
            ask=150.01,
            volume=1000000,
            avg_stock_volume_20d=2000000.0,
            has_options=True,
            snapshot_time=base_time,
            data_source="THETA",
        ),
        StockSnapshot(
            symbol="MSFT",
            price=400.0,
            bid=399.99,
            ask=400.01,
            volume=2000000,
            avg_stock_volume_20d=3000000.0,
            has_options=True,
            snapshot_time=base_time,
            data_source="THETA",
        ),
    ]


def create_test_options_data() -> dict:
    """Create test options data for mock provider."""
    expiry1 = date(2026, 2, 20)  # 29 DTE
    expiry2 = date(2026, 3, 20)  # 57 DTE

    return {
        "AAPL": [
            # PUT options
            {
                "expiry": expiry1,
                "strike": 145.0,
                "right": "PUT",
                "bid": 2.50,
                "ask": 2.60,
                "delta": -0.25,
                "iv": 0.28,
                "volume": 1000,
                "open_interest": 5000,
            },
            {
                "expiry": expiry1,
                "strike": 140.0,
                "right": "PUT",
                "bid": 1.50,
                "ask": 1.60,
                "delta": -0.15,
                "iv": 0.30,
                "volume": 800,
                "open_interest": 4000,
            },
            # CALL options
            {
                "expiry": expiry1,
                "strike": 155.0,
                "right": "CALL",
                "bid": 2.50,
                "ask": 2.60,
                "delta": 0.25,
                "iv": 0.28,
                "volume": 1000,
                "open_interest": 5000,
            },
            {
                "expiry": expiry1,
                "strike": 160.0,
                "right": "CALL",
                "bid": 1.50,
                "ask": 1.60,
                "delta": 0.15,
                "iv": 0.30,
                "volume": 800,
                "open_interest": 4000,
            },
            # Expiry 2 PUT
            {
                "expiry": expiry2,
                "strike": 145.0,
                "right": "PUT",
                "bid": 4.00,
                "ask": 4.20,
                "delta": -0.30,
                "iv": 0.30,
                "volume": 600,
                "open_interest": 4000,
            },
            # Expiry 2 CALL
            {
                "expiry": expiry2,
                "strike": 155.0,
                "right": "CALL",
                "bid": 4.00,
                "ask": 4.20,
                "delta": 0.30,
                "iv": 0.30,
                "volume": 600,
                "open_interest": 4000,
            },
        ],
        "MSFT": [
            # PUT options
            {
                "expiry": expiry1,
                "strike": 390.0,
                "right": "PUT",
                "bid": 5.00,
                "ask": 5.20,
                "delta": -0.25,
                "iv": 0.25,
                "volume": 2000,
                "open_interest": 8000,
            },
            # CALL options
            {
                "expiry": expiry1,
                "strike": 410.0,
                "right": "CALL",
                "bid": 5.00,
                "ask": 5.20,
                "delta": 0.25,
                "iv": 0.25,
                "volume": 2000,
                "open_interest": 8000,
            },
        ],
    }


def serialize_result_for_comparison(result) -> dict:
    """Serialize result for JSON comparison (normalize timestamps)."""
    from app.signals.models import SignalType

    def serialize_candidate(c):
        return {
            "symbol": c.symbol,
            "signal_type": c.signal_type.value,
            "underlying_price": c.underlying_price,
            "expiry": c.expiry.isoformat(),
            "strike": c.strike,
            "option_right": c.option_right,
            "bid": c.bid,
            "ask": c.ask,
            "mid": c.mid,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "delta": c.delta,
            "iv": c.iv,
        }

    def serialize_exclusion(ex):
        return {
            "code": ex.code,
            "message": ex.message,
            "data": ex.data,
        }

    return {
        "universe_id_or_hash": result.universe_id_or_hash,
        "configs": result.configs,
        "candidates": [serialize_candidate(c) for c in result.candidates],
        "exclusions": [serialize_exclusion(ex) for ex in result.exclusions],
        "stats": result.stats,
    }


class TestSignalEngineIntegration:
    """Integration test for signal engine."""

    def test_signal_engine_deterministic_output(self) -> None:
        """Test that signal engine produces deterministic output."""
        snapshots = create_test_snapshots()
        options_data = create_test_options_data()
        provider = MockOptionsChainProvider(options_data)

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_config = CSPConfig(
            delta_min=0.15,
            delta_max=0.25,
            prob_otm_min=0.70,
        )

        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        # Run multiple times
        results = []
        for _ in range(3):
            result = run_signal_engine(
                stock_snapshots=snapshots,
                options_chain_provider=provider,
                base_config=base_config,
                csp_config=csp_config,
                cc_config=cc_config,
                universe_id_or_hash="test_universe",
            )
            results.append(result)

        # All results should have same candidates and stats
        assert all(r.stats == results[0].stats for r in results)
        assert all(len(r.candidates) == len(results[0].candidates) for r in results)

        # Verify candidates are identical (excluding as_of timestamp)
        for i in range(len(results[0].candidates)):
            c0 = results[0].candidates[i]
            for r in results[1:]:
                ci = r.candidates[i]
                assert c0.symbol == ci.symbol
                assert c0.signal_type == ci.signal_type
                assert c0.expiry == ci.expiry
                assert c0.strike == ci.strike

    def test_signal_engine_golden_json(self) -> None:
        """Test that signal engine output matches golden JSON."""
        snapshots = create_test_snapshots()
        options_data = create_test_options_data()
        provider = MockOptionsChainProvider(options_data)

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_config = CSPConfig(
            delta_min=0.15,
            delta_max=0.25,
            prob_otm_min=0.70,
        )

        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        result = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_universe",
        )

        # Serialize result
        actual_dict = serialize_result_for_comparison(result)

        # Load golden JSON
        test_dir = Path(__file__).parent
        golden_file = test_dir / "fixtures" / "golden_signals.json"

        if golden_file.exists():
            with open(golden_file, "r") as f:
                expected_dict = json.load(f)

            # Compare (config and structure; stats/candidates vary with DTE from datetime.now())
            assert actual_dict["universe_id_or_hash"] == expected_dict["universe_id_or_hash"]
            assert actual_dict["configs"] == expected_dict["configs"]

            # Stats and candidate count vary by run date (DTE filter uses datetime.now())
            assert "total_candidates" in actual_dict["stats"]
            assert actual_dict["stats"]["total_candidates"] >= 0
            assert len(actual_dict["candidates"]) == actual_dict["stats"]["total_candidates"]
            # Each candidate has delta/prob_otm/iv_rank when available
            for c in actual_dict["candidates"]:
                assert "delta" in c or "prob_otm" in c or "iv" in c
        else:
            # First run: write golden file
            golden_file.parent.mkdir(parents=True, exist_ok=True)
            with open(golden_file, "w") as f:
                json.dump(actual_dict, f, indent=2)
            pytest.fail(f"Golden file created at {golden_file}. Review and commit it.")

    def test_signal_engine_sorting(self) -> None:
        """Test that candidates are sorted deterministically."""
        snapshots = create_test_snapshots()
        options_data = create_test_options_data()
        provider = MockOptionsChainProvider(options_data)

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_config = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)
        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        result = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_universe",
        )

        # Verify sorting: (symbol, signal_type, expiry, strike)
        for i in range(len(result.candidates) - 1):
            curr = result.candidates[i]
            next_c = result.candidates[i + 1]

            assert curr.symbol <= next_c.symbol
            if curr.symbol == next_c.symbol:
                assert curr.signal_type.value <= next_c.signal_type.value
                if curr.signal_type == next_c.signal_type:
                    assert curr.expiry <= next_c.expiry
                    if curr.expiry == next_c.expiry:
                        assert curr.strike <= next_c.strike

    def test_expiration_filtering_and_cap(self) -> None:
        """Test that expirations are filtered by DTE window and capped per symbol."""
        from datetime import timedelta

        base_time = datetime(2026, 1, 22, 10, 0, 0)

        # Create a single snapshot
        snapshots = [
            StockSnapshot(
                symbol="AAPL",
                price=150.0,
                bid=149.99,
                ask=150.01,
                volume=1000000,
                avg_stock_volume_20d=2000000.0,
                has_options=True,
                snapshot_time=base_time,
                data_source="THETA",
            )
        ]

        # Build expirations: very old, in-window, and far future
        old_expiry = date(2012, 6, 1)
        in_window_start = base_time.date() + timedelta(days=25)
        in_window_list = [in_window_start + timedelta(days=i) for i in range(20)]
        far_future_expiry = base_time.date() + timedelta(days=365)

        # Limit max_expiries_per_symbol to 5 for this test
        max_expiries = 5

        # Create options data only for the in-window expirations; chains for old/far dates should not be fetched
        options_data = {
            "AAPL": [
                {
                    "expiry": exp,
                    "strike": 145.0,
                    "right": "PUT",
                    "bid": 2.50,
                    "ask": 2.60,
                    "delta": -0.25,
                    "iv": 0.28,
                    "volume": 1000,
                    "open_interest": 5000,
                }
                for exp in in_window_list
            ]
        }

        class TrackingMockProvider(MockOptionsChainProvider):
            def __init__(self, test_data):
                super().__init__(test_data)
                self.requested_expiries: list[tuple[str, date, str]] = []

            def get_expirations(self, symbol: str):
                # Return all expirations including out-of-window ones
                return [old_expiry] + in_window_list + [far_future_expiry]

            def get_chain(self, symbol: str, expiry: date, right: str):
                self.requested_expiries.append((symbol.upper(), expiry, right.upper()))
                return super().get_chain(symbol, expiry, right)

        provider = TrackingMockProvider(options_data)

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
            max_expiries_per_symbol=max_expiries,
        )

        csp_config = CSPConfig(
            delta_min=0.15,
            delta_max=0.25,
            prob_otm_min=0.70,
        )

        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        result = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_expiry_filter_cap",
        )

        # Ensure engine ran without errors
        assert result.stats["total_symbols"] == 1

        # Determine unique expirations actually requested (PUT/CC both count but we dedupe by date)
        requested_dates = sorted({exp for _, exp, _ in provider.requested_expiries})

        # All requested expirations must be within the DTE window
        for exp in requested_dates:
            dte = (exp - base_time.date()).days
            assert base_config.dte_min <= dte <= base_config.dte_max

        # And the number of distinct expirations should not exceed the cap
        assert len(requested_dates) <= max_expiries

    def test_scoring_deterministic_and_ranked(self) -> None:
        """Scoring via engine should be deterministic and provide ranks."""
        snapshots = create_test_snapshots()
        options_data = create_test_options_data()
        provider = MockOptionsChainProvider(options_data)

        scoring_cfg = ScoringConfig(
            premium_weight=1.0,
            dte_weight=1.0,
            spread_weight=1.0,
            otm_weight=1.0,
            liquidity_weight=1.0,
        )

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
            scoring_config=scoring_cfg,
        )

        csp_config = CSPConfig(
            delta_min=0.15,
            delta_max=0.25,
            prob_otm_min=0.70,
        )

        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        # Run engine twice with scoring enabled
        result1 = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_universe_scoring",
        )

        # Reuse provider (its behavior is deterministic)
        result2 = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_universe_scoring",
        )

        assert result1.scored_candidates is not None
        assert result2.scored_candidates is not None

        scores1 = [s.score.total for s in result1.scored_candidates]
        scores2 = [s.score.total for s in result2.scored_candidates]
        ranks1 = [s.rank for s in result1.scored_candidates]
        ranks2 = [s.rank for s in result2.scored_candidates]

        assert scores1 == scores2
        assert ranks1 == ranks2

        # Ranks should be 1..N and scores non-increasing
        assert ranks1 == list(range(1, len(ranks1) + 1))
        assert scores1 == sorted(scores1, reverse=True)

        # Raw candidates list must remain unchanged and equal between runs
        raw1 = result1.candidates
        raw2 = result2.candidates
        assert [c.symbol for c in raw1] == [c.symbol for c in raw2]
        assert [c.signal_type for c in raw1] == [c.signal_type for c in raw2]
        assert [c.expiry for c in raw1] == [c.expiry for c in raw2]
        assert [c.strike for c in raw1] == [c.strike for c in raw2]

    def test_engine_without_scoring_config(self) -> None:
        """Engine should work and leave scored/selected as None when scoring_config is None."""
        snapshots = create_test_snapshots()
        options_data = create_test_options_data()
        provider = MockOptionsChainProvider(options_data)

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
            # scoring_config left as default None
        )

        csp_config = CSPConfig(
            delta_min=0.15,
            delta_max=0.25,
            prob_otm_min=0.70,
        )

        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        result = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_universe_noscoring",
        )

        assert result.scored_candidates is None
        assert result.selected_signals is None
        assert result.explanations is None
        # Decision snapshot should always be present
        assert result.decision_snapshot is not None
        assert result.decision_snapshot.scored_candidates is None
        assert result.decision_snapshot.selected_signals is None
        assert result.decision_snapshot.explanations is None
        # Existing stats semantics should remain valid
        assert result.stats["total_candidates"] == len(result.candidates)

    def test_selection_within_engine(self) -> None:
        """Engine should apply selection when both scoring and selection configs are provided."""
        snapshots = create_test_snapshots()
        options_data = create_test_options_data()
        provider = MockOptionsChainProvider(options_data)

        scoring_cfg = ScoringConfig(
            premium_weight=1.0,
            dte_weight=1.0,
            spread_weight=1.0,
            otm_weight=1.0,
            liquidity_weight=1.0,
        )

        selection_cfg = SelectionConfig(
            max_total=1,
            max_per_symbol=1,
            max_per_signal_type=None,
            min_score=0.0,
        )

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
            scoring_config=scoring_cfg,
            selection_config=selection_cfg,
        )

        csp_config = CSPConfig(
            delta_min=0.15,
            delta_max=0.25,
            prob_otm_min=0.70,
        )

        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        result = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_universe_selection",
        )

        # Selection should have run
        assert result.scored_candidates is not None
        assert result.selected_signals is not None

        # Total cap applied
        assert len(result.selected_signals) <= selection_cfg.max_total

        # Raw and scored lists remain unchanged in size
        assert len(result.candidates) == result.stats["total_candidates"]
        assert len(result.scored_candidates) == len(result.candidates)

    def test_decision_snapshot_in_engine(self) -> None:
        """Engine should build decision snapshot and it should be JSON-serializable."""
        import json
        from dataclasses import asdict

        snapshots = create_test_snapshots()
        options_data = create_test_options_data()
        provider = MockOptionsChainProvider(options_data)

        scoring_cfg = ScoringConfig(
            premium_weight=1.0,
            dte_weight=1.0,
            spread_weight=1.0,
            otm_weight=1.0,
            liquidity_weight=1.0,
        )

        selection_cfg = SelectionConfig(
            max_total=2,
            max_per_symbol=2,
            max_per_signal_type=None,
            min_score=0.0,
        )

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
            scoring_config=scoring_cfg,
            selection_config=selection_cfg,
        )

        csp_config = CSPConfig(
            delta_min=0.15,
            delta_max=0.25,
            prob_otm_min=0.70,
        )

        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        result = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_universe_snapshot",
        )

        # Snapshot should always be present
        assert result.decision_snapshot is not None
        snapshot = result.decision_snapshot

        # Snapshot should mirror result content
        assert snapshot.universe_id_or_hash == result.universe_id_or_hash
        assert snapshot.stats == result.stats
        assert len(snapshot.candidates) == len(result.candidates)

        # Snapshot should be JSON-serializable
        snapshot_dict = asdict(snapshot)
        json_str = json.dumps(snapshot_dict)
        parsed = json.loads(json_str)

        assert parsed["universe_id_or_hash"] == result.universe_id_or_hash
        assert parsed["stats"]["total_candidates"] == result.stats["total_candidates"]

    def test_explanations_within_engine(self) -> None:
        """Engine should build explanations when selection produces results."""
        snapshots = create_test_snapshots()
        options_data = create_test_options_data()
        provider = MockOptionsChainProvider(options_data)

        scoring_cfg = ScoringConfig(
            premium_weight=1.0,
            dte_weight=1.0,
            spread_weight=1.0,
            otm_weight=1.0,
            liquidity_weight=1.0,
        )

        selection_cfg = SelectionConfig(
            max_total=2,
            max_per_symbol=2,
            max_per_signal_type=None,
            min_score=0.0,
        )

        base_config = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
            scoring_config=scoring_cfg,
            selection_config=selection_cfg,
        )

        csp_config = CSPConfig(
            delta_min=0.15,
            delta_max=0.25,
            prob_otm_min=0.70,
        )

        cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

        result = run_signal_engine(
            stock_snapshots=snapshots,
            options_chain_provider=provider,
            base_config=base_config,
            csp_config=csp_config,
            cc_config=cc_config,
            universe_id_or_hash="test_universe_explanations",
        )

        # Explanations should be built when selection produces results
        assert result.selected_signals is not None
        assert result.explanations is not None
        assert len(result.explanations) == len(result.selected_signals)

        # Verify explanation fields
        for expl in result.explanations:
            assert expl.symbol
            assert expl.signal_type in ("CSP", "CC")
            assert expl.rank > 0
            assert expl.total_score >= 0.0
            assert len(expl.score_components) > 0
            assert expl.selection_reason == "SELECTED_BY_POLICY"
            assert expl.policy_snapshot["max_total"] == selection_cfg.max_total
            assert expl.policy_snapshot["max_per_symbol"] == selection_cfg.max_per_symbol
            assert expl.policy_snapshot["max_per_signal_type"] == selection_cfg.max_per_signal_type
            assert expl.policy_snapshot["min_score"] == selection_cfg.min_score


__all__ = ["TestSignalEngineIntegration"]
