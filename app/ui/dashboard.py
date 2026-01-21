#!/usr/bin/env python3
"""ChakraOps Dashboard - Streamlit web interface."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

# Set page config
st.set_page_config(
    page_title="ChakraOps Dashboard",
    page_icon="📊",
    layout="wide",
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


def main() -> None:
    """Main dashboard function."""
    # Header
    st.title("📊 ChakraOps Dashboard")

    # Check if database exists
    if not db_exists():
        st.error("⚠️ Database not found")
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

    # Sidebar for refresh
    with st.sidebar:
        st.header("Controls")
        if st.button("🔄 Refresh Data"):
            st.session_state.regime_cache = None
            st.session_state.candidates_cache = None
            st.rerun()

    # Regime Section
    st.header("📈 Market Regime")
    regime = get_regime_snapshot()
    if regime:
        col1, col2, col3 = st.columns(3)

        with col1:
            regime_color = "🟢" if regime["regime"] == "RISK_ON" else "🔴"
            st.metric("Regime", f"{regime_color} {regime['regime']}")

        with col2:
            st.metric("Confidence", f"{regime['confidence']}%")

        with col3:
            if regime.get("created_at"):
                st.metric("Last Updated", regime["created_at"][:16] if len(regime["created_at"]) > 16 else regime["created_at"])

        # Details
        with st.expander("View Details"):
            st.json(regime.get("details", {}))
    else:
        st.info("No regime data available. Run the main application to collect regime snapshots.")

    st.divider()

    # CSP Candidates Section
    st.header("🎯 CSP Candidates")
    candidates = get_csp_candidates()

    if candidates:
        # Create DataFrame for display
        df_candidates = pd.DataFrame([
            {
                "Symbol": c["symbol"],
                "Score": c["score"],
                "Reasons": " | ".join(c.get("reasons", [])),
                "Close": c.get("key_levels", {}).get("close", "N/A"),
                "EMA50": c.get("key_levels", {}).get("ema50", "N/A"),
                "EMA200": c.get("key_levels", {}).get("ema200", "N/A"),
            }
            for c in candidates
        ])

        st.dataframe(df_candidates, use_container_width=True, hide_index=True)

        # Show top candidates
        if len(candidates) > 0:
            top_candidate = candidates[0]
            st.success(f"🏆 Top Candidate: **{top_candidate['symbol']}** (Score: {top_candidate['score']}/100)")
    else:
        st.info("No CSP candidates found. Run the wheel engine to generate candidates.")

    st.divider()

    # Alerts Section
    st.header("🔔 Recent Alerts")
    alerts = get_alerts(limit=20)

    if alerts:
        df_alerts = pd.DataFrame(alerts)
        df_alerts.columns = ["Message", "Level", "Timestamp"]
        st.dataframe(df_alerts, use_container_width=True, hide_index=True)
    else:
        st.info("No alerts found in database.")


if __name__ == "__main__":
    main()
