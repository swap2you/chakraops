# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS Live Data options chain provider. Implements OptionsChainProvider."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.options.providers.orats_client import (
    OratsAuthError,
    OratsClient,
    get_expirations,
    get_strikes_monthly,
)
from app.data.options_chain_provider import CHAIN_REQUEST_TIMEOUT
from app.models.option_context import OptionContext

logger = logging.getLogger(__name__)

# Canonical empty-chain reasons for diagnostics
REASON_EMPTY_RESPONSE = "empty_response"
REASON_NO_OPTIONS = "no_options"
REASON_INVALID_TICKER = "invalid_ticker"
REASON_DELAYED_DATA = "delayed_data"
REASON_AUTH_ERROR = "auth_error"
REASON_RATE_LIMIT = "rate_limit"


def _parse_date(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, date):
        return x
    s = str(x).strip()
    if len(s) >= 8 and s.replace("-", "").replace("/", "")[:8].isdigit():
        clean = s.replace("-", "").replace("/", "")[:8]
        try:
            return date(int(clean[:4]), int(clean[4:6]), int(clean[6:8]))
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        pass
    return None


def _row_to_contracts(row: Dict[str, Any], symbol: str, exp_str: str, right: str) -> Optional[Dict[str, Any]]:
    """Convert one ORATS strike row to our contract format for the given right (P or C)."""
    if right.upper() == "P":
        bid = row.get("putBidPrice")
        ask = row.get("putAskPrice")
        val = row.get("putValue")
        iv = row.get("putMidIv") or row.get("putBidIv") or row.get("putAskIv")
        oi = row.get("putOpenInterest")
        prob_otm = row.get("putProbOtm") or row.get("probOTM")
    else:
        bid = row.get("callBidPrice")
        ask = row.get("callAskPrice")
        val = row.get("callValue")
        iv = row.get("callMidIv") or row.get("callBidIv") or row.get("callAskIv")
        oi = row.get("callOpenInterest")
        prob_otm = row.get("callProbOtm") or row.get("probOTM")

    strike = row.get("strike")
    if strike is None:
        return None
    try:
        strike_f = float(strike)
    except (TypeError, ValueError):
        return None

    mid = None
    if bid is not None and ask is not None:
        try:
            mid = (float(bid) + float(ask)) / 2.0
        except (TypeError, ValueError):
            pass
    if mid is None and val is not None:
        try:
            mid = float(val)
        except (TypeError, ValueError):
            pass

    delta_raw = row.get("delta")
    delta_f = float(delta_raw) if delta_raw is not None else None
    prob_otm_f = float(prob_otm) if prob_otm is not None else None
    iv_rank_raw = row.get("iv_rank_100_day") or row.get("ivRank100d") or row.get("iv_percentile")
    iv_rank_f = float(iv_rank_raw) if iv_rank_raw is not None else None

    return {
        "strike": strike_f,
        "bid": float(bid) if bid is not None else None,
        "ask": float(ask) if ask is not None else None,
        "mid": mid,
        "delta": delta_f,
        "prob_otm": prob_otm_f,
        "iv_rank": iv_rank_f,
        "gamma": row.get("gamma"),
        "theta": row.get("theta"),
        "vega": row.get("vega"),
        "iv": float(iv) if iv is not None else None,
        "open_interest": int(oi) if oi is not None else None,
        "volume": row.get("putVolume") if right.upper() == "P" else row.get("callVolume"),
        "right": right.upper(),
        "expiry": exp_str,
        "expiration": exp_str,
        "dte": row.get("dte"),
        "symbol": symbol,
    }


