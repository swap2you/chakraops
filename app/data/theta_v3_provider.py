# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ThetaData v3 provider using snapshot_ohlc for complete chain retrieval.

Key endpoint: /option/snapshot/ohlc
- Called WITHOUT strike parameter to get all contracts at once
- Use expiration='*' or omit expiration to fetch all expirations
- Returns complete chain with bid, ask, open, high, low, close, Greeks

This replaces per-strike fetching which returned empty results.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.settings import (
    get_theta_base_url,
    get_theta_timeout,
    is_fallback_enabled,
    get_output_dir,
)

logger = logging.getLogger(__name__)

# Data source constants
DATA_SOURCE_LIVE = "live"
DATA_SOURCE_SNAPSHOT = "snapshot"
DATA_SOURCE_UNAVAILABLE = "unavailable"

# Concurrency limit - match Theta Terminal's limit (shown in console)
MAX_CONCURRENT_REQUESTS = 4


@dataclass
class ThetaHealthStatus:
    """Result of Theta Terminal health check."""
    healthy: bool
    message: str
    response_time_ms: Optional[float] = None


@dataclass
class StockSnapshotResult:
    """Result of stock snapshot fetch."""
    symbol: str
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    timestamp: Optional[str] = None
    data_source: str = DATA_SOURCE_LIVE
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class OptionChainResult:
    """Result of fetching a full option chain."""
    symbol: str
    expirations: List[str] = field(default_factory=list)
    contracts: List[Dict[str, Any]] = field(default_factory=list)
    puts: List[Dict[str, Any]] = field(default_factory=list)
    calls: List[Dict[str, Any]] = field(default_factory=list)
    expiration_count: int = 0
    contract_count: int = 0
    timestamp: Optional[str] = None
    data_source: str = DATA_SOURCE_LIVE
    error: Optional[str] = None
    chain_status: str = "ok"  # "ok", "empty_chain", "no_options_for_symbol"


