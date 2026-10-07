# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Alert deduplication and cooldown engine.

This module prevents duplicate alerts by tracking decision fingerprints
and implementing cooldown periods for high-urgency alerts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional

from app.core.engine.actions import ActionDecision, Urgency


class AlertDedupeEngine:
    """Manages alert deduplication and cooldown logic.
    
    Tracks decision fingerprints per symbol to prevent duplicate notifications.
    Implements cooldown periods for high-urgency alerts.
    """
    
    def __init__(self):
        """Initialize the dedupe engine with in-memory storage."""
        # Symbol -> (fingerprint, last_sent_at)
        self._decision_cache: dict[str, tuple[str, datetime]] = {}
    
    def _compute_fingerprint(self, symbol: str, decision: ActionDecision) -> str:
        """Compute a fingerprint for a decision.
        
        Parameters
        ----------
        symbol:
            Position symbol.
        decision:
            Action decision to fingerprint.
        
        Returns
        -------
        str
            SHA256 hash of the decision's key attributes.
        """
        # Create a stable representation of the decision
        key_data = {
            "symbol": symbol,
            "action": decision.action.value,
            "urgency": decision.urgency.value,
            "reasons": sorted(decision.reasons),  # Sort for consistency
            # Include roll plan if present
            "roll_plan": None,
        }
        
        if decision.roll_plan:
            key_data["roll_plan"] = {
                "roll_type": decision.roll_plan.roll_type,
                "suggested_strike": decision.roll_plan.suggested_strike,
                "suggested_expiry": decision.roll_plan.suggested_expiry.isoformat(),
            }
        
        # Serialize to JSON and hash
        json_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def should_notify(
        self,
        symbol: str,
        decision: ActionDecision,
        cooldown_minutes: int = 60,
    ) -> bool:
        """Determine if an alert should be sent.
        
        Rules:
        - If fingerprint unchanged and urgency != HIGH => do not notify
        - If urgency == HIGH and fingerprint unchanged:
          - notify only if last_sent_at older than cooldown_minutes
        
        Parameters
        ----------
        symbol:
            Position symbol.
        decision:
            Action decision to evaluate.
        cooldown_minutes:
            Cooldown period in minutes for HIGH urgency alerts (default: 60).
        
        Returns
        -------
        bool
            True if alert should be sent, False otherwise.
        """
        fingerprint = self._compute_fingerprint(symbol, decision)
        
        # Check if we have a previous decision for this symbol
        if symbol in self._decision_cache:
            prev_fingerprint, last_sent_at = self._decision_cache[symbol]
            
            # If fingerprint unchanged
            if fingerprint == prev_fingerprint:
                # If urgency is not HIGH, do not notify
                if decision.urgency != Urgency.HIGH:
                    return False
                
                # If urgency is HIGH, check cooldown
                if decision.urgency == Urgency.HIGH:
                    cooldown_delta = timedelta(minutes=cooldown_minutes)
                    if datetime.now() - last_sent_at < cooldown_delta:
                        return False
        
        # Update cache and return True
        self._decision_cache[symbol] = (fingerprint, datetime.now())
        return True
    
    def record_notification(self, symbol: str, decision: ActionDecision) -> None:
        """Record that a notification was sent.
        
        This method updates the cache with the current fingerprint and timestamp.
        It's called after a notification is successfully sent.
        
        Parameters
        ----------
        symbol:
            Position symbol.
        decision:
            Action decision that was sent.
        """
        fingerprint = self._compute_fingerprint(symbol, decision)
        self._decision_cache[symbol] = (fingerprint, datetime.now())
    
    def clear_cache(self) -> None:
        """Clear all cached decisions."""
        self._decision_cache.clear()
    
    def get_last_sent_at(self, symbol: str) -> Optional[datetime]:
        """Get the last sent timestamp for a symbol.
        
        Parameters
        ----------
        symbol:
            Position symbol.
        
        Returns
        -------
        Optional[datetime]
            Last sent timestamp, or None if not found.
        """
        if symbol in self._decision_cache:
            return self._decision_cache[symbol][1]
        return None


__all__ = ["AlertDedupeEngine"]
