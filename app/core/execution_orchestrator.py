# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Execution Orchestrator for simulating execution of ExecutionPlan (DRY-RUN ONLY).

This module provides a pure, deterministic simulation layer that simulates
execution of ExecutionPlan objects and produces ExecutionResult objects.

The orchestrator does NOT execute trades, integrate with broker APIs, or mutate
position state. It is a DRY-RUN ONLY simulation layer with no side effects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from app.core.execution_planner import ExecutionPlan

logger = logging.getLogger(__name__)


class ExecutionOrchestrationError(Exception):
    """Raised when execution orchestration fails due to invalid inputs."""
    
    def __init__(self, message: str, symbol: Optional[str] = None):
        self.message = message
        self.symbol = symbol
        super().__init__(message)


@dataclass
class ExecutionResult:
    """Result of simulated execution of an ExecutionPlan.
    
    Attributes
    ----------
    symbol:
        Position symbol.
    action:
        Action type: "HOLD" | "CLOSE" | "ROLL" | "ALERT".
    status:
        Execution status: "SIMULATED" | "NO_OP" | "ERROR".
    executed_steps:
        List of steps that were simulated as executed.
    skipped_steps:
        List of steps that were skipped (if any).
    notes:
        List of notes and observations from simulation.
    simulated_at:
        Timestamp when this simulation was performed (ISO format).
    """
    symbol: str
    action: str  # HOLD | CLOSE | ROLL | ALERT
    status: str  # SIMULATED | NO_OP | ERROR
    executed_steps: List[str] = field(default_factory=list)
    skipped_steps: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    simulated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def orchestrate_execution(execution_plan: ExecutionPlan) -> ExecutionResult:
    """Simulate execution of an ExecutionPlan (DRY-RUN ONLY).
    
    This function is deterministic, stateless, and never mutates position state
    or accesses databases. It simulates execution of an ExecutionPlan and
    produces an ExecutionResult.
    
    Parameters
    ----------
    execution_plan:
        ExecutionPlan object to simulate execution for.
    
    Returns
    -------
    ExecutionResult
        Result of simulated execution with executed steps, skipped steps, and notes.
    
    Raises
    ------
    ExecutionOrchestrationError
        If execution_plan is None or invalid.
    
    Simulation Rules:
    -----------------
    - Iterate through execution_plan.steps and log each as simulated
    - HOLD / ALERT produce empty execution with explanatory notes
    - All steps are simulated (not actually executed)
    - Status is "SIMULATED" for actionable plans, "NO_OP" for HOLD/ALERT
    """
    # Validate input
    if not execution_plan:
        error_msg = "execution_plan is None or invalid"
        logger.error(f"ExecutionOrchestrator: {error_msg}")
        raise ExecutionOrchestrationError(error_msg)
    
    symbol = execution_plan.symbol
    action = execution_plan.action
    steps = execution_plan.steps or []
    
    # Create base result
    result = ExecutionResult(
        symbol=symbol,
        action=action,
        status="SIMULATED",
        simulated_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Handle different action types
    if action == "HOLD":
        result = _orchestrate_hold(result, execution_plan)
    elif action == "ALERT":
        result = _orchestrate_alert(result, execution_plan)
    elif action == "CLOSE":
        result = _orchestrate_close(result, execution_plan)
    elif action == "ROLL":
        result = _orchestrate_roll(result, execution_plan)
    else:
        # Unknown action type
        result.status = "ERROR"
        result.notes.append(f"Unknown action type: {action}")
        logger.error(f"ExecutionOrchestrator: Unknown action type {action} for {symbol}")
    
    # Log result
    if result.status == "NO_OP":
        logger.warning(
            f"ExecutionOrchestrator: {symbol} | {action} NO_OP | steps_simulated={len(result.executed_steps)}"
        )
    elif result.status == "ERROR":
        logger.error(
            f"ExecutionOrchestrator: {symbol} | {action} ERROR | {result.notes}"
        )
    else:
        logger.info(
            f"ExecutionOrchestrator: {symbol} | {action} SIMULATED | steps_executed={len(result.executed_steps)} | steps_skipped={len(result.skipped_steps)}"
        )
    
    return result


def _orchestrate_hold(result: ExecutionResult, plan: ExecutionPlan) -> ExecutionResult:
    """Simulate HOLD action (no-op)."""
    result.status = "NO_OP"
    result.notes.append("HOLD action requires no execution")
    result.notes.append("Position remains unchanged")
    
    # Simulate the steps (they are informational only)
    for step in plan.steps:
        result.executed_steps.append(f"[SIMULATED] {step}")
        logger.info(f"ExecutionOrchestrator: {result.symbol} | HOLD | Simulated: {step}")
    
    return result


def _orchestrate_alert(result: ExecutionResult, plan: ExecutionPlan) -> ExecutionResult:
    """Simulate ALERT action (notification-only)."""
    result.status = "NO_OP"
    result.notes.append("ALERT action requires no position execution")
    result.notes.append("Notification would be sent to configured channels")
    
    # Simulate the steps
    for step in plan.steps:
        result.executed_steps.append(f"[SIMULATED] {step}")
        logger.info(f"ExecutionOrchestrator: {result.symbol} | ALERT | Simulated: {step}")
    
    return result


def _orchestrate_close(result: ExecutionResult, plan: ExecutionPlan) -> ExecutionResult:
    """Simulate CLOSE action (buy-to-close)."""
    result.status = "SIMULATED"
    result.notes.append("DRY-RUN: No actual trade execution")
    result.notes.append("Buy-to-close order would be placed with limit pricing")
    
    # Simulate each step
    for i, step in enumerate(plan.steps, 1):
        simulated_step = f"[SIMULATED] {step}"
        result.executed_steps.append(simulated_step)
        logger.info(f"ExecutionOrchestrator: {result.symbol} | CLOSE | Step {i}: {simulated_step}")
        
        # Add notes for key steps
        if "limit price" in step.lower() or "place" in step.lower():
            result.notes.append(f"Step {i}: {step}")
    
    # Add execution parameters to notes
    if plan.parameters:
        pricing_strategy = plan.parameters.get("pricing_strategy", "N/A")
        limit_offset = plan.parameters.get("limit_price_offset", 0.0)
        result.notes.append(f"Pricing strategy: {pricing_strategy} with offset ${limit_offset:.2f}")
    
    return result


def _orchestrate_roll(result: ExecutionResult, plan: ExecutionPlan) -> ExecutionResult:
    """Simulate ROLL action (buy-to-close + sell-to-open)."""
    result.status = "SIMULATED"
    result.notes.append("DRY-RUN: No actual trade execution")
    result.notes.append("Two-leg roll would be executed: buy-to-close + sell-to-open")
    
    # Simulate each step
    for i, step in enumerate(plan.steps, 1):
        simulated_step = f"[SIMULATED] {step}"
        result.executed_steps.append(simulated_step)
        logger.info(f"ExecutionOrchestrator: {result.symbol} | ROLL | Step {i}: {simulated_step}")
        
        # Add notes for key steps
        if "place" in step.lower() or "order" in step.lower():
            result.notes.append(f"Step {i}: {step}")
    
    # Add execution parameters to notes
    if plan.parameters:
        leg1_type = plan.parameters.get("leg1_type", "N/A")
        leg2_type = plan.parameters.get("leg2_type", "N/A")
        result.notes.append(f"Leg 1: {leg1_type}, Leg 2: {leg2_type}")
        
        net_credit_target = plan.parameters.get("roll_net_credit_target", "N/A")
        result.notes.append(f"Net credit target: {net_credit_target}")
    
    return result


__all__ = ["ExecutionResult", "ExecutionOrchestrationError", "orchestrate_execution"]
