# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1: Position service — manual execution tracking.

IMPORTANT: ChakraOps NEVER places trades. The "Execute" action records the user's
intention and creates a Position with status=OPEN. The user must execute the trade
manually in their brokerage account.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.positions.models import (
    Position,
    VALID_STATUSES,
    VALID_STRATEGIES,
    generate_position_id,
)
from app.core.positions import store
from app.core.accounts import store as account_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_manual_execute(data: Dict[str, Any]) -> List[str]:
    """Validate manual execution payload. Returns list of error messages."""
    errors: List[str] = []

    if not data.get("account_id"):
        errors.append("account_id is required")
    else:
        account = account_store.get_account(data["account_id"])
        if account is None:
            errors.append(f"Account {data['account_id']} not found")
        elif not account.active:
            errors.append(f"Account {data['account_id']} is not active")

    if not data.get("symbol"):
        errors.append("symbol is required")

    strategy = data.get("strategy", "")
    if strategy not in VALID_STRATEGIES:
        errors.append(f"strategy must be one of {sorted(VALID_STRATEGIES)}")

    if strategy in ("CSP", "CC"):
        contracts = data.get("contracts", 0)
        if not isinstance(contracts, int) or contracts <= 0:
            errors.append("contracts must be a positive integer for options strategies")
    elif strategy == "STOCK":
        quantity = data.get("quantity", 0)
        if not isinstance(quantity, int) or quantity <= 0:
            errors.append("quantity must be a positive integer for STOCK strategy")

    return errors


# ---------------------------------------------------------------------------
# Service operations
# ---------------------------------------------------------------------------


def list_positions(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    exclude_test: bool = False,
) -> List[Position]:
    """List all tracked positions, optionally filtered by symbol and exclude_test."""
    return store.list_positions(status=status, symbol=symbol, exclude_test=exclude_test)


def get_position(position_id: str) -> Optional[Position]:
    """Get a single position."""
    return store.get_position(position_id)


def close_position(
    position_id: str,
    close_price: float,
    close_time_utc: Optional[str] = None,
    close_fees: Optional[float] = None,
) -> Tuple[Optional[Position], List[str]]:
    """
    Close an OPEN position. Sets status=CLOSED, computes realized_pnl.
    close_price: Debit per share to buy back (for options). For CSP: realized = open_credit - (close_price*100*contracts).
    Returns (updated position, errors).
    """
    position = store.get_position(position_id)
    if position is None:
        return None, [f"Position {position_id} not found"]
    if (position.status or "").upper() not in ("OPEN", "PARTIAL_EXIT"):
        return None, [f"Position is already {position.status}; cannot close"]
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    close_ts = close_time_utc or now
    # Compute close_debit and realized_pnl for options
    strategy = (position.strategy or "").upper()
    close_debit: Optional[float] = None
    realized_pnl: Optional[float] = None
    if strategy in ("CSP", "CC") and position.contracts:
        close_debit = float(close_price) * 100 * int(position.contracts)
        open_credit = position.open_credit or position.credit_expected
        if open_credit is not None:
            # credit_expected is typically total premium; if < 10 assume per-share
            cred = float(open_credit)
            open_total = cred * 100 * int(position.contracts) if cred < 10 else cred
            realized_pnl = open_total - close_debit - (close_fees or 0)
        else:
            realized_pnl = -close_debit - (close_fees or 0)
    updates = {
        "status": "CLOSED",
        "closed_at": close_ts,
        "close_price": close_price,
        "close_debit": close_debit,
        "close_fees": close_fees,
        "close_time_utc": close_ts,
        "realized_pnl": realized_pnl,
        "updated_at_utc": now,
    }
    updated = store.update_position(position_id, updates)
    return updated, []


def delete_position(position_id: str) -> Tuple[bool, Optional[str]]:
    """
    Delete a position. Allowed only when is_test=True OR status=CLOSED.
    Returns (success, error_message).
    """
    position = store.get_position(position_id)
    if position is None:
        return False, f"Position {position_id} not found"
    if not position.is_test and (position.status or "").upper() not in ("CLOSED", "ABORTED"):
        return False, "Delete allowed only for CLOSED/ABORTED positions or test (is_test=true) positions"
    ok = store.delete_position(position_id)
    return ok, None


