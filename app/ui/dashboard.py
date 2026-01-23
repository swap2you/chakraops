#!/usr/bin/env python3
"""ChakraOps Dashboard - Streamlit web interface."""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
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
from app.core.persistence import (
    record_trade,
    upsert_position_from_trade,
    list_open_positions as persistence_list_open_positions,
    mark_candidate_executed,
    list_candidates as persistence_list_candidates,
    list_alerts,
    ack_alert,
    archive_alert,
    bulk_ack_alerts,
    bulk_archive_non_action_alerts,
    save_portfolio_snapshot,
    get_latest_portfolio_snapshot,
    get_enabled_symbols,
    list_universe_symbols,
    add_universe_symbol,
    toggle_universe_symbol,
    delete_universe_symbol,
    reset_local_trading_state,
    get_assignment_profile,
    set_assignment_override,
    is_assignment_blocked,
)
from app.core.symbol_cache import (
    fetch_and_cache_theta_symbols,
    search_symbols,
    get_cached_symbol_count,
)
from app.core.market_time import get_market_state, is_market_open
from app.core.heartbeat import HeartbeatManager, REGIME_STALE_THRESHOLD_MINUTES

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
if "record_execution_modal" not in st.session_state:
    st.session_state.record_execution_modal = None
if "show_reset_confirm" not in st.session_state:
    st.session_state.show_reset_confirm = False
if "selected_brokerage" not in st.session_state:
    st.session_state.selected_brokerage = "Robinhood"
if "heartbeat_started" not in st.session_state:
    st.session_state.heartbeat_started = False

# Defensive check: ensure all required tables exist on startup (Phase 1B fix)
try:
    from app.core.persistence import init_persistence_db
    init_persistence_db()
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to initialize persistence database on dashboard startup: {e}")
    # Don't fail dashboard load, but log the error


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
    """Get CSP candidates - filtered by enabled symbols only, with assignment profiles (Phase 1B)."""
    # Check cache first
    if st.session_state.candidates_cache is not None:
        # Filter by enabled symbols and enrich with assignment profiles
        try:
            enabled_symbols = set(get_enabled_symbols())
            filtered = [c for c in st.session_state.candidates_cache if c.get("symbol") in enabled_symbols]
            # Enrich with assignment profiles
            for candidate in filtered:
                symbol = candidate.get("symbol")
                if symbol:
                    profile = get_assignment_profile(symbol)
                    if profile:
                        candidate["assignment_score"] = profile.get("assignment_score", 0)
                        candidate["assignment_label"] = profile.get("assignment_label", "NEUTRAL")
                        candidate["operator_override"] = profile.get("operator_override", False)
                        candidate["blocked"] = is_assignment_blocked(symbol)
                    else:
                        # No profile yet - not blocked
                        candidate["assignment_score"] = 0
                        candidate["assignment_label"] = "NEUTRAL"
                        candidate["operator_override"] = False
                        candidate["blocked"] = False
            return filtered
        except Exception:
            return st.session_state.candidates_cache

    # Use persistence module to get candidates (excludes executed by default)
    try:
        candidates = persistence_list_candidates(include_executed=False)
        # Filter by enabled symbols
        enabled_symbols = set(get_enabled_symbols())
        candidates = [c for c in candidates if c.get("symbol") in enabled_symbols]
        
        # Enrich with assignment profiles (Phase 1B)
        for candidate in candidates:
            symbol = candidate.get("symbol")
            if symbol:
                profile = get_assignment_profile(symbol)
                if profile:
                    candidate["assignment_score"] = profile.get("assignment_score", 0)
                    candidate["assignment_label"] = profile.get("assignment_label", "NEUTRAL")
                    candidate["operator_override"] = profile.get("operator_override", False)
                    candidate["blocked"] = is_assignment_blocked(symbol)
                else:
                    # No profile yet - not blocked
                    candidate["assignment_score"] = 0
                    candidate["assignment_label"] = "NEUTRAL"
                    candidate["operator_override"] = False
                    candidate["blocked"] = False
        
        st.session_state.candidates_cache = candidates
        return candidates
    except Exception:
        pass

    # If no DB or empty, return empty list
    return []


