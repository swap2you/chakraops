# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.6: EvaluationStoreV2 — single source of truth for DecisionArtifactV2."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

# Phase 11.2: Keep last N decision history files per symbol (configurable; DECISION_ARCHIVE_MAX overrides)
DECISION_HISTORY_KEEP = int(os.getenv("DECISION_ARCHIVE_MAX", os.getenv("DECISION_HISTORY_KEEP", "50")))

from app.core.eval.decision_artifact_v2 import (
    CandidateRow,
    DecisionArtifactV2,
    EarningsInfo,
    GateEvaluation,
    SymbolDiagnosticsDetails,
    SymbolEvalSummary,
)

logger = logging.getLogger(__name__)

# Phase 7.6.1: Canonical path — <REPO_ROOT>/out/decision_latest.json (ONE source of truth)
# __file__ = chakraops/app/core/eval/evaluation_store_v2.py -> parents[4] = repo root (ChakraOps)
_REPO_ROOT = Path(__file__).resolve().parents[4]
DECISION_STORE_PATH = (_REPO_ROOT / "out" / "decision_latest.json").resolve()

_DEFAULT_OUTPUT_DIR: Optional[Path] = None
_LOCK = threading.RLock()


def _get_output_dir() -> Path:
    global _DEFAULT_OUTPUT_DIR
    if _DEFAULT_OUTPUT_DIR is not None:
        return _DEFAULT_OUTPUT_DIR
    return DECISION_STORE_PATH.parent


def set_output_dir(path: Path) -> None:
    """Override output directory (for tests)."""
    global _DEFAULT_OUTPUT_DIR
    _DEFAULT_OUTPUT_DIR = Path(path).resolve()


def reset_output_dir() -> None:
    """Reset output dir to canonical (for test isolation)."""
    global _DEFAULT_OUTPUT_DIR
    _DEFAULT_OUTPUT_DIR = None


def get_decision_store_path() -> Path:
    """Return canonical decision_latest.json path (write target). ONE source of truth."""
    if _DEFAULT_OUTPUT_DIR is not None:
        return _DEFAULT_OUTPUT_DIR / "decision_latest.json"
    return DECISION_STORE_PATH


def _frozen_path() -> Path:
    """Path for EOD frozen snapshot (decision_frozen.json). Same dir as canonical store."""
    return get_decision_store_path().parent / "decision_frozen.json"


def get_active_decision_path(market_phase: Optional[str] = None) -> Path:
    """
    Path to read for UI/API: when market CLOSED and frozen exists, use decision_frozen.json;
    else use decision_latest.json. Tests (set_output_dir) always use decision_latest.
    """
    if _DEFAULT_OUTPUT_DIR is not None:
        return get_decision_store_path()
    if market_phase is None:
        try:
            from app.market.market_hours import get_market_phase
            market_phase = get_market_phase() or "OPEN"
        except Exception:
            market_phase = "OPEN"
    if (market_phase or "OPEN").upper() != "OPEN":
        frozen = _frozen_path()
        if frozen.exists():
            return frozen
    return get_decision_store_path()


def _decision_latest_path() -> Path:
    return get_decision_store_path()


def _active_read_path() -> Path:
    """Path to read from disk for current request (latest or frozen)."""
    return get_active_decision_path()


def _history_dir() -> Path:
    """Phase 11.2: Directory for decision history: out/decisions (per-symbol subdirs)."""
    return _get_output_dir() / "decisions"


def _history_path(symbol: str, run_id: str) -> Path:
    """Phase 11.2: Path for a specific run: out/decisions/{symbol}/{run_id}.json."""
    sym_upper = (symbol or "").strip().upper()
    if not sym_upper or not run_id:
        raise ValueError("symbol and run_id required")
    return _history_dir() / sym_upper / f"{run_id}.json"


def get_decision_by_run(symbol: str, run_id: str) -> Optional[DecisionArtifactV2]:
    """Phase 11.2: Load decision artifact from history by symbol and run_id. Returns None if missing."""
    try:
        path = _history_path(symbol, run_id)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("metadata") or data
        if meta.get("artifact_version") == "v2":
            return DecisionArtifactV2.from_dict(data)
        return None
    except Exception as e:
        logger.warning("[EVAL_STORE_V2] Failed to load history %s: %s", path, e)
        return None