@dataclass
class FallbackResult:
    """Result of loading fallback snapshot."""
    loaded: bool
    file_path: Optional[Path] = None
    file_timestamp: Optional[str] = None
    snapshot_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ThetaV3Provider:
    """ThetaData v3 provider using snapshot_ohlc for complete chains.
    
    Key method: snapshot_ohlc(symbol, expiration='*')
    - Fetches ALL contracts for a symbol in ONE call
    - No strike parameter = returns all strikes
    - expiration='*' = returns all expirations
    
    Usage:
        provider = ThetaV3Provider()
        
        # Health check
        health = provider.health_check()
        
        # Fetch complete chain (all expirations, all strikes)
        contracts = provider.snapshot_ohlc("AAPL", "*")
        
        # Or fetch for DTE window
        chain = provider.fetch_full_chain("AAPL", dte_min=7, dte_max=45)
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        fallback_enabled: Optional[bool] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or get_theta_base_url()).rstrip("/")
        self.timeout = timeout if timeout is not None else get_theta_timeout()
        self.fallback_enabled = fallback_enabled if fallback_enabled is not None else is_fallback_enabled()
        self.output_dir = Path(output_dir or get_output_dir())
        
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._is_healthy: Optional[bool] = None
    
    def _get_client(self) -> httpx.Client:
        """Get or create sync HTTP client."""
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client
    
    async def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        return self._async_client
    
    def close(self) -> None:
        """Close HTTP clients."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
    
    async def aclose(self) -> None:
        """Close async HTTP client."""
        if self._async_client is not None:
            try:
                await self._async_client.aclose()
            except Exception:
                pass
            self._async_client = None
    
    def __del__(self):
        self.close()
    
    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------
    
    def health_check(self) -> ThetaHealthStatus:
        """Check if Theta Terminal is reachable via /system/status or fallback."""
        import time
        
        start = time.monotonic()
        try:
            client = self._get_client()
            # Try simple endpoint to verify connectivity
            response = client.get("/stock/list/symbols", params={"format": "json"})
            elapsed_ms = (time.monotonic() - start) * 1000
            
            if response.status_code == 200:
                self._is_healthy = True
                return ThetaHealthStatus(
                    healthy=True,
                    message=f"Theta Terminal OK at {self.base_url} ({elapsed_ms:.0f}ms)",
                    response_time_ms=elapsed_ms,
                )
            else:
                self._is_healthy = False
                return ThetaHealthStatus(
                    healthy=False,
                    message=f"HTTP {response.status_code}",
                    response_time_ms=elapsed_ms,
                )
        except httpx.ConnectError as e:
            self._is_healthy = False
            return ThetaHealthStatus(healthy=False, message=f"Cannot connect to {self.base_url}: {e}")
        except httpx.TimeoutException:
            self._is_healthy = False
            return ThetaHealthStatus(healthy=False, message=f"Timeout connecting to {self.base_url}")
        except Exception as e:
            self._is_healthy = False
            return ThetaHealthStatus(healthy=False, message=str(e))
    
    # -------------------------------------------------------------------------
    # snapshot_ohlc - THE primary endpoint for chain retrieval
    # -------------------------------------------------------------------------
    
    def snapshot_ohlc(
        self,
        symbol: str,
        expiration: str = "*",
        right: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch complete option chain via /option/snapshot/ohlc.
        
        This is THE correct endpoint for getting full chains:
        - DO NOT pass strike parameter (returns all strikes)
        - Pass expiration='*' to get all expirations at once
        - Returns bid, ask, open, high, low, close, and Greeks
        
        Parameters
        ----------
        symbol : str
            Underlying symbol (e.g., "AAPL", "SPY")
        expiration : str
            Expiration date (YYYYMMDD or YYYY-MM-DD) or '*' for all expirations
        right : str, optional
            "C" for calls, "P" for puts, None for both
        
        Returns
        -------
        list[dict]
            List of contract dicts with: symbol, expiration, strike, right,
            bid, ask, open, high, low, close, iv, delta, gamma, theta, vega
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        try:
            client = self._get_client()
            
            # Build params - DO NOT include strike to get all strikes
            params: Dict[str, Any] = {
                "symbol": symbol,
                "format": "json",
            }
            
            # Handle expiration - '*' means all expirations
            if expiration and expiration != "*":
                params["expiration"] = self._normalize_expiration(expiration)
            # If expiration is '*' or empty, don't include it to get all expirations
            
            # Optionally filter by right (C or P)
            if right and right.upper() in ("C", "P"):
                params["right"] = right.upper()
            
            logger.debug("snapshot_ohlc request: %s params=%s", "/option/snapshot/ohlc", params)
            
            response = client.get("/option/snapshot/ohlc", params=params)
            
            if response.status_code in (404, 204):
                logger.info("snapshot_ohlc: no data for %s (HTTP %d)", symbol, response.status_code)
                return []
            
            if response.status_code == 472:
                logger.warning("snapshot_ohlc: rate limited (HTTP 472) for %s", symbol)
                return []
            
            if response.status_code != 200:
                logger.warning("snapshot_ohlc: HTTP %d for %s", response.status_code, symbol)
                return []
            
            # Parse response
            data = response.json()
            contracts = self._parse_ohlc_response(data, symbol)
            
            logger.info("snapshot_ohlc: %s returned %d contracts", symbol, len(contracts))
            return contracts
            
        except Exception as e:
            logger.warning("snapshot_ohlc failed for %s: %s", symbol, e)
            return []
    
    async def snapshot_ohlc_async(
        self,
        symbol: str,
        expiration: str = "*",
        right: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Async version of snapshot_ohlc."""
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        try:
            client = await self._get_async_client()
            
            params: Dict[str, Any] = {"symbol": symbol, "format": "json"}
            if expiration and expiration != "*":
                params["expiration"] = self._normalize_expiration(expiration)
            if right and right.upper() in ("C", "P"):
                params["right"] = right.upper()
            
            async with self._semaphore:
                response = await client.get("/option/snapshot/ohlc", params=params)
            
            if response.status_code not in (200,):
                return []
            
            data = response.json()
            return self._parse_ohlc_response(data, symbol)
            
        except Exception as e:
            logger.warning("snapshot_ohlc_async failed for %s: %s", symbol, e)
            return []
    
    # -------------------------------------------------------------------------
    # fetch_full_chain - Main entry point with DTE filtering
    # -------------------------------------------------------------------------
    
    def fetch_full_chain(
        self,
        symbol: str,
        dte_min: int = 7,
        dte_max: int = 45,
    ) -> OptionChainResult:
        """Fetch full option chain with DTE filtering.
        
        Uses snapshot_ohlc(symbol, '*') to get ALL contracts in one call,
        then filters by DTE window.
        
        Parameters
        ----------
        symbol : str
            Underlying symbol
        dte_min : int
            Minimum days to expiration (default: 7)
        dte_max : int
            Maximum days to expiration (default: 45)
        
        Returns
        -------
        OptionChainResult
            Full chain with contracts, expirations, and status
        """
        symbol = (symbol or "").upper()
        now_utc = datetime.now(timezone.utc).isoformat()
        
        if not symbol:
            return OptionChainResult(
                symbol="",
                timestamp=now_utc,
                error="Invalid symbol",
                chain_status="no_options_for_symbol",
            )
        
        # Fetch ALL contracts in ONE call
        all_contracts = self.snapshot_ohlc(symbol, "*")
        
        if not all_contracts:
            return OptionChainResult(
                symbol=symbol,
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                chain_status="no_options_for_symbol",
                error="No contracts returned from snapshot_ohlc",
            )
        
        # Filter by DTE window
        today = date.today()
        filtered_contracts: List[Dict[str, Any]] = []
        puts: List[Dict[str, Any]] = []
        calls: List[Dict[str, Any]] = []
        expirations_set: set = set()
        
        for contract in all_contracts:
            exp_str = contract.get("expiration", "")
            if not exp_str:
                continue
            
            try:
                # Parse expiration
                exp_clean = str(exp_str).replace("-", "")
                if len(exp_clean) >= 8:
                    exp_date = date(int(exp_clean[:4]), int(exp_clean[4:6]), int(exp_clean[6:8]))
                    dte = (exp_date - today).days
                    
                    # Skip if outside DTE window
                    if dte < dte_min or dte > dte_max:
                        continue
                    
                    # Add DTE to contract
                    contract["dte"] = dte
                    expirations_set.add(exp_str)
            except (ValueError, TypeError):
                continue
            
            filtered_contracts.append(contract)
            right = contract.get("right", "").upper()
            if right == "P":
                puts.append(contract)
            elif right == "C":
                calls.append(contract)
        
        if not filtered_contracts:
            return OptionChainResult(
                symbol=symbol,
                expirations=sorted(expirations_set),
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                chain_status="empty_chain",
                error=f"No contracts in DTE window [{dte_min}-{dte_max}] (total fetched: {len(all_contracts)})",
            )
        
        return OptionChainResult(
            symbol=symbol,
            expirations=sorted(expirations_set),
            contracts=filtered_contracts,
            puts=puts,
            calls=calls,
            expiration_count=len(expirations_set),
            contract_count=len(filtered_contracts),
            timestamp=now_utc,
            data_source=DATA_SOURCE_LIVE,
            chain_status="ok",
        )
    
    async def fetch_full_chain_async(
        self,
        symbol: str,
        dte_min: int = 7,
        dte_max: int = 45,
    ) -> OptionChainResult:
        """Async version of fetch_full_chain."""
        symbol = (symbol or "").upper()
        now_utc = datetime.now(timezone.utc).isoformat()
        
        if not symbol:
            return OptionChainResult(symbol="", timestamp=now_utc, error="Invalid symbol", chain_status="no_options_for_symbol")
        
        all_contracts = await self.snapshot_ohlc_async(symbol, "*")
        
        if not all_contracts:
            return OptionChainResult(symbol=symbol, timestamp=now_utc, chain_status="no_options_for_symbol", error="No contracts")
        
        today = date.today()
        filtered: List[Dict[str, Any]] = []
        puts: List[Dict[str, Any]] = []
        calls: List[Dict[str, Any]] = []
        expirations_set: set = set()
        
        for contract in all_contracts:
            exp_str = contract.get("expiration", "")
            if not exp_str:
                continue
            try:
                exp_clean = str(exp_str).replace("-", "")
                if len(exp_clean) >= 8:
                    exp_date = date(int(exp_clean[:4]), int(exp_clean[4:6]), int(exp_clean[6:8]))
                    dte = (exp_date - today).days
                    if dte < dte_min or dte > dte_max:
                        continue
                    contract["dte"] = dte
                    expirations_set.add(exp_str)
            except (ValueError, TypeError):
                continue
            
            filtered.append(contract)
            right = contract.get("right", "").upper()
            if right == "P":
                puts.append(contract)
            elif right == "C":
                calls.append(contract)
        
        return OptionChainResult(
            symbol=symbol,
            expirations=sorted(expirations_set),
            contracts=filtered,
            puts=puts,
            calls=calls,
            expiration_count=len(expirations_set),
            contract_count=len(filtered),
            timestamp=now_utc,
            data_source=DATA_SOURCE_LIVE,
            chain_status="ok" if filtered else "empty_chain",
        )
    
    # -------------------------------------------------------------------------
    # Stock Snapshot
    # -------------------------------------------------------------------------
    
    def get_stock_snapshot(self, symbol: str) -> StockSnapshotResult:
        """Fetch real-time stock snapshot."""
        symbol = (symbol or "").upper()
        if not symbol:
            return StockSnapshotResult(symbol="", error="Invalid symbol")
        
        now_utc = datetime.now(timezone.utc).isoformat()
        
        try:
            client = self._get_client()
            response = client.get(
                "/stock/snapshot/quote",
                params={"symbol": symbol, "format": "json", "venue": "utp_cta"},
            )
            
            if response.status_code in (404, 204):
                if self.fallback_enabled:
                    return self._fallback_stock_snapshot(symbol)
                return StockSnapshotResult(symbol=symbol, timestamp=now_utc, data_source=DATA_SOURCE_UNAVAILABLE, error="Data unavailable")
            
            if response.status_code != 200:
                if self.fallback_enabled:
                    return self._fallback_stock_snapshot(symbol)
                return StockSnapshotResult(symbol=symbol, timestamp=now_utc, data_source=DATA_SOURCE_UNAVAILABLE, error=f"HTTP {response.status_code}")
            
            data = response.json()
            row = self._extract_response_row(data)
            
            if not row:
                if self.fallback_enabled:
                    return self._fallback_stock_snapshot(symbol)
                return StockSnapshotResult(symbol=symbol, timestamp=now_utc, data_source=DATA_SOURCE_UNAVAILABLE, error="Empty response")
            
            return StockSnapshotResult(
                symbol=symbol,
                price=self._extract_float(row, ["price", "last", "trade_price", "close", "midpoint"]),
                bid=self._extract_float(row, ["bid", "bid_price"]),
                ask=self._extract_float(row, ["ask", "ask_price"]),
                volume=self._extract_int(row, ["volume", "vol"]),
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                raw_response=row,
            )
            
        except Exception as e:
            logger.warning("Stock snapshot failed for %s: %s", symbol, e)
            if self.fallback_enabled:
                return self._fallback_stock_snapshot(symbol)
            return StockSnapshotResult(symbol=symbol, timestamp=now_utc, data_source=DATA_SOURCE_UNAVAILABLE, error=str(e))
    
    # -------------------------------------------------------------------------
    # List Expirations (for reference, not needed with snapshot_ohlc '*')
    # -------------------------------------------------------------------------
    
    def list_expirations(self, symbol: str) -> List[str]:
        """List available expirations for a symbol."""
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        try:
            client = self._get_client()
            response = client.get("/option/list/expirations", params={"symbol": symbol, "format": "json"})
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            return self._parse_expiration_list(data)
            
        except Exception as e:
            logger.warning("list_expirations failed for %s: %s", symbol, e)
            return []
    
    # -------------------------------------------------------------------------
    # Fallback Loading
    # -------------------------------------------------------------------------
    
    def load_fallback_snapshot(self) -> FallbackResult:
        """Load the most recent decision snapshot from disk."""
        try:
            if not self.output_dir.exists():
                return FallbackResult(loaded=False, error=f"Directory not found: {self.output_dir}")
            
            # Prefer decision_latest.json
            latest = self.output_dir / "decision_latest.json"
            if latest.exists():
                with open(latest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                file_mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat()
                return FallbackResult(loaded=True, file_path=latest, file_timestamp=file_mtime, snapshot_data=data)
            
            # Fallback to most recent decision_*.json
            decision_files = sorted(
                self.output_dir.glob("decision_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            
            if not decision_files:
                return FallbackResult(loaded=False, error="No decision files found")
            
            latest_file = decision_files[0]
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            file_mtime = datetime.fromtimestamp(latest_file.stat().st_mtime, tz=timezone.utc).isoformat()
            return FallbackResult(loaded=True, file_path=latest_file, file_timestamp=file_mtime, snapshot_data=data)
            
        except Exception as e:
            return FallbackResult(loaded=False, error=str(e))
    
    def _fallback_stock_snapshot(self, symbol: str) -> StockSnapshotResult:
        """Load stock snapshot from fallback."""
        fallback = self.load_fallback_snapshot()
        if not fallback.loaded or not fallback.snapshot_data:
            return StockSnapshotResult(symbol=symbol, timestamp=datetime.now(timezone.utc).isoformat(), data_source=DATA_SOURCE_UNAVAILABLE, error=fallback.error)
        
        snapshot = fallback.snapshot_data.get("decision_snapshot", {})
        price = None
        for sc in snapshot.get("scored_candidates", []):
            if isinstance(sc, dict):
                cand = sc.get("candidate", {})
                if isinstance(cand, dict) and cand.get("symbol") == symbol:
                    price = cand.get("underlying_price")
                    break
        
        return StockSnapshotResult(symbol=symbol, price=price, timestamp=fallback.file_timestamp, data_source=DATA_SOURCE_SNAPSHOT)
    
    # -------------------------------------------------------------------------
    # Response Parsing
    # -------------------------------------------------------------------------
    
    def _parse_ohlc_response(self, data: Any, symbol: str) -> List[Dict[str, Any]]:
        """Parse snapshot_ohlc response into contract dicts.
        
        Theta v3 returns data in 'response' key as list of dicts.
        Each row has: contract symbol, strike, right, expiration, bid, ask, etc.
        """
        contracts: List[Dict[str, Any]] = []
        rows = self._extract_response_list(data)
        
        for row in rows:
            if not isinstance(row, dict):
                continue
            
            strike = self._extract_float(row, ["strike"])
            if strike is None:
                continue
            
            # Get right (C/P)
            right = str(row.get("right", "") or row.get("option_type", "")).upper()
            if right not in ("P", "C", "PUT", "CALL"):
                continue
            right = "P" if right in ("P", "PUT") else "C"
            
            # Get expiration from response
            exp = row.get("expiration") or row.get("exp") or row.get("date")
            if exp:
                exp = self._format_expiration(exp)
            
            bid = self._extract_float(row, ["bid", "bid_price"])
            ask = self._extract_float(row, ["ask", "ask_price"])
            mid = None
            if bid is not None and ask is not None and bid > 0 and ask > 0:
                mid = (bid + ask) / 2
            
            contracts.append({
                "symbol": symbol,
                "expiration": exp,
                "strike": strike,
                "right": right,
                "option_type": "PUT" if right == "P" else "CALL",
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "open": self._extract_float(row, ["open"]),
                "high": self._extract_float(row, ["high"]),
                "low": self._extract_float(row, ["low"]),
                "close": self._extract_float(row, ["close"]),
                "iv": self._extract_float(row, ["implied_vol", "iv", "implied_volatility"]),
                "delta": self._extract_float(row, ["delta"]),
                "gamma": self._extract_float(row, ["gamma"]),
                "theta": self._extract_float(row, ["theta"]),
                "vega": self._extract_float(row, ["vega"]),
                "volume": self._extract_int(row, ["volume", "vol"]),
                "open_interest": self._extract_int(row, ["open_interest", "oi"]),
            })
        
        return contracts
    
    def _parse_expiration_list(self, data: Any) -> List[str]:
        """Parse expiration list from API response."""
        expirations: List[str] = []
        
        if isinstance(data, dict):
            data = data.get("response") or data.get("expirations") or []
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    expirations.append(item)
                elif isinstance(item, dict):
                    exp = item.get("expiration") or item.get("exp") or item.get("date")
                    if exp:
                        expirations.append(str(exp))
                elif isinstance(item, int):
                    expirations.append(str(item))
        
        # Normalize to YYYY-MM-DD
        normalized = []
        for exp in expirations:
            formatted = self._format_expiration(exp)
            if formatted:
                normalized.append(formatted)
        
        return sorted(set(normalized))
    
    @staticmethod
    def _extract_response_row(data: Any) -> Optional[Dict[str, Any]]:
        """Extract single row from response."""
        if isinstance(data, dict):
            if "response" in data and isinstance(data["response"], list) and data["response"]:
                return data["response"][0] if isinstance(data["response"][0], dict) else None
            return data
        if isinstance(data, list) and data:
            return data[0] if isinstance(data[0], dict) else None
        return None
    
    @staticmethod
    def _extract_response_list(data: Any) -> List[Dict[str, Any]]:
        """Extract list of rows from response."""
        if isinstance(data, dict) and "response" in data:
            resp = data["response"]
            if isinstance(resp, list):
                return [r for r in resp if isinstance(r, dict)]
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        return []
    
    @staticmethod
    def _extract_float(row: Dict[str, Any], keys: List[str]) -> Optional[float]:
        """Extract first valid float from row."""
        for key in keys:
            val = row.get(key)
            if val is not None:
                try:
                    f = float(val)
                    if f != 0 or key in ("delta", "gamma", "theta", "vega"):
                        return f
                except (TypeError, ValueError):
                    continue
        return None
    
    @staticmethod
    def _extract_int(row: Dict[str, Any], keys: List[str]) -> Optional[int]:
        """Extract first valid int from row."""
        for key in keys:
            val = row.get(key)
            if val is not None:
                try:
                    return int(float(val))
                except (TypeError, ValueError):
                    continue
        return None
    
    @staticmethod
    def _normalize_expiration(exp: Optional[str]) -> str:
        """Normalize expiration to YYYYMMDD format for API calls."""
        if not exp or exp == "*":
            return ""
        return str(exp).replace("-", "").replace("/", "")[:8]
    
    @staticmethod
    def _format_expiration(exp: Any) -> str:
        """Format expiration to YYYY-MM-DD for display."""
        if not exp:
            return ""
        exp_str = str(exp).replace("-", "").replace("/", "")
        if len(exp_str) >= 8 and exp_str[:8].isdigit():
            return f"{exp_str[:4]}-{exp_str[4:6]}-{exp_str[6:8]}"
        if isinstance(exp, str) and "-" in exp and len(exp) == 10:
            return exp
        return str(exp)


# -------------------------------------------------------------------------
# Convenience Functions
# -------------------------------------------------------------------------


def check_theta_health(base_url: Optional[str] = None, timeout: Optional[float] = None) -> Tuple[bool, str]:
    """Check Theta Terminal health. Returns (healthy, message)."""
    provider = ThetaV3Provider(base_url=base_url, timeout=timeout)
    status = provider.health_check()
    provider.close()
    return status.healthy, status.message


def fetch_chain_for_symbol(symbol: str, dte_min: int = 7, dte_max: int = 60) -> OptionChainResult:
    """Convenience function to fetch chain for a symbol."""
    provider = ThetaV3Provider()
    try:
        return provider.fetch_full_chain(symbol, dte_min=dte_min, dte_max=dte_max)
    finally:
        provider.close()


__all__ = [
    "ThetaV3Provider",
    "ThetaHealthStatus",
    "StockSnapshotResult",
    "OptionChainResult",
    "FallbackResult",
    "check_theta_health",
    "fetch_chain_for_symbol",
    "DATA_SOURCE_LIVE",
    "DATA_SOURCE_SNAPSHOT",
    "DATA_SOURCE_UNAVAILABLE",
    "MAX_CONCURRENT_REQUESTS",
]
