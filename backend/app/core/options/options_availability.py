# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options availability diagnostics per symbol (Phase 8 fix).

Records per-symbol: expirations_found, contracts_found, reason when empty.
Does NOT change existing provider logic — only adds visibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List

from app.data.options_chain_provider import OptionsChainProvider


# Canonical reason codes for diagnostics
REASON_NO_EXPIRATIONS = "no_expirations_from_provider"
REASON_EMPTY_CHAIN = "empty_chain"
REASON_OK = "ok"
REASON_CHAIN_FETCH_ERROR = "chain_fetch_error"
REASON_NO_EXPIRY_IN_DTE_WINDOW = "no_expiry_in_dte_window"


@dataclass
class SymbolOptionsDiagnostic:
    """Per-symbol options availability diagnostic."""

    symbol: str
    expirations_found: int = 0
    contracts_found: int = 0  # total put + call raw contracts from provider
    put_contracts: int = 0
    call_contracts: int = 0
    reason: str = REASON_OK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "expirations_found": self.expirations_found,
            "contracts_found": self.contracts_found,
            "put_contracts": self.put_contracts,
            "call_contracts": self.call_contracts,
            "reason": self.reason,
        }


class OptionsAvailabilityRecorder:
    """Records options availability per symbol during a pipeline run."""

    def __init__(self) -> None:
        self._by_symbol: Dict[str, SymbolOptionsDiagnostic] = {}

    def record_expirations(self, symbol: str, count: int) -> None:
        """Record expirations count for symbol (call after get_expirations)."""
        sym = symbol.upper()
        if sym not in self._by_symbol:
            self._by_symbol[sym] = SymbolOptionsDiagnostic(symbol=sym)
        self._by_symbol[sym].expirations_found = count
        if count == 0:
            self._by_symbol[sym].reason = REASON_NO_EXPIRATIONS

    def record_chain(self, symbol: str, right: str, count: int) -> None:
        """Record chain contract count for symbol/right (call after get_chain)."""
        sym = symbol.upper()
        if sym not in self._by_symbol:
            self._by_symbol[sym] = SymbolOptionsDiagnostic(symbol=sym)
        d = self._by_symbol[sym]
        if right.upper() == "PUT":
            d.put_contracts += count
        else:
            d.call_contracts += count
        d.contracts_found = d.put_contracts + d.call_contracts
        if d.contracts_found == 0 and d.expirations_found > 0:
            d.reason = REASON_EMPTY_CHAIN

    def record_reason(self, symbol: str, reason: str) -> None:
        """Override reason for symbol (e.g. NO_EXPIRY_IN_DTE_WINDOW, CHAIN_FETCH_ERROR)."""
        sym = symbol.upper()
        if sym not in self._by_symbol:
            self._by_symbol[sym] = SymbolOptionsDiagnostic(symbol=sym)
        self._by_symbol[sym].reason = reason

    def get_diagnostics(self) -> List[Dict[str, Any]]:
        """Return list of per-symbol diagnostic dicts (symbol, expirations_found, contracts_found, reason)."""
        out: List[Dict[str, Any]] = []
        for sym in sorted(self._by_symbol.keys()):
            d = self._by_symbol[sym]
            out.append(d.to_dict())
        return out

    def get_symbols_with_options(self) -> List[str]:
        """Symbols that have at least one expiration and at least one contract (put or call)."""
        return [
            sym for sym, d in self._by_symbol.items()
            if d.expirations_found > 0 and d.contracts_found > 0
        ]

    def get_symbols_without_options(self) -> Dict[str, str]:
        """Symbol -> reason for symbols that have no usable options."""
        return {
            sym: d.reason
            for sym, d in self._by_symbol.items()
            if d.expirations_found == 0 or d.contracts_found == 0
        }


class DiagnosticsOptionsChainProvider(OptionsChainProvider):
    """Wraps an OptionsChainProvider and records per-symbol diagnostics."""

    def __init__(self, inner: OptionsChainProvider, recorder: OptionsAvailabilityRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def get_expirations(self, symbol: str) -> List[date]:
        result = self._inner.get_expirations(symbol)
        count = len(result) if result is not None else 0
        self._recorder.record_expirations(symbol, count)
        return result or []

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        result = self._inner.get_chain(symbol, expiry, right)
        count = len(result) if result is not None else 0
        self._recorder.record_chain(symbol, right, count)
        return result or []


__all__ = [
    "DiagnosticsOptionsChainProvider",
    "OptionsAvailabilityRecorder",
    "SymbolOptionsDiagnostic",
    "REASON_NO_EXPIRATIONS",
    "REASON_EMPTY_CHAIN",
    "REASON_OK",
    "REASON_CHAIN_FETCH_ERROR",
    "REASON_NO_EXPIRY_IN_DTE_WINDOW",
]
