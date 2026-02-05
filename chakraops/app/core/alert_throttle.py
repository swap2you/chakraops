# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Alert Throttling & Signal De-duplication.

This module provides a deterministic function for preventing alert spam by
suppressing duplicate alerts unless something materially changes.

The throttling is in-memory only and stateless across restarts. It maintains
a cache of alert signatures and their last sent timestamps to enforce
cooldown periods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# In-memory cache: signature -> last_sent_timestamp
# This is module-level and will be reset on restart (acceptable per requirements)
_alert_cache: Dict[str, datetime] = {}


@dataclass(frozen=True)
class AlertSignature:
    """Alert signature for de-duplication.
    
    Attributes
    ----------
    symbol:
        Symbol for which alert is generated.
    action:
        Action type: "HOLD" | "CLOSE" | "ROLL" | "ALERT".
    confidence_level:
        Confidence level: "HIGH" | "MEDIUM" | "LOW".
    """
    symbol: str
    action: str  # HOLD | CLOSE | ROLL | ALERT
    confidence_level: str  # HIGH | MEDIUM | LOW
    
    def __str__(self) -> str:
        """String representation for cache key."""
        return f"{self.symbol}|{self.action}|{self.confidence_level}"


def should_emit_alert(
    signature: AlertSignature,
    now: Optional[datetime] = None,
    cooldown_minutes: int = 30,
) -> bool:
    """Determine if an alert should be emitted based on throttling rules.
    
    This function is deterministic, stateless (except for in-memory cache),
    and never accesses databases or external services. It checks if an alert
    with the same signature was recently sent and suppresses it if within
    the cooldown period.
    
    Parameters
    ----------
    signature:
        Alert signature to check.
    now:
        Current timestamp (default: current UTC time).
        Provided for testing determinism.
    cooldown_minutes:
        Cooldown period in minutes (default: 30).
        Alerts with the same signature are suppressed if sent within this period.
    
    Returns
    -------
    bool
        True if alert should be emitted, False if it should be suppressed.
    
    Rules:
    ------
    1. Suppress alert if same signature was sent within cooldown period.
    2. Allow alert if signature changes (different symbol, action, or confidence).
    3. Allow alert if cooldown period has expired.
    4. First alert with a signature is always allowed.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Normalize signature
    signature_str = str(signature)
    
    # Check if we have a cached timestamp for this signature
    last_sent = _alert_cache.get(signature_str)
    
    if last_sent is None:
        # First time seeing this signature - allow alert
        _alert_cache[signature_str] = now
        logger.info(
            f"AlertThrottle: {signature.symbol} | {signature.action} | "
            f"{signature.confidence_level} | EMIT (first occurrence)"
        )
        return True
    
    # Check if cooldown has expired
    cooldown_delta = timedelta(minutes=cooldown_minutes)
    time_since_last = now - last_sent
    
    if time_since_last >= cooldown_delta:
        # Cooldown expired - allow alert and update cache
        _alert_cache[signature_str] = now
        logger.info(
            f"AlertThrottle: {signature.symbol} | {signature.action} | "
            f"{signature.confidence_level} | EMIT (cooldown expired, "
            f"{time_since_last.total_seconds() / 60:.1f} min since last)"
        )
        return True
    
    # Still within cooldown - suppress alert
    remaining_minutes = (cooldown_delta - time_since_last).total_seconds() / 60
    logger.info(
        f"AlertThrottle: {signature.symbol} | {signature.action} | "
        f"{signature.confidence_level} | SUPPRESS (cooldown active, "
        f"{remaining_minutes:.1f} min remaining)"
    )
    return False


def clear_cache() -> None:
    """Clear the alert cache.
    
    This function is primarily for testing purposes. It clears all cached
    alert signatures and their timestamps.
    """
    global _alert_cache
    _alert_cache.clear()
    logger.info("AlertThrottle: Cache cleared")


def get_cache_size() -> int:
    """Get the current size of the alert cache.
    
    Returns
    -------
    int
        Number of cached alert signatures.
    """
    return len(_alert_cache)


__all__ = ["AlertSignature", "should_emit_alert", "clear_cache", "get_cache_size"]
