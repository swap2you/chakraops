# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Premium ChakraOps Dashboard — Option Alpha-style trading platform UI.

A modern, professional trading dashboard with:
- Clean sidebar navigation with dark/light mode
- Hero section with decision status and key metrics
- Charts for exclusion analysis and candidate distribution
- Detailed tables for candidates, signals, and exclusions
- Modular design, separate from business logic
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# Import theme utilities
from app.ui.ui_theme import (
    COLORS,
    PALETTE_DARK,
    PALETTE_LIGHT,
    SPACING,
    TYPO,
    badge,
    get_theme_palette,
    humanize_label,
    icon_svg,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DECISION_LATEST = Path("out/decision_latest.json")
SAMPLE_DECISION = Path("out/sample_decision.json")

NAV_ITEMS = [
    ("Dashboard", "dashboard", "📊"),
    ("Strategies", "strategies", "🎯"),
    ("Analytics", "analytics", "📈"),
    ("History", "history", "📜"),
    ("Settings", "settings", "⚙️"),
]


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------


def load_decision_data() -> Tuple[Dict[str, Any], bool]:
    """Load decision data from latest or sample file.
    
    Returns:
        Tuple of (data dict, is_sample_data boolean)
    """
    # Try decision_latest.json first
    if DECISION_LATEST.exists():
        try:
            with open(DECISION_LATEST, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, False
        except (json.JSONDecodeError, IOError):
            pass
    
    # Fall back to sample data
    if SAMPLE_DECISION.exists():
        try:
            with open(SAMPLE_DECISION, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, True
        except (json.JSONDecodeError, IOError):
            pass
    
    # Return empty structure if nothing found
    return {
        "decision_snapshot": {
            "stats": {},
            "candidates": [],
            "selected_signals": [],
            "exclusions": [],
            "symbols_with_options": [],
            "symbols_without_options": {},
            "data_source": "unavailable",
        },
        "execution_gate": {"allowed": False, "reasons": ["No data available"]},
        "execution_plan": {"orders": []},
        "metadata": {},
    }, True


def parse_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse decision snapshot into component parts."""
    snapshot = data.get("decision_snapshot", {})
    return {
        "stats": snapshot.get("stats", {}),
        "candidates": snapshot.get("candidates", []),
        "scored_candidates": snapshot.get("scored_candidates", []),
        "selected_signals": snapshot.get("selected_signals", []),
        "exclusions": snapshot.get("exclusions", []),
        "exclusion_summary": snapshot.get("exclusion_summary", {}),
        "symbols_with_options": snapshot.get("symbols_with_options", []),
        "symbols_without_options": snapshot.get("symbols_without_options", {}),
        "data_source": snapshot.get("data_source", "unknown"),
        "as_of": snapshot.get("as_of", ""),
        "pipeline_timestamp": snapshot.get("pipeline_timestamp", ""),
    }


# ---------------------------------------------------------------------------
# Theme CSS Injection
# ---------------------------------------------------------------------------


def inject_premium_css(dark: bool = False) -> None:
    """Inject premium dashboard CSS with modern styling."""
    p = get_theme_palette(dark)
    
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    :root {{
        --bg-primary: {p['bg']};
        --bg-surface: {p['surface']};
        --border-color: {p['border']};
        --text-primary: {p['text_primary']};
        --text-secondary: {p['text_secondary']};
        --accent: {p['accent']};
        --success: {p['success']};
        --danger: {p['danger']};
        --warning: {p['warning']};
    }}
    
    * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    
    .stApp {{ background: var(--bg-primary); }}
    .main .block-container {{ max-width: 1400px; padding: 1rem 2rem; }}
    
    /* Hide Streamlit branding */
    #MainMenu, footer, header {{ visibility: hidden; }}
    
    /* Premium card styling */
    .premium-card {{
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    
    .premium-card-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 1rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid var(--border-color);
    }}
    
    .premium-card-title {{
        font-size: 1rem;
        font-weight: 600;
        color: var(--text-primary);
        margin: 0;
    }}
    
    /* Hero section */
    .hero-section {{
        background: linear-gradient(135deg, var(--bg-surface) 0%, {'#1a1f2e' if dark else '#f8fafc'} 100%);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }}
    
    .hero-status {{
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1rem;
    }}
    
    .status-badge {{
        display: inline-flex;
        align-items: center;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.875rem;
    }}
    
    .status-allowed {{ background: #dcfce7; color: #166534; }}
    .status-blocked {{ background: #fee2e2; color: #991b1b; }}
    .status-live {{ background: #dbeafe; color: #1e40af; }}
    .status-snapshot {{ background: #fef3c7; color: #92400e; }}
    .status-sample {{ background: #e5e7eb; color: #374151; }}
    
    /* Metrics row */
    .metrics-row {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 1rem;
        margin-top: 1rem;
    }}
    
    .metric-tile {{
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }}
    
    .metric-value {{
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-primary);
    }}
    
    .metric-label {{
        font-size: 0.75rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.25rem;
    }}
    
    .metric-warning {{ border-left: 3px solid var(--warning); }}
    .metric-success {{ border-left: 3px solid var(--success); }}
    .metric-danger {{ border-left: 3px solid var(--danger); }}
    
    /* Tables */
    .premium-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.875rem;
    }}
    
    .premium-table th {{
        background: {'#1f2937' if dark else '#f9fafb'};
        padding: 0.75rem;
        text-align: left;
        font-weight: 600;
        color: var(--text-secondary);
        border-bottom: 2px solid var(--border-color);
        position: sticky;
        top: 0;
    }}
    
    .premium-table td {{
        padding: 0.75rem;
        border-bottom: 1px solid var(--border-color);
        color: var(--text-primary);
    }}
    
    .premium-table tr:hover {{
        background: {'#374151' if dark else '#f3f4f6'};
    }}
    
    .premium-table tr.selected {{
        background: {'#1e3a5f' if dark else '#dbeafe'};
    }}
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {{
        background: {'#0f172a' if dark else '#1e293b'};
    }}
    
    [data-testid="stSidebar"] .stMarkdown {{
        color: #e2e8f0;
    }}
    
    .sidebar-nav-item {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        color: #94a3b8;
        text-decoration: none;
        margin-bottom: 0.25rem;
        cursor: pointer;
        transition: all 0.15s ease;
    }}
    
    .sidebar-nav-item:hover {{
        background: rgba(255,255,255,0.1);
        color: #f1f5f9;
    }}
    
    .sidebar-nav-item.active {{
        background: {'#3b82f6' if dark else '#2563eb'};
        color: white;
    }}
    
    /* Badges */
    .badge {{
        display: inline-flex;
        align-items: center;
        padding: 0.25rem 0.625rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 500;
    }}
    
    .badge-success {{ background: #dcfce7; color: #166534; }}
    .badge-warning {{ background: #fef3c7; color: #92400e; }}
    .badge-danger {{ background: #fee2e2; color: #991b1b; }}
    .badge-info {{ background: #dbeafe; color: #1e40af; }}
    .badge-neutral {{ background: #e5e7eb; color: #374151; }}
    
    /* Charts container */
    .chart-container {{
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1rem;
    }}
    
    /* Expander styling */
    .streamlit-expanderHeader {{
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
    }}
    
    /* DataFrames */
    .stDataFrame {{
        border-radius: 8px;
        overflow: hidden;
    }}
    
    div[data-testid="stDataFrameResizable"] {{
        border: 1px solid var(--border-color);
        border-radius: 8px;
    }}
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar Components
# ---------------------------------------------------------------------------


def render_sidebar(dark_mode: bool, current_page: str) -> Tuple[str, bool]:
    """Render the sidebar with navigation and controls.
    
    Returns:
        Tuple of (selected_page, dark_mode)
    """
    with st.sidebar:
        # Logo/Brand
        st.markdown("""
        <div style="padding: 1rem 0.5rem 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 1rem;">
            <h1 style="color: white; font-size: 1.5rem; font-weight: 700; margin: 0;">
                ⚡ ChakraOps
            </h1>
            <p style="color: #94a3b8; font-size: 0.75rem; margin: 0.25rem 0 0;">
                Options Trading Platform
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Navigation
        st.markdown('<p style="color: #64748b; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.5rem; padding-left: 0.5rem;">Navigation</p>', unsafe_allow_html=True)
        
        selected_page = current_page
        for label, page_id, icon in NAV_ITEMS:
            is_active = page_id == current_page
            active_class = "active" if is_active else ""
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{page_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                selected_page = page_id
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Controls section
        st.markdown('<p style="color: #64748b; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.5rem; padding-left: 0.5rem;">Controls</p>', unsafe_allow_html=True)
        
        # Dark mode toggle
        new_dark_mode = st.toggle("🌙 Dark Mode", value=dark_mode, key="dark_mode_toggle")
        
        # Refresh button
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
        
        # Snapshot info
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<p style="color: #64748b; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.5rem; padding-left: 0.5rem;">Data Source</p>', unsafe_allow_html=True)
        
        snapshot_files = sorted(Path("out").glob("decision_*.json"), reverse=True)[:5]
        file_options = [f.name for f in snapshot_files if f.name != "decision_latest.json"]
        if file_options:
            st.selectbox("Snapshot", file_options, key="snapshot_selector", label_visibility="collapsed")
    
    return selected_page, new_dark_mode


# ---------------------------------------------------------------------------
# Hero Section
# ---------------------------------------------------------------------------


def render_hero(
    data: Dict[str, Any],
    parsed: Dict[str, Any],
    is_sample: bool,
    dark: bool,
) -> None:
    """Render the hero section with status and metrics."""
    gate = data.get("execution_gate", {})
    gate_allowed = gate.get("allowed", False)
    stats = parsed["stats"]
    data_source = parsed["data_source"]
    as_of = parsed.get("as_of", "")
    symbols_without = parsed.get("symbols_without_options", {})
    
    # Format timestamp
    try:
        ts = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        formatted_time = ts.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        formatted_time = as_of or "Unknown"
    
    # Status badges
    gate_status = "ALLOWED" if gate_allowed else "BLOCKED"
    gate_class = "status-allowed" if gate_allowed else "status-blocked"
    
    source_class = "status-sample" if is_sample else ("status-live" if data_source == "live" else "status-snapshot")
    source_label = "Sample Data" if is_sample else ("Live Data" if data_source == "live" else "Snapshot Data")
    
    st.markdown(f"""
    <div class="hero-section">
        <div class="hero-status">
            <span class="status-badge {gate_class}">{gate_status}</span>
            <span class="status-badge {source_class}">{source_label}</span>
            <span style="color: var(--text-secondary); font-size: 0.875rem;">
                Last updated: {formatted_time}
            </span>
        </div>
        {'<p style="color: var(--text-secondary); font-size: 0.875rem; margin: 0;">⚠️ Using sample data — Market may be closed or no live data available</p>' if is_sample else ''}
    </div>
    """, unsafe_allow_html=True)
    
    # Metrics row
    cols = st.columns(6)
    
    metrics = [
        ("Total Symbols", stats.get("total_symbols", 0), None),
        ("Evaluated", stats.get("symbols_evaluated", 0), None),
        ("Candidates", stats.get("total_candidates", 0), "success" if stats.get("total_candidates", 0) > 0 else None),
        ("Selected", len(parsed.get("selected_signals", []) or []), "success" if len(parsed.get("selected_signals", []) or []) > 0 else None),
        ("Missing Chains", len(symbols_without), "warning" if len(symbols_without) > 0 else None),
        ("Exclusions", stats.get("total_exclusions", 0), "danger" if stats.get("total_exclusions", 0) > 10 else None),
    ]
    
    for col, (label, value, tone) in zip(cols, metrics):
        with col:
            tone_class = f"metric-{tone}" if tone else ""
            st.markdown(f"""
            <div class="metric-tile {tone_class}">
                <div class="metric-value">{value}</div>
                <div class="metric-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Charts Section
# ---------------------------------------------------------------------------


def render_charts(parsed: Dict[str, Any], dark: bool) -> None:
    """Render charts section with exclusion breakdown and distribution."""
    import pandas as pd
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="premium-card"><div class="premium-card-header"><h3 class="premium-card-title">Exclusion Breakdown</h3></div>', unsafe_allow_html=True)
        
        exclusion_summary = parsed.get("exclusion_summary", {})
        rule_counts = exclusion_summary.get("rule_counts", {})
        
        if rule_counts:
            df = pd.DataFrame([
                {"Rule": humanize_label(rule), "Count": count}
                for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1])
            ])
            st.bar_chart(df.set_index("Rule"), use_container_width=True, height=250)
        else:
            st.info("No exclusions recorded")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="premium-card"><div class="premium-card-header"><h3 class="premium-card-title">Candidate Distribution</h3></div>', unsafe_allow_html=True)
        
        candidates = parsed.get("candidates", [])
        if candidates:
            # Count by signal type
            type_counts = Counter(c.get("signal_type", "Unknown") for c in candidates)
            df = pd.DataFrame([
                {"Strategy": stype, "Count": count}
                for stype, count in type_counts.items()
            ])
            st.bar_chart(df.set_index("Strategy"), use_container_width=True, height=250, color=["#3b82f6"])
        else:
            st.info("No candidates found")
        
        st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tables Section
# ---------------------------------------------------------------------------


def render_candidates_table(parsed: Dict[str, Any], dark: bool) -> None:
    """Render the candidates table."""
    import pandas as pd
    
    st.markdown('<div class="premium-card"><div class="premium-card-header"><h3 class="premium-card-title">Top Candidates</h3></div>', unsafe_allow_html=True)
    
    scored = parsed.get("scored_candidates", [])
    selected_symbols = {
        s.get("scored", {}).get("candidate", {}).get("symbol")
        for s in (parsed.get("selected_signals", []) or [])
    }
    
    if scored:
        rows = []
        for sc in scored[:20]:  # Limit to top 20
            candidate = sc.get("candidate", {})
            score = sc.get("score", {})
            symbol = candidate.get("symbol", "")
            
            rows.append({
                "Symbol": symbol,
                "Type": candidate.get("signal_type", ""),
                "Strike": f"${candidate.get('strike', 0):.2f}",
                "Expiration": candidate.get("expiry", ""),
                "Premium": f"${candidate.get('mid', 0):.2f}",
                "Delta": f"{candidate.get('delta', 0):.2f}" if candidate.get("delta") else "—",
                "IV": f"{candidate.get('iv', 0)*100:.1f}%" if candidate.get("iv") else "—",
                "Score": f"{score.get('total', 0):.2f}",
                "Selected": "✅" if symbol in selected_symbols else "",
            })
        
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Symbol": st.column_config.TextColumn("Symbol", width="small"),
                "Type": st.column_config.TextColumn("Type", width="small"),
                "Strike": st.column_config.TextColumn("Strike", width="small"),
                "Expiration": st.column_config.TextColumn("Expiration", width="medium"),
                "Premium": st.column_config.TextColumn("Premium", width="small"),
                "Delta": st.column_config.TextColumn("Delta", width="small"),
                "IV": st.column_config.TextColumn("IV", width="small"),
                "Score": st.column_config.TextColumn("Score", width="small"),
                "Selected": st.column_config.TextColumn("", width="small"),
            }
        )
    else:
        # Fall back to raw candidates
        candidates = parsed.get("candidates", [])
        if candidates:
            rows = []
            for c in candidates[:20]:
                rows.append({
                    "Symbol": c.get("symbol", ""),
                    "Type": c.get("signal_type", ""),
                    "Strike": f"${c.get('strike', 0):.2f}",
                    "Expiration": c.get("expiry", ""),
                    "Premium": f"${c.get('mid', 0):.2f}",
                    "Delta": f"{c.get('delta', 0):.2f}" if c.get("delta") else "—",
                })
            
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No candidates to display")
    
    st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Detail Panels
# ---------------------------------------------------------------------------


def render_detail_panels(data: Dict[str, Any], parsed: Dict[str, Any], dark: bool) -> None:
    """Render expandable detail panels."""
    import pandas as pd
    
    # Selected Signals Panel
    with st.expander("📌 Selected Signals", expanded=False):
        selected = parsed.get("selected_signals", []) or []
        if selected:
            for i, signal in enumerate(selected):
                scored = signal.get("scored", {})
                candidate = scored.get("candidate", {})
                score = scored.get("score", {})
                
                st.markdown(f"""
                <div class="premium-card" style="margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong style="font-size: 1rem;">{candidate.get('symbol', 'N/A')}</strong>
                            <span class="badge badge-info" style="margin-left: 0.5rem;">{candidate.get('signal_type', 'N/A')}</span>
                        </div>
                        <div style="text-align: right;">
                            <span style="font-weight: 600;">Score: {score.get('total', 0):.2f}</span>
                        </div>
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.875rem; color: var(--text-secondary);">
                        Strike: ${candidate.get('strike', 0):.2f} | 
                        Expiration: {candidate.get('expiry', 'N/A')} | 
                        Premium: ${candidate.get('mid', 0):.2f} |
                        Delta: {candidate.get('delta', 'N/A')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Copy button
                col1, col2 = st.columns([4, 1])
                with col2:
                    signal_str = json.dumps(candidate, indent=2)
                    st.code(signal_str, language="json")
        else:
            st.info("No signals selected")
    
    # Exclusions Panel
    with st.expander("🚫 Exclusions", expanded=False):
        exclusion_summary = parsed.get("exclusion_summary", {})
        symbols_by_rule = exclusion_summary.get("symbols_by_rule", {})
        
        if symbols_by_rule:
            for rule, symbols in symbols_by_rule.items():
                st.markdown(f"**{humanize_label(rule)}** ({len(symbols)} symbols)")
                st.markdown(f"<span style='color: var(--text-secondary); font-size: 0.875rem;'>{', '.join(symbols)}</span>", unsafe_allow_html=True)
                st.markdown("---")
        else:
            exclusions = parsed.get("exclusions", [])
            if exclusions:
                df = pd.DataFrame([
                    {
                        "Symbol": e.get("symbol", ""),
                        "Rule": humanize_label(e.get("rule", "")),
                        "Message": e.get("message", ""),
                    }
                    for e in exclusions[:50]
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No exclusions recorded")
    
    # Execution Plan Panel
    with st.expander("📋 Execution Plan", expanded=False):
        plan = data.get("execution_plan", {})
        orders = plan.get("orders", [])
        
        if orders:
            df = pd.DataFrame([
                {
                    "Symbol": o.get("symbol", ""),
                    "Action": o.get("action", ""),
                    "Qty": o.get("quantity", 1),
                    "Strike": f"${o.get('strike', 0):.2f}",
                    "Expiry": o.get("expiry", ""),
                    "Type": o.get("option_type", ""),
                    "Limit": f"${o.get('limit_price', 0):.2f}",
                }
                for o in orders
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            blocked_reason = plan.get("blocked_reason", "No orders generated")
            st.warning(f"Execution blocked: {humanize_label(blocked_reason)}")


# ---------------------------------------------------------------------------
# Page Renderers
# ---------------------------------------------------------------------------


def render_dashboard_page(data: Dict[str, Any], parsed: Dict[str, Any], is_sample: bool, dark: bool) -> None:
    """Render the main dashboard page."""
    render_hero(data, parsed, is_sample, dark)
    render_charts(parsed, dark)
    render_candidates_table(parsed, dark)
    render_detail_panels(data, parsed, dark)


def render_strategies_page(data: Dict[str, Any], parsed: Dict[str, Any], dark: bool) -> None:
    """Render the strategies page."""
    st.markdown("## Strategies")
    st.info("Strategy configuration and analysis coming soon.")
    
    # Show current config if available
    with st.expander("Current Configuration"):
        configs = data.get("decision_snapshot", {}).get("configs", {})
        if configs:
            st.json(configs)
        else:
            st.write("No configuration data available")


def render_analytics_page(data: Dict[str, Any], parsed: Dict[str, Any], dark: bool) -> None:
    """Render the analytics page."""
    st.markdown("## Analytics")
    st.info("Historical analytics and performance tracking coming soon.")


def render_history_page(data: Dict[str, Any], parsed: Dict[str, Any], dark: bool) -> None:
    """Render the history page."""
    st.markdown("## History")
    
    # List available snapshots
    snapshot_files = sorted(Path("out").glob("decision_*.json"), reverse=True)[:20]
    
    if snapshot_files:
        import pandas as pd
        
        rows = []
        for f in snapshot_files:
            if f.name == "decision_latest.json":
                continue
            try:
                stat = f.stat()
                rows.append({
                    "Filename": f.name,
                    "Size": f"{stat.st_size / 1024:.1f} KB",
                    "Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
            except OSError:
                continue
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No historical snapshots found")


def render_settings_page(dark: bool) -> None:
    """Render the settings page."""
    st.markdown("## Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Display")
        st.checkbox("Dark Mode", value=dark, key="settings_dark_mode", disabled=True)
        st.checkbox("Show Tooltips", value=True)
        st.checkbox("Auto-refresh", value=False)
    
    with col2:
        st.markdown("### Data")
        st.text_input("Output Directory", value="out/", disabled=True)
        st.number_input("Refresh Interval (sec)", value=30, min_value=10, max_value=300)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the premium dashboard."""
    st.set_page_config(
        page_title="ChakraOps Dashboard",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Initialize session state
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False
    if "current_page" not in st.session_state:
        st.session_state.current_page = "dashboard"
    
    # Load data
    data, is_sample = load_decision_data()
    parsed = parse_snapshot(data)
    
    # Render sidebar and get current state
    selected_page, dark_mode = render_sidebar(
        st.session_state.dark_mode,
        st.session_state.current_page,
    )
    
    # Update session state
    if selected_page != st.session_state.current_page:
        st.session_state.current_page = selected_page
        st.rerun()
    
    if dark_mode != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_mode
        st.rerun()
    
    # Inject CSS
    inject_premium_css(st.session_state.dark_mode)
    
    # Render current page
    if st.session_state.current_page == "dashboard":
        render_dashboard_page(data, parsed, is_sample, st.session_state.dark_mode)
    elif st.session_state.current_page == "strategies":
        render_strategies_page(data, parsed, st.session_state.dark_mode)
    elif st.session_state.current_page == "analytics":
        render_analytics_page(data, parsed, st.session_state.dark_mode)
    elif st.session_state.current_page == "history":
        render_history_page(data, parsed, st.session_state.dark_mode)
    elif st.session_state.current_page == "settings":
        render_settings_page(st.session_state.dark_mode)
    
    # Footer
    st.markdown("""
    <div style="margin-top: 2rem; padding: 1rem; border-top: 1px solid var(--border-color); text-align: center; color: var(--text-secondary); font-size: 0.75rem;">
        ChakraOps v1.0 — Options Trading Platform
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
