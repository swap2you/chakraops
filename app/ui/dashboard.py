#!/usr/bin/env python3
"""ChakraOps Dashboard - Streamlit web interface."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from app.core.engine.csp_trade_engine import CSPTradeEngine
from app.core.engine.position_engine import PositionEngine
from app.core.engine.risk_engine import RiskEngine

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
        
        risk_engine = RiskEngine()
        position_data = []
        
        for position in open_positions:
            # Build market context
            market_context = {"regime": regime_value}
            
            # Fetch current price and EMA200 if provider available
            if price_provider:
                try:
                    df = price_provider.get_daily(position.symbol, lookback=250)
                    if not df.empty:
                        df = df.sort_values("date", ascending=True).reset_index(drop=True)
                        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
                        latest = df.iloc[-1]
                        market_context["current_price"] = float(latest["close"])
                        market_context["ema200"] = float(latest["ema200"])
                except Exception:
                    pass  # Continue without price data
            
            # Evaluate position risk
            try:
                evaluation = risk_engine.evaluate_position(position, market_context)
                risk_status = evaluation["status"]
                premium_pct = evaluation["premium_pct"]
                reasons = evaluation["reasons"]
            except Exception as e:
                risk_status = "HOLD"
                premium_pct = 0.0
                reasons = [f"Evaluation error: {e}"]
            
            position_data.append({
                "position": position,
                "risk_status": risk_status,
                "premium_pct": premium_pct,
                "reasons": reasons,
            })
        
        # Display positions with risk status
        for i, data in enumerate(position_data):
            position = data["position"]
            risk_status = data["risk_status"]
            premium_pct = data["premium_pct"]
            reasons = data["reasons"]
            
            # Color code status
            if risk_status == "HOLD":
                status_color = "🟢"
                status_style = "color: green; font-weight: bold;"
            elif risk_status == "PREPARE_ROLL":
                status_color = "🟡"
                status_style = "color: orange; font-weight: bold;"
            else:  # ACTION_REQUIRED
                status_color = "🔴"
                status_style = "color: red; font-weight: bold;"
            
            with st.container():
                col1, col2, col3, col4, col5, col6, col7 = st.columns([1, 1, 1, 1, 1, 1, 1])
                
                with col1:
                    st.write(f"**{position.symbol}**")
                
                with col2:
                    st.write(position.position_type)
                
                with col3:
                    st.write(f"${position.strike:.2f}" if position.strike else "N/A")
                
                with col4:
                    st.write(position.expiry or "N/A")
                
                with col5:
                    st.write(position.contracts)
                
                with col6:
                    st.markdown(f'<span style="{status_style}">{status_color} {risk_status}</span>', unsafe_allow_html=True)
                
                with col7:
                    st.write(f"{premium_pct:.1f}%")
                
                # Expander for reasons
                with st.expander("❓ Why?", expanded=False):
                    if reasons:
                        for reason in reasons:
                            st.write(f"• {reason}")
                    else:
                        st.write("No reasons available")
            
            if i < len(position_data) - 1:
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