class OratsOptionsChainProvider:
    """Options chain provider using ORATS Live Data API. Token from ORATS_API_TOKEN only."""

    def __init__(self, timeout: float = CHAIN_REQUEST_TIMEOUT) -> None:
        self.timeout = timeout
        self._client = OratsClient(timeout=timeout)
        self._expiration_cache: Dict[str, List[str]] = {}
        self._chain_cache: Dict[str, List[Dict[str, Any]]] = {}

    def get_expirations(self, symbol: str) -> List[date]:
        """Return expiration dates for symbol. Empty list on auth/rate limit; log and return [] on empty."""
        symbol = (symbol or "").upper()
        if not symbol:
            return []

        if symbol in self._expiration_cache:
            exp_strings = self._expiration_cache[symbol]
        else:
            try:
                raw = get_expirations(symbol, include_strikes=False, timeout=self.timeout)
            except OratsAuthError as e:
                logger.warning("ORATS get_expirations auth failed for %s: %s", symbol, e)
                return []
            except ValueError as e:
                if "rate limit" in str(e).lower():
                    logger.warning("ORATS get_expirations rate limit for %s", symbol)
                else:
                    logger.warning("ORATS get_expirations failed for %s: %s", symbol, e)
                return []

            if not raw:
                logger.info("ORATS get_expirations empty for %s (empty_response)", symbol)
                self._expiration_cache[symbol] = []
                return []

            exp_strings = []
            for item in raw:
                if isinstance(item, str):
                    exp_strings.append(item)
                elif isinstance(item, dict) and "expiration" in item:
                    exp_strings.append(str(item["expiration"]))
            self._expiration_cache[symbol] = exp_strings

        out: List[date] = []
        for exp_str in exp_strings:
            d = _parse_date(exp_str)
            if d:
                out.append(d)
        return sorted(out)

    def get_strikes(self, symbol: str, expiry: date) -> List[float]:
        """Return strike prices for symbol/expiry. Empty on auth/empty; log reason."""
        symbol = (symbol or "").upper()
        exp_str = expiry.strftime("%Y-%m-%d")
        try:
            rows = get_strikes_monthly(symbol, exp_str, timeout=self.timeout)
        except OratsAuthError as e:
            logger.warning("ORATS get_strikes auth failed for %s %s: %s", symbol, exp_str, e)
            return []
        except ValueError as e:
            logger.warning("ORATS get_strikes failed for %s %s: %s", symbol, exp_str, e)
            return []

        if not rows:
            logger.debug("ORATS get_strikes empty for %s %s", symbol, exp_str)
            return []
        strikes = sorted({float(r["strike"]) for r in rows if r.get("strike") is not None})
        return strikes

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Return contracts for symbol/expiry/right. Empty list on auth/empty; log reason."""
        symbol = (symbol or "").upper()
        right_upper = (right or "P").upper()
        if right_upper not in ("P", "C"):
            right_upper = "P"
        exp_str = expiry.strftime("%Y-%m-%d")
        cache_key = f"{symbol}:{exp_str}:{right_upper}"

        if cache_key in self._chain_cache:
            return self._chain_cache[cache_key]

        try:
            rows = get_strikes_monthly(symbol, exp_str, timeout=self.timeout)
        except OratsAuthError as e:
            logger.warning("ORATS get_chain auth failed for %s %s %s: %s", symbol, exp_str, right_upper, e)
            self._chain_cache[cache_key] = []
            return []
        except ValueError as e:
            logger.warning("ORATS get_chain failed for %s %s %s: %s", symbol, exp_str, right_upper, e)
            self._chain_cache[cache_key] = []
            return []

        if not rows:
            logger.debug("ORATS get_chain empty for %s %s %s", symbol, exp_str, right_upper)
            self._chain_cache[cache_key] = []
            return []

        out: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            c = _row_to_contracts(row, symbol, exp_str, right_upper)
            if c:
                out.append(c)
        self._chain_cache[cache_key] = out
        logger.debug("ORATS get_chain %s %s %s returned %d contracts", symbol, exp_str, right_upper, len(out))
        return out

    def get_full_chain(
        self,
        symbol: str,
        dte_min: int = 7,
        dte_max: int = 45,
    ) -> Dict[str, Any]:
        """Get full chain with DTE filtering. Returns {contracts, puts, calls, expirations, chain_status, error?}."""
        symbol = (symbol or "").upper()
        today = date.today()
        expirations = self.get_expirations(symbol)
        if not expirations:
            return {
                "symbol": symbol,
                "contracts": [],
                "puts": [],
                "calls": [],
                "expirations": [],
                "expiration_count": 0,
                "contract_count": 0,
                "chain_status": "no_expirations",
                "data_source": "live",
                "error": "No expirations from ORATS",
            }

        valid_exp = [d for d in expirations if dte_min <= (d - today).days <= dte_max]
        if not valid_exp:
            return {
                "symbol": symbol,
                "contracts": [],
                "puts": [],
                "calls": [],
                "expirations": [],
                "expiration_count": 0,
                "contract_count": 0,
                "chain_status": "no_expiry_in_dte_window",
                "data_source": "live",
                "error": f"No expirations in DTE [{dte_min}-{dte_max}]",
            }

        all_contracts: List[Dict[str, Any]] = []
        for d in valid_exp:
            puts = self.get_chain(symbol, d, "P")
            calls = self.get_chain(symbol, d, "C")
            for c in puts:
                c["expiration"] = d.strftime("%Y-%m-%d")
                all_contracts.append(c)
            for c in calls:
                c["expiration"] = d.strftime("%Y-%m-%d")
                all_contracts.append(c)

        exp_strs = sorted(set(c.get("expiration", "") for c in all_contracts if c.get("expiration")))
        puts_list = [c for c in all_contracts if c.get("right") == "P"]
        calls_list = [c for c in all_contracts if c.get("right") == "C"]

        return {
            "symbol": symbol,
            "expirations": exp_strs,
            "contracts": all_contracts,
            "puts": puts_list,
            "calls": calls_list,
            "expiration_count": len(exp_strs),
            "contract_count": len(all_contracts),
            "chain_status": "ok" if all_contracts else "empty_chain",
            "data_source": "live",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def healthcheck(self) -> Dict[str, Any]:
        """Check ORATS connectivity. Returns {ok, message, response_time_ms?}."""
        import time
        start = time.monotonic()
        elapsed_ms = 0.0
        try:
            self._client.get_summaries("SPY")
            elapsed_ms = (time.monotonic() - start) * 1000
            return {"ok": True, "message": f"ORATS OK ({elapsed_ms:.0f}ms)", "response_time_ms": elapsed_ms}
        except OratsAuthError as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning("ORATS healthcheck auth failed: %s", e)
            return {"ok": False, "message": f"ORATS auth failed: {e}", "response_time_ms": elapsed_ms}
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning("ORATS healthcheck failed: %s", e)
            return {"ok": False, "message": str(e), "response_time_ms": elapsed_ms}

    def clear_cache(self) -> None:
        self._expiration_cache.clear()
        self._chain_cache.clear()

    def get_option_context(self, symbol: str) -> OptionContext:
        """Build OptionContext with expected move, IV rank/percentile, term structure, skew, earnings, event flags.

        Fetches summaries (impliedMove, iv30d, iv90d, skewing), ivrank (ivRank1y, ivPct1y),
        and cores (daysToNextErn, nextErn). Handles missing endpoints or data gracefully;
        unhandled exceptions are not swallowed.
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return OptionContext(symbol="", raw={})

        raw: Dict[str, Any] = {}
        expected_move_1sd: Optional[float] = None
        iv_rank: Optional[float] = None
        iv_percentile: Optional[float] = None
        term_structure_slope: Optional[float] = None
        skew_metric: Optional[float] = None
        days_to_earnings: Optional[int] = None
        event_flags: List[str] = []

        # Summaries: impliedMove (1sd), iv30d, iv90d, skewing
        try:
            summaries = self._client.get_summaries(symbol)
            if summaries and isinstance(summaries[0], dict):
                s = summaries[0]
                raw["summaries"] = s
                implied_move = s.get("impliedMove")
                if implied_move is not None:
                    try:
                        expected_move_1sd = float(implied_move)
                    except (TypeError, ValueError):
                        pass
                iv30 = s.get("iv30d")
                iv90 = s.get("iv90d")
                if iv30 is not None and iv90 is not None:
                    try:
                        iv30_f = float(iv30)
                        iv90_f = float(iv90)
                        term_structure_slope = iv30_f - iv90_f
                    except (TypeError, ValueError):
                        pass
                skewing = s.get("skewing")
                if skewing is not None:
                    try:
                        skew_metric = float(skewing)
                    except (TypeError, ValueError):
                        pass
        except (OratsAuthError, ValueError) as e:
            logger.debug("ORATS get_option_context summaries for %s: %s", symbol, e)

        # IV rank: ivRank1y, ivPct1y
        try:
            ivrank_list = self._client.get_iv_rank(symbol)
            if ivrank_list and isinstance(ivrank_list[0], dict):
                r = ivrank_list[0]
                raw["ivrank"] = r
                rank = r.get("ivRank1y")
                pct = r.get("ivPct1y")
                if rank is not None:
                    try:
                        iv_rank = float(rank)
                    except (TypeError, ValueError):
                        pass
                if pct is not None:
                    try:
                        iv_percentile = float(pct)
                    except (TypeError, ValueError):
                        pass
        except (OratsAuthError, ValueError) as e:
            logger.debug("ORATS get_option_context ivrank for %s: %s", symbol, e)

        # Cores: daysToNextErn, nextErn (and optionally ivPctile1y if we prefer over ivrank)
        try:
            cores_list = self._client.get_cores(symbol)
            if cores_list and isinstance(cores_list[0], dict):
                c = cores_list[0]
                raw["cores"] = c
                dte = c.get("daysToNextErn")
                if dte is not None:
                    try:
                        days_to_earnings = int(dte)
                    except (TypeError, ValueError):
                        pass
                if iv_percentile is None:
                    pct = c.get("ivPctile1y")
                    if pct is not None:
                        try:
                            iv_percentile = float(pct)
                        except (TypeError, ValueError):
                            pass
        except (OratsAuthError, ValueError) as e:
            logger.debug("ORATS get_option_context cores for %s: %s", symbol, e)

        # Event proximity: FOMC, CPI, NFP — no calendar in repo; leave event_flags empty
        # unless we add a calendar or ORATS provides it

        return OptionContext(
            symbol=symbol,
            expected_move_1sd=expected_move_1sd,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            term_structure_slope=term_structure_slope,
            skew_metric=skew_metric,
            days_to_earnings=days_to_earnings,
            event_flags=event_flags,
            raw=raw,
        )


__all__ = ["OratsOptionsChainProvider"]
