# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unified ThetaData v3 provider with reliable chain retrieval.

This module provides comprehensive Theta v3 API interactions:
- Health check before any data fetching
- Efficient chain retrieval using snapshot endpoints
- list_expirations, list_strikes, snapshot_ohlc for full chains
- fetch_full_chain for DTE-filtered chain retrieval
- Automatic fallback to latest decision JSON when live data unavailable
- Data source annotation for dashboard display
- Async support with semaphore for concurrency control
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

# Concurrency limit for Theta API (respect subscription limits)
MAX_CONCURRENT_REQUESTS = 5


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
    avg_volume: Optional[int] = None
    timestamp: Optional[str] = None
    data_source: str = DATA_SOURCE_LIVE
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class OptionContract:
    """Single option contract with quotes and Greeks."""
    symbol: str
    expiration: str
    strike: float
    option_type: str  # "PUT" or "CALL"
    right: str  # "P" or "C"
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None


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
    """Unified ThetaData v3 provider with health check, chain retrieval, and fallback.
    
    Usage:
        provider = ThetaV3Provider()
        
        # Health check
        health = provider.health_check()
        
        # List expirations
        expirations = provider.list_expirations("AAPL")
        
        # Fetch full chain for DTE window
        chain = provider.fetch_full_chain("AAPL", dte_min=30, dte_max=45)
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
                    message=f"Theta Terminal OK at {self.base_url}",
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
            return ThetaHealthStatus(healthy=False, message=f"Cannot connect: {e}")
        except httpx.TimeoutException:
            self._is_healthy = False
            return ThetaHealthStatus(healthy=False, message="Timeout")
        except Exception as e:
            self._is_healthy = False
            return ThetaHealthStatus(healthy=False, message=str(e))
    
    # -------------------------------------------------------------------------
    # Expiration and Strike Listing
    # -------------------------------------------------------------------------
    
    def list_expirations(self, symbol: str) -> List[str]:
        """List all available expirations for a symbol.
        
        GET /option/list/expirations?symbol={symbol}
        
        Returns list of expiration strings (YYYY-MM-DD format).
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        try:
            client = self._get_client()
            response = client.get(
                "/option/list/expirations",
                params={"symbol": symbol, "format": "json"}
            )
            
            if response.status_code != 200:
                logger.warning("list_expirations HTTP %d for %s", response.status_code, symbol)
                return []
            
            data = response.json()
            expirations = self._parse_expiration_list(data)
            return expirations
            
        except Exception as e:
            logger.warning("list_expirations failed for %s: %s", symbol, e)
            return []
    
    async def list_expirations_async(self, symbol: str) -> List[str]:
        """Async version of list_expirations."""
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        try:
            client = await self._get_async_client()
            async with self._semaphore:
                response = await client.get(
                    "/option/list/expirations",
                    params={"symbol": symbol, "format": "json"}
                )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            return self._parse_expiration_list(data)
            
        except Exception as e:
            logger.warning("list_expirations_async failed for %s: %s", symbol, e)
            return []
    
    def list_strikes(self, symbol: str, expiration: str) -> List[float]:
        """List all strikes for a symbol/expiration.
        
        GET /option/list/strikes?symbol={symbol}&expiration={expiration}
        
        Returns list of strike prices.
        """
        symbol = (symbol or "").upper()
        exp_normalized = self._normalize_expiration(expiration)
        if not symbol or not exp_normalized:
            return []
        
        try:
            client = self._get_client()
            response = client.get(
                "/option/list/strikes",
                params={"symbol": symbol, "expiration": exp_normalized, "format": "json"}
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            return self._parse_strike_list(data)
            
        except Exception as e:
            logger.warning("list_strikes failed for %s %s: %s", symbol, expiration, e)
            return []
    
    # -------------------------------------------------------------------------
    # Snapshot OHLC - Efficient bulk fetch
    # -------------------------------------------------------------------------
    
    def snapshot_ohlc(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        """Fetch OHLC snapshot for all contracts at an expiration.
        
        GET /option/snapshot/ohlc?symbol={symbol}&expiration={expiration}
        
        Returns list of contract dicts with bid, ask, IV, Greeks.
        This is more efficient than fetching each strike individually.
        """
        symbol = (symbol or "").upper()
        exp_normalized = self._normalize_expiration(expiration)
        if not symbol or not exp_normalized:
            return []
        
        try:
            client = self._get_client()
            response = client.get(
                "/option/snapshot/ohlc",
                params={"symbol": symbol, "expiration": exp_normalized, "format": "json"}
            )
            
            if response.status_code in (404, 204):
                logger.debug("snapshot_ohlc no data for %s %s", symbol, expiration)
                return []
            
            if response.status_code != 200:
                logger.warning("snapshot_ohlc HTTP %d for %s %s", response.status_code, symbol, expiration)
                return []
            
            data = response.json()
            return self._parse_ohlc_response(data, symbol, expiration)
            
        except Exception as e:
            logger.warning("snapshot_ohlc failed for %s %s: %s", symbol, expiration, e)
            return []
    
    async def snapshot_ohlc_async(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        """Async version of snapshot_ohlc."""
        symbol = (symbol or "").upper()
        exp_normalized = self._normalize_expiration(expiration)
        if not symbol or not exp_normalized:
            return []
        
        try:
            client = await self._get_async_client()
            async with self._semaphore:
                response = await client.get(
                    "/option/snapshot/ohlc",
                    params={"symbol": symbol, "expiration": exp_normalized, "format": "json"}
                )
            
            if response.status_code not in (200,):
                return []
            
            data = response.json()
            return self._parse_ohlc_response(data, symbol, expiration)
            
        except Exception as e:
            logger.warning("snapshot_ohlc_async failed for %s %s: %s", symbol, expiration, e)
            return []
    
    def snapshot_quote(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        """Alternative: fetch quote snapshot for an expiration.
        
        GET /option/snapshot/quote?symbol={symbol}&expiration={expiration}
        
        Use this if snapshot_ohlc is not available in subscription.
        """
        symbol = (symbol or "").upper()
        exp_normalized = self._normalize_expiration(expiration)
        if not symbol or not exp_normalized:
            return []
        
        try:
            client = self._get_client()
            response = client.get(
                "/option/snapshot/quote",
                params={"symbol": symbol, "expiration": exp_normalized, "format": "json"}
            )
            
            if response.status_code not in (200,):
                return []
            
            data = response.json()
            return self._parse_quote_response(data, symbol, expiration)
            
        except Exception as e:
            logger.warning("snapshot_quote failed for %s %s: %s", symbol, expiration, e)
            return []
    
    # -------------------------------------------------------------------------
    # Full Chain Fetch - Main entry point
    # -------------------------------------------------------------------------
    
    def fetch_full_chain(
        self,
        symbol: str,
        dte_min: int = 30,
        dte_max: int = 45,
    ) -> OptionChainResult:
        """Fetch full option chain for a symbol within DTE window.
        
        1. Get all expirations via list_expirations()
        2. Filter by DTE between dte_min and dte_max
        3. For each expiration, call snapshot_ohlc() or snapshot_quote()
        4. Collect all puts and calls into result
        
        Parameters
        ----------
        symbol : str
            Underlying symbol
        dte_min : int
            Minimum days to expiration (default: 30)
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
        
        # Step 1: Get expirations
        expirations = self.list_expirations(symbol)
        
        if not expirations:
            logger.warning("No expirations found for %s", symbol)
            return OptionChainResult(
                symbol=symbol,
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                chain_status="no_options_for_symbol",
                error="No expirations available",
            )
        
        # Step 2: Filter by DTE
        today = date.today()
        valid_expirations: List[str] = []
        
        for exp_str in expirations:
            try:
                # Parse expiration (handle YYYYMMDD or YYYY-MM-DD)
                exp_clean = exp_str.replace("-", "")
                if len(exp_clean) == 8:
                    exp_date = date(int(exp_clean[:4]), int(exp_clean[4:6]), int(exp_clean[6:8]))
                else:
                    continue
                
                dte = (exp_date - today).days
                if dte_min <= dte <= dte_max:
                    valid_expirations.append(exp_str)
            except (ValueError, TypeError):
                continue
        
        if not valid_expirations:
            logger.info("No expirations in DTE window [%d-%d] for %s", dte_min, dte_max, symbol)
            return OptionChainResult(
                symbol=symbol,
                expirations=expirations,
                expiration_count=len(expirations),
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                chain_status="empty_chain",
                error=f"No expirations in DTE window [{dte_min}-{dte_max}]",
            )
        
        # Step 3: Fetch contracts for each valid expiration
        all_contracts: List[Dict[str, Any]] = []
        puts: List[Dict[str, Any]] = []
        calls: List[Dict[str, Any]] = []
        
        for exp in valid_expirations:
            # Try snapshot_ohlc first (more complete), fall back to snapshot_quote
            contracts = self.snapshot_ohlc(symbol, exp)
            if not contracts:
                contracts = self.snapshot_quote(symbol, exp)
            
            for contract in contracts:
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
                error="No contracts returned from snapshot endpoints",
            )
        
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
        dte_min: int = 30,
        dte_max: int = 45,
    ) -> OptionChainResult:
        """Async version of fetch_full_chain for concurrent fetching."""
        symbol = (symbol or "").upper()
        now_utc = datetime.now(timezone.utc).isoformat()
        
        if not symbol:
            return OptionChainResult(symbol="", timestamp=now_utc, error="Invalid symbol", chain_status="no_options_for_symbol")
        
        # Get expirations
        expirations = await self.list_expirations_async(symbol)
        if not expirations:
            return OptionChainResult(symbol=symbol, timestamp=now_utc, chain_status="no_options_for_symbol", error="No expirations")
        
        # Filter by DTE
        today = date.today()
        valid_expirations: List[str] = []
        for exp_str in expirations:
            try:
                exp_clean = exp_str.replace("-", "")
                if len(exp_clean) == 8:
                    exp_date = date(int(exp_clean[:4]), int(exp_clean[4:6]), int(exp_clean[6:8]))
                    dte = (exp_date - today).days
                    if dte_min <= dte <= dte_max:
                        valid_expirations.append(exp_str)
            except (ValueError, TypeError):
                continue
        
        if not valid_expirations:
            return OptionChainResult(symbol=symbol, expirations=expirations, timestamp=now_utc, chain_status="empty_chain", error=f"No expirations in DTE [{dte_min}-{dte_max}]")
        
        # Fetch all expirations concurrently
        tasks = [self.snapshot_ohlc_async(symbol, exp) for exp in valid_expirations]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_contracts: List[Dict[str, Any]] = []
        puts: List[Dict[str, Any]] = []
        calls: List[Dict[str, Any]] = []
        
        for result in results:
            if isinstance(result, Exception):
                continue
            for contract in result:
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
                price=self._extract_float(row, ["price", "last", "trade_price", "close"]),
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
            logger.warning("Using fallback: %s", latest_file.name)
            
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
    # Response Parsing Helpers
    # -------------------------------------------------------------------------
    
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
                    exp = item.get("expiration") or item.get("exp")
                    if exp:
                        expirations.append(str(exp))
                elif isinstance(item, int):
                    # YYYYMMDD integer format
                    expirations.append(str(item))
        
        # Normalize to YYYY-MM-DD format
        normalized = []
        for exp in expirations:
            exp_str = str(exp).replace("-", "")
            if len(exp_str) == 8 and exp_str.isdigit():
                normalized.append(f"{exp_str[:4]}-{exp_str[4:6]}-{exp_str[6:8]}")
            elif "-" in str(exp) and len(str(exp)) == 10:
                normalized.append(str(exp))
        
        return sorted(set(normalized))
    
    def _parse_strike_list(self, data: Any) -> List[float]:
        """Parse strike list from API response."""
        strikes: List[float] = []
        
        if isinstance(data, dict):
            data = data.get("response") or data.get("strikes") or []
        
        if isinstance(data, list):
            for item in data:
                try:
                    strikes.append(float(item))
                except (TypeError, ValueError):
                    continue
        
        return sorted(strikes)
    
    def _parse_ohlc_response(self, data: Any, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        """Parse OHLC snapshot response into contract dicts."""
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
            
            bid = self._extract_float(row, ["bid", "bid_price"])
            ask = self._extract_float(row, ["ask", "ask_price"])
            mid = None
            if bid is not None and ask is not None:
                mid = (bid + ask) / 2
            
            contracts.append({
                "symbol": symbol,
                "expiration": expiration,
                "strike": strike,
                "right": right,
                "option_type": "PUT" if right == "P" else "CALL",
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "iv": self._extract_float(row, ["implied_vol", "iv", "implied_volatility"]),
                "delta": self._extract_float(row, ["delta"]),
                "gamma": self._extract_float(row, ["gamma"]),
                "theta": self._extract_float(row, ["theta"]),
                "vega": self._extract_float(row, ["vega"]),
                "volume": self._extract_int(row, ["volume", "vol"]),
                "open_interest": self._extract_int(row, ["open_interest", "oi"]),
            })
        
        return contracts
    
    def _parse_quote_response(self, data: Any, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        """Parse quote snapshot response into contract dicts."""
        return self._parse_ohlc_response(data, symbol, expiration)
    
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
                    return float(val)
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
        """Normalize expiration to YYYYMMDD format."""
        if not exp or exp == "*":
            return exp or ""
        return str(exp).replace("-", "").replace("/", "")[:8]


# -------------------------------------------------------------------------
# Convenience Functions
# -------------------------------------------------------------------------


def check_theta_health(base_url: Optional[str] = None, timeout: Optional[float] = None) -> Tuple[bool, str]:
    """Check Theta Terminal health. Returns (healthy, message)."""
    provider = ThetaV3Provider(base_url=base_url, timeout=timeout)
    status = provider.health_check()
    provider.close()
    return status.healthy, status.message


def fetch_chain_for_symbol(symbol: str, dte_min: int = 30, dte_max: int = 60) -> OptionChainResult:
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
    "OptionContract",
    "OptionChainResult",
    "FallbackResult",
    "check_theta_health",
    "fetch_chain_for_symbol",
    "DATA_SOURCE_LIVE",
    "DATA_SOURCE_SNAPSHOT",
    "DATA_SOURCE_UNAVAILABLE",
]