def manual_execute(data: Dict[str, Any]) -> Tuple[Optional[Position], List[str]]:
    """Create a position from manual execution.

    This does NOT place a trade. It records the user's intention to execute.
    The user must execute the actual trade in their brokerage.

    Returns (position, errors).
    """
    errors = validate_manual_execute(data)
    if errors:
        return None, errors

    now = datetime.now(timezone.utc).isoformat()
    position_id = data.get("position_id") or generate_position_id()

    # Phase 4: Optional entry decision snapshot (band, risk_flags, etc.)
    position = Position(
        position_id=position_id,
        account_id=data["account_id"],
        symbol=data["symbol"].upper().strip(),
        strategy=data["strategy"],
        contracts=int(data.get("contracts", 0)),
        strike=data.get("strike"),
        expiration=data.get("expiration"),
        credit_expected=data.get("credit_expected") or data.get("entry_credit"),
        quantity=data.get("quantity"),
        status="OPEN",
        opened_at=now,
        closed_at=None,
        notes=data.get("notes", ""),
        band=data.get("band"),
        risk_flags_at_entry=data.get("risk_flags_at_entry"),
        portfolio_utilization_pct=data.get("portfolio_utilization_pct"),
        sector_exposure_pct=data.get("sector_exposure_pct"),
        thesis_strength=data.get("thesis_strength"),
        data_sufficiency=data.get("data_sufficiency"),
        risk_amount_at_entry=data.get("risk_amount_at_entry"),
        data_sufficiency_override=data.get("data_sufficiency_override"),
        data_sufficiency_override_source=data.get("data_sufficiency_override_source"),
    )

    try:
        created = store.create_position(position)
        try:
            from app.core.audit import audit_manual_execution_intent
            audit_manual_execution_intent(
                position.position_id, position.symbol, position.strategy,
                position.account_id, position.contracts,
            )
        except Exception as e:
            logger.warning("[POSITIONS] Audit log failed: %s", e)
        logger.info(
            "[POSITIONS] Manual execution recorded: %s %s %s (%d contracts)",
            position.symbol,
            position.strategy,
            position.position_id,
            position.contracts,
        )
        return created, []
    except ValueError as e:
        return None, [str(e)]


# Paper positions: same store, account_id="paper"; sizing validated against default account
PAPER_ACCOUNT_ID = "paper"


def _compute_collateral(strategy: str, strike: float, contracts: int) -> float:
    """CSP/CC collateral = strike * 100 * contracts."""
    if (strategy or "").upper() in ("CSP", "CC") and strike and contracts:
        return float(strike) * 100 * int(contracts)
    return 0.0


def _derive_contract_key(strategy: str, strike: float, expiration: str) -> str:
    """Derive contract_key from strike-expiry-type."""
    opt = "PUT" if (strategy or "").upper() == "CSP" else "CALL"
    exp = (expiration or "")[:10] if expiration else ""
    return f"{strike}-{exp}-{opt}"


def _resolve_run_id_from_timestamp(evaluation_timestamp_utc: str) -> Optional[str]:
    """
    Phase 11.1: Attempt to resolve run_id from evaluation_timestamp_utc.
    Try canonical artifact first, then run artifacts latest.
    """
    if not evaluation_timestamp_utc or not isinstance(evaluation_timestamp_utc, str):
        return None
    ts = evaluation_timestamp_utc.strip()[:26]  # trim to avoid timezone suffix mismatch
    try:
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
        store = get_evaluation_store_v2()
        artifact = store.get_latest()
        if artifact and artifact.metadata:
            pt = (artifact.metadata.get("pipeline_timestamp") or artifact.metadata.get("evaluation_timestamp_utc") or "")
            if pt and pt.strip()[:26] == ts:
                return artifact.metadata.get("run_id")
    except Exception:
        pass
    try:
        from app.core.eval.run_artifacts import _latest_manifest_path
        p = _latest_manifest_path()
        if p.exists():
            import json
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            completed = (data.get("completed_at") or "")[:26]
            if completed and completed == ts:
                return data.get("run_id")
    except Exception:
        pass
    return None


