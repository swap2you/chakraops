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
    """Return canonical decision_latest.json path. ONE source of truth."""
    if _DEFAULT_OUTPUT_DIR is not None:
        return _DEFAULT_OUTPUT_DIR / "decision_latest.json"
    return DECISION_STORE_PATH


def _decision_latest_path() -> Path:
    return get_decision_store_path()


class EvaluationStoreV2:
    """Single source of truth for DecisionArtifactV2. In-memory + disk with atomic write."""

    def __init__(self) -> None:
        self._artifact: Optional[DecisionArtifactV2] = None
        self._load_latest_from_disk()

    def _load_latest_from_disk(self) -> None:
        """Load decision_latest.json on startup if present and v2-compatible."""
        path = _decision_latest_path()
        logger.info("[EVAL_STORE_V2] DECISION_STORE_PATH=%s", path)
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
        """Atomic write: temp file then rename."""
        path = _decision_latest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(artifact.to_dict(), f, indent=2, default=str)
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

