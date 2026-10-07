# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Signal generation package for CSP and CC candidates."""

from app.signals.models import (
    CCConfig,
    CSPConfig,
    ExclusionReason,
    ExplanationItem,
    SignalCandidate,
    SignalEngineConfig,
    SignalType,
)
from app.signals.engine import SignalRunResult, run_signal_engine
from app.signals.utils import calc_dte, mid, spread_pct

__all__ = [
    "SignalType",
    "SignalCandidate",
    "ExplanationItem",
    "ExclusionReason",
    "SignalEngineConfig",
    "CSPConfig",
    "CCConfig",
    "SignalRunResult",
    "run_signal_engine",
    "calc_dte",
    "mid",
    "spread_pct",
]
