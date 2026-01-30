# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unified ThetaData v3 provider with fallback mechanism.

This module provides a single entry point for all ThetaData v3 API interactions:
- Health check before any data fetching
- Stock and option snapshot fetching
- Automatic fallback to latest decision JSON when live data unavailable
- Data source annotation for dashboard display

All requests use the centralized config (config.yaml / environment variables).
No v2 or hardcoded URLs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


# Data source constants for annotation
DATA_SOURCE_LIVE = "live"
DATA_SOURCE_SNAPSHOT = "snapshot"
DATA_SOURCE_UNAVAILABLE = "unavailable"


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
class OptionSnapshotResult:
    """Result of option snapshot fetch."""
    symbol: str
    expiration: str
    contracts: List[Dict[str, Any]] = field(default_factory=list)
    greeks_available: bool = False
    timestamp: Optional[str] = None
    data_source: str = DATA_SOURCE_LIVE
    error: Optional[str] = None


@dataclass
class FallbackResult:
    """Result of loading fallback snapshot."""
    loaded: bool
    file_path: Optional[Path] = None
    file_timestamp: Optional[str] = None
    snapshot_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class OptionChainResult:
    """Result of fetching a full option chain for a symbol/expiration."""
    symbol: str
    expiration: str
    contracts: List[Dict[str, Any]] = field(default_factory=list)
    puts: List[Dict[str, Any]] = field(default_factory=list)
    calls: List[Dict[str, Any]] = field(default_factory=list)
    strike_count: int = 0
    greeks_available: bool = False
    timestamp: Optional[str] = None
    data_source: str = DATA_SOURCE_LIVE
    error: Optional[str] = None
    chain_status: str = "ok"  # "ok", "empty_chain", "no_options_for_symbol"


