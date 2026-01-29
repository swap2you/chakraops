from __future__ import annotations

"""
ChakraOps – Live Decision Monitor.

Operator-facing, read-only UI that loads the latest DecisionSnapshot JSON artifact
from disk (out/decision_*.json) and renders snapshot metadata, selected signals,
gate, execution plan, dry-run, live market status, and operator recommendations.

STRICT: This UI does NOT trade, does NOT place orders, and does NOT call brokers.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from streamlit.components.v1 import html as st_html

from app.signals.decision_snapshot import _derive_operator_verdict
from app.ui.live_dashboard_utils import (
    compute_status_label,
    extract_exclusions,
    extract_snapshot_gate_plan_dryrun,
    list_decision_files,
    load_decision_artifact,
    status_color,
)
from app.ui.sandbox import SandboxParams, evaluate_sandbox
from app.ui.viability_analysis import analyze_signal_viability
from app.ui.operator_recommendations import (
    OperatorRecommendation,
    RecommendationSeverity,
    generate_operator_recommendations,
)
from app.market.live_market_adapter import LiveMarketData, fetch_live_market_data
from app.market.drift_detector import DriftReason, DriftStatus, detect_drift
from app.market.market_hours import is_market_open, get_polling_interval_seconds, get_mode_label
from app.notifications.slack_notifier import slack_webhook_available, send_decision_alert
from app.db.database import get_db_path
from app.core.persistence import get_enabled_symbols
from app.db.universe_import import import_universe_from_csv, get_effective_universe_csv_path
from app.ui.ui_theme import (
    badge,
    card_header,
    card_html,
    humanize_label,
    inject_global_css,
    metric_tile,
    icon_svg,
    COLORS,
    STATUS_TONE,
)

# Footer version/build (UI-only)
UI_VERSION = "1.0"


def _repo_root() -> Path:
    # chakraops/app/ui/live_decision_dashboard.py -> chakraops/
    return Path(__file__).resolve().parents[2]


def _default_out_dir() -> Path:
    return _repo_root() / "out"


def _fmt_money(v: Any) -> str:
    if isinstance(v, (int, float)):
        return f"${v:,.2f}"
    return str(v)


def _fmt_float(v: Any, digits: int = 4) -> str:
    if isinstance(v, (int, float)):
        return f"{v:.{digits}f}"
    return str(v)


def _inject_autorefresh(seconds: int) -> None:
    # Client-side refresh (no background jobs, no server polling).
    sec = max(5, int(seconds))
    st_html(
        f"""
        <script>
          setTimeout(function() {{
            window.location.reload();
          }}, {sec * 1000});
        </script>
        """,
        height=0,
    )


def _render_status_badge(status: str) -> None:
    color = status_color(status)
    st.markdown(
        f"""
        <div style="display:inline-block;padding:6px 10px;border-radius:999px;background:{color};color:white;
                    font-weight:700;font-size:12px;letter-spacing:0.5px;">
          {status}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_kv(label: str, value: Any) -> None:
    st.markdown(f"**{label}**  \n{value}")


def _candidate_key(candidate_dict: Dict[str, Any]) -> tuple:
    """Extract candidate key for comparison (Phase 7.5)."""
    if not isinstance(candidate_dict, dict):
        return None
    
    scored = candidate_dict.get("scored", {})
    if not isinstance(scored, dict):
        return None
    
    candidate = scored.get("candidate", {})
    if not isinstance(candidate, dict):
        return None
    
    return (
        candidate.get("symbol"),
        candidate.get("signal_type"),
        candidate.get("expiry"),
        candidate.get("strike"),
    )


