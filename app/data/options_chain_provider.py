# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options chain provider abstraction (Phase 5). Fail fast, short timeouts, no retries."""

from __future__ import annotations

import csv
import io
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Timeout for all provider calls; retries=0 by default
CHAIN_REQUEST_TIMEOUT = 5.0


class OptionsChainProvider(ABC):
    """Interface for options expirations and chain data. Implementations must fail fast."""

    @abstractmethod
    def get_expirations(self, symbol: str) -> List[date]:
        """Return expiration dates for symbol. Empty list on failure -> chain_unavailable."""
        ...

    @abstractmethod
    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Return list of contract records for symbol/expiry/right.

        Each record must have: strike, bid, ask, delta, iv (or None).
        Optional: volume, open_interest (or oi). Empty list on failure.
        """
        ...


class ThetaDataOptionsChainProvider(OptionsChainProvider):
    """Theta REST (localhost:25503/v3). Short timeout, no retries. Returns [] on any error."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = CHAIN_REQUEST_TIMEOUT,
    ) -> None:
        import os
        self.base_url = (base_url or os.getenv("THETA_REST_URL", "http://127.0.0.1:25503/v3")).rstrip("/")
        self.timeout = timeout

    def get_expirations(self, symbol: str) -> List[date]:
        try:
            import httpx
            # Theta often exposes expirations via expirations or snapshot; try common path
            url = f"{self.base_url}/list/expirations"
            params: Dict[str, Any] = {"root": (symbol or "").upper()}
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(url, params=params)
                if r.status_code != 200:
                    return []
                # Accept JSON list of YYYYMMDD or CSV
                ct = (r.headers.get("content-type") or "").lower()
                if "json" in ct:
                    data = r.json()
                    if isinstance(data, list):
                        return [_parse_date_any(x) for x in data if _parse_date_any(x) is not None]
                    if isinstance(data, dict) and "expirations" in data:
                        return [_parse_date_any(x) for x in data["expirations"] if _parse_date_any(x) is not None]
                    return []
                text = r.text.strip()
                if not text:
                    return []
                out: List[date] = []
                for line in text.splitlines():
                    d = _parse_date_any(line.strip())
                    if d is not None:
                        out.append(d)
                return out
        except Exception as e:
            logger.debug("[OptionsChain] get_expirations failed for %s: %s", symbol, e)
            return []

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        try:
            import httpx
            exp_str = expiry.strftime("%Y%m%d")
            root = (symbol or "").upper()
            # Theta bulk_snapshot/option/greeks returns CSV with strike, bid, ask, delta, implied_vol, etc.
            path = "/bulk_snapshot/option/greeks"
            params: Dict[str, Any] = {"root": root, "exp": exp_str}
            if right:
                params["right"] = right.upper() if right.upper() in ("P", "C") else right
            url = f"{self.base_url}{path}"
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(url, params=params)
                if r.status_code != 200:
                    return []
                rows = _parse_csv_rows(r.text)
                if not rows:
                    return []
                header = rows[0]
                header_lower = [h.lower() if isinstance(h, str) else "" for h in header]
                def col(name: str) -> int:
                    for n in name.split("|"):
                        nlo = n.strip().lower()
                        for i, h in enumerate(header_lower):
                            if h == nlo or nlo in h:
                                return i
                    return -1
                def val(row: List[str], c: int, f=float) -> Any:
                    if c < 0 or c >= len(row):
                        return None
                    s = row[c].strip()
                    if not s:
                        return None
                    try:
                        return f(s)
                    except (TypeError, ValueError):
                        return None
                out: List[Dict[str, Any]] = []
                for row in rows[1:]:
                    if len(row) < 2:
                        continue
                    strike_col = col("strike|strike_price")
                    bid_col = col("bid")
                    ask_col = col("ask")
                    delta_col = col("delta")
                    iv_col = col("implied_vol|iv")
                    vol_col = col("volume")
                    oi_col = col("open_interest|oi|open interest")
                    strike = val(row, strike_col) if strike_col >= 0 else None
                    if strike is None and strike_col < 0:
                        # Theta sometimes uses strike in 1/10 cent
                        for i, h in enumerate(header_lower):
                            if "strike" in h and i < len(row):
                                try:
                                    strike = float(row[i]) / 1000.0 if float(row[i]) > 1000 else float(row[i])
                                except (TypeError, ValueError):
                                    pass
                                break
                    if strike is None:
                        continue
                    bid = val(row, bid_col)
                    ask = val(row, ask_col)
                    delta = val(row, delta_col)
                    iv = val(row, iv_col)
                    vol = val(row, vol_col, int) if vol_col >= 0 else None
                    oi = val(row, oi_col, int) if oi_col >= 0 else None
                    out.append({
                        "strike": strike,
                        "bid": bid,
                        "ask": ask,
                        "delta": delta,
                        "iv": iv,
                        "volume": vol,
                        "open_interest": oi,
                    })
                return out
        except Exception as e:
            logger.debug("[OptionsChain] get_chain failed for %s %s %s: %s", symbol, expiry, right, e)
            return []


def _parse_date_any(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    s = str(x).strip()
    if len(s) >= 8 and s.isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        pass
    return None


def _parse_csv_rows(text: str) -> List[List[str]]:
    rows: List[List[str]] = []
    try:
        for row in csv.reader(io.StringIO(text)):
            rows.append(row)
    except csv.Error:
        pass
    return rows


__all__ = [
    "OptionsChainProvider",
    "ThetaDataOptionsChainProvider",
    "CHAIN_REQUEST_TIMEOUT",
]