class ThetaV3Provider:
    """Unified ThetaData v3 provider with health check and fallback.
    
    Usage:
        provider = ThetaV3Provider()
        
        # Check health before fetching
        health = provider.health_check()
        if not health.healthy and not is_fallback_enabled():
            sys.exit("Theta Terminal not reachable and fallback disabled")
        
        # Fetch stock snapshot
        result = provider.get_stock_snapshot("AAPL")
        if result.data_source == "snapshot":
            print("Using cached data")
        
        # Fetch option snapshot
        option_result = provider.get_option_snapshot("SPY", "2026-02-21")
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        fallback_enabled: Optional[bool] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        """Initialize the provider.
        
        Parameters
        ----------
        base_url : str, optional
            Override Theta base URL (default: from config)
        timeout : float, optional
            Override request timeout (default: from config)
        fallback_enabled : bool, optional
            Override fallback setting (default: from config)
        output_dir : str, optional
            Override output directory for fallback (default: from config)
        """
        self.base_url = (base_url or get_theta_base_url()).rstrip("/")
        self.timeout = timeout if timeout is not None else get_theta_timeout()
        self.fallback_enabled = fallback_enabled if fallback_enabled is not None else is_fallback_enabled()
        self.output_dir = Path(output_dir or get_output_dir())
        
        self._client: Optional[httpx.Client] = None
        self._is_healthy: Optional[bool] = None
        self._last_health_check: Optional[datetime] = None
    
    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client
    
    def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
    
    def __del__(self):
        self.close()
    
    def health_check(self) -> ThetaHealthStatus:
        """Check if Theta Terminal is reachable.
        
        Sends a lightweight GET request to verify the terminal is running.
        This should be called before any data fetching.
        
        Returns
        -------
        ThetaHealthStatus
            Health status with healthy flag, message, and response time.
        """
        import time
        
        start = time.monotonic()
        try:
            client = self._get_client()
            # Use /stock/list/symbols as a lightweight health check endpoint
            # It's fast and doesn't require any specific symbol
            response = client.get("/stock/list/symbols", params={"format": "json"})
            elapsed_ms = (time.monotonic() - start) * 1000
            
            if response.status_code == 200:
                self._is_healthy = True
                self._last_health_check = datetime.now(timezone.utc)
                return ThetaHealthStatus(
                    healthy=True,
                    message=f"Theta Terminal OK at {self.base_url}",
                    response_time_ms=elapsed_ms,
                )
            else:
                self._is_healthy = False
                return ThetaHealthStatus(
                    healthy=False,
                    message=f"Theta Terminal returned HTTP {response.status_code}",
                    response_time_ms=elapsed_ms,
                )
        except httpx.ConnectError as e:
            self._is_healthy = False
            return ThetaHealthStatus(
                healthy=False,
                message=f"Cannot connect to Theta Terminal at {self.base_url}: {e}",
            )
        except httpx.TimeoutException as e:
            self._is_healthy = False
            return ThetaHealthStatus(
                healthy=False,
                message=f"Theta Terminal timeout: {e}",
            )
        except Exception as e:
            self._is_healthy = False
            return ThetaHealthStatus(
                healthy=False,
                message=f"Theta Terminal health check failed: {e}",
            )
    
    def get_stock_snapshot(
        self,
        symbol: str,
        fields: Optional[List[str]] = None,
    ) -> StockSnapshotResult:
        """Fetch real-time stock snapshot from /stock/snapshot/quote.
        
        Parameters
        ----------
        symbol : str
            Stock symbol (e.g., "AAPL")
        fields : list[str], optional
            Fields to request (not used in v3, included for API compatibility)
        
        Returns
        -------
        StockSnapshotResult
            Snapshot result with price, bid, ask, volume, data_source, etc.
            data_source will be "snapshot" if fallback was used.
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return StockSnapshotResult(symbol="", error="Invalid symbol")
        
        now_utc = datetime.now(timezone.utc).isoformat()
        
        # Try live data first
        try:
            client = self._get_client()
            
            # Try /stock/snapshot/quote first (works with Value plan)
            response = client.get(
                "/stock/snapshot/quote",
                params={"symbol": symbol, "format": "json", "venue": "utp_cta"},
            )
            
            # Handle 404/204 as "data unavailable" (market closed, symbol halted)
            if response.status_code in (404, 204):
                logger.warning(
                    "Stock snapshot unavailable for %s (HTTP %d), will try fallback",
                    symbol, response.status_code
                )
                if self.fallback_enabled:
                    return self._fallback_stock_snapshot(symbol)
                return StockSnapshotResult(
                    symbol=symbol,
                    timestamp=now_utc,
                    data_source=DATA_SOURCE_UNAVAILABLE,
                    error=f"Data unavailable (HTTP {response.status_code})",
                )
            
            # Handle other errors
            if response.status_code != 200:
                logger.warning(
                    "Stock snapshot HTTP %d for %s",
                    response.status_code, symbol
                )
                if self.fallback_enabled:
                    return self._fallback_stock_snapshot(symbol)
                return StockSnapshotResult(
                    symbol=symbol,
                    timestamp=now_utc,
                    data_source=DATA_SOURCE_UNAVAILABLE,
                    error=f"HTTP {response.status_code}",
                )
            
            # Parse response
            data = response.json()
            row = self._extract_response_row(data)
            
            if not row:
                logger.warning("Empty stock snapshot response for %s", symbol)
                if self.fallback_enabled:
                    return self._fallback_stock_snapshot(symbol)
                return StockSnapshotResult(
                    symbol=symbol,
                    timestamp=now_utc,
                    data_source=DATA_SOURCE_UNAVAILABLE,
                    error="Empty response",
                )
            
            return StockSnapshotResult(
                symbol=symbol,
                price=self._extract_float(row, ["price", "last", "trade_price", "close"]),
                bid=self._extract_float(row, ["bid", "bid_price"]),
                ask=self._extract_float(row, ["ask", "ask_price"]),
                volume=self._extract_int(row, ["volume", "vol"]),
                avg_volume=self._extract_int(row, ["avg_volume", "avgVol", "avg_volume_30d"]),
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                raw_response=row,
            )
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 204):
                logger.warning("Stock snapshot not found for %s", symbol)
                if self.fallback_enabled:
                    return self._fallback_stock_snapshot(symbol)
            return StockSnapshotResult(
                symbol=symbol,
                timestamp=now_utc,
                data_source=DATA_SOURCE_UNAVAILABLE,
                error=f"HTTP {e.response.status_code}",
            )
        except Exception as e:
            logger.warning("Stock snapshot failed for %s: %s", symbol, e)
            if self.fallback_enabled:
                return self._fallback_stock_snapshot(symbol)
            return StockSnapshotResult(
                symbol=symbol,
                timestamp=now_utc,
                data_source=DATA_SOURCE_UNAVAILABLE,
                error=str(e),
            )
    
    def get_option_snapshot(
        self,
        symbol: str,
        expiration: str,
        fields: Optional[List[str]] = None,
        right: str = "*",
    ) -> OptionSnapshotResult:
        """Fetch real-time option snapshot with quotes and greeks.
        
        Hits /option/snapshot/quote for quotes and optionally /option/snapshot/all_greeks.
        
        Parameters
        ----------
        symbol : str
            Underlying symbol (e.g., "SPY")
        expiration : str
            Expiration date (YYYY-MM-DD or YYYYMMDD or "*" for all)
        fields : list[str], optional
            Fields to request (for future use)
        right : str
            Option right: "P", "C", or "*" for both
        
        Returns
        -------
        OptionSnapshotResult
            Snapshot result with contracts, greeks availability, data_source, etc.
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return OptionSnapshotResult(symbol="", expiration="", error="Invalid symbol")
        
        # Normalize expiration format
        exp_normalized = self._normalize_expiration(expiration)
        now_utc = datetime.now(timezone.utc).isoformat()
        
        try:
            client = self._get_client()
            contracts: List[Dict[str, Any]] = []
            greeks_available = False
            
            # Build params
            params: Dict[str, Any] = {
                "symbol": symbol,
                "format": "json",
            }
            if exp_normalized and exp_normalized != "*":
                params["expiration"] = exp_normalized
            if right and right != "*":
                params["right"] = right.upper()
            
            # Fetch quote snapshot
            response = client.get("/option/snapshot/quote", params=params)
            
            if response.status_code in (404, 204):
                logger.warning(
                    "Option snapshot unavailable for %s exp=%s (HTTP %d)",
                    symbol, expiration, response.status_code
                )
                if self.fallback_enabled:
                    return self._fallback_option_snapshot(symbol, expiration)
                return OptionSnapshotResult(
                    symbol=symbol,
                    expiration=expiration,
                    timestamp=now_utc,
                    data_source=DATA_SOURCE_UNAVAILABLE,
                    error=f"Data unavailable (HTTP {response.status_code})",
                )
            
            if response.status_code != 200:
                logger.warning("Option snapshot HTTP %d for %s", response.status_code, symbol)
                if self.fallback_enabled:
                    return self._fallback_option_snapshot(symbol, expiration)
                return OptionSnapshotResult(
                    symbol=symbol,
                    expiration=expiration,
                    timestamp=now_utc,
                    data_source=DATA_SOURCE_UNAVAILABLE,
                    error=f"HTTP {response.status_code}",
                )
            
            # Parse quote response
            data = response.json()
            rows = self._extract_response_list(data)
            
            for row in rows:
                if not isinstance(row, dict):
                    continue
                contract = {
                    "symbol": symbol,
                    "strike": self._extract_float(row, ["strike"]),
                    "expiration": row.get("expiration") or exp_normalized,
                    "right": row.get("right", right),
                    "bid": self._extract_float(row, ["bid", "bid_price"]),
                    "ask": self._extract_float(row, ["ask", "ask_price"]),
                    "volume": self._extract_int(row, ["volume", "vol"]),
                    "open_interest": self._extract_int(row, ["open_interest", "oi"]),
                    "delta": self._extract_float(row, ["delta"]),
                    "gamma": self._extract_float(row, ["gamma"]),
                    "theta": self._extract_float(row, ["theta"]),
                    "vega": self._extract_float(row, ["vega"]),
                    "iv": self._extract_float(row, ["implied_vol", "iv", "implied_volatility"]),
                }
                # Check if greeks are present
                if contract.get("delta") is not None or contract.get("iv") is not None:
                    greeks_available = True
                contracts.append(contract)
            
            # Try to fetch additional greeks if not in quote response
            if contracts and not greeks_available:
                try:
                    greeks_response = client.get("/option/snapshot/all_greeks", params=params)
                    if greeks_response.status_code == 200:
                        greeks_data = greeks_response.json()
                        greeks_rows = self._extract_response_list(greeks_data)
                        greeks_by_key = {}
                        for gr in greeks_rows:
                            if not isinstance(gr, dict):
                                continue
                            key = (gr.get("strike"), gr.get("right", "").upper())
                            greeks_by_key[key] = gr
                        
                        for contract in contracts:
                            key = (contract.get("strike"), (contract.get("right") or "").upper())
                            if key in greeks_by_key:
                                gr = greeks_by_key[key]
                                contract["delta"] = contract.get("delta") or self._extract_float(gr, ["delta"])
                                contract["gamma"] = contract.get("gamma") or self._extract_float(gr, ["gamma"])
                                contract["theta"] = contract.get("theta") or self._extract_float(gr, ["theta"])
                                contract["vega"] = contract.get("vega") or self._extract_float(gr, ["vega"])
                                contract["iv"] = contract.get("iv") or self._extract_float(gr, ["implied_vol", "iv"])
                                greeks_available = True
                except Exception as e:
                    logger.debug("Failed to fetch additional greeks for %s: %s", symbol, e)
            
            return OptionSnapshotResult(
                symbol=symbol,
                expiration=expiration,
                contracts=contracts,
                greeks_available=greeks_available,
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
            )
            
        except Exception as e:
            logger.warning("Option snapshot failed for %s: %s", symbol, e)
            if self.fallback_enabled:
                return self._fallback_option_snapshot(symbol, expiration)
            return OptionSnapshotResult(
                symbol=symbol,
                expiration=expiration,
                timestamp=now_utc,
                data_source=DATA_SOURCE_UNAVAILABLE,
                error=str(e),
            )
    
    def get_option_chain(
        self,
        symbol: str,
        expiration: str,
        include_greeks: bool = True,
    ) -> OptionChainResult:
        """Fetch full option chain for a symbol/expiration using /option/list/strikes.
        
        This method retrieves all strikes for an expiration and fetches quotes/greeks
        for each contract. It returns both puts and calls.
        
        Parameters
        ----------
        symbol : str
            Underlying symbol (e.g., "SPY")
        expiration : str
            Expiration date (YYYY-MM-DD or YYYYMMDD)
        include_greeks : bool
            Whether to fetch Greeks (default: True)
        
        Returns
        -------
        OptionChainResult
            Full chain with puts, calls, strike count, and status.
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return OptionChainResult(
                symbol="", expiration="", error="Invalid symbol",
                chain_status="no_options_for_symbol"
            )
        
        exp_normalized = self._normalize_expiration(expiration)
        now_utc = datetime.now(timezone.utc).isoformat()
        
        try:
            client = self._get_client()
            
            # Step 1: Fetch strikes for this expiration
            strikes_params: Dict[str, Any] = {
                "symbol": symbol,
                "expiration": exp_normalized,
                "format": "json",
            }
            
            strikes_response = client.get("/option/list/strikes", params=strikes_params)
            
            if strikes_response.status_code in (404, 204):
                logger.warning(
                    "Option chain unavailable for %s exp=%s (HTTP %d)",
                    symbol, expiration, strikes_response.status_code
                )
                return OptionChainResult(
                    symbol=symbol,
                    expiration=expiration,
                    timestamp=now_utc,
                    data_source=DATA_SOURCE_UNAVAILABLE,
                    error=f"No strikes available (HTTP {strikes_response.status_code})",
                    chain_status="empty_chain",
                )
            
            if strikes_response.status_code != 200:
                logger.warning(
                    "Option chain HTTP %d for %s exp=%s",
                    strikes_response.status_code, symbol, expiration
                )
                return OptionChainResult(
                    symbol=symbol,
                    expiration=expiration,
                    timestamp=now_utc,
                    data_source=DATA_SOURCE_UNAVAILABLE,
                    error=f"HTTP {strikes_response.status_code}",
                    chain_status="empty_chain",
                )
            
            # Parse strikes
            strikes_data = strikes_response.json()
            strikes: List[float] = []
            
            if isinstance(strikes_data, list):
                for s in strikes_data:
                    try:
                        strikes.append(float(s))
                    except (TypeError, ValueError):
                        continue
            elif isinstance(strikes_data, dict):
                strikes_list = strikes_data.get("strikes") or strikes_data.get("response") or []
                for s in strikes_list:
                    try:
                        strikes.append(float(s))
                    except (TypeError, ValueError):
                        continue
            
            if not strikes:
                return OptionChainResult(
                    symbol=symbol,
                    expiration=expiration,
                    timestamp=now_utc,
                    data_source=DATA_SOURCE_LIVE,
                    chain_status="empty_chain",
                    error="No strikes found for expiration",
                )
            
            strikes = sorted(strikes)
            
            # Step 2: Fetch quotes for puts and calls
            puts: List[Dict[str, Any]] = []
            calls: List[Dict[str, Any]] = []
            greeks_available = False
            
            for right in ["P", "C"]:
                for strike in strikes:
                    try:
                        quote_params: Dict[str, Any] = {
                            "symbol": symbol,
                            "expiration": exp_normalized,
                            "strike": strike,
                            "right": right,
                            "format": "json",
                        }
                        
                        quote_response = client.get("/option/snapshot/quote", params=quote_params)
                        
                        if quote_response.status_code != 200:
                            continue
                        
                        quote_data = quote_response.json()
                        row = self._extract_response_row(quote_data)
                        
                        if not row:
                            continue
                        
                        contract = {
                            "symbol": symbol,
                            "strike": strike,
                            "expiration": expiration,
                            "right": right,
                            "option_type": "PUT" if right == "P" else "CALL",
                            "bid": self._extract_float(row, ["bid", "bid_price"]),
                            "ask": self._extract_float(row, ["ask", "ask_price"]),
                            "volume": self._extract_int(row, ["volume", "vol"]),
                            "open_interest": self._extract_int(row, ["open_interest", "oi"]),
                            "delta": self._extract_float(row, ["delta"]),
                            "gamma": self._extract_float(row, ["gamma"]),
                            "theta": self._extract_float(row, ["theta"]),
                            "vega": self._extract_float(row, ["vega"]),
                            "iv": self._extract_float(row, ["implied_vol", "iv", "implied_volatility"]),
                        }
                        
                        if contract.get("delta") is not None or contract.get("iv") is not None:
                            greeks_available = True
                        
                        if right == "P":
                            puts.append(contract)
                        else:
                            calls.append(contract)
                    
                    except Exception as e:
                        logger.debug(
                            "Failed to fetch quote for %s %s %s %s: %s",
                            symbol, expiration, strike, right, e
                        )
                        continue
            
            all_contracts = puts + calls
            
            return OptionChainResult(
                symbol=symbol,
                expiration=expiration,
                contracts=all_contracts,
                puts=puts,
                calls=calls,
                strike_count=len(strikes),
                greeks_available=greeks_available,
                timestamp=now_utc,
                data_source=DATA_SOURCE_LIVE,
                chain_status="ok" if all_contracts else "empty_chain",
            )
        
        except Exception as e:
            logger.warning("Option chain failed for %s exp=%s: %s", symbol, expiration, e)
            return OptionChainResult(
                symbol=symbol,
                expiration=expiration,
                timestamp=now_utc,
                data_source=DATA_SOURCE_UNAVAILABLE,
                error=str(e),
                chain_status="empty_chain",
            )

    def load_fallback_snapshot(self) -> FallbackResult:
        """Load the most recent decision snapshot from disk.
        
        Returns
        -------
        FallbackResult
            Result with loaded flag, file path, timestamp, and snapshot data.
        """
        try:
            # Find decision_*.json files in output directory
            if not self.output_dir.exists():
                return FallbackResult(
                    loaded=False,
                    error=f"Output directory does not exist: {self.output_dir}",
                )
            
            decision_files = sorted(
                self.output_dir.glob("decision_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            
            if not decision_files:
                return FallbackResult(
                    loaded=False,
                    error=f"No decision files found in {self.output_dir}",
                )
            
            # Load the most recent file
            latest_file = decision_files[0]
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            file_mtime = datetime.fromtimestamp(
                latest_file.stat().st_mtime, tz=timezone.utc
            ).isoformat()
            
            logger.warning(
                "Using fallback snapshot from %s (modified %s)",
                latest_file.name, file_mtime
            )
            
            return FallbackResult(
                loaded=True,
                file_path=latest_file,
                file_timestamp=file_mtime,
                snapshot_data=data,
            )
            
        except Exception as e:
            return FallbackResult(
                loaded=False,
                error=f"Failed to load fallback snapshot: {e}",
            )
    
    def _fallback_stock_snapshot(self, symbol: str) -> StockSnapshotResult:
        """Load stock snapshot from fallback decision file."""
        fallback = self.load_fallback_snapshot()
        
        if not fallback.loaded or not fallback.snapshot_data:
            return StockSnapshotResult(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc).isoformat(),
                data_source=DATA_SOURCE_UNAVAILABLE,
                error=fallback.error or "No fallback available",
            )
        
        # Try to extract symbol data from the decision snapshot
        # The structure is: decision_snapshot.candidates or scored_candidates
        snapshot = fallback.snapshot_data.get("decision_snapshot", {})
        
        # Look for price in various places
        price = None
        scored_candidates = snapshot.get("scored_candidates") or []
        for sc in scored_candidates:
            if not isinstance(sc, dict):
                continue
            candidate = sc.get("candidate", {})
            if isinstance(candidate, dict) and candidate.get("symbol") == symbol:
                # Found the symbol in candidates
                price = candidate.get("underlying_price")
                break
        
        return StockSnapshotResult(
            symbol=symbol,
            price=price,
            timestamp=fallback.file_timestamp,
            data_source=DATA_SOURCE_SNAPSHOT,
            error=None if price else f"Symbol {symbol} not found in fallback",
        )
    
    def _fallback_option_snapshot(self, symbol: str, expiration: str) -> OptionSnapshotResult:
        """Load option snapshot from fallback decision file."""
        fallback = self.load_fallback_snapshot()
        
        if not fallback.loaded or not fallback.snapshot_data:
            return OptionSnapshotResult(
                symbol=symbol,
                expiration=expiration,
                timestamp=datetime.now(timezone.utc).isoformat(),
                data_source=DATA_SOURCE_UNAVAILABLE,
                error=fallback.error or "No fallback available",
            )
        
        # Extract option data from the decision snapshot
        snapshot = fallback.snapshot_data.get("decision_snapshot", {})
        contracts: List[Dict[str, Any]] = []
        
        scored_candidates = snapshot.get("scored_candidates") or []
        for sc in scored_candidates:
            if not isinstance(sc, dict):
                continue
            candidate = sc.get("candidate", {})
            if not isinstance(candidate, dict):
                continue
            if candidate.get("symbol") != symbol:
                continue
            # Include this contract if expiration matches or we want all
            cand_exp = candidate.get("expiry") or candidate.get("expiration")
            if expiration == "*" or self._normalize_expiration(cand_exp) == self._normalize_expiration(expiration):
                contracts.append({
                    "symbol": symbol,
                    "strike": candidate.get("strike"),
                    "expiration": cand_exp,
                    "right": candidate.get("signal_type", "").replace("CSP", "P").replace("CC", "C")[:1] or "P",
                    "bid": candidate.get("bid"),
                    "ask": candidate.get("ask"),
                    "delta": candidate.get("delta"),
                    "iv": candidate.get("iv"),
                })
        
        return OptionSnapshotResult(
            symbol=symbol,
            expiration=expiration,
            contracts=contracts,
            greeks_available=any(c.get("delta") is not None for c in contracts),
            timestamp=fallback.file_timestamp,
            data_source=DATA_SOURCE_SNAPSHOT,
        )
    
    @staticmethod
    def _extract_response_row(data: Any) -> Optional[Dict[str, Any]]:
        """Extract single row from Theta v3 response."""
        if isinstance(data, dict):
            if "response" in data and isinstance(data["response"], list) and data["response"]:
                return data["response"][0] if isinstance(data["response"][0], dict) else None
            return data
        if isinstance(data, list) and data:
            return data[0] if isinstance(data[0], dict) else None
        return None
    
    @staticmethod
    def _extract_response_list(data: Any) -> List[Dict[str, Any]]:
        """Extract list of rows from Theta v3 response."""
        if isinstance(data, dict) and "response" in data:
            resp = data["response"]
            if isinstance(resp, list):
                return [r for r in resp if isinstance(r, dict)]
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        return []
    
    @staticmethod
    def _extract_float(row: Dict[str, Any], keys: List[str]) -> Optional[float]:
        """Extract first valid float from row by trying multiple keys."""
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
        """Extract first valid int from row by trying multiple keys."""
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
        exp = str(exp).replace("-", "").replace("/", "")[:8]
        # If it looks like YYYY-MM-DD, strip dashes
        return exp


def check_theta_health(
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[bool, str]:
    """Convenience function to check Theta Terminal health.
    
    Returns
    -------
    tuple[bool, str]
        (healthy, message)
    """
    provider = ThetaV3Provider(base_url=base_url, timeout=timeout)
    status = provider.health_check()
    provider.close()
    return status.healthy, status.message


__all__ = [
    "ThetaV3Provider",
    "ThetaHealthStatus",
    "StockSnapshotResult",
    "OptionSnapshotResult",
    "OptionChainResult",
    "FallbackResult",
    "check_theta_health",
    "DATA_SOURCE_LIVE",
    "DATA_SOURCE_SNAPSHOT",
    "DATA_SOURCE_UNAVAILABLE",
]
