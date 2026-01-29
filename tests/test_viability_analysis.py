"""Tests for Signal Viability Analysis (Phase 7.6)."""

import json
from datetime import date, datetime

import pytest

from app.ui.viability_analysis import (
    SymbolViability,
    analyze_signal_viability,
    _classify_primary_blockage,
    _check_iv_available,
    _count_calls_scanned,
    _count_expiries_in_dte_window,
    _count_puts_scanned,
)


def test_symbol_viability():
    """Test SymbolViability dataclass."""
    viability = SymbolViability(
        symbol="AAPL",
        expiries_in_dte_window=3,
        puts_scanned=5,
        calls_scanned=2,
        iv_available=True,
        primary_blockage="VIABLE",
    )
    assert viability.symbol == "AAPL"
    assert viability.expiries_in_dte_window == 3
    assert viability.puts_scanned == 5
    assert viability.calls_scanned == 2
    assert viability.iv_available is True
    assert viability.primary_blockage == "VIABLE"


def test_count_expiries_in_dte_window():
    """Test expiry counting."""
    candidates = [
        {"symbol": "AAPL", "expiry": "2026-02-20"},
        {"symbol": "AAPL", "expiry": "2026-02-20"},  # Duplicate
        {"symbol": "AAPL", "expiry": "2026-02-27"},
        {"symbol": "MSFT", "expiry": "2026-02-20"},
    ]
    
    assert _count_expiries_in_dte_window("AAPL", candidates) == 2
    assert _count_expiries_in_dte_window("MSFT", candidates) == 1
    assert _count_expiries_in_dte_window("GOOGL", candidates) == 0


def test_count_puts_scanned():
    """Test PUT counting."""
    candidates = [
        {"symbol": "AAPL", "signal_type": "CSP", "option_right": "PUT"},
        {"symbol": "AAPL", "signal_type": {"value": "CSP"}, "option_right": "PUT"},
        {"symbol": "AAPL", "signal_type": "CC", "option_right": "CALL"},
        {"symbol": "MSFT", "signal_type": "CSP", "option_right": "PUT"},
    ]
    
    assert _count_puts_scanned("AAPL", candidates) == 2
    assert _count_puts_scanned("MSFT", candidates) == 1
    assert _count_puts_scanned("GOOGL", candidates) == 0


def test_count_calls_scanned():
    """Test CALL counting."""
    candidates = [
        {"symbol": "AAPL", "signal_type": "CC", "option_right": "CALL"},
        {"symbol": "AAPL", "signal_type": {"value": "CC"}, "option_right": "CALL"},
        {"symbol": "AAPL", "signal_type": "CSP", "option_right": "PUT"},
        {"symbol": "MSFT", "signal_type": "CC", "option_right": "CALL"},
    ]
    
    assert _count_calls_scanned("AAPL", candidates) == 2
    assert _count_calls_scanned("MSFT", candidates) == 1
    assert _count_calls_scanned("GOOGL", candidates) == 0


def test_check_iv_available():
    """Test IV availability check."""
    candidates = [
        {"symbol": "AAPL", "iv": None},
        {"symbol": "AAPL", "iv": 0.0},
        {"symbol": "AAPL", "iv": 0.25},
        {"symbol": "MSFT", "iv": None},
    ]
    
    assert _check_iv_available("AAPL", candidates) is True
    assert _check_iv_available("MSFT", candidates) is False
    assert _check_iv_available("GOOGL", candidates) is False


def test_classify_primary_blockage_viable():
    """Test classification when symbol has selected signals."""
    snapshot = {
        "selected_signals": [
            {
                "scored": {
                    "candidate": {
                        "symbol": "AAPL",
                    }
                }
            }
        ],
    }
    
    blockage = _classify_primary_blockage("AAPL", snapshot, 3, 5, 2)
    assert blockage == "VIABLE"


def test_classify_primary_blockage_data_unavailable():
    """Test classification for data unavailable."""
    snapshot = {
        "exclusions": [
            {
                "symbol": "AAPL",
                "rule": "CHAIN_FETCH_ERROR",
                "stage": "CHAIN_FETCH",
            }
        ],
    }
    
    blockage = _classify_primary_blockage("AAPL", snapshot, 0, 0, 0)
    assert blockage == "DATA_UNAVAILABLE"


def test_classify_primary_blockage_no_expiries():
    """Test classification for no expiries in DTE window."""
    snapshot = {
        "exclusions": [
            {
                "symbol": "AAPL",
                "rule": "NO_EXPIRY_IN_DTE_WINDOW",
                "stage": "CSP_GENERATION",
            }
        ],
    }
    
    blockage = _classify_primary_blockage("AAPL", snapshot, 0, 0, 0)
    assert blockage == "NO_EXPIRIES_IN_DTE"


def test_classify_primary_blockage_no_strikes():
    """Test classification for no strikes matching delta."""
    snapshot = {
        "exclusions": [
            {
                "symbol": "AAPL",
                "rule": "NO_STRIKES_IN_DELTA_RANGE",
                "stage": "CSP_GENERATION",
            }
        ],
    }
    
    blockage = _classify_primary_blockage("AAPL", snapshot, 3, 0, 0)
    assert blockage == "NO_STRIKES_MATCHING_DELTA"


