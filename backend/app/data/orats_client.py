# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS API client for options chain data.

DEPRECATED: This module uses api.orats.com and /chain/{symbol} (v1-style).
All ORATS v2 traffic MUST go through app.core.orats (endpoints.py + orats_client,
orats_equity_quote, orats_opra). Migrate callers (e.g. main.py RollEngine) to
use app.core.orats or app.core.options.orats_chain_pipeline and remove this module.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


class OratsClient:
    """Client for fetching options chain data from ORATS API.
    
    This is a read-only client that fetches raw chain records.
    No filtering or strategy logic is applied.
    """

    def __init__(self, api_key: Optional[str] = None, session: Optional[requests.Session] = None) -> None:
        """
        Parameters
        ----------
        api_key:
            ORATS API key. If not provided, uses ``ORATS_API_KEY`` from the environment.
        session:
            Optional ``requests.Session`` for connection reuse/testing.
        """
        self.api_key = api_key or os.getenv("ORATS_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ORATS_API_KEY is not set. Please set it in your environment."
            )
        self.session = session or requests.Session()
        self.base_url = "https://api.orats.com/datav2"

    def get_chain(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch options chain for the given symbol.
        
        Parameters
        ----------
        symbol:
            Ticker symbol (e.g., "SPY").
        
        Returns
        -------
        list[dict]
            Raw chain records. Each record contains:
            - expiry: expiration date
            - strike: strike price
            - delta: option delta
            - bid: bid price
            - ask: ask price
            - oi: open interest
            - iv: implied volatility
        
        Raises
        ------
        ValueError
            If API key is invalid, rate limit exceeded, or empty response.
        """
        symbol = symbol.upper()
        url = f"{self.base_url}/chain/{symbol}"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        
        try:
            response = self.session.get(url, headers=headers, timeout=15)
        except requests.RequestException as exc:
            raise ValueError(f"ORATS API request failed: {exc}") from exc

        # Handle HTTP status codes
        if response.status_code == 401:
            raise ValueError(
                "ORATS API error: Invalid API key. Please check your ORATS_API_KEY."
            )
        elif response.status_code == 429:
            raise ValueError(
                "ORATS API error: Rate limit exceeded. Please wait before retrying."
            )
        elif response.status_code != 200:
            error_text = response.text[:200] if response.text else "Unknown error"
            raise ValueError(
                f"ORATS API error {response.status_code}: {error_text}"
            )

        # Parse JSON response
        try:
            payload: Dict[str, Any] = response.json()
        except ValueError as exc:  # JSONDecodeError
            raise ValueError("ORATS API returned invalid JSON") from exc

        # Check for error in response payload
        if "error" in payload:
            error_msg = payload.get("error") or "Unknown error"
            raise ValueError(f"ORATS API error: {error_msg}")
        
        # Extract chain data
        # ORATS API structure may vary, but typically returns data in a 'data' or 'chain' field
        chain_data = payload.get("data") or payload.get("chain") or payload.get("results") or []
        
        # If payload is a list directly, use it
        if isinstance(payload, list):
            chain_data = payload
        
        if not chain_data:
            raise ValueError(f"No chain data returned for {symbol}")

        # Normalize chain records to ensure consistent field names
        normalized_records = []
        for record in chain_data:
            if not isinstance(record, dict):
                continue
            
            # Map common ORATS field names to our expected format
            normalized = {
                "expiry": record.get("expiry") or record.get("expirationDate") or record.get("expDate"),
                "strike": record.get("strike") or record.get("strikePrice"),
                "delta": record.get("delta"),
                "bid": record.get("bid") or record.get("bidPrice"),
                "ask": record.get("ask") or record.get("askPrice"),
                "oi": record.get("oi") or record.get("openInterest") or record.get("open_interest"),
                "iv": record.get("iv") or record.get("impliedVolatility") or record.get("implied_volatility"),
            }
            
            # Only include records with at least expiry and strike
            if normalized.get("expiry") and normalized.get("strike") is not None:
                normalized_records.append(normalized)

        if not normalized_records:
            raise ValueError(f"Empty chain data for {symbol} after normalization")

        return normalized_records


__all__ = ["OratsClient"]
