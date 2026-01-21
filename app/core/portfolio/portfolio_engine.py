# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Portfolio summary computation engine.

This module contains pure business logic for computing portfolio metrics.
No UI, alerts, or external integrations - only computation logic.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Literal

from app.core.models.position import Position

logger = logging.getLogger(__name__)

ProgressStatus = Literal["BEHIND", "ON_TRACK", "AHEAD"]


class PortfolioEngine:
    """Engine for computing portfolio summary metrics."""

    def compute_summary(
        self,
        positions: List[Position],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute portfolio summary metrics.
        
        Parameters
        ----------
        positions:
            List of Position objects to analyze.
        config:
            Configuration dictionary. Expected keys:
            - target_monthly_income: float (optional, defaults to 0.0)
        
        Returns
        -------
        dict
            Summary with:
            - open_positions: int
            - capital_at_risk: float
            - premium_collected_mtd: float
            - estimated_monthly_income: float
            - target_monthly_income: float
            - progress_status: "BEHIND" | "ON_TRACK" | "AHEAD"
        """
        today = date.today()
        first_of_month = date(today.year, today.month, 1)
        
        # Get days elapsed in current month
        days_elapsed = (today - first_of_month).days + 1
        
        # Calculate days in current month
        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)
        days_in_month = (next_month - first_of_month).days
        
        # Filter open positions
        open_positions = [p for p in positions if p.status == "OPEN"]
        open_count = len(open_positions)
        
        # Calculate capital at risk (for CSP positions only)
        capital_at_risk = 0.0
        for position in open_positions:
            if position.position_type == "CSP" and position.strike and position.contracts:
                # Capital at risk = strike * contracts * 100 (per contract)
                capital_at_risk += position.strike * position.contracts * 100
        
        # Calculate premium collected month-to-date
        premium_collected_mtd = 0.0
        for position in positions:
            # Check if position was opened this month
            try:
                entry_datetime = datetime.fromisoformat(position.entry_date)
                entry_date = entry_datetime.date()
                
                if entry_date >= first_of_month:
                    premium_collected_mtd += position.premium_collected
            except (ValueError, AttributeError, TypeError):
                # Skip positions with invalid entry_date
                logger.warning(f"Invalid entry_date for position {position.id}: {position.entry_date}")
                continue
        
        # Estimate monthly income based on current pace
        estimated_monthly_income = 0.0
        if days_elapsed > 0:
            # Extrapolate: (premium_mtd / days_elapsed) * days_in_month
            estimated_monthly_income = (premium_collected_mtd / days_elapsed) * days_in_month
        
        # Get target monthly income from config
        target_monthly_income = float(config.get("target_monthly_income", 0.0))
        
        # Determine progress status
        progress_status: ProgressStatus = "BEHIND"
        if target_monthly_income > 0:
            if estimated_monthly_income >= target_monthly_income * 1.1:
                # 110% or more of target
                progress_status = "AHEAD"
            elif estimated_monthly_income >= target_monthly_income * 0.9:
                # 90-110% of target
                progress_status = "ON_TRACK"
            else:
                # Less than 90% of target
                progress_status = "BEHIND"
        else:
            # No target set - consider ON_TRACK if we have any income
            if estimated_monthly_income > 0:
                progress_status = "ON_TRACK"
        
        return {
            "open_positions": open_count,
            "capital_at_risk": capital_at_risk,
            "premium_collected_mtd": premium_collected_mtd,
            "estimated_monthly_income": estimated_monthly_income,
            "target_monthly_income": target_monthly_income,
            "progress_status": progress_status,
        }


__all__ = ["PortfolioEngine", "ProgressStatus"]