class EvaluationStoreV2:
    """Single source of truth for DecisionArtifactV2. In-memory + disk with atomic write."""

    def __init__(self) -> None:
        self._artifact: Optional[DecisionArtifactV2] = None
        self._load_latest_from_disk()

    def _load_latest_from_disk(self) -> None:
        """Load active artifact (decision_latest or decision_frozen) from disk if present and v2-compatible."""
        path = _active_read_path()
        logger.debug("[EVAL_STORE_V2] Reading from %s", path)
        if not path.exists():
            logger.info("[EVAL_STORE_V2] No artifact at path (v2 not loaded)")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("metadata") or data
            version = meta.get("artifact_version")
            if version == "v2":
                self._artifact = DecisionArtifactV2.from_dict(data)
                logger.info("[EVAL_STORE_V2] Loaded v2 from %s", path)
            else:
                logger.info("[EVAL_STORE_V2] Artifact at path not v2 (skipped). Run evaluation to generate v2.")
        except Exception as e:
            logger.warning("[EVAL_STORE_V2] Failed to load %s: %s", path, e)

    def reload_from_disk(self) -> None:
        """Reload artifact from disk (canonical path). Use on every request to avoid stale cache."""
        with _LOCK:
            self._load_latest_from_disk()

    def get_latest(self) -> Optional[DecisionArtifactV2]:
        """Return latest artifact or None."""
        with _LOCK:
            return self._artifact

    def set_latest(self, artifact: DecisionArtifactV2) -> None:
        """Store in memory and write to disk (atomic write)."""
        with _LOCK:
            self._artifact = artifact
            self._write_to_disk(artifact)

    def _write_to_disk(self, artifact: DecisionArtifactV2) -> None:
        """Atomic write: temp file then rename. Phase 11.2: Also write history + apply retention."""
        path = _decision_latest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        try:
            data = artifact.to_dict()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(path)  # replace handles existing file (Windows)
            logger.info("[EVAL_STORE_V2] Wrote %s", path)
        except Exception as e:
            logger.exception("[EVAL_STORE_V2] Failed to write %s: %s", path, e)
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            return
        # Phase 11.2: Write history per symbol and apply retention
        self._write_history(artifact)
        for sym in getattr(artifact, "symbols", []) or []:
            s = (getattr(sym, "symbol", "") or "").strip().upper()
            if s:
                self._apply_retention(s)

    def _write_history(self, artifact: DecisionArtifactV2) -> None:
        """Phase 11.2: Write full artifact to out/decisions/{symbol}/{run_id}.json for each symbol."""
        meta = getattr(artifact, "metadata", None) or {}
        run_id = meta.get("run_id")
        if not run_id:
            return
        data = artifact.to_dict()
        symbols = getattr(artifact, "symbols", []) or []
        for sym in symbols:
            s = (getattr(sym, "symbol", "") or "").strip().upper()
            if not s:
                continue
            try:
                hist_path = _history_path(s, run_id)
                hist_path.parent.mkdir(parents=True, exist_ok=True)
                with open(hist_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str)
                    f.flush()
                    os.fsync(f.fileno())
                logger.debug("[EVAL_STORE_V2] Wrote history %s", hist_path)
            except Exception as e:
                logger.warning("[EVAL_STORE_V2] Failed to write history %s/%s: %s", s, run_id, e)

    def _apply_retention(self, symbol: str) -> None:
        """Phase 11.2: Keep last DECISION_HISTORY_KEEP files per symbol; delete oldest beyond N."""
        sym_dir = _history_dir() / symbol.strip().upper()
        if not sym_dir.exists() or not sym_dir.is_dir():
            return
        files: List[tuple[float, Path]] = []
        for p in sym_dir.iterdir():
            if p.suffix == ".json" and p.is_file():
                try:
                    mtime = p.stat().st_mtime
                    files.append((mtime, p))
                except OSError:
                    pass
        if len(files) <= DECISION_HISTORY_KEEP:
            return
        files.sort(key=lambda x: x[0], reverse=True)  # newest first
        for mtime, p in files[DECISION_HISTORY_KEEP:]:
            try:
                p.unlink()
                logger.debug("[EVAL_STORE_V2] Retained: removed %s", p)
            except OSError as e:
                logger.warning("[EVAL_STORE_V2] Failed to remove %s: %s", p, e)

    def get_symbol(
        self,
        symbol: str,
    ) -> Optional[tuple[SymbolEvalSummary, List[CandidateRow], List[GateEvaluation], Optional[EarningsInfo], Optional[SymbolDiagnosticsDetails]]]:
        """Get symbol eval + candidates + gates + earnings + diagnostics_details. Returns None if not in store."""
        with _LOCK:
            if not self._artifact:
                return None
            sym_upper = symbol.strip().upper()
            summary: Optional[SymbolEvalSummary] = None
            for s in self._artifact.symbols:
                if (s.symbol or "").strip().upper() == sym_upper:
                    summary = s
                    break
            if not summary:
                return None
            candidates = self._artifact.candidates_by_symbol.get(sym_upper, [])
            gates = self._artifact.gates_by_symbol.get(sym_upper, [])
            earnings = self._artifact.earnings_by_symbol.get(sym_upper)
            diagnostics_details = self._artifact.diagnostics_by_symbol.get(sym_upper)
            return (summary, candidates, gates, earnings, diagnostics_details)


def prune_decision_archives() -> Dict[str, Any]:
    """Prune all symbol directories under out/decisions to at most DECISION_HISTORY_KEEP files each. Safe to call repeatedly."""
    removed = 0
    symbols_affected: List[str] = []
    hist = _history_dir()
    if not hist.exists() or not hist.is_dir():
        return {"removed": 0, "symbols_affected": [], "max_per_symbol": DECISION_HISTORY_KEEP}
    for sym_dir in hist.iterdir():
        if not sym_dir.is_dir():
            continue
        sym = sym_dir.name
        files: List[tuple[float, Path]] = []
        for p in sym_dir.iterdir():
            if p.suffix == ".json" and p.is_file():
                try:
                    files.append((p.stat().st_mtime, p))
                except OSError:
                    pass
        if len(files) <= DECISION_HISTORY_KEEP:
            continue
        files.sort(key=lambda x: x[0], reverse=True)
        for _mtime, p in files[DECISION_HISTORY_KEEP:]:
            try:
                p.unlink()
                removed += 1
            except OSError as e:
                logger.warning("[EVAL_STORE_V2] Prune failed %s: %s", p, e)
        symbols_affected.append(sym)
    return {"removed": removed, "symbols_affected": symbols_affected, "max_per_symbol": DECISION_HISTORY_KEEP}


# Singleton instance
_store: Optional[EvaluationStoreV2] = None
_store_lock = threading.Lock()


def get_evaluation_store_v2() -> EvaluationStoreV2:
    """Return singleton EvaluationStoreV2."""
    global _store
    with _store_lock:
        if _store is None:
            _store = EvaluationStoreV2()
        return _store