def add_paper_position(data: Dict[str, Any]) -> Tuple[Optional[Position], List[str], int]:
    """Create a paper position from a candidate.
    Phase 11.0: Requires contract identity (underlying, option_type, strike, expiry, contracts).
    Optional: option_symbol, contract_key, decision_ref, open_credit, open_price, open_time_utc.
    Validates against default account sizing; returns 409 if limits exceeded.
    Returns (position, errors, status_code).
    """
    errors: List[str] = []
    if not data.get("symbol"):
        errors.append("symbol is required")
    strategy = (data.get("strategy") or "CSP").upper().strip()
    if strategy not in VALID_STRATEGIES:
        errors.append(f"strategy must be one of {sorted(VALID_STRATEGIES)}")
    if strategy in ("CSP", "CC"):
        contracts_val = data.get("contracts", 1)
        if not isinstance(contracts_val, int) or contracts_val <= 0:
            errors.append("contracts must be a positive integer for options strategies")
        strike_val = data.get("strike")
        if strike_val is None:
            errors.append("strike is required for CSP/CC")
        exp_val = data.get("expiration") or data.get("expiry")
        if not exp_val:
            errors.append("expiration is required for CSP/CC")
    if errors:
        return None, errors, 400

    strike_val = data.get("strike")
    exp_val = data.get("expiration") or data.get("expiry")
    contracts_val = int(data.get("contracts", 1))
    collateral = _compute_collateral(strategy, float(strike_val or 0), contracts_val)
    option_type = "PUT" if strategy == "CSP" else "CALL"
    contract_key = data.get("contract_key") or (_derive_contract_key(strategy, float(strike_val or 0), exp_val or "") if strategy in ("CSP", "CC") else None)
    option_symbol = data.get("option_symbol")

    # Phase 11.0: Sizing validation against default account
    default_account = account_store.get_default_account()
    if default_account and collateral > 0:
        mcp = getattr(default_account, "max_collateral_per_trade", None)
        if mcp is not None and collateral > float(mcp):
            return None, [f"Collateral ${collateral:,.0f} exceeds max per trade ${mcp:,.0f}"], 409
        mtc = getattr(default_account, "max_total_collateral", None)
        if mtc is not None:
            open_positions = store.list_positions(status=None, symbol=None, exclude_test=False)
            total_collateral = 0.0
            for p in open_positions:
                if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT"):
                    c = getattr(p, "collateral", None)
                    if c is not None:
                        total_collateral += float(c)
                    elif p.strike and p.contracts:
                        total_collateral += _compute_collateral(p.strategy or "", float(p.strike), int(p.contracts))
            if total_collateral + collateral > float(mtc):
                return None, [f"Total collateral would be ${total_collateral + collateral:,.0f}, exceeds max ${mtc:,.0f}"], 409
        mpo = getattr(default_account, "max_positions_open", None)
        if mpo is not None:
            open_count = sum(1 for p in store.list_positions(status=None, symbol=None, exclude_test=False)
                            if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT"))
            if open_count >= int(mpo):
                return None, [f"Max open positions ({mpo}) already reached"], 409
        mcc = getattr(default_account, "min_credit_per_contract", None)
        if mcc is not None:
            credit = data.get("open_credit") or data.get("credit_expected") or data.get("credit")
            if credit is not None:
                per_contract = float(credit) / contracts_val if contracts_val else 0
                if per_contract < float(mcc):
                    return None, [f"Credit per contract ${per_contract:.2f} below minimum ${mcc:.2f}"], 409

    now = datetime.now(timezone.utc).isoformat()
    position_id = data.get("position_id") or generate_position_id()
    decision_ref = data.get("decision_ref")
    if decision_ref is not None and not isinstance(decision_ref, dict):
        decision_ref = None
    # Phase 11.1: Resolve run_id if decision_ref has evaluation_timestamp_utc but no run_id
    if decision_ref and not decision_ref.get("run_id") and decision_ref.get("evaluation_timestamp_utc"):
        resolved = _resolve_run_id_from_timestamp(decision_ref.get("evaluation_timestamp_utc"))
        if resolved:
            decision_ref = dict(decision_ref)
            decision_ref["run_id"] = resolved

    position = Position(
        position_id=position_id,
        account_id=PAPER_ACCOUNT_ID,
        symbol=data["symbol"].upper().strip(),
        strategy=strategy,
        contracts=contracts_val,
        strike=strike_val,
        expiration=exp_val,
        credit_expected=data.get("credit_expected") or data.get("credit"),
        quantity=data.get("quantity"),
        status="OPEN",
        opened_at=data.get("created_at") or now,
        closed_at=None,
        notes=data.get("notes", ""),
        underlying=data["symbol"].upper().strip(),
        option_type=option_type,
        option_symbol=option_symbol,
        contract_key=contract_key,
        decision_ref=decision_ref,
        open_credit=data.get("open_credit") or data.get("credit_expected") or data.get("credit"),
        open_price=data.get("open_price"),
        open_time_utc=data.get("open_time_utc") or now,
    )
    try:
        created = store.create_position(position)
        logger.info("[POSITIONS] Paper position created: %s %s %s", position.symbol, position.strategy, position_id)
        return created, [], 200
    except ValueError as e:
        return None, [str(e)], 400
