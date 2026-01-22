#!/usr/bin/env python3
"""ChakraOps Dashboard - Streamlit web interface."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from app.core.engine.csp_trade_engine import CSPTradeEngine
from app.core.engine.position_engine import PositionEngine
from app.core.engine.risk_engine import RiskEngine
from app.core.engine.roll_engine import RollEngine
from app.core.engine.actions import (
    ActionType,
    Urgency,
    decide_position_action,
)
from app.core.action_engine import evaluate_position_action
from app.core.portfolio.portfolio_engine import PortfolioEngine
from app.core.state_machine.position_state_machine import (
    PositionState,
    get_allowed_transitions,
)

# Set page config
st.set_page_config(
    page_title="ChakraOps Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "regime_cache" not in st.session_state:
    st.session_state.regime_cache = None
if "candidates_cache" not in st.session_state:
    st.session_state.candidates_cache = None


def get_db_path() -> Path:
    """Get path to SQLite database."""
    repo_root = Path(__file__).parent.parent.parent
    db_path = repo_root / "data" / "chakraops.db"
    return db_path


def db_exists() -> bool:
    """Check if database exists."""
    return get_db_path().exists()


def get_regime_snapshot() -> Optional[Dict[str, Any]]:
    """Read latest regime snapshot from database."""
    db_path = get_db_path()
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Try to read from regime_snapshots table
        cursor.execute("""
            SELECT regime, confidence, details, created_at
            FROM regime_snapshots
            ORDER BY created_at DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        conn.close()

        if row:
            import json
            return {
                "regime": row[0],
                "confidence": row[1],
                "details": json.loads(row[2]) if row[2] else {},
                "created_at": row[3],
            }
    except sqlite3.OperationalError:
        # Table doesn't exist
        return None
    except Exception:
        return None

    return None


def get_csp_candidates() -> List[Dict[str, Any]]:
    """Get CSP candidates - re-run wheel engine or read from cache."""
    # Check cache first
    if st.session_state.candidates_cache is not None:
        return st.session_state.candidates_cache

    # Try to get from database
    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT symbol, score, reasons, key_levels, created_at
                FROM csp_candidates
                ORDER BY score DESC, created_at DESC
                LIMIT 50
            """)

            rows = cursor.fetchall()
            conn.close()

            if rows:
                import json
                candidates = []
                for row in rows:
                    candidates.append({
                        "symbol": row[0],
                        "score": row[1],
                        "reasons": json.loads(row[2]) if row[2] else [],
                        "key_levels": json.loads(row[3]) if row[3] else {},
                        "created_at": row[4],
                    })
                st.session_state.candidates_cache = candidates
                return candidates
        except sqlite3.OperationalError:
            pass
        except Exception:
            pass

    # If no DB or empty, return empty list
    return []


def get_alerts(limit: int = 20) -> List[Dict[str, Any]]:
    """Get latest alerts from database."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT message, level, created_at
            FROM alerts
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        alerts = []
        for row in rows:
            alerts.append({
                "message": row[0],
                "level": row[1],
                "created_at": row[2],
            })
        return alerts
    except sqlite3.OperationalError:
        # Table doesn't exist
        return []
    except Exception:
        return []


def get_last_update_time() -> Optional[str]:
    """Get the most recent update time from any table."""
    db_path = get_db_path()
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get latest from regime_snapshots
        cursor.execute("""
            SELECT MAX(created_at) FROM regime_snapshots
        """)
        regime_time = cursor.fetchone()[0]

        # Get latest from csp_candidates
        cursor.execute("""
            SELECT MAX(created_at) FROM csp_candidates
        """)
        candidates_time = cursor.fetchone()[0]

        conn.close()

        # Return the most recent
        times = [t for t in [regime_time, candidates_time] if t]
        if times:
            return max(times)
        return None
    except Exception:
        return None