def get_alerts(limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get latest alerts from database."""
    try:
        alerts = list_alerts(status=status)
        return alerts[:limit]
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
    if level_upper == "HALT":
        return "🔴"
    elif level_upper == "ACTION":
        return "🟠"
    elif level_upper == "WATCH":
        return "🟡"
    else:  # INFO
        return "🔵"


def _render_alert(alert: Dict[str, Any]) -> None:
    """Helper function to render a single alert."""
    alert_id = alert.get("id")
    level = alert.get("level", "INFO")
    status = alert.get("status", "OPEN")
    color_icon = get_level_color(level)
    message = alert.get("message", "")
    timestamp = alert.get("created_at", "")
    
    # Status badge
    status_badge = {
        "OPEN": "🟢",
        "ACKED": "🟡",
        "ARCHIVED": "⚫",
    }.get(status, "⚪")
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        # Create colored container based on level
        if level.upper() == "HALT":
            st.error(f"{color_icon} **{level}** | {status_badge} {status} | {message} | *{timestamp}*")
        elif level.upper() == "ACTION":
            st.error(f"{color_icon} **{level}** | {status_badge} {status} | {message} | *{timestamp}*")
        elif level.upper() == "WATCH":
            st.warning(f"{color_icon} **{level}** | {status_badge} {status} | {message} | *{timestamp}*")
        else:  # INFO
            st.info(f"{color_icon} **{level}** | {status_badge} {status} | {message} | *{timestamp}*")
    
    with col2:
        if status == "OPEN" and alert_id:
            col_ack, col_arch = st.columns(2)
            with col_ack:
                if st.button("✓ Ack", key=f"ack_{alert_id}", use_container_width=True):
                    ack_alert(alert_id)
                    st.rerun()
            with col_arch:
                if st.button("📦 Archive", key=f"arch_{alert_id}", use_container_width=True):
                    archive_alert(alert_id)
                    st.rerun()


def _get_consecutive_zero_candidate_days() -> int:
    """Get consecutive days with 0 actionable candidates (Phase 1C).
    
    Uses ET date for consistency with heartbeat tracking.
    
    Returns
    -------
    int
        Number of consecutive days with 0 candidates.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return 0
    
    try:
        import pytz
        
        # Get ET date (not UTC) for consistency
        et_tz = pytz.timezone("America/New_York")
        et_today = datetime.now(et_tz).date()
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if tracking table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidate_daily_tracking (
                date TEXT PRIMARY KEY,
                candidate_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Check today's count (ET date)
        today_str = et_today.isoformat()
        cursor.execute("""
            SELECT candidate_count FROM candidate_daily_tracking
            WHERE date = ?
        """, (today_str,))
        
        row = cursor.fetchone()
        if row and row[0] == 0:
            # Count consecutive days with 0 candidates
            cursor.execute("""
                SELECT date, candidate_count
                FROM candidate_daily_tracking
                WHERE candidate_count = 0
                ORDER BY date DESC
            """)
            rows = cursor.fetchall()
            
            # Count consecutive days from today backwards (ET dates)
            consecutive = 0
            expected_date = et_today
            
            for row in rows:
                row_date = datetime.fromisoformat(row[0]).date()
                if row_date == expected_date:
                    consecutive += 1
                    expected_date = expected_date - timedelta(days=1)
                else:
                    break
            
            conn.close()
            return consecutive
        
        conn.close()
        return 0
    except Exception:
        return 0


def _update_candidate_daily_tracking(count: int) -> None:
    """Update daily candidate count tracking (Phase 1C - ET date, upsert per day).
    
    Parameters
    ----------
    count:
        Number of actionable candidates today.
    """
    try:
        import pytz
        
        # Get ET date (not UTC) for consistency with heartbeat
        et_tz = pytz.timezone("America/New_York")
        et_now = datetime.now(et_tz)
        et_date = et_now.date().isoformat()
    except Exception:
        # Fallback to UTC if pytz not available
        et_date = datetime.now(timezone.utc).date().isoformat()
    
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidate_daily_tracking (
                date TEXT PRIMARY KEY,
                candidate_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        created_at = datetime.now(timezone.utc).isoformat()
        
        # Upsert (insert or replace, preserve original created_at)
        cursor.execute("""
            INSERT OR REPLACE INTO candidate_daily_tracking (date, candidate_count, created_at, updated_at)
            VALUES (?, ?, 
                COALESCE((SELECT created_at FROM candidate_daily_tracking WHERE date = ?), ?),
                ?)
        """, (et_date, count, et_date, created_at, created_at))
        
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    """Main dashboard function."""
    # Start background heartbeat (once per session)
    if not st.session_state.heartbeat_started:
        try:
            heartbeat = HeartbeatManager.get_instance()
            heartbeat.start()
            st.session_state.heartbeat_started = True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to start heartbeat: {e}")
            # Don't fail dashboard load if heartbeat fails
    
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
        
        # DEV ONLY: Reset Local Trading State
        st.subheader("⚠️ DEV Controls")
        if st.button("🗑️ Reset Local Trading State (DEV ONLY)", use_container_width=True, type="secondary"):
            st.session_state.show_reset_confirm = True
        
        if st.session_state.get("show_reset_confirm", False):
            st.warning("⚠️ This will delete all local trading data!")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("✅ Confirm Reset", use_container_width=True, type="primary"):
                    try:
                        reset_local_trading_state()
                        st.success("✅ Local trading state reset successfully!")
                        st.session_state.show_reset_confirm = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error resetting: {e}")
            with col_no:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.show_reset_confirm = False
                    st.rerun()
        
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
    
    # Portfolio Snapshot Section (Phase 1A.1 - moved here, with brokerage selector)
    st.header("💰 Portfolio Snapshot")
    
    # Brokerage selector
    brokerage_options = ["Robinhood", "Fidelity", "Charles Schwab"]
    selected_brokerage = st.selectbox(
        "Brokerage",
        brokerage_options,
        index=brokerage_options.index(st.session_state.selected_brokerage) if st.session_state.selected_brokerage in brokerage_options else 0,
        key="brokerage_selector"
    )
    st.session_state.selected_brokerage = selected_brokerage
    
    # Show latest snapshot for selected brokerage
    latest_snapshot = get_latest_portfolio_snapshot(brokerage=selected_brokerage)
    if latest_snapshot:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Account Value", f"${latest_snapshot['account_value']:,.2f}")
        with col2:
            st.metric("Cash", f"${latest_snapshot['cash']:,.2f}")
        with col3:
            invested = latest_snapshot['account_value'] - latest_snapshot['cash']
            st.metric("Invested", f"${invested:,.2f}")
        
        st.caption(f"Last updated: {latest_snapshot['timestamp'][:19] if latest_snapshot.get('timestamp') else 'N/A'}")
        if latest_snapshot.get('notes'):
            st.info(f"Notes: {latest_snapshot['notes']}")
    else:
        st.info(f"No snapshot found for {selected_brokerage}. Create one below.")
    
    # Snapshot input form
    with st.expander("📝 Update Portfolio Snapshot", expanded=False):
        with st.form("portfolio_snapshot_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                account_value = st.number_input("Account Value ($)", value=latest_snapshot['account_value'] if latest_snapshot else 0.0, step=100.0)
                cash = st.number_input("Cash ($)", value=latest_snapshot['cash'] if latest_snapshot else 0.0, step=100.0)
            
            with col2:
                timestamp = st.text_input("Timestamp (ISO)", value=datetime.now(timezone.utc).isoformat())
                notes = st.text_area("Notes (optional)", value="")
            
            submit_snapshot = st.form_submit_button("💾 Save Snapshot", use_container_width=True, type="primary")
            
            if submit_snapshot:
                try:
                    snapshot_id = save_portfolio_snapshot(
                        account_value=account_value,
                        cash=cash,
                        brokerage=selected_brokerage,
                        timestamp=timestamp if timestamp else None,
                        notes=notes if notes else None,
                    )
                    st.success(f"✅ Snapshot saved! ID: {snapshot_id}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error saving snapshot: {e}")

    st.divider()

    # Heartbeat Health Panel (Phase 1D - Hardened)
    heartbeat = HeartbeatManager.get_instance()
    health = heartbeat.get_health()
    
    with st.expander("💓 Heartbeat Health", expanded=False):
        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        
        with col_h1:
            if health["last_cycle_time"]:
                last_cycle = datetime.fromisoformat(health["last_cycle_time"])
                age_seconds = (datetime.now(timezone.utc) - last_cycle).total_seconds()
                if age_seconds < 120:
                    st.metric("Status", "🟢 Running", delta=f"{int(age_seconds)}s ago")
                else:
                    st.metric("Status", "🟡 Stale", delta=f"{int(age_seconds/60)}m ago")
            else:
                st.metric("Status", "⚪ Unknown", delta="No cycles")
        
        with col_h2:
            status = health["status"]
            status_icon = {
                "SUCCESS": "✅",
                "ERROR": "❌",
                "NO_REGIME": "⚠️",
                "NO_DATA": "⚠️",
                "NO_SNAPSHOT": "⚠️",
                "REGIME_STALE": "🟡",
            }.get(status, "⚪")
            st.metric("Last Cycle", f"{status_icon} {status}")
        
        with col_h3:
            if health["data_timestamp"]:
                data_time = datetime.fromisoformat(health["data_timestamp"])
                data_age_minutes = (datetime.now(timezone.utc) - data_time).total_seconds() / 60.0
                if data_age_minutes < 5:
                    st.metric("Data Age", f"{data_age_minutes:.1f}m", delta="Fresh")
                elif data_age_minutes < 15:
                    st.metric("Data Age", f"{data_age_minutes:.1f}m", delta="Stale", delta_color="off")
                else:
                    st.metric("Data Age", f"{data_age_minutes:.1f}m", delta="Very Stale", delta_color="inverse")
            else:
                st.metric("Data Age", "N/A")
        
        with col_h4:
            if health["last_error"]:
                st.error(f"❌ {health['last_error'][:50]}")
            else:
                st.success("✅ No errors")
        
        if health["is_running"]:
            st.caption("🟢 Heartbeat thread is running")
        else:
            st.warning("⚠️ Heartbeat thread is not running")
    
    # Heartbeat Evaluation Debug Panel
    eval_details = heartbeat.get_cycle_eval_details()
    
    with st.expander("🔍 Heartbeat Evaluation Debug", expanded=False):
        if health["last_cycle_time"]:
            last_cycle = datetime.fromisoformat(health["last_cycle_time"])
            # Convert to ET for display
            try:
                import pytz
                et_tz = pytz.timezone("America/New_York")
                if last_cycle.tzinfo is None:
                    last_cycle = pytz.UTC.localize(last_cycle)
                last_cycle_et = last_cycle.astimezone(et_tz)
                cycle_time_str = last_cycle_et.strftime("%Y-%m-%d %H:%M:%S %Z")
            except Exception:
                cycle_time_str = last_cycle.strftime("%Y-%m-%d %H:%M:%S UTC")
            
            col_e1, col_e2, col_e3 = st.columns(3)
            
            with col_e1:
                st.metric("Last Cycle Time (ET)", cycle_time_str)
                st.metric("Symbols Evaluated", eval_details.get("symbols_evaluated", 0))
                st.metric("Enabled Universe Size", eval_details.get("enabled_universe_size", 0))
            
            with col_e2:
                st.metric("CSP Candidates Found", eval_details.get("csp_candidates_count", 0))
                st.metric("Rejected Symbols", eval_details.get("rejected_symbols_count", 0))
                market_age = eval_details.get("market_data_age_minutes", 0.0)
                if market_age < 5:
                    st.metric("Market Data Age", f"{market_age:.1f}m", delta="Fresh")
                elif market_age < 15:
                    st.metric("Market Data Age", f"{market_age:.1f}m", delta="Stale", delta_color="off")
                else:
                    st.metric("Market Data Age", f"{market_age:.1f}m", delta="Very Stale", delta_color="inverse")
            
            with col_e3:
                rejection_reasons = eval_details.get("rejection_reasons", {})
                if rejection_reasons:
                    st.write("**Top Rejection Reasons:**")
                    # Sort by count, get top 3
                    sorted_reasons = sorted(
                        rejection_reasons.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:3]
                    for reason, count in sorted_reasons:
                        st.write(f"- {reason}: {count}")
                else:
                    st.write("**Top Rejection Reasons:**")
                    st.caption("No rejections recorded")
        else:
            st.info("No cycle evaluation data available yet. Heartbeat may not have completed a cycle.")
    
    # Market Snapshot Panel (Phase 2A)
    from app.core.market_snapshot import get_active_snapshot, build_market_snapshot, load_snapshot_data, normalize_symbol
    from app.core.persistence import get_enabled_symbols
    
    # Reload snapshot explicitly (refresh after build)
    snapshot = get_active_snapshot()
    with st.expander("📸 Market Snapshot", expanded=False):
        if snapshot:
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            
            with col_s1:
                try:
                    import pytz
                    et_tz = pytz.timezone("America/New_York")
                    snapshot_time = datetime.fromisoformat(snapshot["snapshot_timestamp_et"])
                    if snapshot_time.tzinfo is None:
                        snapshot_time = pytz.UTC.localize(snapshot_time)
                    snapshot_time_et = snapshot_time.astimezone(et_tz)
                    snapshot_str = snapshot_time_et.strftime("%Y-%m-%d %H:%M:%S %Z")
                except Exception:
                    snapshot_str = snapshot["snapshot_timestamp_et"]
                st.metric("Snapshot Time (ET)", snapshot_str)
            
            with col_s2:
                # Extract source from provider field
                provider = snapshot.get("provider", "snapshot")
                source = "UNKNOWN"
                if "csv" in provider.lower():
                    source = "CSV"
                elif "cache" in provider.lower():
                    source = "CACHE"
                else:
                    source = "SNAPSHOT"
                st.metric("Mode", "SNAPSHOT", delta=f"Source: {source}")
            
            with col_s3:
                # Calculate coverage: normalized(snapshot_symbols) ∩ normalized(enabled_universe_symbols)
                snapshot_data = load_snapshot_data(snapshot["snapshot_id"])
                snapshot_symbols_normalized = {normalize_symbol(s) for s in snapshot_data.keys()}
                
                enabled_symbols = get_enabled_symbols()
                enabled_symbols_normalized = {normalize_symbol(s) for s in enabled_symbols}
                
                # Intersection = covered symbols
                covered_symbols = snapshot_symbols_normalized & enabled_symbols_normalized
                symbols_with_data = len([v for s, v in snapshot_data.items() if normalize_symbol(s) in covered_symbols and v is not None])
                
                st.metric(
                    "Symbols Covered",
                    f"{len(covered_symbols)}/{len(enabled_symbols_normalized)}",
                    delta=f"{len(enabled_symbols_normalized) - len(covered_symbols)} missing"
                )
            
            with col_s4:
                age_minutes = snapshot.get("data_age_minutes", 0.0)
                age_hours = age_minutes / 60.0
                if age_hours < 1:
                    age_str = f"{age_minutes:.1f}m"
                else:
                    age_str = f"{age_hours:.1f}h"
                st.metric("Snapshot Age", age_str)
        else:
            st.warning("⚠️ No active snapshot available. Build a snapshot to enable evaluation.")
        
        # Build snapshot button
        if st.button("🔨 Build New Snapshot", use_container_width=True, type="primary"):
            with st.spinner("Building market snapshot from enabled universe..."):
                try:
                    result = build_market_snapshot(mode="AUTO")
                    source = result.get("source", "UNKNOWN")
                    st.success(
                        f"✅ Snapshot built! "
                        f"ID: {result['snapshot_id'][:8]}... | "
                        f"Source: {source} | "
                        f"Symbols: {result['symbols_with_data']}/{result['symbol_count']} with data"
                    )
                    st.rerun()
                except ValueError as e:
                    # Operator-facing error message
                    st.error(f"❌ {str(e)}")
                except Exception as e:
                    st.error(f"❌ Failed to build snapshot: {e}")
    
    st.divider()

    # Daily Trading Plan Card (Phase 1C)
    st.header("📋 Daily Trading Plan")
    
    # Get actionable candidates (not blocked, not executed)
    actionable_candidates = []
    has_error = False
    error_message = ""
    
    try:
        all_candidates = get_csp_candidates()
        actionable_candidates = [
            c for c in all_candidates
            if not c.get("blocked", False) or c.get("operator_override", False)
        ]
    except Exception as e:
        has_error = True
        error_message = str(e)
        actionable_candidates = []
    
    # Determine plan status
    if has_error:
        plan_status = "HALT"
        plan_message = f"System halted — data unavailable: {error_message}"
        plan_color = "#721c24"
        plan_bg = "#f8d7da"
        plan_icon = "🛑"
    elif len(actionable_candidates) > 0:
        plan_status = "ACTIONABLE"
        plan_message = f"{len(actionable_candidates)} CSP opportunity{'ies' if len(actionable_candidates) != 1 else 'y'} available"
        plan_color = "#155724"
        plan_bg = "#d4edda"
        plan_icon = "✅"
    else:
        plan_status = "INFO"
        plan_message = "No trades today — conditions not favorable"
        plan_color = "#856404"
        plan_bg = "#fff3cd"
        plan_icon = "ℹ️"
    
    # Display plan card
    st.markdown(
        f"""
        <div style="background-color: {plan_bg}; color: {plan_color}; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            <h2 style="margin: 0; color: {plan_color};">
                {plan_icon} {plan_status}
            </h2>
            <p style="margin: 10px 0 0 0; color: {plan_color}; font-size: 16px;">
                {plan_message}
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Universe Guidance (Phase 1C) - Track consecutive days with 0 candidates
    if len(actionable_candidates) == 0 and not has_error:
        # Check consecutive days with 0 candidates
        consecutive_days = _get_consecutive_zero_candidate_days()
        if consecutive_days >= 2:
            st.info(
                f"📊 No opportunities found for {consecutive_days} consecutive days. "
                "Consider expanding your symbol universe. See Universe Manager section below."
            )
    
    st.divider()

    # Market Regime Section - Large Status Card
    st.header("📈 Market Regime")
    regime = get_regime_snapshot()
    
    # Check regime freshness (Phase 1D)
    regime_stale_warning = None
    if regime:
        try:
            created_at_str = regime.get("created_at")
            if created_at_str:
                created_at = datetime.fromisoformat(created_at_str)
                age_minutes = (datetime.now(timezone.utc) - created_at).total_seconds() / 60.0
                if age_minutes > REGIME_STALE_THRESHOLD_MINUTES:
                    regime_stale_warning = f"⚠️ Regime data is {age_minutes:.1f} minutes old (stale threshold: {REGIME_STALE_THRESHOLD_MINUTES} min)"
        except Exception:
            pass
    
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
        
        # Regime freshness warning (Phase 1D)
        if regime_stale_warning:
            st.warning(regime_stale_warning)
        
        # Details expander
        with st.expander("📋 View Detailed Metrics", expanded=False):
            st.json(regime.get("details", {}))
    else:
        st.warning("⚠️ No regime data available. Run the main application to collect regime snapshots.")

    st.divider()

    # CSP Candidates Section (Phase 1B - with Assignment-Worthy scoring)
    st.header("🎯 CSP Candidates")
    
    # Get candidates with assignment profiles
    candidates = get_csp_candidates()
    
    # Update daily tracking (Phase 1C)
    actionable_count = len([c for c in candidates if not c.get("blocked", False) or c.get("operator_override", False)])
    _update_candidate_daily_tracking(actionable_count)

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
            symbol = candidate.get("symbol", "")
            score = candidate.get("score", 0)
            assignment_score = candidate.get("assignment_score", 0)
            assignment_label = candidate.get("assignment_label", "NEUTRAL")
            blocked = candidate.get("blocked", False)
            operator_override = candidate.get("operator_override", False)
            
            with st.container():
                # Score badge color
                if score >= 80:
                    badge_color = "🟢"
                elif score >= 60:
                    badge_color = "🟡"
                else:
                    badge_color = "🟠"
                
                # Assignment badge (Phase 1B)
                if assignment_label == "OK_TO_OWN":
                    aw_badge = "✅ OK_TO_OWN"
                    aw_color = "🟢"
                    aw_style = "background-color: #d4edda; color: #155724; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                elif assignment_label == "NEUTRAL":
                    aw_badge = "⚪ NEUTRAL"
                    aw_color = "⚪"
                    aw_style = "background-color: #e9ecef; color: #495057; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                else:  # RENT_ONLY
                    aw_badge = "🚫 RENT_ONLY"
                    aw_color = "🔴"
                    aw_style = "background-color: #f8d7da; color: #721c24; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
                
                # Blocked status
                if blocked and not operator_override:
                    blocked_banner = st.error(f"🚫 **Blocked: Not Assignment-Worthy** - {symbol} is marked as RENT_ONLY. Override required to allow CSP.")
                elif blocked and operator_override:
                    blocked_banner = st.warning(f"⚠️ **Overridden** - {symbol} is RENT_ONLY but operator override is active.")
                else:
                    blocked_banner = None
                
                # Main candidate card
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col1:
                    st.markdown(f"### {badge_color} {symbol}")
                    st.metric("CSP Score", f"{score}/100")
                    st.markdown(f'<span style="{aw_style}">{aw_color} {aw_badge}</span>', unsafe_allow_html=True)
                    st.metric("Assignment Score", f"{assignment_score}/100")
                
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
                    # Assignment Override Control (Phase 1B)
                    if assignment_label == "RENT_ONLY":
                        st.write("**Assignment Override:**")
                        current_override = operator_override
                        override_key = f"override_{symbol}_{i}"
                        override_reason_key = f"override_reason_{symbol}_{i}"
                        
                        # Use form for override to handle state properly
                        with st.form(f"override_form_{symbol}_{i}"):
                            override_enabled = st.checkbox(
                                "Allow CSP (Override)",
                                value=current_override,
                                key=override_key
                            )
                            
                            if override_enabled and not current_override:
                                # Show reason input when enabling override
                                override_reason = st.text_input(
                                    "Override Reason (optional)",
                                    key=override_reason_key,
                                    placeholder="e.g., Temporary trade, monitoring closely"
                                )
                            elif current_override:
                                # Show current override reason if exists
                                profile = get_assignment_profile(symbol)
                                if profile and profile.get("override_reason"):
                                    st.caption(f"Reason: {profile.get('override_reason')}")
                            
                            col_save, col_remove = st.columns(2)
                            with col_save:
                                if st.form_submit_button("💾 Save", use_container_width=True):
                                    try:
                                        reason = None
                                        if override_enabled:
                                            # Get reason from session state if available
                                            reason_key = f"override_reason_{symbol}_{i}"
                                            if reason_key in st.session_state:
                                                reason = st.session_state[reason_key]
                                        
                                        set_assignment_override(
                                            symbol=symbol,
                                            override=override_enabled,
                                            reason=reason
                                        )
                                        st.session_state.candidates_cache = None
                                        st.success(f"✅ Override {'enabled' if override_enabled else 'disabled'} for {symbol}")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
                            
                            with col_remove:
                                if current_override and st.form_submit_button("Remove", use_container_width=True):
                                    try:
                                        set_assignment_override(
                                            symbol=symbol,
                                            override=False,
                                            reason=None
                                        )
                                        st.session_state.candidates_cache = None
                                        st.success(f"✅ Override removed for {symbol}")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
                    
                    # Record Execution button (only if not blocked or overridden) - with market-time awareness (Phase 1C)
                    contract = candidate.get("contract")
                    market_state = get_market_state()
                    market_is_open = is_market_open()
                    
                    if contract and (not blocked or operator_override):
                        button_key = f"record_exec_{symbol}_{i}"
                        button_disabled = not market_is_open
                        button_tooltip = ""
                        
                        if not market_is_open:
                            if market_state == "WEEKEND":
                                button_tooltip = "Market is closed (Weekend)"
                            elif market_state == "PRE_MARKET":
                                button_tooltip = "Market opens at 9:30 AM ET"
                            else:
                                button_tooltip = "Market is closed"
                        
                        if st.button(
                            "📝 Record Execution",
                            key=button_key,
                            use_container_width=True,
                            disabled=button_disabled,
                            help=button_tooltip if button_tooltip else None
                        ):
                            st.session_state.record_execution_modal = symbol
                            st.rerun()
                        
                        if button_disabled:
                            st.caption(f"⏸️ {button_tooltip}")
                    elif blocked and not operator_override:
                        st.caption("⚠️ Blocked - Override required")
                    
                    # Candidate Explainability (Phase 1C) - "Why?" expander
                    with st.expander("❓ Why?", expanded=False):
                        # CSP Score Components
                        st.write("**CSP Score Components:**")
                        st.metric("CSP Score", f"{score}/100")
                        reasons = candidate.get("reasons", [])
                        if reasons:
                            for reason in reasons:
                                st.write(f"• {reason}")
                        else:
                            st.write("No CSP reasons provided")
                        
                        st.divider()
                        
                        # Assignment Score + Label
                        st.write("**Assignment-Worthiness:**")
                        st.metric("Assignment Score", f"{assignment_score}/100")
                        st.write(f"**Label:** {assignment_label}")
                        
                        assignment_reasons = candidate.get("assignment_reasons", [])
                        if assignment_reasons:
                            for reason in assignment_reasons:
                                st.write(f"• {reason}")
                        
                        # Blocking reason if RENT_ONLY
                        if blocked and not operator_override:
                            st.divider()
                            st.warning(f"**Blocked:** {symbol} is marked as RENT_ONLY. Override required to allow CSP.")
                        elif operator_override:
                            st.info(f"**Override Active:** Operator has overridden RENT_ONLY blocking for {symbol}.")
                        
                        # Key Levels
                        key_levels = candidate.get("key_levels", {})
                        if key_levels:
                            st.divider()
                            st.write("**Key Levels:**")
                            if key_levels.get("close"):
                                st.write(f"• Close: ${key_levels['close']:.2f}")
                            if key_levels.get("ema50"):
                                st.write(f"• EMA50: ${key_levels['ema50']:.2f}")
                            if key_levels.get("ema200"):
                                st.write(f"• EMA200: ${key_levels['ema200']:.2f}")
                            if key_levels.get("rsi") is not None:
                                st.write(f"• RSI: {key_levels['rsi']:.1f}")
                
                if i < len(candidates):
                    st.divider()
    else:
        st.info("📭 No CSP candidates found. Run the wheel engine to generate candidates.")

    st.divider()
    
    # Record Execution Modal
    if st.session_state.record_execution_modal:
        candidate_symbol = st.session_state.record_execution_modal
        # Find candidate details
        candidate_details = None
        for c in candidates:
            if c['symbol'] == candidate_symbol:
                candidate_details = c
                break
        
        if candidate_details:
            contract = candidate_details.get("contract", {})
            with st.container():
                st.header("📝 Record Trade Execution")
                
                with st.form(f"record_trade_form_{candidate_symbol}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        symbol = st.text_input("Symbol", value=candidate_symbol, disabled=True)
                        strike = st.number_input("Strike", value=float(contract.get('strike', 0)) if contract.get('strike') else 0.0, step=0.5)
                        expiry = st.text_input("Expiry (YYYY-MM-DD)", value=contract.get('expiry', ''))
                        contracts = st.number_input("Contracts", value=1, min_value=1, step=1)
                    
                    with col2:
                        premium = st.number_input("Premium Collected ($)", value=float(contract.get('premium_estimate', 0)) if contract.get('premium_estimate') else 0.0, step=0.01)
                        timestamp = st.text_input("Timestamp (ISO)", value=datetime.now(timezone.utc).isoformat())
                        notes = st.text_area("Notes (optional)", value="")
                    
                    # Capital Impact Preview (Phase 1C)
                    if strike > 0 and contracts > 0:
                        required_cash = strike * contracts * 100
                        
                        # Get available cash from latest snapshot
                        latest_snapshot = get_latest_portfolio_snapshot(brokerage=st.session_state.selected_brokerage)
                        available_cash = latest_snapshot.get('cash', 0.0) if latest_snapshot else 0.0
                        
                        cash_percentage = (required_cash / available_cash * 100) if available_cash > 0 else 0
                        
                        st.divider()
                        st.write("**💰 Capital Impact Preview:**")
                        col_cash1, col_cash2 = st.columns(2)
                        with col_cash1:
                            st.metric("Required Cash", f"${required_cash:,.2f}")
                        with col_cash2:
                            st.metric("Available Cash", f"${available_cash:,.2f}")
                        
                        # Warnings
                        if available_cash > 0:
                            if required_cash > available_cash:
                                st.error(f"❌ **Insufficient Cash:** Required ${required_cash:,.2f} exceeds available ${available_cash:,.2f}")
                                execution_disabled = True
                            elif cash_percentage > 25:
                                st.warning(f"⚠️ **High Cash Usage:** {cash_percentage:.1f}% of available cash")
                                execution_disabled = False
                            else:
                                st.success(f"✅ **Cash Available:** {cash_percentage:.1f}% of available cash")
                                execution_disabled = False
                        else:
                            st.warning("⚠️ **No Cash Data:** Update portfolio snapshot to see cash impact")
                            execution_disabled = False
                        
                        st.divider()
                    else:
                        execution_disabled = False
                    
                    # Market-time awareness (Phase 1C)
                    market_state = get_market_state()
                    market_is_open = is_market_open()
                    
                    if not market_is_open:
                        if market_state == "WEEKEND":
                            st.info("⏸️ **Market Closed:** Weekend. Execution disabled.")
                        elif market_state == "PRE_MARKET":
                            st.info("⏸️ **Market Closed:** Pre-market. Market opens at 9:30 AM ET.")
                        else:
                            st.info("⏸️ **Market Closed:** After hours. Execution disabled.")
                        execution_disabled = True
                    
                    col_submit, col_cancel = st.columns(2)
                    with col_submit:
                        submit = st.form_submit_button(
                            "💾 Save Trade",
                            use_container_width=True,
                            type="primary",
                            disabled=execution_disabled
                        )
                    with col_cancel:
                        cancel = st.form_submit_button("❌ Cancel", use_container_width=True)
                    
                    if submit and not execution_disabled:
                        try:
                            # Record trade
                            trade_id = record_trade(
                                symbol=symbol,
                                action="SELL_TO_OPEN",
                                strike=strike if strike > 0 else None,
                                expiry=expiry if expiry else None,
                                contracts=contracts,
                                premium=premium,
                                timestamp=timestamp if timestamp else None,
                                notes=notes if notes else None,
                            )
                            
                            # Create position from trade
                            position = upsert_position_from_trade(trade_id)
                            
                            # Mark candidate as executed
                            mark_candidate_executed(symbol, executed=True)
                            
                            # Clear cache and modal
                            st.session_state.candidates_cache = None
                            st.session_state.record_execution_modal = None
                            
                            st.success(f"✅ Trade recorded! Position created: {position.id if position else 'N/A'}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error recording trade: {e}")
                    
                    if cancel:
                        st.session_state.record_execution_modal = None
                        st.rerun()
    
    st.divider()
    
    # Active Positions Section (Phase 1A)
    st.header("📊 Active Positions")
    try:
        open_positions = persistence_list_open_positions()
        
        if open_positions:
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            total_contracts = sum(p.contracts for p in open_positions)
            total_premium = sum(p.premium_collected for p in open_positions)
            unique_symbols = len(set(p.symbol for p in open_positions))
            
            with col1:
                st.metric("Open Positions", len(open_positions))
            with col2:
                st.metric("Total Contracts", total_contracts)
            with col3:
                st.metric("Total Premium", f"${total_premium:,.2f}")
            with col4:
                st.metric("Unique Symbols", unique_symbols)
            
            st.write("")  # Spacing
            
            # Positions table
            positions_data = []
            for pos in open_positions:
                avg_credit = pos.premium_collected / pos.contracts if pos.contracts > 0 else 0
                positions_data.append({
                    "Symbol": pos.symbol,
                    "Strike": f"${pos.strike:.2f}" if pos.strike else "N/A",
                    "Expiry": pos.expiry or "N/A",
                    "Contracts": pos.contracts,
                    "Avg Credit": f"${avg_credit:.2f}",
                    "Total Premium": f"${pos.premium_collected:.2f}",
                    "Status": pos.state or pos.status,
                    "Entry Date": pos.entry_date[:10] if pos.entry_date else "N/A",
                })
            
            df_positions = pd.DataFrame(positions_data)
            st.dataframe(df_positions, use_container_width=True, hide_index=True)
        else:
            st.info("No open positions.")
    except Exception as e:
        st.warning(f"Unable to load positions: {e}")

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

    # Alerts Section (Phase 1A.1 - with grouping, scroll, bulk actions)
    st.header("🔔 Alerts")
    
    # Alert status filter
    alert_status_filter = st.selectbox(
        "Filter by Status",
        ["OPEN", "ACKED", "ARCHIVED", "ALL"],
        index=0,
        key="alert_status_filter"
    )
    
    status_filter = None if alert_status_filter == "ALL" else alert_status_filter
    all_alerts = get_alerts(limit=200, status=status_filter)
    
    # Filter out system/internal errors (only show operator alerts)
    operator_alerts = [
        a for a in all_alerts
        if a.get("level", "").upper() in ["INFO", "WATCH", "ACTION", "HALT"]
    ]
    
    if operator_alerts:
        # Bulk actions
        col_bulk1, col_bulk2 = st.columns(2)
        with col_bulk1:
            if st.button("✓ Ack All (Visible)", use_container_width=True, key="bulk_ack"):
                visible_ids = [a["id"] for a in operator_alerts if a.get("status") == "OPEN"]
                if visible_ids:
                    bulk_ack_alerts(visible_ids)
                    st.success(f"✅ Acknowledged {len(visible_ids)} alert(s)")
                    st.rerun()
        with col_bulk2:
            if st.button("📦 Archive All (Non-Action)", use_container_width=True, key="bulk_archive"):
                non_action_ids = [a["id"] for a in operator_alerts if a.get("level") != "ACTION" and a.get("status") != "ARCHIVED"]
                if non_action_ids:
                    bulk_archive_non_action_alerts(non_action_ids)
                    st.success(f"✅ Archived {len(non_action_ids)} alert(s)")
                    st.rerun()
        
        # Group alerts by date
        from datetime import date as date_type
        today = date_type.today()
        yesterday = date_type.fromordinal(today.toordinal() - 1)
        
        alerts_today = []
        alerts_yesterday = []
        alerts_older = []
        
        for alert in operator_alerts:
            try:
                alert_date_str = alert.get("created_at", "")[:10]  # YYYY-MM-DD
                if alert_date_str:
                    alert_date = date_type.fromisoformat(alert_date_str)
                    if alert_date == today:
                        alerts_today.append(alert)
                    elif alert_date == yesterday:
                        alerts_yesterday.append(alert)
                    else:
                        alerts_older.append(alert)
                else:
                    alerts_older.append(alert)
            except Exception:
                alerts_older.append(alert)
        
        # Scrollable container with fixed max height
        alerts_container = st.container()
        with alerts_container:
            # Use custom CSS for scroll containment
            st.markdown("""
                <style>
                .alerts-scroll-container {
                    max-height: 400px;
                    overflow-y: auto;
                    border: 1px solid #e0e0e0;
                    border-radius: 5px;
                    padding: 10px;
                }
                </style>
            """, unsafe_allow_html=True)
            
            alerts_html = '<div class="alerts-scroll-container">'
            
            # Today (expanded by default)
            if alerts_today:
                with st.expander(f"📅 Today ({len(alerts_today)})", expanded=True):
                    for alert in alerts_today:
                        _render_alert(alert)
            
            # Yesterday (collapsed by default)
            if alerts_yesterday:
                with st.expander(f"📅 Yesterday ({len(alerts_yesterday)})", expanded=False):
                    for alert in alerts_yesterday:
                        _render_alert(alert)
            
            # Older (collapsed by default)
            if alerts_older:
                with st.expander(f"📅 Older ({len(alerts_older)})", expanded=False):
                    for alert in alerts_older:
                        _render_alert(alert)
    else:
        st.info("✅ No alerts found.")
    
    st.divider()
    
    # Universe Manager Section (Phase 1B.2 - with symbol search)
    st.header("🌐 Symbol Universe Manager", anchor="symbol-universe-manager")
    
    try:
        universe_symbols = list_universe_symbols()
        
        # Symbol Search and Cache Management (Phase 1B.2)
        col_cache1, col_cache2 = st.columns([2, 1])
        with col_cache1:
            search_query = st.text_input(
                "🔍 Search Symbols (Type to search cached symbols)",
                value="",
                key="symbol_search",
                placeholder="Type 1-2 characters to search...",
                help="Searches cached ThetaData symbols. Cache symbols first if needed."
            )
        with col_cache2:
            cached_count = get_cached_symbol_count()
            if cached_count == 0:
                if st.button("📥 Fetch & Cache Symbols", use_container_width=True, key="fetch_symbols"):
                    with st.spinner("Fetching symbols from ThetaData..."):
                        try:
                            count = fetch_and_cache_theta_symbols()
                            st.success(f"✅ Cached {count} symbols")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Failed to fetch symbols: {e}")
            else:
                st.caption(f"📊 {cached_count} symbols cached")
                if st.button("🔄 Refresh Cache", use_container_width=True, key="refresh_cache"):
                    with st.spinner("Refreshing symbol cache..."):
                        try:
                            count = fetch_and_cache_theta_symbols()
                            st.success(f"✅ Refreshed {count} symbols")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Failed to refresh: {e}")
        
        # Show search results if query entered
        search_results = []
        if search_query and len(search_query) >= 1:
            search_results = search_symbols(search_query, limit=20)
            if search_results:
                st.subheader(f"Search Results ({len(search_results)} found)")
                # Display search results in a selectable format
                for result in search_results:
                    symbol = result["symbol"]
                    name = result.get("name", "")
                    exchange = result.get("exchange", "")
                    
                    col_sym, col_name, col_action = st.columns([1, 3, 1])
                    with col_sym:
                        st.write(f"**{symbol}**")
                    with col_name:
                        if name:
                            st.caption(f"{name} ({exchange})" if exchange else name)
                        else:
                            st.caption(exchange if exchange else "")
                    with col_action:
                        # Check if already in universe
                        in_universe = any(s["symbol"] == symbol for s in universe_symbols)
                        if in_universe:
                            st.caption("✓ In universe")
                        else:
                            if st.button("➕ Add", key=f"add_search_{symbol}", use_container_width=True):
                                try:
                                    add_universe_symbol(symbol, enabled=True, notes=f"Added from search")
                                    st.success(f"✅ Added {symbol}")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")
                st.divider()
        
        if universe_symbols:
            # Editable table
            df_universe = pd.DataFrame([
                {
                    "Symbol": s["symbol"],
                    "Enabled": "✓" if s["enabled"] else "✗",
                    "Notes": s.get("notes", ""),
                }
                for s in universe_symbols
            ])
            
            st.dataframe(df_universe, use_container_width=True, hide_index=True)
            
            # Add/Edit controls
            with st.expander("➕ Add/Edit Symbol", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    new_symbol = st.text_input("Symbol", value="", key="new_symbol_input").upper()
                    enabled = st.checkbox("Enabled", value=True, key="new_symbol_enabled")
                with col2:
                    notes = st.text_area("Notes", value="", key="new_symbol_notes")
                
                col_add, col_space = st.columns([1, 3])
                with col_add:
                    if st.button("➕ Add/Update Symbol", use_container_width=True, key="add_symbol_btn"):
                        if new_symbol:
                            try:
                                add_universe_symbol(new_symbol, enabled=enabled, notes=notes if notes else None)
                                st.success(f"✅ Symbol {new_symbol} {'enabled' if enabled else 'disabled'}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {e}")
                        else:
                            st.warning("Please enter a symbol")
            
            # Quick toggle controls
            st.subheader("Quick Toggle")
            toggle_cols = st.columns(min(5, len(universe_symbols)))
            for i, symbol_data in enumerate(universe_symbols):
                col_idx = i % len(toggle_cols)
                with toggle_cols[col_idx]:
                    symbol = symbol_data["symbol"]
                    current_enabled = symbol_data["enabled"]
                    button_label = f"Disable {symbol}" if current_enabled else f"Enable {symbol}"
                    if st.button(button_label, key=f"toggle_{symbol}", use_container_width=True):
                        toggle_universe_symbol(symbol, not current_enabled)
                        st.rerun()
        else:
            st.info("No symbols in universe. Add symbols using the form above.")
    except Exception as e:
        st.warning(f"Unable to load universe: {e}")


if __name__ == "__main__":
    main()
