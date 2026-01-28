from __future__ import annotations

"""Decision snapshot JSON contract (Phase 4B Step 2).

This module creates a JSON-serializable snapshot of a SignalRunResult.
It does NOT modify generation, scoring, selection, or explainability behavior.

The snapshot is a pure data structure that preserves all information
from the engine run in a deterministic, serializable format.
"""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from app.signals.engine import SignalRunResult


@dataclass(frozen=True)
class DecisionSnapshot:
    """JSON-serializable snapshot of a signal engine run decision.

    All fields are deterministic and can be serialized to JSON without
    custom encoders. Datetimes are ISO strings, dataclasses are dicts.
    """

    as_of: str  # ISO datetime string
    universe_id_or_hash: str
    stats: Dict[str, int]
    candidates: List[Dict[str, Any]]
    scored_candidates: List[Dict[str, Any]] | None
    selected_signals: List[Dict[str, Any]] | None
    explanations: List[Dict[str, Any]] | None


def _convert_datetime_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO string for JSON serialization."""
    return dt.isoformat()


def _convert_to_json_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable types.
    
    Handles:
    - datetime -> ISO string
    - date -> ISO string
    - dataclasses -> dicts
    - lists -> lists with converted elements
    - dicts -> dicts with converted values
    - enums -> their values (handled by asdict)
    """
    if obj is None:
        return None
    
    if isinstance(obj, datetime):
        return obj.isoformat()
    
    if isinstance(obj, date):
        return obj.isoformat()
    
    # Check if it's a dataclass (but not a dict or list)
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _convert_to_json_serializable(v) for k, v in asdict(obj).items()}
    
    if isinstance(obj, list):
        return [_convert_to_json_serializable(item) for item in obj]
    
    if isinstance(obj, dict):
        return {k: _convert_to_json_serializable(v) for k, v in obj.items()}
    
    # Primitive types (str, int, float, bool) pass through
    return obj


def _convert_list_of_dataclasses(lst: List[Any] | None) -> List[Dict[str, Any]] | None:
    """Convert a list of dataclasses to a list of dicts with JSON-serializable values."""
    if lst is None:
        return None
    return [_convert_to_json_serializable(item) for item in lst]


def build_decision_snapshot(result: "SignalRunResult") -> DecisionSnapshot:
    """Build a JSON-serializable snapshot from a SignalRunResult.

    Preserves all data and ordering from the result. Converts:
    - datetime -> ISO string
    - dataclasses -> dicts (via asdict)
    - enums -> their values (handled by asdict)

    Args:
        result: SignalRunResult from run_signal_engine

    Returns:
        DecisionSnapshot with all fields converted to JSON-serializable types
    """
    # Convert datetime to ISO string
    as_of_iso = _convert_datetime_to_iso(result.as_of)

    # Convert lists of dataclasses to lists of dicts
    candidates_dicts = _convert_list_of_dataclasses(result.candidates)
    scored_candidates_dicts = _convert_list_of_dataclasses(result.scored_candidates)
    selected_signals_dicts = _convert_list_of_dataclasses(result.selected_signals)
    explanations_dicts = _convert_list_of_dataclasses(result.explanations)

    return DecisionSnapshot(
        as_of=as_of_iso,
        universe_id_or_hash=result.universe_id_or_hash,
        stats=result.stats.copy(),  # Already a dict, just copy
        candidates=candidates_dicts or [],
        scored_candidates=scored_candidates_dicts,
        selected_signals=selected_signals_dicts,
        explanations=explanations_dicts,
    )


__all__ = ["DecisionSnapshot", "build_decision_snapshot"]