def test_classify_primary_blockage_score_too_low():
    """Test classification for score too low."""
    snapshot = {
        "coverage_summary": {
            "by_symbol": {
                "AAPL": {
                    "generation": 5,
                    "scoring": 3,
                    "selection": 0,
                }
            }
        },
    }
    
    blockage = _classify_primary_blockage("AAPL", snapshot, 3, 5, 0)
    assert blockage == "SCORE_TOO_LOW"


def test_classify_primary_blockage_config_cap():
    """Test classification for config cap."""
    snapshot = {
        "coverage_summary": {
            "by_symbol": {
                "AAPL": {
                    "generation": 5,
                    "scoring": 3,
                    "selection": 0,
                }
            }
        },
        "near_misses": [
            {
                "symbol": "AAPL",
                "failed_rule": "max_per_symbol",
            }
        ],
    }
    
    blockage = _classify_primary_blockage("AAPL", snapshot, 3, 5, 0)
    assert blockage == "CONFIG_CAP"


def test_analyze_signal_viability_empty_snapshot():
    """Test analysis with empty snapshot."""
    snapshot = {}
    
    result = analyze_signal_viability(snapshot)
    assert len(result) == 0


def test_analyze_signal_viability_with_candidates():
    """Test analysis with candidates."""
    snapshot = {
        "candidates": [
            {"symbol": "AAPL", "expiry": "2026-02-20", "signal_type": "CSP", "iv": 0.25},
            {"symbol": "AAPL", "expiry": "2026-02-27", "signal_type": "CC", "iv": 0.30},
            {"symbol": "MSFT", "expiry": "2026-02-20", "signal_type": "CSP", "iv": None},
        ],
        "selected_signals": [
            {
                "scored": {
                    "candidate": {
                        "symbol": "AAPL",
                    }
                }
            }
        ],
    }
    
    result = analyze_signal_viability(snapshot)
    
    assert len(result) == 2
    
    aapl = next((v for v in result if v.symbol == "AAPL"), None)
    assert aapl is not None
    assert aapl.expiries_in_dte_window == 2
    assert aapl.puts_scanned == 1
    assert aapl.calls_scanned == 1
    assert aapl.iv_available is True
    assert aapl.primary_blockage == "VIABLE"
    
    msft = next((v for v in result if v.symbol == "MSFT"), None)
    assert msft is not None
    assert msft.expiries_in_dte_window == 1
    assert msft.puts_scanned == 1
    assert msft.calls_scanned == 0
    assert msft.iv_available is False


def test_analyze_signal_viability_does_not_mutate_snapshot():
    """Test that analysis does not mutate snapshot."""
    snapshot = {
        "candidates": [
            {"symbol": "AAPL", "expiry": "2026-02-20", "signal_type": "CSP"},
        ],
    }
    snapshot_copy = json.loads(json.dumps(snapshot))  # Deep copy
    
    analyze_signal_viability(snapshot)
    
    # Snapshot should be unchanged
    assert snapshot == snapshot_copy


def test_analyze_signal_viability_with_exclusions():
    """Test analysis with exclusions."""
    snapshot = {
        "exclusions": [
            {
                "symbol": "AAPL",
                "rule": "CHAIN_FETCH_ERROR",
                "stage": "CHAIN_FETCH",
            },
            {
                "symbol": "MSFT",
                "rule": "NO_STRIKES_IN_DELTA_RANGE",
                "stage": "CSP_GENERATION",
            },
        ],
    }
    
    result = analyze_signal_viability(snapshot)
    
    assert len(result) == 2
    
    aapl = next((v for v in result if v.symbol == "AAPL"), None)
    assert aapl is not None
    assert aapl.primary_blockage == "DATA_UNAVAILABLE"
    
    msft = next((v for v in result if v.symbol == "MSFT"), None)
    assert msft is not None
    assert msft.primary_blockage == "NO_STRIKES_MATCHING_DELTA"


def test_analyze_signal_viability_with_coverage_summary():
    """Test analysis with coverage summary."""
    snapshot = {
        "coverage_summary": {
            "by_symbol": {
                "AAPL": {
                    "generation": 5,
                    "scoring": 3,
                    "selection": 0,
                },
                "MSFT": {
                    "generation": 2,
                    "scoring": 2,
                    "selection": 1,
                },
            }
        },
        "selected_signals": [
            {
                "scored": {
                    "candidate": {
                        "symbol": "MSFT",
                    }
                }
            }
        ],
    }
    
    result = analyze_signal_viability(snapshot)
    
    assert len(result) == 2
    
    aapl = next((v for v in result if v.symbol == "AAPL"), None)
    assert aapl is not None
    assert aapl.primary_blockage == "SCORE_TOO_LOW"
    
    msft = next((v for v in result if v.symbol == "MSFT"), None)
    assert msft is not None
    assert msft.primary_blockage == "VIABLE"


__all__ = [
    "test_symbol_viability",
    "test_count_expiries_in_dte_window",
    "test_count_puts_scanned",
    "test_count_calls_scanned",
    "test_check_iv_available",
    "test_classify_primary_blockage_viable",
    "test_classify_primary_blockage_data_unavailable",
    "test_classify_primary_blockage_no_expiries",
    "test_classify_primary_blockage_no_strikes",
    "test_classify_primary_blockage_score_too_low",
    "test_classify_primary_blockage_config_cap",
    "test_analyze_signal_viability_empty_snapshot",
    "test_analyze_signal_viability_with_candidates",
    "test_analyze_signal_viability_does_not_mutate_snapshot",
    "test_analyze_signal_viability_with_exclusions",
    "test_analyze_signal_viability_with_coverage_summary",
]
