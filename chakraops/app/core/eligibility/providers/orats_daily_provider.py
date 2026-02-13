# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS Daily Price History provider — production candle source for Phase 4 eligibility.

GET https://api.orats.io/datav2/hist/dailies
Full pull per symbol, ascending by tradeDate, slice last N client-side.
File cache: artifacts/candles_cache/<SYMBOL>.json (use if from today, else fetch and overwrite).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import requests

from app.core.orats.endpoints import BASE_DATAV2, url_hist_dailies

logger = logging.getLogger(__name__)

ORATS_DAILY_FIELDS = "tradeDate,openPx,hiPx,loPx,clsPx,stockVolume"
DEFAULT_LOOKBACK = 400
DEFAULT_TIMEOUT_SEC = 30.0


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ORATS row to {ts, open, high, low, close, volume}."""
    ts = row.get("tradeDate")
    if ts is None:
        return {"ts": None, "open": None, "high": None, "low": None, "close": None, "volume": None}
    if hasattr(ts, "isoformat"):
        ts = ts.isoformat()[:10] if ts else None
    else:
        ts = str(ts)[:10] if ts else None
    try:
        open_ = float(row.get("openPx") or row.get("open") or 0)
    except (TypeError, ValueError):
        open_ = None
    try:
        high = float(row.get("hiPx") or row.get("high") or 0)
    except (TypeError, ValueError):
        high = None
    try:
        low = float(row.get("loPx") or row.get("low") or 0)
    except (TypeError, ValueError):
        low = None
    try:
        close = float(row.get("clsPx") or row.get("close") or 0)
    except (TypeError, ValueError):
        close = None
    try:
        vol = int(float(row.get("stockVolume") or row.get("stockVolu") or row.get("volume") or 0))
    except (TypeError, ValueError):
        vol = None
    return {"ts": ts, "open": open_, "high": high, "low": low, "close": close, "volume": vol}


class OratsDailyProvider:
    """Production candle provider: ORATS hist/dailies + file cache (same-day reuse)."""

    def __init__(
        self,
        token: str | None = None,
        cache_dir: str | Path | None = None,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        if token is not None and (not token or not str(token).strip()):
            raise ValueError("ORATS token is required and must be non-empty")
        self._token: str | None = (token or "").strip() or None
        if cache_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            cache_dir = repo_root / "artifacts" / "candles_cache"
        self._cache_dir = Path(cache_dir)
        self._timeout_sec = timeout_sec

    def _get_token(self) -> str:
        if self._token:
            return self._token
        try:
            from app.core.config.orats_secrets import ORATS_API_TOKEN
            t = (ORATS_API_TOKEN or "").strip()
            if not t:
                raise ValueError("ORATS_API_TOKEN is missing or empty")
            return t
        except ImportError as e:
            raise ValueError("ORATS token not provided and orats_secrets not available") from e

    def _cache_path(self, symbol: str) -> Path:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir / f"{symbol.strip().upper()}.json"

    def _load_cache(self, symbol: str) -> List[Dict[str, Any]] | None:
        """Load cache if it exists and was written today. Return None if miss or stale."""
        path = self._cache_path(symbol)
        if not path.exists():
            return None
        try:
            stat = path.stat()
            # Compare date of file mtime to today (local date)
            if date.fromtimestamp(stat.st_mtime) != date.today():
                return None
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
            return None
        except Exception as e:
            logger.debug("[ORATS_DAILY] cache load failed for %s: %s", symbol, e)
            return None

    def _save_cache(self, symbol: str, rows: List[Dict[str, Any]]) -> None:
        path = self._cache_path(symbol)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=0, default=str)
        except Exception as e:
            logger.warning("[ORATS_DAILY] cache save failed for %s: %s", symbol, e)

    def get_daily(
        self,
        symbol: str,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> List[Dict[str, Any]]:
        """
        Return daily OHLCV candles for symbol. Each item: {ts, open, high, low, close, volume}.
        Uses file cache if from today; else fetches from ORATS and overwrites cache.
        Sorts ascending by tradeDate and returns last `lookback` rows.
        """
        sym = (symbol or "").strip().upper()
        if not sym:
            return []

        token = self._get_token()

        cached = self._load_cache(sym)
        if cached is not None:
            total = len(cached)
            out = cached[-lookback:] if lookback > 0 else cached
            logger.info(
                "[ORATS_DAILY] symbol=%s total_rows=%s returned_rows=%s (cache)",
                sym, total, len(out),
            )
            return out

        url = url_hist_dailies(BASE_DATAV2)
        params: Dict[str, str] = {
            "token": token,
            "ticker": sym,
            "fields": ORATS_DAILY_FIELDS,
        }
        try:
            resp = requests.get(url, params=params, timeout=self._timeout_sec)
        except requests.RequestException as e:
            logger.error("[ORATS_DAILY] symbol=%s request failed: %s", sym, e)
            return []

        if resp.status_code != 200:
            logger.error(
                "[ORATS_DAILY] symbol=%s HTTP %s %s",
                sym, resp.status_code, (resp.text or "")[:300],
            )
            return []

        try:
            raw: Any = resp.json()
        except Exception as e:
            logger.error("[ORATS_DAILY] symbol=%s invalid JSON: %s", sym, e)
            return []

        rows: List[Dict[str, Any]] = []
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and "data" in raw:
            d = raw.get("data")
            if isinstance(d, list):
                rows = d

        if not rows:
            logger.info("[ORATS_DAILY] symbol=%s empty response", sym)
            return []

        # Sort ascending by tradeDate
        def _sort_key(r: Dict[str, Any]) -> str:
            t = r.get("tradeDate")
            if t is None:
                return ""
            return str(t)[:10]

        rows = sorted(rows, key=_sort_key)
        normalized = [_normalize_row(r) for r in rows]
        self._save_cache(sym, normalized)

        total = len(normalized)
        out = normalized[-lookback:] if lookback > 0 else normalized
        logger.info(
            "[ORATS_DAILY] symbol=%s total_rows=%s returned_rows=%s",
            sym, total, len(out),
        )
        return out