def _selected_signals_table(selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in selected:
        scored = item.get("scored", {}) if isinstance(item, dict) else {}
        cand = scored.get("candidate", {}) if isinstance(scored, dict) else {}
        score = scored.get("score", {}) if isinstance(scored, dict) else {}
        rows.append(
            {
                "rank": scored.get("rank"),
                "symbol": cand.get("symbol"),
                "type": cand.get("signal_type"),
                "strike": cand.get("strike"),
                "expiry": cand.get("expiry"),
                "score_total": score.get("total"),
                "bid": cand.get("bid"),
                "ask": cand.get("ask"),
                "mid": cand.get("mid"),
            }
        )
    return rows


def _orders_table(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for o in orders:
        if not isinstance(o, dict):
            continue
        rows.append(
            {
                "symbol": o.get("symbol"),
                "action": o.get("action"),
                "right": o.get("option_right"),
                "strike": o.get("strike"),
                "expiry": o.get("expiry"),
                "qty": o.get("quantity"),
                "limit_price": o.get("limit_price"),
            }
        )
    return rows


def _render_footer() -> None:
    """Footer: ChakraOps © Internal, rendered from JSON, version/build."""
    st.markdown(
        f'<div class="chakra-theme-footer">ChakraOps © Internal · Rendered from immutable decision JSON · v{UI_VERSION}</div>',
        unsafe_allow_html=True,
    )


def _group_exclusions(exclusions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for e in exclusions:
        data = e.get("data", {}) if isinstance(e, dict) else {}
        symbol = data.get("symbol") if isinstance(data, dict) else None
        symbol_key = str(symbol) if symbol else "UNKNOWN"
        by_symbol.setdefault(symbol_key, []).append(e)
    # Deterministic order: symbol, then code/message
    for sym in list(by_symbol.keys()):
        by_symbol[sym].sort(key=lambda x: (str(x.get("code", "")), str(x.get("message", ""))))
    return dict(sorted(by_symbol.items(), key=lambda kv: kv[0]))


def _render_nav(current_page: str) -> None:
    """Top nav: logo, title, and nav buttons (set session state and rerun)."""
    logo_path = Path(__file__).resolve().parent / "static" / "chakra_logo.svg"
    logo_placeholder = st.empty()
    with logo_placeholder.container():
        col_logo, col_title, c1, c2, c3, c4, c5 = st.columns([0.5, 2, 0.8, 0.8, 1, 1.2, 0.8])
        with col_logo:
            if logo_path.exists():
                try:
                    st.image(str(logo_path), width=28)
                except Exception:
                    st.write("")
            else:
                st.write("")
        with col_title:
            st.markdown("**ChakraOps — Live Decision Monitor**")
        with c1:
            if st.button("Dashboard", key="nav_dashboard", type="primary" if current_page == "dashboard" else "secondary"):
                st.session_state.nav_page = "dashboard"
                st.rerun()
        with c2:
            if st.button("Strategy", key="nav_strategy", type="primary" if current_page == "strategy" else "secondary"):
                st.session_state.nav_page = "strategy"
                st.rerun()
        with c3:
            if st.button("Diagnostics", key="nav_diagnostics", type="primary" if current_page == "diagnostics" else "secondary"):
                st.session_state.nav_page = "diagnostics"
                st.rerun()
        with c4:
            if st.button("Configuration", key="nav_config", type="primary" if current_page == "configuration" else "secondary"):
                st.session_state.nav_page = "configuration"
                st.rerun()
        with c5:
            if st.button("About", key="nav_about", type="primary" if current_page == "about" else "secondary"):
                st.session_state.nav_page = "about"
                st.rerun()
    st.markdown("---")


def main() -> None:
    # Favicon: same Chakra-style logo (SVG supported in modern browsers)
    static_dir = Path(__file__).resolve().parent / "static"
    favicon_path = static_dir / "chakra_logo.svg"
    st.set_page_config(
        page_title="ChakraOps — Live Decision Monitor",
        layout="wide",
        initial_sidebar_state="expanded",
        page_icon=str(favicon_path) if favicon_path.exists() else None,
    )
    inject_global_css()

    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "dashboard"
    current_page = st.session_state.nav_page

    # Sidebar: minimal Controls only; output dir hidden in Advanced expander
    st.sidebar.header("Controls")
    with st.sidebar.expander("Advanced", expanded=False):
        st.sidebar.text_input("Output directory", str(_default_out_dir()), key="out_dir")
    out_dir = Path(st.session_state.get("out_dir", str(_default_out_dir())))
    out_dir_resolved = out_dir.resolve() if out_dir.exists() else out_dir
    decision_files = list_decision_files(out_dir)

    if not decision_files and current_page in ("dashboard", "diagnostics"):
        st.error(f"No decision files found in: {out_dir}")
        st.info("Expected files like: out/decision_<timestamp>.json (produced by scripts/run_and_save.py)")
        _render_footer()
        return

    file_labels = [f.path.name for f in decision_files]
    default_idx = 0
    selected_label = st.sidebar.selectbox("Snapshot", file_labels, index=default_idx, key="snapshot_select")
    selected_path = next((f.path for f in decision_files if f.path.name == selected_label), decision_files[0].path) if decision_files else None

    st.sidebar.markdown("**Refresh**")
    if st.sidebar.button("Refresh now", key="refresh_btn"):
        st.rerun()
    poll_default = get_polling_interval_seconds()
    auto_refresh = st.sidebar.checkbox("Auto-refresh", value=False, key="auto_refresh")
    refresh_seconds = int(st.sidebar.number_input("Interval (sec)", min_value=5, max_value=600, value=poll_default, key="refresh_sec"))
    if auto_refresh:
        _inject_autorefresh(refresh_seconds)

    st.sidebar.markdown("**Sandbox**")
    sandbox_enabled = st.sidebar.checkbox("Enable sandbox mode", value=False, key="sandbox_enabled")

    # --- Page routing: Strategy, Configuration, About (no artifact needed) ---
    _render_nav(current_page)
    if current_page == "strategy":
        st.subheader("Strategy")
        card_html(
            "Principles",
            "<ul style='margin:0;padding-left:1.2rem;font-size:0.875rem;'>"
            "<li>Curated universe from database (enabled symbols only)</li>"
            "<li>Options expirations and chains from Theta Terminal</li>"
            "<li>CSP (Cash-Secured Put) and CC (Covered Call) candidates scored and ranked</li>"
            "<li>Selection policy: max total, max per symbol, min score</li>"
            "<li>Execution gate blocks unless selected signals exist and snapshot is fresh</li>"
            "<li>No trades placed by this system; execution is manual only</li>"
            "</ul>",
            icon="shield",
        )
        card_html(
            "Pipeline (text)",
            "<p style='margin:0;font-size:0.875rem;'><strong>1.</strong> Load universe from DB → <strong>2.</strong> Fetch options (Theta) → "
            "<strong>3.</strong> Build CSP/CC candidates → <strong>4.</strong> Score & select → <strong>5.</strong> Evaluate gate → "
            "<strong>6.</strong> Build execution plan (read-only). No JSON dumps in UI.</p>",
        )
        _render_footer()
        return
    if current_page == "configuration":
        st.subheader("Configuration")
        try:
            db_path = get_db_path()
            enabled_symbols = get_enabled_symbols()
            st.markdown("**Database**")
            st.text(f"Path: {db_path.resolve()}")
            st.text(f"Enabled symbols: {len(enabled_symbols)}")
            csv_path_effective = get_effective_universe_csv_path()
            st.markdown("**Universe CSV**")
            st.text(f"Path: {os.environ.get('UNIVERSE_CSV_PATH', '(default)')} → {csv_path_effective}")
            if st.button("Import universe from CSV"):
                n = import_universe_from_csv(notes="core_watchlist", enabled=True)
                st.success(f"Imported {n} symbols")
                st.rerun()
        except Exception as e:
            st.warning(str(e))
        st.markdown("**Slack**")
        slack_ok, slack_msg = slack_webhook_available()
        st.caption(slack_msg)
        st.caption("Notifications are sent only on: gate state change, advisory severity change, or manual send.")
        if st.button("Send Slack now (manual)"):
            try:
                from app.signals.decision_snapshot import DecisionSnapshot
                from app.execution.execution_plan import ExecutionPlan
                dummy_snapshot = DecisionSnapshot(
                    as_of=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
                    universe_id_or_hash="config_test",
                    stats={"total_candidates": 0},
                    candidates=[],
                    scored_candidates=None,
                    selected_signals=None,
                    explanations=None,
                )
                from app.execution.execution_gate import ExecutionGateResult
                dummy_gate = ExecutionGateResult(allowed=False, reasons=[])
                dummy_plan = ExecutionPlan(allowed=False, blocked_reason="test", orders=[])
                sent = send_decision_alert(dummy_snapshot, dummy_gate, dummy_plan, heartbeat=True)
                st.success("Slack sent." if sent else "Slack skipped (filter).")
            except Exception as e:
                st.error(str(e))
        with st.expander("Debug paths"):
            st.text(f"Output dir: {out_dir_resolved}")
            st.text("Glob: decision_*.json")
            if selected_path:
                st.text(f"Selected file: {selected_path.resolve()}")
        _render_footer()
        return
    if current_page == "about":
        st.subheader("About / Help")
        card_html(
            "ChakraOps — Live Decision Monitor",
            "<p style='margin:0;font-size:0.875rem;'>Operator-facing, read-only UI. It loads the latest DecisionSnapshot JSON from disk and "
            "renders snapshot metadata, signals, gate, execution plan, and recommendations.</p>"
            "<p style='margin:8px 0 0 0;font-size:0.875rem;'><strong>STRICT:</strong> This UI does not trade, does not place orders, and does not call brokers. "
            "Rendered from immutable decision JSON written by <code>scripts.run_and_save</code>.</p>",
            icon="shield",
        )
        _render_footer()
        return

    # --- Dashboard / Diagnostics: need artifact ---
    if not selected_path:
        st.warning("No snapshot selected.")
        _render_footer()
        return

    # Load artifact
    try:
        artifact = load_decision_artifact(selected_path)
    except Exception as e:
        st.error(f"Failed to load JSON: {selected_path}")
        st.code(str(e))
        return

    snapshot, gate, plan, dry_run = extract_snapshot_gate_plan_dryrun(artifact)
    exclusions = extract_exclusions(artifact, snapshot)
    
    # Phase 7.5: Extract current config from snapshot for sandbox defaults
    current_config = {}
    explanations = snapshot.get("explanations") or []
    if isinstance(explanations, list) and len(explanations) > 0:
        first_expl = explanations[0]
        if isinstance(first_expl, dict):
            policy = first_expl.get("policy_snapshot", {})
            if isinstance(policy, dict):
                current_config = policy
    
    # Initialize sandbox defaults from current config (using session state to persist)
    if current_config:
        if "sandbox_min_score" not in st.session_state:
            st.session_state.sandbox_min_score = current_config.get("min_score", 0.0) or 0.0
        if "sandbox_max_total" not in st.session_state:
            st.session_state.sandbox_max_total = current_config.get("max_total", 10)
        if "sandbox_max_per_symbol" not in st.session_state:
            st.session_state.sandbox_max_per_symbol = current_config.get("max_per_symbol", 2)
        if "sandbox_max_per_signal_type" not in st.session_state:
            st.session_state.sandbox_max_per_signal_type = current_config.get("max_per_signal_type") or 0
    
    default_min_score = st.session_state.get("sandbox_min_score", 0.0)
    default_max_total = st.session_state.get("sandbox_max_total", 10)
    default_max_per_symbol = st.session_state.get("sandbox_max_per_symbol", 2)
    default_max_per_signal_type = st.session_state.get("sandbox_max_per_signal_type", 0)
    # Sandbox params: sliders live in Sandbox tab; use session state for recommendations when sandbox enabled
    sandbox_min_score = float(default_min_score)
    sandbox_max_total = int(default_max_total)
    sandbox_max_per_symbol = int(default_max_per_symbol)
    sandbox_max_per_signal_type = int(default_max_per_signal_type)
    sandbox_max_per_signal_type_val = None if sandbox_max_per_signal_type == 0 else sandbox_max_per_signal_type

    # --- Design system: status, stats, live data ---
    status = compute_status_label(gate, plan, dry_run)
    gate_allowed = bool(gate.get("allowed", False))
    gate_reasons = gate.get("reasons", []) if isinstance(gate.get("reasons", []), list) else []
    stats = snapshot.get("stats", {}) if isinstance(snapshot.get("stats", {}), dict) else {}
    symbols_with_options = snapshot.get("symbols_with_options") or []
    symbols_without_options = snapshot.get("symbols_without_options") or {}
    if not isinstance(symbols_with_options, list):
        symbols_with_options = []
    if not isinstance(symbols_without_options, dict):
        symbols_without_options = {}
    with_options_count = len(symbols_with_options)
    without_options_count = len(symbols_without_options)
    as_of = snapshot.get("as_of", "N/A")
    modified_ts = datetime.fromtimestamp(selected_path.stat().st_mtime)
    modified_str = modified_ts.strftime("%Y-%m-%d %H:%M")

    # Live data for hero and tiles
    mode_label: Optional[str] = None
    live_data = None
    drift_status = None
    market_open = False
    try:
        symbols_for_live: List[str] = []
        for sel in (snapshot.get("selected_signals") or []) + (snapshot.get("scored_candidates") or [])[:30]:
            if not isinstance(sel, dict):
                continue
            scored = sel.get("scored") or {}
            cand = (scored.get("candidate") or {}) if isinstance(scored, dict) else {}
            if isinstance(cand, dict) and cand.get("symbol"):
                symbols_for_live.append(str(cand["symbol"]))
        symbols_for_live = list(dict.fromkeys(symbols_for_live)) or ["SPY"]
        live_data = fetch_live_market_data(symbols_for_live, out_dir=out_dir)
        drift_status = detect_drift(snapshot, live_data)
        market_open = is_market_open()
        mode_label = get_mode_label(live_data.data_source, market_open)
    except Exception:
        pass
    live_str = (mode_label or "—") if live_data else "Unavailable"
    reason_line = "; ".join(gate_reasons[:2]) if gate_reasons else ("—" if gate_allowed else "No selected signals")

    # Compact dashboard header: LIVE / MARKET CLOSED + last updated (no long text)
    _live_label = "LIVE" if market_open else "MARKET CLOSED"
    _pulse_class = "chakra-theme-pulse" if market_open else ""
    _live_style = f'<span style="color:{COLORS["success"]};">' if market_open else f'<span style="color:{COLORS["text_muted"]};">'
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:1rem;margin-bottom:1rem;">'
        f'<span class="{_pulse_class}" style="width:8px;height:8px;border-radius:50%;background:{COLORS["success"] if market_open else COLORS["text_muted"]};"></span>'
        f'{_live_style}{_live_label}</span>'
        f'<span style="color:{COLORS["text_muted"]};font-size:0.875rem;">Last updated: {modified_str}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Hero row: full width — left: big status badge + one-line reason; right: tiles (Market, Provider, Snapshot Time)
    hero_tone = "allowed" if status == "ALLOWED" else ("warning" if status == "REVIEW" else "blocked")
    gate_badge_html = badge("BLOCKED" if not gate_allowed else "ALLOWED", "danger" if not gate_allowed else "success")
    c_left, c_right = st.columns([2, 1])
    with c_left:
        st.markdown(
            f'<div class="chakra-theme-card chakra-theme-hero hero-{hero_tone}">'
            f'<h4 style="margin:0 0 8px 0;">System Status</h4>'
            f'<div style="margin-bottom:4px;">{gate_badge_html}</div>'
            f'<p style="margin:0;font-size:0.875rem;color:{COLORS["text_muted"]};">{reason_line}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c_right:
        metric_tile("Market", live_str)
        metric_tile("Provider", "Theta Terminal")
        metric_tile("Snapshot time", as_of)

    # Second row: 3 cards — Snapshot Summary, Options Data Health, Operator Advisory
    col1, col2, col3 = st.columns(3)
    with col1:
        summary_body = (
            f'<p style="margin:0;font-size:0.875rem;">As of: {as_of}</p>'
            f'<p style="margin:4px 0 0 0;font-size:0.875rem;">Universe: {snapshot.get("universe_id_or_hash", "N/A")}</p>'
            f'<p style="margin:4px 0 0 0;font-size:0.875rem;">Symbols evaluated: {stats.get("symbols_evaluated", 0)} · Candidates: {stats.get("total_candidates", 0)}</p>'
            f'<p style="margin:4px 0 0 0;font-size:0.8rem;color:{COLORS["text_muted"]};">File: {selected_path.name}</p>'
        )
        card_html("Snapshot Summary", summary_body, icon="database")
        with st.expander("👁️ Info"):
            st.caption("Key metrics from the current decision artifact. Human-readable only.")

    with col2:
        options_pass = with_options_count > 0
        health_body = (
            f'<p style="margin:0;font-size:0.875rem;">Provider: Theta Terminal</p>'
            f'<p style="margin:4px 0 0 0;">With options: <strong>{with_options_count}</strong> · Without: <strong>{without_options_count}</strong></p>'
        )
        card_html("Options Data Health", health_body, icon="pulse", status_badge=("PASS" if options_pass else "FAIL"))
        if with_options_count == 0:
            st.caption("No symbols have valid options chains. Execution is blocked.")
        with st.expander("View details"):
            if symbols_without_options:
                reason_counts: Dict[str, int] = {}
                for r in symbols_without_options.values():
                    reason_counts[r] = reason_counts.get(r, 0) + 1
                for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                    st.caption(f"{reason}: {count} symbol(s)")
        with st.expander("👁️ Info"):
            st.caption("Whether the pipeline had valid options chains. FAIL when zero symbols have options.")

    with col3:
        try:
            sandbox_result_for_rec = None
            if sandbox_enabled:
                try:
                    sandbox_result_for_rec = evaluate_sandbox(snapshot, SandboxParams(
                        min_score=sandbox_min_score if sandbox_min_score > 0 else None,
                        max_total=sandbox_max_total,
                        max_per_symbol=sandbox_max_per_symbol,
                        max_per_signal_type=sandbox_max_per_signal_type_val,
                    ))
                except Exception:
                    pass
            recommendations = generate_operator_recommendations(snapshot, sandbox_result=sandbox_result_for_rec)
            top = [r for r in recommendations if r.severity in (RecommendationSeverity.HIGH, RecommendationSeverity.MEDIUM)][:1]
            if top:
                rec = top[0]
                sev = rec.severity.value
                adv_body = (
                    f'<p style="margin:0;font-size:0.875rem;"><strong>{sev}</strong> · {rec.title}</p>'
                    f'<p style="margin:4px 0 0 0;font-size:0.8rem;">Action: {rec.action}</p>'
                    f'<p style="margin:2px 0 0 0;font-size:0.75rem;color:{COLORS["text_muted"]};">{" · ".join(rec.evidence[:2])}</p>'
                )
                card_html("Operator Advisory", adv_body, icon="alert", status_badge=sev)
            else:
                card_html("Operator Advisory", '<p style="margin:0;font-size:0.875rem;">No recommendations. System operating normally.</p>', icon="alert")
        except Exception:
            card_html("Operator Advisory", '<p style="margin:0;font-size:0.875rem;">Recommendations unavailable.</p>', icon="alert")
        with st.expander("👁️ Info"):
            st.caption("Severity and recommended action from diagnostics. Advisory only.")

    # Tabs: Signals, Diagnostics, Why Not, Sandbox, Execution Plan
    default_tab = 1 if current_page == "diagnostics" else 0
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Signals", "Diagnostics", "Why Not", "Sandbox", "Execution Plan"])

    # Tab content: Signals, Diagnostics, Why Not, Sandbox, Execution Plan
    with tab1:
        # Signals: selected signals table
        selected_signals = snapshot.get("selected_signals") or []
        if not isinstance(selected_signals, list):
            selected_signals = []
        st.markdown("**Selected Signals (Ranked)**")
        if selected_signals:
            st.dataframe(_selected_signals_table(selected_signals), width="stretch")
        else:
            st.caption("No selected signals in this snapshot.")
        # WHY THIS (score components)
        explanations = snapshot.get("explanations") or []
        if isinstance(explanations, list) and explanations:
            st.markdown("---")
            st.markdown("**Why This (Score Components)**")
            for expl in explanations:
                if not isinstance(expl, dict):
                    continue
                symbol = expl.get("symbol", "N/A")
                signal_type = expl.get("signal_type", "N/A")
                rank = expl.get("rank", "N/A")
                total_score = expl.get("total_score", "N/A")
                comps = expl.get("score_components", []) if isinstance(expl.get("score_components", []), list) else []
                policy = expl.get("policy_snapshot", {}) if isinstance(expl.get("policy_snapshot", {}), dict) else {}
                with st.expander(f"{symbol} {signal_type} · rank {rank} · score {_fmt_float(total_score)}"):
                    _render_kv("Selection reason", expl.get("selection_reason", "N/A"))
                    if comps:
                        st.dataframe([{"Name": c.get("name"), "Value": c.get("value"), "Weight": c.get("weight")} for c in comps if isinstance(c, dict)], width="stretch")
                    if policy:
                        st.caption("Policy snapshot: see artifact for full details.")

    with tab2:
        # Diagnostics: Operator Action Recommendations + exclusion summary + coverage
        try:
            sandbox_result_for_recommendations = None
            if sandbox_enabled:
                try:
                    sandbox_params = SandboxParams(
                        min_score=sandbox_min_score if sandbox_min_score > 0 else None,
                        max_total=sandbox_max_total,
                        max_per_symbol=sandbox_max_per_symbol,
                        max_per_signal_type=sandbox_max_per_signal_type_val,
                    )
                    sandbox_result_for_recommendations = evaluate_sandbox(snapshot, sandbox_params)
                except Exception:
                    pass
            recommendations = generate_operator_recommendations(
                snapshot,
                sandbox_result=sandbox_result_for_recommendations,
            )
            if recommendations:
                high_recs = [r for r in recommendations if r.severity == RecommendationSeverity.HIGH]
                medium_recs = [r for r in recommendations if r.severity == RecommendationSeverity.MEDIUM]
                low_recs = [r for r in recommendations if r.severity == RecommendationSeverity.LOW]
                for rec in high_recs:
                    with st.expander(f"🔴 **HIGH:** {rec.title}", expanded=True):
                        st.markdown(f"**Action:** {rec.action}")
                        st.markdown("**Evidence:**")
                        for evidence_line in rec.evidence:
                            st.markdown(f"- {evidence_line}")
                        st.caption(f"Category: {rec.category}")
                for rec in medium_recs:
                    with st.expander(f"🟡 **MEDIUM:** {rec.title}", expanded=False):
                        st.markdown(f"**Action:** {rec.action}")
                        st.markdown("**Evidence:**")
                        for evidence_line in rec.evidence:
                            st.markdown(f"- {evidence_line}")
                        st.caption(f"Category: {rec.category}")
                for rec in low_recs:
                    with st.expander(f"🟢 **LOW:** {rec.title}", expanded=False):
                        st.markdown(f"**Action:** {rec.action}")
                        st.markdown("**Evidence:**")
                        for evidence_line in rec.evidence:
                            st.markdown(f"- {evidence_line}")
                        st.caption(f"Category: {rec.category}")
            else:
                st.info("No recommendations. System operating normally.")
        except Exception as e:
            st.error(f"Recommendation generation failed: {e}")

        # Phase 7.3: Diagnostics (Why the system is blocked)
        if not gate_allowed:
            exclusion_summary = snapshot.get("exclusion_summary")
            if isinstance(exclusion_summary, dict):
                st.subheader("Diagnostics (Why the system is blocked)")
                verdict = _derive_operator_verdict(exclusion_summary)
                st.info(f"**Operator Verdict:** {verdict}")
                rule_counts = exclusion_summary.get("rule_counts", {})
                symbols_by_rule = exclusion_summary.get("symbols_by_rule", {})
                if rule_counts:
                    diagnostics_rows = []
                    for rule, count in sorted(rule_counts.items(), key=lambda x: x[1], reverse=True):
                        stage = None
                        snapshot_exclusions = snapshot.get("exclusions") or []
                        for excl in snapshot_exclusions:
                            if isinstance(excl, dict) and excl.get("rule") == rule:
                                stage = excl.get("stage", "UNKNOWN")
                                break
                        symbols = symbols_by_rule.get(rule, [])
                        symbol_str = ", ".join(symbols[:5])
                        if len(symbols) > 5:
                            symbol_str += f" (+{len(symbols) - 5} more)"
                        diagnostics_rows.append({
                            "Rule": rule,
                            "Count": count,
                            "Stage": stage or "UNKNOWN",
                            "Symbols": symbol_str if symbol_str else "N/A",
                        })
                    st.dataframe(diagnostics_rows, width="stretch")
                else:
                    st.info("No exclusion rules found in diagnostics.")
            coverage_summary = snapshot.get("coverage_summary")
            near_misses = snapshot.get("near_misses")
            if isinstance(coverage_summary, dict) or (isinstance(near_misses, list) and len(near_misses) > 0):
                st.subheader("Coverage & Near-Miss Diagnostics")
                if isinstance(coverage_summary, dict):
                    coverage_by_symbol = coverage_summary.get("by_symbol", {})
                    if coverage_by_symbol:
                        st.markdown("**Coverage Funnel (per symbol)**")
                        funnel_rows = []
                        for symbol in sorted(coverage_by_symbol.keys()):
                            counts = coverage_by_symbol[symbol]
                            funnel_rows.append({
                                "Symbol": symbol,
                                "Normalization": counts.get("normalization", 0),
                                "Generation": counts.get("generation", 0),
                                "Scoring": counts.get("scoring", 0),
                                "Selection": counts.get("selection", 0),
                            })
                        st.dataframe(funnel_rows, width="stretch")
                if isinstance(near_misses, list) and len(near_misses) > 0:
                    st.markdown(f"**Near-Misses ({len(near_misses)} candidates that failed exactly one rule)**")
                    with st.expander("View near-misses"):
                        near_miss_rows = []
                        for nm in near_misses:
                            if isinstance(nm, dict):
                                near_miss_rows.append({
                                    "Symbol": nm.get("symbol", "N/A"),
                                    "Strategy": nm.get("strategy", "N/A"),
                                    "Failed Rule": nm.get("failed_rule", "N/A"),
                                    "Actual": nm.get("actual_value", "N/A"),
                                    "Required": nm.get("required_value", "N/A"),
                                    "Score": _fmt_float(nm.get("score")),
                                    "Strike": nm.get("strike", "N/A"),
                                    "Expiry": nm.get("expiry", "N/A"),
                                })
                        if near_miss_rows:
                            st.dataframe(near_miss_rows, width="stretch")
                elif isinstance(coverage_summary, dict):
                    st.info("No near-misses identified.")

        # Signal Viability (inside Diagnostics tab)
        st.markdown("---")
        st.markdown("**Signal Viability**")
        try:
            viability_list = analyze_signal_viability(snapshot)
            if viability_list:
                viable_count = sum(1 for v in viability_list if v.primary_blockage == "VIABLE")
                total_symbols = len(viability_list)
                if viable_count > 0:
                    st.success(f"**{viable_count} of {total_symbols} symbols** produced viable candidates.")
                else:
                    st.caption(f"0 of {total_symbols} symbols produced viable candidates.")
                viability_rows = []
                for v in viability_list:
                    blockage_display = v.primary_blockage.replace("_", " ").title()
                    if v.primary_blockage == "VIABLE":
                        blockage_display = "Viable"
                    viability_rows.append({
                        "Symbol": v.symbol,
                        "Expiries in DTE Window": v.expiries_in_dte_window,
                        "PUTs Scanned": v.puts_scanned,
                        "CALLs Scanned": v.calls_scanned,
                        "IV Available": "Yes" if v.iv_available else "No",
                        "Primary Blockage": blockage_display,
                    })
                st.dataframe(viability_rows, width="stretch")
            else:
                st.caption("No symbol viability data.")
        except Exception as e:
            st.error(f"Viability analysis failed: {e}")

    with tab3:
        # Why Not: exclusions grouped by rule (not by symbol list spam) + symbol search
        st.markdown("**Gate-level blocks**")
        if gate_reasons:
            for r in gate_reasons:
                st.caption(f"• {r}")
        else:
            st.caption("(none)")
        snapshot_exclusions = snapshot.get("exclusions") or []
        if isinstance(snapshot_exclusions, list) and len(snapshot_exclusions) > 0:
            # Group by rule (reason), not by symbol
            by_rule: Dict[str, List[Dict[str, Any]]] = {}
            for excl in snapshot_exclusions:
                if not isinstance(excl, dict):
                    continue
                rule = excl.get("rule") or excl.get("code") or "UNKNOWN"
                by_rule.setdefault(str(rule), []).append(excl)
            symbol_filter = st.text_input("Filter by symbol", key="why_not_symbol_filter", placeholder="e.g. AAPL")
            for rule, items in sorted(by_rule.items(), key=lambda x: -len(x[1])):
                symbols_in_rule = list({(e.get("data") or {}).get("symbol") or e.get("symbol") for e in items if isinstance(e, dict)})
                symbols_in_rule = [s for s in symbols_in_rule if s]
                if symbol_filter and symbol_filter.strip():
                    q = symbol_filter.strip().upper()
                    symbols_in_rule = [s for s in symbols_in_rule if q in str(s).upper()]
                    if not symbols_in_rule:
                        continue
                with st.expander(f"**{humanize_label(rule)}** ({len(items)} exclusions, {len(symbols_in_rule)} symbols)", expanded=False):
                    rows = []
                    for e in items:
                        if isinstance(e, dict):
                            data = e.get("data") or {}
                            sym = data.get("symbol") if isinstance(data, dict) else e.get("symbol")
                            rows.append({"Rule": rule, "Symbol": sym, "Stage": e.get("stage"), "Message": e.get("message")})
                    if rows:
                        st.dataframe(rows, width="stretch")
        elif exclusions:
            grouped = _group_exclusions(exclusions)
            symbol_filter_legacy = st.text_input("Filter by symbol", key="why_not_symbol_filter_legacy", placeholder="e.g. AAPL")
            for symbol, items in sorted(grouped.items()):
                if symbol_filter_legacy and symbol_filter_legacy.strip() and symbol_filter_legacy.strip().upper() not in str(symbol).upper():
                    continue
                with st.expander(f"{symbol} ({len(items)} exclusions)", expanded=False):
                    st.dataframe([{"code": e.get("code"), "message": e.get("message")} for e in items], width="stretch")
        else:
            st.caption("No exclusions in this artifact.")

    with tab4:
        # Sandbox
        if sandbox_enabled:
            st.subheader("Operator Calibration Sandbox")
            st.warning(
                "⚠️ **Sandbox Mode – Hypothetical Analysis Only**\n\n"
                "This sandbox allows you to test different selection parameters without modifying:\n"
                "- Live DecisionSnapshot (source of truth)\n"
                "- Execution gate evaluation\n"
                "- Execution plans\n"
                "- Slack alerts\n"
                "- Any persisted artifacts\n\n"
                "All sandbox evaluation runs entirely in memory. No changes are saved."
            )
            try:
                sandbox_params = SandboxParams(
                    min_score=sandbox_min_score if sandbox_min_score > 0 else None,
                    max_total=sandbox_max_total,
                    max_per_symbol=sandbox_max_per_symbol,
                    max_per_signal_type=sandbox_max_per_signal_type_val,
                )
                sandbox_result = evaluate_sandbox(snapshot, sandbox_params)
                sandbox_symbols = []
                for sel in sandbox_result.selected_signals or []:
                    if not isinstance(sel, dict):
                        continue
                    scored = sel.get("scored") or {}
                    cand = scored.get("candidate") if isinstance(scored, dict) else {}
                    if isinstance(cand, dict) and cand.get("symbol"):
                        sandbox_symbols.append(str(cand["symbol"]))
                sandbox_symbols = sorted(set(sandbox_symbols))
                st.markdown("**Hypothetical eligible symbols under current sandbox settings**")
                st.caption("Read-only. Does not affect real gating or execution.")
                if sandbox_symbols:
                    st.text(", ".join(sandbox_symbols))
                else:
                    st.caption("(none – no signals would be selected with these parameters)")
                live_count = len(selected_signals)
                sandbox_count = sandbox_result.selected_count
                st.markdown("**Live vs Sandbox Comparison**")
                comp_cols = st.columns(2)
                with comp_cols[0]:
                    st.metric("Live Selected", live_count)
                with comp_cols[1]:
                    st.metric("Sandbox Selected", sandbox_count)
                if sandbox_result.newly_admitted:
                    st.markdown(f"**Newly Admitted Candidates ({len(sandbox_result.newly_admitted)})**")
                    newly_admitted_rows = []
                    for nm in sandbox_result.newly_admitted:
                        if isinstance(nm, dict):
                            scored = nm.get("scored", {}) or {}
                            candidate = scored.get("candidate", {}) or {}
                            score = scored.get("score", {}) or {}
                            key = _candidate_key(nm)
                            reason = sandbox_result.rejected_reasons.get(str(key), "UNKNOWN")
                            newly_admitted_rows.append({
                                "Symbol": candidate.get("symbol", "N/A"),
                                "Strategy": candidate.get("signal_type", "N/A"),
                                "Strike": candidate.get("strike", "N/A"),
                                "Expiry": candidate.get("expiry", "N/A"),
                                "Score": _fmt_float(score.get("total")),
                                "Why Rejected Live": reason,
                            })
                    if newly_admitted_rows:
                        st.dataframe(newly_admitted_rows, width="stretch")
                else:
                    st.caption("No newly admitted candidates.")
                if sandbox_count != live_count or sandbox_result.newly_admitted:
                    with st.expander("View all sandbox selected signals"):
                        if sandbox_result.selected_signals:
                            st.dataframe(_selected_signals_table(sandbox_result.selected_signals), width="stretch")
                        else:
                            st.caption("No signals selected in sandbox.")
            except Exception as e:
                st.error(f"Sandbox evaluation failed: {e}")
        else:
            st.caption("Enable sandbox mode in the sidebar to run hypothetical selection.")

    with tab5:
        # Execution Plan and Dry-run
        st.subheader("Execution Plan")
        plan_allowed = bool(plan.get("allowed", False))
        plan_blocked_reason = plan.get("blocked_reason")
        plan_orders = plan.get("orders", []) if isinstance(plan.get("orders", []), list) else []
        if plan_allowed:
            if plan_orders:
                st.success(f"Plan status: ALLOWED ({len(plan_orders)} orders)")
            else:
                st.warning("Plan status: ALLOWED but zero orders (REVIEW)")
        else:
            st.error("Plan status: BLOCKED")
        if plan_blocked_reason:
            _render_kv("Blocked reason", plan_blocked_reason)
        if plan_orders:
            st.dataframe(_orders_table(plan_orders), width="stretch")
        st.subheader("Dry-Run Result")
        dry_allowed = bool(dry_run.get("allowed", False))
        dry_blocked_reason = dry_run.get("blocked_reason")
        dry_executed_at = dry_run.get("executed_at")
        dry_orders = dry_run.get("orders", []) if isinstance(dry_run.get("orders", []), list) else []
        if dry_allowed:
            st.success(f"Dry-run status: ALLOWED ({len(dry_orders)} orders)")
        else:
            st.error("Dry-run status: BLOCKED")
        if dry_executed_at:
            _render_kv("Executed at", dry_executed_at)
        if dry_blocked_reason:
            _render_kv("Blocked reason", dry_blocked_reason)
        if dry_orders:
            st.dataframe(_orders_table(dry_orders), width="stretch")

    st.markdown("---")
    _render_footer()


if __name__ == "__main__":
    main()