def get_level_color(level: str) -> str:
    """Get color for alert level."""
    level_upper = level.upper()
    if level_upper == "URGENT":
        return "🔴"
    elif level_upper == "WATCH":
        return "🟡"
    else:  # INFO
        return "🔵"


def main() -> None:
    """Main dashboard function."""
    # Header
    st.title("📊 ChakraOps Dashboard")
    st.caption("Real-time market regime and CSP candidate analysis")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Controls")
        
        if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
            st.session_state.regime_cache = None
            st.session_state.candidates_cache = None
            st.rerun()
        
        st.divider()
        
        # Filters
        st.subheader("🔍 Filters")
        
        # Urgency filter
        urgency_filter = st.selectbox(
            "Urgency",
            ["ALL", "HIGH", "MEDIUM", "LOW"],
            index=0,
        )
        
        # Action filter
        action_filter = st.selectbox(
            "Action",
            ["ALL", "HOLD", "CLOSE", "ROLL", "ALERT"],
            index=0,
        )
        
        st.divider()
        
        # Last update time
        last_update = get_last_update_time()
        if last_update:
            st.metric("Last Update", last_update[:16] if len(last_update) > 16 else last_update)
        else:
            st.info("No data available")
        
        st.divider()
        st.caption("ChakraOps v1.0")

    # Check if database exists
    if not db_exists():
        st.error("⚠️ Database not found")
        with st.container():
            st.info(
                """
                **Setup Instructions:**
                
                1. Make sure you have created the database by running the main application.
                2. The database should be located at: `data/chakraops.db`
                3. Run `python main.py` first to initialize the database and collect data.
                
                Once the database is created, refresh this page to see the dashboard.
                """
            )
        return

    # Portfolio Overview Section
    st.header("💼 Portfolio Overview")
    try:
        from app.core.storage.position_store import PositionStore
        from pathlib import Path
        import sqlite3
        from app.core.models.position import Position
        
        # Get all positions (for MTD calculation) - query directly from database
        all_positions = []
        try:
            db_path = get_db_path()
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        id, symbol, position_type, strike, expiry,
                        contracts, premium_collected, entry_date,
                        status, notes
                    FROM positions
                    ORDER BY entry_date DESC
                """)
                rows = cursor.fetchall()
                conn.close()
                
                # Convert rows to Position objects
                for row in rows:
                    (
                        id_, symbol, position_type, strike, expiry,
                        contracts, premium_collected, entry_date,
                        status, notes,
                    ) = row
                    all_positions.append(Position(
                        id=id_,
                        symbol=symbol,
                        position_type=position_type,  # type: ignore
                        strike=strike,
                        expiry=expiry,
                        contracts=contracts,
                        premium_collected=premium_collected,
                        entry_date=entry_date,
                        status=status,  # type: ignore
                        notes=notes,
                    ))
        except Exception:
            # Fallback to open positions only
            position_engine = PositionEngine()
            all_positions = position_engine.get_open_positions()
        
        # Get config (try to load from config.yaml or use defaults)
        config = {}
        try:
            import yaml
            config_path = Path("config.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f) or {}
        except Exception:
            pass
        
        # Extract portfolio config
        portfolio_config = config.get("portfolio", {})
        target_monthly_income = portfolio_config.get("target_monthly_income", 0.0)
        
        # Compute portfolio summary
        portfolio_engine = PortfolioEngine()
        summary = portfolio_engine.compute_summary(all_positions, {"target_monthly_income": target_monthly_income})
        
        # Display portfolio overview card
        with st.container():
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Open Positions", f"{summary['open_positions']}")
            
            with col2:
                st.metric("Capital at Risk", f"${summary['capital_at_risk']:,.0f}")
            
            with col3:
                # Monthly income: actual + projected
                mtd_actual = summary['premium_collected_mtd']
                projected = summary['estimated_monthly_income']
                st.metric(
                    "Monthly Income",
                    f"${projected:,.0f}",
                    delta=f"${mtd_actual:,.0f} MTD"
                )
            
            with col4:
                # Progress badge
                progress = summary['progress_status']
                if progress == "AHEAD":
                    badge_color = "🟢"
                    badge_style = "background-color: #d4edda; color: #155724; padding: 8px 16px; border-radius: 6px; font-weight: bold;"
                elif progress == "ON_TRACK":
                    badge_color = "🟡"
                    badge_style = "background-color: #fff3cd; color: #856404; padding: 8px 16px; border-radius: 6px; font-weight: bold;"
                else:  # BEHIND
                    badge_color = "🔴"
                    badge_style = "background-color: #f8d7da; color: #721c24; padding: 8px 16px; border-radius: 6px; font-weight: bold;"
                
                st.markdown(
                    f'<div style="{badge_style}">{badge_color} {progress}</div>',
                    unsafe_allow_html=True
                )
        
        # Show target if set
        if summary['target_monthly_income'] > 0:
            st.caption(f"Target: ${summary['target_monthly_income']:,.0f}/month | Progress: {summary['progress_status']}")
    
    except Exception as e:
        st.warning(f"Unable to load portfolio overview: {e}")

    st.divider()

    # Market Regime Section - Large Status Card
    st.header("📈 Market Regime")
    regime = get_regime_snapshot()
    
    if regime:
        # Large status card
        is_risk_on = regime["regime"] == "RISK_ON"
        status_color = "🟢" if is_risk_on else "🔴"
        status_bg = "background-color: #d4edda; padding: 20px; border-radius: 10px;" if is_risk_on else "background-color: #f8d7da; padding: 20px; border-radius: 10px;"
        
        with st.container():
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(
                    f"""
                    <div style="{status_bg}">
                        <h2 style="margin: 0; color: {'#155724' if is_risk_on else '#721c24'};">
                            {status_color} {regime['regime']}
                        </h2>
                        <p style="margin: 5px 0 0 0; color: {'#155724' if is_risk_on else '#721c24'};">
                            Confidence: {regime['confidence']}%
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            with col2:
                st.metric("Confidence", f"{regime['confidence']}%")
            
            with col3:
                if regime.get("created_at"):
                    update_time = regime["created_at"][:16] if len(regime["created_at"]) > 16 else regime["created_at"]
                    st.metric("Updated", update_time)
        
        # Details expander
        with st.expander("📋 View Detailed Metrics", expanded=False):
            st.json(regime.get("details", {}))
    else:
        st.warning("⚠️ No regime data available. Run the main application to collect regime snapshots.")

    st.divider()

    # Proposed CSP Trades Section
    st.header("💼 Proposed CSP Trades")
    
    # Get regime for trade planning
    regime_snapshot = get_regime_snapshot()
    regime_value = regime_snapshot.get("regime") if regime_snapshot else None
    
    # Get candidates
    candidates = get_csp_candidates()
    
    # Generate trade plans
    trade_engine = CSPTradeEngine()
    trade_plans = []
    
    # Default portfolio value (can be made configurable later)
    portfolio_value = 100000.0  # $100k default
    
    if regime_value and candidates:
        for candidate in candidates:
            # Only process candidates with contract details
            if candidate.get("contract"):
                trade_plan = trade_engine.generate_trade_plan(
                    candidate,
                    portfolio_value,
                    regime_value
                )
                if trade_plan:
                    trade_plans.append(trade_plan)
    
    if trade_plans:
        for i, plan in enumerate(trade_plans, 1):
            with st.container():
                col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                
                with col1:
                    st.markdown(f"### {plan['symbol']}")
                    st.metric("Strike", f"${plan['strike']:.2f}")
                
                with col2:
                    st.write("**Expiry:**")
                    st.write(plan['expiry'])
                    st.write("**Contracts:**")
                    st.write(plan['contracts'])
                
                with col3:
                    st.write("**Capital Required:**")
                    st.metric("", f"${plan['capital_required']:,.2f}")
                    st.write("**Est. Premium:**")
                    st.write(f"${plan['estimated_premium']:,.2f}")
                
                with col4:
                    with st.expander("📋 Rationale", expanded=False):
                        for reason in plan.get('rationale', []):
                            st.write(f"• {reason}")
                
                if i < len(trade_plans):
                    st.divider()
    else:
        st.info("No actionable CSP trades today.")
    
    st.divider()

    # CSP Candidates Section
    st.header("🎯 CSP Candidates")

    if candidates:
        # Top candidate highlight
        if len(candidates) > 0:
            top_candidate = candidates[0]
            with st.container():
                st.success(
                    f"🏆 **Top Candidate: {top_candidate['symbol']}** "
                    f"| Score: **{top_candidate['score']}/100**"
                )
        
        st.write("")  # Spacing
        
        # Candidate cards
        for i, candidate in enumerate(candidates, 1):
            with st.container():
                # Score badge color
                score = candidate.get("score", 0)
                if score >= 80:
                    badge_color = "🟢"
                elif score >= 60:
                    badge_color = "🟡"
                else:
                    badge_color = "🟠"
                
                # Main candidate card
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col1:
                    st.markdown(f"### {badge_color} {candidate['symbol']}")
                    st.metric("Score", f"{score}/100")
                
                with col2:
                    key_levels = candidate.get("key_levels", {})
                    st.write("**Key Levels:**")
                    cols = st.columns(3)
                    with cols[0]:
                        st.caption(f"Close: ${key_levels.get('close', 'N/A'):.2f}" if isinstance(key_levels.get('close'), (int, float)) else f"Close: {key_levels.get('close', 'N/A')}")
                    with cols[1]:
                        st.caption(f"EMA50: ${key_levels.get('ema50', 'N/A'):.2f}" if isinstance(key_levels.get('ema50'), (int, float)) else f"EMA50: {key_levels.get('ema50', 'N/A')}")
                    with cols[2]:
                        st.caption(f"EMA200: ${key_levels.get('ema200', 'N/A'):.2f}" if isinstance(key_levels.get('ema200'), (int, float)) else f"EMA200: {key_levels.get('ema200', 'N/A')}")
                    
                    # Contract details if available
                    contract = candidate.get("contract")
                    if contract:
                        st.write("**Contract:**")
                        contract_cols = st.columns(4)
                        with contract_cols[0]:
                            st.caption(f"Expiry: {contract.get('expiry', 'N/A')}")
                        with contract_cols[1]:
                            st.caption(f"Strike: ${contract.get('strike', 'N/A'):.2f}" if isinstance(contract.get('strike'), (int, float)) else f"Strike: {contract.get('strike', 'N/A')}")
                        with contract_cols[2]:
                            st.caption(f"Delta: {contract.get('delta', 'N/A'):.3f}" if isinstance(contract.get('delta'), (int, float)) else f"Delta: {contract.get('delta', 'N/A')}")
                        with contract_cols[3]:
                            premium = contract.get('premium_estimate')
                            if isinstance(premium, (int, float)):
                                st.caption(f"Premium: ${premium:.2f}")
                            else:
                                st.caption(f"Premium: {premium or 'N/A'}")
                
                with col3:
                    with st.expander("📊 Details", expanded=False):
                        st.write("**Reasons:**")
                        reasons = candidate.get("reasons", [])
                        if reasons:
                            for reason in reasons:
                                st.write(f"• {reason}")
                        else:
                            st.write("No reasons provided")
                        
                        st.write("**Full Data:**")
                        st.json(candidate)
                
                if i < len(candidates):
                    st.divider()
    else:
        st.info("📭 No CSP candidates found. Run the wheel engine to generate candidates.")

    st.divider()

    # Today's Focus Card (HIGH urgency count)
    try:
        position_engine = PositionEngine()
        all_open_positions = position_engine.get_open_positions()
        
        # Quick count of HIGH urgency (without full evaluation)
        high_urgency_count = 0
        if all_open_positions:
            regime_snapshot = get_regime_snapshot()
            regime_value = regime_snapshot.get("regime") if regime_snapshot else "RISK_OFF"
            
            try:
                from app.data.yfinance_provider import YFinanceProvider
                price_provider = YFinanceProvider()
            except Exception:
                price_provider = None
            
            for pos in all_open_positions:
                try:
                    market_ctx = {"regime": regime_value}
                    if price_provider:
                        try:
                            df = price_provider.get_daily(pos.symbol, lookback=250)
                            if not df.empty:
                                df = df.sort_values("date", ascending=True).reset_index(drop=True)
                                latest = df.iloc[-1]
                                market_ctx["underlying_price"] = float(latest["close"])
                        except Exception:
                            pass
                    
                    # Use new action engine
                    decision = evaluate_position_action(pos, market_ctx)
                    if decision and decision.urgency == "HIGH":
                        high_urgency_count += 1
                except Exception:
                    pass
    except Exception:
        high_urgency_count = 0
    
    # Today's Focus Card
    if high_urgency_count > 0:
        with st.container():
            st.markdown(
                f"""
                <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: #856404;">🎯 Today's Focus</h3>
                    <p style="margin: 5px 0 0 0; color: #856404; font-size: 18px; font-weight: bold;">
                        {high_urgency_count} HIGH Urgency Alert{'s' if high_urgency_count != 1 else ''}
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )

    # Open Positions Section
    st.header("📂 Open Positions")
    try:
        position_engine = PositionEngine()
        open_positions = position_engine.get_open_positions()
    except Exception as e:
        st.warning(f"Unable to load positions: {e}")
        open_positions = []

    if open_positions:
        # Get regime for market context
        regime_snapshot = get_regime_snapshot()
        regime_value = regime_snapshot.get("regime") if regime_snapshot else "RISK_OFF"
        
        # Get price provider for fetching current prices
        try:
            from app.data.yfinance_provider import YFinanceProvider
            price_provider = YFinanceProvider()
        except Exception:
            price_provider = None
        
        position_data = []
        
        for position in open_positions:
            # Build market context for Action Engine
            market_context = {"regime": regime_value}
            
            # Fetch current price, EMA200, EMA50 if provider available
            if price_provider:
                try:
                    df = price_provider.get_daily(position.symbol, lookback=250)
                    if not df.empty:
                        df = df.sort_values("date", ascending=True).reset_index(drop=True)
                        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
                        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
                        latest = df.iloc[-1]
                        current_price = float(latest["close"])
                        market_context["underlying_price"] = current_price
                        market_context["current_price"] = current_price
                        market_context["EMA200"] = float(latest["ema200"])
                        market_context["EMA50"] = float(latest["ema50"])
                        market_context["price"] = current_price
                        market_context["price_df"] = df
                        
                        # Calculate ATR proxy (3% default)
                        market_context["ATR_pct"] = 0.03
                        
                        # Calculate premium collected percentage
                        if position.strike and position.strike > 0 and position.contracts > 0:
                            premium_per_contract = position.premium_collected / position.contracts
                            premium_pct = (premium_per_contract / (position.strike * 100)) * 100
                            market_context["premium_collected_pct"] = premium_pct
                except Exception:
                    pass  # Continue without price data
            
            # Evaluate position with Action Engine (new Week 4 Day 2 engine)
            action_decision = None
            try:
                action_decision = evaluate_position_action(position, market_context)
            except Exception as e:
                # Fallback to basic decision if Action Engine fails
                action_decision = None
            
            position_data.append({
                "position": position,
                "action_decision": action_decision,
                "market_context": market_context,
            })
        
        # Apply filters
        filtered_data = position_data
        if urgency_filter != "ALL":
            filtered_data = [
                d for d in filtered_data
                if d["action_decision"] and d["action_decision"].urgency == urgency_filter
            ]
        
        if action_filter != "ALL":
            filtered_data = [
                d for d in filtered_data
                if d["action_decision"] and d["action_decision"].action == action_filter
            ]
        
        # Display filtered positions
        if not filtered_data:
            st.info(f"No positions match the selected filters (Urgency: {urgency_filter}, Action: {action_filter})")
        else:
            for i, data in enumerate(filtered_data):
                position = data["position"]
                action_decision = data["action_decision"]
                market_context = data["market_context"]
                
                # Get action and urgency (with fallbacks)
                if action_decision:
                    action = action_decision.action
                    urgency = action_decision.urgency
                    reason_codes = action_decision.reason_codes
                    explanation = action_decision.explanation
                    allowed_next_states = action_decision.allowed_next_states
                else:
                    action = "HOLD"
                    urgency = "LOW"
                    reason_codes = ["Action Engine evaluation unavailable"]
                    explanation = "Unable to evaluate position"
                    allowed_next_states = []
                
                # Calculate premium percentage
                premium_pct = 0.0
                if position.strike and position.strike > 0 and position.contracts > 0:
                    premium_per_contract = position.premium_collected / position.contracts
                    premium_pct = (premium_per_contract / (position.strike * 100)) * 100
                
                # Show position state
                position_state_str = position.state or (position.status if hasattr(position, 'status') else "OPEN")
                try:
                    position_state = PositionState(position_state_str)
                except (ValueError, AttributeError, TypeError):
                    position_state = PositionState.OPEN
                
                with st.container():
                    # Main row with columns
                    col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([1.2, 0.8, 1, 1, 0.8, 1, 1, 1, 1])
                    
                    with col1:
                        st.write(f"**{position.symbol}**")
                    
                    with col2:
                        st.caption(position.position_type)
                    
                    with col3:
                        st.caption(f"${position.strike:.2f}" if position.strike else "N/A")
                    
                    with col4:
                        st.caption(position.expiry or "N/A")
                    
                    with col5:
                        st.caption(f"{position.contracts}")
                    
                    with col6:
                        # State badge
                        if position_state in [PositionState.HOLD, PositionState.OPEN]:
                            state_color = "🟢"
                            state_style = "background-color: #d4edda; color: #155724; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif position_state in [PositionState.ROLL_CANDIDATE, PositionState.ROLLING]:
                            state_color = "🟡"
                            state_style = "background-color: #fff3cd; color: #856404; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif position_state == PositionState.CLOSED:
                            state_color = "⚫"
                            state_style = "background-color: #e2e3e5; color: #383d41; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif position_state == PositionState.ASSIGNED:
                            state_color = "🟣"
                            state_style = "background-color: #d1ecf1; color: #0c5460; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        else:
                            state_color = "⚪"
                            state_style = "background-color: #f8f9fa; color: #6c757d; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        
                        st.markdown(
                            f'<span style="{state_style}">{state_color} {position_state.value}</span>',
                            unsafe_allow_html=True
                        )
                    
                    with col7:
                        # Action badge
                        if action == "HOLD":
                            action_color = "⚪"
                            action_style = "background-color: #e9ecef; color: #495057; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif action == "CLOSE":
                            action_color = "🔵"
                            action_style = "background-color: #cfe2ff; color: #084298; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif action == "ROLL":
                            action_color = "🟡"
                            action_style = "background-color: #fff3cd; color: #856404; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        else:  # ALERT
                            action_color = "🔴"
                            action_style = "background-color: #f8d7da; color: #721c24; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        
                        st.markdown(
                            f'<span style="{action_style}">{action_color} {action}</span>',
                            unsafe_allow_html=True
                        )
                    
                    with col8:
                        # Urgency badge
                        if urgency == "HIGH":
                            urgency_color = "🔴"
                            urgency_style = "background-color: #f8d7da; color: #721c24; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        elif urgency == "MEDIUM":
                            urgency_color = "🟡"
                            urgency_style = "background-color: #fff3cd; color: #856404; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        else:  # LOW
                            urgency_color = "🟢"
                            urgency_style = "background-color: #d4edda; color: #155724; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                        
                        st.markdown(
                            f'<span style="{urgency_style}">{urgency_color} {urgency}</span>',
                            unsafe_allow_html=True
                        )
                    
                    with col9:
                        st.caption(f"{premium_pct:.1f}%")
                    
                    # Expander for details including Action Engine information
                    with st.expander("📋 Details", expanded=False):
                        # Action Decision Section (Week 4 Day 2 Action Engine)
                        if action_decision:
                            st.write("**Action Decision:**")
                            col_a1, col_a2 = st.columns(2)
                            with col_a1:
                                st.metric("Action", action)
                            with col_a2:
                                st.metric("Urgency", urgency)
                            
                            # Explanation
                            if explanation:
                                st.write("**Explanation:**")
                                st.info(explanation)
                            
                            # Reason Codes
                            if reason_codes:
                                st.write("**Reason Codes:**")
                                for code in reason_codes:
                                    st.caption(f"• {code}")
                            
                            # Allowed Next States
                            if allowed_next_states:
                                st.write("**Allowed Next States:**")
                                states_str = ", ".join(allowed_next_states)
                                st.caption(states_str)
                            
                            st.divider()
                        
                        # Current State
                        st.write("**Current State:**")
                        st.write(f"`{position_state.value}`")
                        
                        # Allowed next states
                        allowed_next = get_allowed_transitions(position_state)
                        if allowed_next:
                            st.write("**Allowed Next States:**")
                            allowed_str = ", ".join([s.value for s in allowed_next])
                            st.caption(allowed_str)
                        else:
                            st.write("**Allowed Next States:**")
                            st.caption("None (terminal state)")
                        
                        # State History
                        st.write("**State History:**")
                        state_history = position.state_history or []
                        if state_history:
                            history_data = []
                            for event in state_history:
                                if isinstance(event, dict):
                                    history_data.append({
                                        "From": event.get("from_state", "N/A"),
                                        "To": event.get("to_state", "N/A"),
                                        "Reason": event.get("reason", "N/A"),
                                        "Source": event.get("source", "N/A"),
                                        "Timestamp": event.get("timestamp_iso", "N/A")[:19] if event.get("timestamp_iso") else "N/A",
                                    })
                                else:
                                    # Handle StateTransitionEvent objects
                                    history_data.append({
                                        "From": getattr(event, "from_state", "N/A"),
                                        "To": getattr(event, "to_state", "N/A"),
                                        "Reason": getattr(event, "reason", "N/A"),
                                        "Source": getattr(event, "source", "N/A"),
                                        "Timestamp": getattr(event, "timestamp_iso", "N/A")[:19] if hasattr(event, "timestamp_iso") else "N/A",
                                    })
                            
                            if history_data:
                                st.dataframe(pd.DataFrame(history_data), use_container_width=True, hide_index=True)
                            else:
                                st.caption("No state transitions recorded")
                        else:
                            st.caption("No state history available")
                
                if i < len(filtered_data) - 1:
                    st.divider()
    else:
        st.info("No open positions.")

    st.divider()

    # Alerts Section
    st.header("🔔 Recent Alerts")
    alerts = get_alerts(limit=20)

    if alerts:
        # Color-coded alerts
        for alert in alerts:
            level = alert.get("level", "INFO")
            color_icon = get_level_color(level)
            message = alert.get("message", "")
            timestamp = alert.get("created_at", "")
            
            # Create colored container based on level
            if level.upper() == "URGENT":
                st.error(f"{color_icon} **{level}** | {message} | *{timestamp}*")
            elif level.upper() == "WATCH":
                st.warning(f"{color_icon} **{level}** | {message} | *{timestamp}*")
            else:
                st.info(f"{color_icon} **{level}** | {message} | *{timestamp}*")
    else:
        st.info("✅ No alerts found in database.")


if __name__ == "__main__":
    main()
