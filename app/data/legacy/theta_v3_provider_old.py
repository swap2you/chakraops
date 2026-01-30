# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ThetaData v3 provider using per-expiration snapshot_ohlc calls.

Correct approach:
1. Call list_expirations(symbol) to get available expirations
2. For each expiration, call snapshot_ohlc(symbol, expiration) 
3. DO NOT pass expiration="*" - Theta API rejects it with HTTP 400
4. DO NOT pass optional params as None - only include params that have values
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

# Concurrency limit - match Theta Terminal's limit
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
    """ThetaData v3 provider with per-expiration chain retrieval.
    
    Correct usage:
        provider = ThetaV3Provider()
        
        # Get expirations first
        expirations = provider.list_expirations("AAPL")
        
        # Fetch chain for specific expiration
        contracts = provider.snapshot_ohlc("AAPL", "2026-02-21")
        
        # Or fetch full chain (handles expiration iteration internally)
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
        """Check if Theta Terminal is reachable."""
        import time
        
        start = time.monotonic()
        try:
            client = self._get_client()
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
    # List Expirations - REQUIRED first step
    # -------------------------------------------------------------------------
    
    def list_expirations(self, symbol: str) -> List[str]:
        """List available expirations for a symbol.
        
        GET /option/list/expirations?symbol={symbol}
        
        This MUST be called first to get valid expiration dates,
        then call snapshot_ohlc for each expiration.
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        try:
            client = self._get_client()
            # Only include required params - no optional params
            params = {"symbol": symbol, "format": "json"}
            
            response = client.get("/option/list/expirations", params=params)
            
            if response.status_code != 200:
                logger.warning("list_expirations HTTP %d for %s", response.status_code, symbol)
                return []
            
            data = response.json()
            expirations = self._parse_expiration_list(data)
            logger.info("list_expirations: %s has %d expirations", symbol, len(expirations))
            return expirations
            
        except Exception as e:
            logger.warning("list_expirations failed for %s: %s", symbol, e)
            return []
    
    # -------------------------------------------------------------------------
    # snapshot_ohlc - Per-expiration call
    # -------------------------------------------------------------------------
    
    def snapshot_ohlc(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        """Fetch OHLC data for all contracts at a specific expiration.
        
        GET /option/snapshot/ohlc?symbol={symbol}&expiration={expiration}
        
        Parameters
        ----------
        symbol : str
            Underlying ticker (e.g., "AAPL")
        expiration : str
            Expiration date in YYYY-MM-DD or YYYYMMDD format (REQUIRED)
        
        Returns
        -------
        list[dict]
            List of contract dicts with strike, right, bid, ask, Greeks, etc.
        
        IMPORTANT:
        - expiration is REQUIRED - do NOT pass "*" or empty string
        - Do NOT include strike parameter (returns all strikes)
        - Do NOT include optional params that are None
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        # Validate expiration - MUST be a specific date, not "*"
        if not expiration or expiration == "*":
            logger.error("snapshot_ohlc: expiration is required (got '%s')", expiration)
            return []
        
        exp_normalized = self._normalize_expiration(expiration)
        if not exp_normalized:
            logger.error("snapshot_ohlc: invalid expiration format '%s'", expiration)
            return []
        
        try:
            client = self._get_client()
            
            # Only include symbol and expiration - no other params
            params = {
                "symbol": symbol,
                "expiration": exp_normalized,
                "format": "json",
            }
            
            logger.debug("snapshot_ohlc: GET /option/snapshot/ohlc params=%s", params)
            
            response = client.get("/option/snapshot/ohlc", params=params)
            
            if response.status_code == 400:
                logger.warning("snapshot_ohlc: HTTP 400 Bad Request for %s %s - check params", symbol, expiration)
                return []
            
            if response.status_code in (404, 204):
                logger.debug("snapshot_ohlc: no data for %s %s (HTTP %d)", symbol, expiration, response.status_code)
                return []
            
            if response.status_code == 472:
                logger.warning("snapshot_ohlc: rate limited (HTTP 472) for %s", symbol)
                return []
            
            if response.status_code != 200:
                logger.warning("snapshot_ohlc: HTTP %d for %s %s", response.status_code, symbol, expiration)
                return []
            
            data = response.json()
            contracts = self._parse_ohlc_response(data, symbol, expiration)
            
            logger.debug("snapshot_ohlc: %s %s returned %d contracts", symbol, expiration, len(contracts))
            return contracts
            
        except Exception as e:
            logger.warning("snapshot_ohlc failed for %s %s: %s", symbol, expiration, e)
            return []
    
    async def snapshot_ohlc_async(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        """Async version of snapshot_ohlc."""
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        if not expiration or expiration == "*":
            return []
        
        exp_normalized = self._normalize_expiration(expiration)
        if not exp_normalized:
            return []
        
        try:
            client = await self._get_async_client()
            
            params = {
                "symbol": symbol,
                "expiration": exp_normalized,
                "format": "json",
            }
            
            async with self._semaphore:
                response = await client.get("/option/snapshot/ohlc", params=params)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            return self._parse_ohlc_response(data, symbol, expiration)
            
        except Exception as e:
            logger.warning("snapshot_ohlc_async failed for %s %s: %s", symbol, expiration, e)
            return []
    
    # -------------------------------------------------------------------------
    # fetch_full_chain - Main entry point
    # -------------------------------------------------------------------------
    
    def fetch_full_chain(
        self,
        symbol: str,
        dte_min: int = 7,
        dte_max: int = 45,
    ) -> OptionChainResult:
        """Fetch full option chain with DTE filtering.
        
        1. Calls list_expirations() to get all expirations
        2. Filters expirations by DTE window
        3. Calls snapshot_ohlc() for EACH valid expiration
        4. Combines results into single chain
        
        Parameters
        ----------
        symbol : str
            Underlying symbol
        dte_min : int
            Minimum days to expiration (default: 7)
        dte_max : int
            Maximum days to expiration (default: 45)
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
        
        # Step 1: Get all expirations
        all_expirations = self.list_expirations(symbol)
        
        if not all_expirations:
            return OptionChainResult(
                symbol=symbol,
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                chain_status="no_options_for_symbol",
                error="No expirations found for symbol",
            )
        
        # Step 2: Filter by DTE window
        today = date.today()
        valid_expirations: List[str] = []
        
        for exp_str in all_expirations:
            try:
                exp_clean = exp_str.replace("-", "")
                if len(exp_clean) >= 8 and exp_clean[:8].isdigit():
                    exp_date = date(int(exp_clean[:4]), int(exp_clean[4:6]), int(exp_clean[6:8]))
                    dte = (exp_date - today).days
                    if dte_min <= dte <= dte_max:
                        valid_expirations.append(exp_str)
            except (ValueError, TypeError):
                continue
        
        if not valid_expirations:
            return OptionChainResult(
                symbol=symbol,
                expirations=all_expirations,
                expiration_count=len(all_expirations),
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                chain_status="empty_chain",
                error=f"No expirations in DTE window [{dte_min}-{dte_max}]. Total expirations: {len(all_expirations)}",
            )
        
        # Step 3: Fetch contracts for each valid expiration
        all_contracts: List[Dict[str, Any]] = []
        puts: List[Dict[str, Any]] = []
        calls: List[Dict[str, Any]] = []
        
        for exp in valid_expirations:
            contracts = self.snapshot_ohlc(symbol, exp)
            
            for contract in contracts:
                # Add DTE
                try:
                    exp_clean = str(contract.get("expiration", exp)).replace("-", "")
                    if len(exp_clean) >= 8:
                        exp_date = date(int(exp_clean[:4]), int(exp_clean[4:6]), int(exp_clean[6:8]))
                        contract["dte"] = (exp_date - today).days
                except (ValueError, TypeError):
                    pass
                
                all_contracts.append(contract)
                right = contract.get("right", "").upper()
                if right == "P":
                    puts.append(contract)
                elif right == "C":
                    calls.append(contract)
        
        if not all_contracts:
            return OptionChainResult(
                symbol=symbol,
                expirations=valid_expirations,
                expiration_count=len(valid_expirations),
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                chain_status="empty_chain",
                error=f"No contracts returned for {len(valid_expirations)} expirations",
            )
        
        logger.info("fetch_full_chain: %s returned %d contracts from %d expirations", 
                   symbol, len(all_contracts), len(valid_expirations))
        
        return OptionChainResult(
            symbol=symbol,
            expirations=valid_expirations,
            contracts=all_contracts,
            puts=puts,
            calls=calls,
            expiration_count=len(valid_expirations),
            contract_count=len(all_contracts),
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
        """Async version of fetch_full_chain with concurrent expiration fetching."""
        symbol = (symbol or "").upper()
        now_utc = datetime.now(timezone.utc).isoformat()
        
        if not symbol:
            return OptionChainResult(symbol="", timestamp=now_utc, error="Invalid symbol", chain_status="no_options_for_symbol")
        
        # Get expirations (sync call, usually fast)
        all_expirations = self.list_expirations(symbol)
        
        if not all_expirations:
            return OptionChainResult(symbol=symbol, timestamp=now_utc, chain_status="no_options_for_symbol", error="No expirations")
        
        # Filter by DTE
        today = date.today()
        valid_expirations: List[str] = []
        for exp_str in all_expirations:
            try:
                exp_clean = exp_str.replace("-", "")
                if len(exp_clean) >= 8 and exp_clean[:8].isdigit():
                    exp_date = date(int(exp_clean[:4]), int(exp_clean[4:6]), int(exp_clean[6:8]))
                    dte = (exp_date - today).days
                    if dte_min <= dte <= dte_max:
                        valid_expirations.append(exp_str)
            except (ValueError, TypeError):
                continue
        
        if not valid_expirations:
            return OptionChainResult(symbol=symbol, expirations=all_expirations, timestamp=now_utc, chain_status="empty_chain", error=f"No expirations in DTE [{dte_min}-{dte_max}]")
        
        # Fetch all expirations concurrently (respecting semaphore)
        tasks = [self.snapshot_ohlc_async(symbol, exp) for exp in valid_expirations]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_contracts: List[Dict[str, Any]] = []
        puts: List[Dict[str, Any]] = []
        calls: List[Dict[str, Any]] = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("Async fetch failed for %s %s: %s", symbol, valid_expirations[i], result)
                continue
            
            for contract in result:
                try:
                    exp_clean = str(contract.get("expiration", valid_expirations[i])).replace("-", "")
                    if len(exp_clean) >= 8:
                        exp_date = date(int(exp_clean[:4]), int(exp_clean[4:6]), int(exp_clean[6:8]))
                        contract["dte"] = (exp_date - today).days
                except (ValueError, TypeError):
                    pass
                
                all_contracts.append(contract)
                right = contract.get("right", "").upper()
                if right == "P":
                    puts.append(contract)
                elif right == "C":
                    calls.append(contract)
        
        return OptionChainResult(
            symbol=symbol,
            expirations=valid_expirations,
            contracts=all_contracts,
            puts=puts,
            calls=calls,
            expiration_count=len(valid_expirations),
            contract_count=len(all_contracts),
            timestamp=now_utc,
            data_source=DATA_SOURCE_LIVE,
            chain_status="ok" if all_contracts else "empty_chain",
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
            # Only include required params
            params = {"symbol": symbol, "format": "json"}
            
            response = client.get("/stock/snapshot/quote", params=params)
            
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
    # Fallback Loading
    # -------------------------------------------------------------------------
    
    def load_fallback_snapshot(self) -> FallbackResult:
        """Load the most recent decision snapshot from disk."""
        try:
            if not self.output_dir.exists():
                return FallbackResult(loaded=False, error=f"Directory not found: {self.output_dir}")
            
            latest = self.output_dir / "decision_latest.json"
            if latest.exists():
                with open(latest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                file_mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat()
                return FallbackResult(loaded=True, file_path=latest, file_timestamp=file_mtime, snapshot_data=data)
            
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
    
    def _parse_ohlc_response(self, data: Any, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        """Parse snapshot_ohlc response into contract dicts."""
        contracts: List[Dict[str, Any]] = []
        rows = self._extract_response_list(data)
        
        for row in rows:
            if not isinstance(row, dict):
                continue
            
            strike = self._extract_float(row, ["strike"])
            if strike is None:
                continue
            
            right = str(row.get("right", "") or row.get("option_type", "")).upper()
            if right not in ("P", "C", "PUT", "CALL"):
                continue
            right = "P" if right in ("P", "PUT") else "C"
            
            # Use expiration from response if available, otherwise use parameter
            exp = row.get("expiration") or row.get("exp") or row.get("date") or expiration
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
        if not exp:
            return ""
        exp_str = str(exp).replace("-", "").replace("/", "")
        if len(exp_str) >= 8 and exp_str[:8].isdigit():
            return exp_str[:8]
        return ""
    
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
