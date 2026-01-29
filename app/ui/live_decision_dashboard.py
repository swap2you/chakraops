from __future__ import annotations

"""
Live Decision Dashboard (Phase 7 Step 1)

Operator-facing, read-only UI that loads the latest DecisionSnapshot JSON artifact
from disk (out/decision_*.json) and renders:
- Snapshot metadata (as_of, universe)
- Selected signals (ranked)
- WHY THIS (score components)
- WHY NOT (exclusions + gate reasons)
- Execution plan
- Dry-run result

STRICT: This UI does NOT trade, does NOT place orders, and does NOT call brokers.
It only reads JSON artifacts produced by the pipeline.
"""

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


def main() -> None:
    st.set_page_config(page_title="ChakraOps – Live Decision Monitor", layout="wide")

    st.title("ChakraOps – Live Decision Monitor")
    st.caption(
        "Read-only decision intelligence. No broker integration. Manual execution only."
    )

    # Sidebar controls
    st.sidebar.header("Data Source")
    out_dir = Path(st.sidebar.text_input("Output directory", str(_default_out_dir())))
    decision_files = list_decision_files(out_dir)

    if not decision_files:
        st.error(f"No decision files found in: {out_dir}")
        st.info("Expected files like: out/decision_<timestamp>.json (produced by scripts/run_and_save.py)")
        return

    file_labels = [f.path.name for f in decision_files]
    default_idx = 0
    selected_label = st.sidebar.selectbox("Decision file", file_labels, index=default_idx)
    selected_path = next((f.path for f in decision_files if f.path.name == selected_label), decision_files[0].path)

    st.sidebar.header("Refresh")
    if st.sidebar.button("Refresh now"):
        st.rerun()

    auto_refresh = st.sidebar.checkbox("Auto-refresh (client-side)", value=False)
    refresh_seconds = int(st.sidebar.number_input("Refresh interval (seconds)", min_value=5, max_value=300, value=20))
    if auto_refresh:
        _inject_autorefresh(refresh_seconds)

    # Phase 7.5: Sandbox controls header (values set after snapshot load)
    st.sidebar.header("Operator Calibration Sandbox")
    sandbox_enabled = st.sidebar.checkbox("Enable sandbox mode", value=False)

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
    
    # Set defaults if not in session state
    default_min_score = st.session_state.get("sandbox_min_score", 0.0)
    default_max_total = st.session_state.get("sandbox_max_total", 10)
    default_max_per_symbol = st.session_state.get("sandbox_max_per_symbol", 2)
    default_max_per_signal_type = st.session_state.get("sandbox_max_per_signal_type", 0)
    
    # Sandbox controls (after snapshot load)
    sandbox_min_score = st.sidebar.slider(
        "min_score",
        min_value=0.0,
        max_value=1.0,
        value=float(default_min_score),
        step=0.01,
        disabled=not sandbox_enabled,
        key="sandbox_min_score",
    )
    sandbox_max_total = st.sidebar.number_input(
        "max_total",
        min_value=1,
        max_value=50,
        value=int(default_max_total),
        step=1,
        disabled=not sandbox_enabled,
        key="sandbox_max_total",
    )
    sandbox_max_per_symbol = st.sidebar.number_input(
        "max_per_symbol",
        min_value=1,
        max_value=10,
        value=int(default_max_per_symbol),
        step=1,
        disabled=not sandbox_enabled,
        key="sandbox_max_per_symbol",
    )
    sandbox_max_per_signal_type = st.sidebar.number_input(
        "max_per_signal_type (0 = disabled)",
        min_value=0,
        max_value=20,
        value=int(default_max_per_signal_type),
        step=1,
        disabled=not sandbox_enabled,
        key="sandbox_max_per_signal_type",
    )
    sandbox_max_per_signal_type_val = None if sandbox_max_per_signal_type == 0 else sandbox_max_per_signal_type

    # Top status
    status = compute_status_label(gate, plan, dry_run)
    cols = st.columns([1, 3])
    with cols[0]:
        _render_status_badge(status)
    with cols[1]:
        st.markdown(
            "**Interpretation:** Green = allowed, Yellow = review, Red = blocked. This UI never executes trades."
        )

    # Live Market Status (Phase 8.2) – advisory only
    st.subheader("Live Market Status")
    try:
        symbols_for_live: List[str] = []
        for sel in (snapshot.get("selected_signals") or []) + (snapshot.get("scored_candidates") or [])[:30]:
            if not isinstance(sel, dict):
                continue
            scored = sel.get("scored") or {}
            if not isinstance(scored, dict):
                continue
            cand = scored.get("candidate") or {}
            if isinstance(cand, dict) and cand.get("symbol"):
                symbols_for_live.append(str(cand["symbol"]))
        symbols_for_live = list(dict.fromkeys(symbols_for_live))
        if not symbols_for_live:
            symbols_for_live = ["SPY"]
        live_data = fetch_live_market_data(symbols_for_live)
        drift_status = detect_drift(snapshot, live_data)
    except Exception as e:
        live_data = None
        drift_status = None
        st.warning(f"Live market data unavailable: {e}")
    if live_data is not None:
        st.markdown(f"**Data source:** {live_data.data_source}")
        st.markdown(f"**Last update (UTC):** {live_data.last_update_utc}")
        if live_data.errors:
            with st.expander("Live data warnings", expanded=False):
                for err in live_data.errors[:10]:
                    st.caption(err)
        if drift_status is not None and drift_status.has_drift:
            st.warning("Drift detected (snapshot vs live – advisory only)")
            for item in drift_status.items:
                st.caption(f"[{item.reason.value}] {item.symbol}: {item.message}")
        else:
            st.caption("No drift detected. Snapshot and live data aligned (or live unavailable).")

    # Snapshot metadata
    st.subheader("Snapshot metadata")
    meta_cols = st.columns(4)
    as_of = snapshot.get("as_of", "N/A")
    universe = snapshot.get("universe_id_or_hash", "N/A")
    stats = snapshot.get("stats", {}) if isinstance(snapshot.get("stats", {}), dict) else {}
    modified = datetime.fromtimestamp(selected_path.stat().st_mtime).isoformat(timespec="seconds")

    with meta_cols[0]:
        _render_kv("as_of", as_of)
    with meta_cols[1]:
        _render_kv("universe", universe)
    with meta_cols[2]:
        _render_kv("file", selected_path.name)
    with meta_cols[3]:
        _render_kv("last modified", modified)

    st.markdown("")
    st.write(
        {
            "symbols_evaluated": stats.get("symbols_evaluated", 0),
            "total_candidates": stats.get("total_candidates", 0),
            "csp_candidates": stats.get("csp_candidates", 0),
            "cc_candidates": stats.get("cc_candidates", 0),
            "total_exclusions": stats.get("total_exclusions", 0),
        }
    )

    # Gate
    st.subheader("Execution gate (read-only)")
    gate_allowed = bool(gate.get("allowed", False))
    gate_reasons = gate.get("reasons", []) if isinstance(gate.get("reasons", []), list) else []
    if gate_allowed:
        st.success("Gate status: ALLOWED")
    else:
        st.error("Gate status: BLOCKED")
    if gate_reasons:
        st.markdown("**Gate reasons**")
        st.write(gate_reasons)
    
    # Phase 8.1: Operator Action Recommendations (Advisory)
    # Show recommendations when blocked, optional when allowed
    if not gate_allowed or True:  # Always show for now, can be made conditional
        st.subheader("Operator Action Recommendations (Advisory)")
        st.info(
            "⚠️ **Advisory Only** - These recommendations are derived from diagnostics "
            "and are for operator consideration only. They do not modify any logic or execution."
        )
        
        try:
            # Get sandbox result if available
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
                    pass  # Ignore sandbox errors for recommendations
            
            recommendations = generate_operator_recommendations(
                snapshot,
                sandbox_result=sandbox_result_for_recommendations,
            )
            
            if recommendations:
                # Group by severity
                high_recs = [r for r in recommendations if r.severity == RecommendationSeverity.HIGH]
                medium_recs = [r for r in recommendations if r.severity == RecommendationSeverity.MEDIUM]
                low_recs = [r for r in recommendations if r.severity == RecommendationSeverity.LOW]
                
                # Render HIGH severity first
                for rec in high_recs:
                    with st.expander(f"🔴 **HIGH:** {rec.title}", expanded=True):
                        st.markdown(f"**Action:** {rec.action}")
                        st.markdown("**Evidence:**")
                        for evidence_line in rec.evidence:
                            st.markdown(f"- {evidence_line}")
                        st.caption(f"Category: {rec.category}")
                
                # Render MEDIUM severity
                for rec in medium_recs:
                    with st.expander(f"🟡 **MEDIUM:** {rec.title}", expanded=False):
                        st.markdown(f"**Action:** {rec.action}")
                        st.markdown("**Evidence:**")
                        for evidence_line in rec.evidence:
                            st.markdown(f"- {evidence_line}")
                        st.caption(f"Category: {rec.category}")
                
                # Render LOW severity
                for rec in low_recs:
                    with st.expander(f"🟢 **LOW:** {rec.title}", expanded=False):
                        st.markdown(f"**Action:** {rec.action}")
                        st.markdown("**Evidence:**")
                        for evidence_line in rec.evidence:
                            st.markdown(f"- {evidence_line}")
                        st.caption(f"Category: {rec.category}")
            else:
                st.info("No recommendations available. System appears to be operating normally.")
        
        except Exception as e:
            st.error(f"Recommendation generation failed: {e}")
            st.code(str(e))

    # Phase 7.3: Diagnostics (Why the system is blocked)
    if not gate_allowed:
        exclusion_summary = snapshot.get("exclusion_summary")
        if isinstance(exclusion_summary, dict):
            st.subheader("Diagnostics (Why the system is blocked)")
            
            # Operator verdict
            verdict = _derive_operator_verdict(exclusion_summary)
            st.info(f"**Operator Verdict:** {verdict}")
            
            # Diagnostics table
            rule_counts = exclusion_summary.get("rule_counts", {})
            stage_counts = exclusion_summary.get("stage_counts", {})
            symbols_by_rule = exclusion_summary.get("symbols_by_rule", {})
            
            if rule_counts:
                # Build diagnostics table
                diagnostics_rows = []
                for rule, count in sorted(rule_counts.items(), key=lambda x: x[1], reverse=True):
                    stage = None
                    # Find stage for this rule (from first exclusion with this rule)
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
                
                st.dataframe(diagnostics_rows, use_container_width=True)
            else:
                st.info("No exclusion rules found in diagnostics.")
        
        # Phase 7.4: Coverage & Near-Miss Diagnostics
        coverage_summary = snapshot.get("coverage_summary")
        near_misses = snapshot.get("near_misses")
        
        if isinstance(coverage_summary, dict) or (isinstance(near_misses, list) and len(near_misses) > 0):
            st.subheader("Coverage & Near-Miss Diagnostics")
            
            # Coverage funnel table
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
                    st.dataframe(funnel_rows, use_container_width=True)
            
            # Near-misses
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
                        st.dataframe(near_miss_rows, use_container_width=True)
            elif isinstance(coverage_summary, dict):
                st.info("No near-misses identified (all candidates either selected or failed multiple rules).")

    # Selected signals
    st.subheader("Selected signals (ranked)")
    selected_signals = snapshot.get("selected_signals") or []
    if not isinstance(selected_signals, list):
        selected_signals = []

    if selected_signals:
        st.dataframe(_selected_signals_table(selected_signals), use_container_width=True)
    else:
        st.info("No selected signals in this snapshot.")
    
    # Phase 7.5: Operator Calibration Sandbox
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
        
        # Evaluate sandbox
        try:
            sandbox_params = SandboxParams(
                min_score=sandbox_min_score if sandbox_min_score > 0 else None,
                max_total=sandbox_max_total,
                max_per_symbol=sandbox_max_per_symbol,
                max_per_signal_type=sandbox_max_per_signal_type_val,
            )
            
            sandbox_result = evaluate_sandbox(snapshot, sandbox_params)
            
            # Comparison
            live_count = len(selected_signals)
            sandbox_count = sandbox_result.selected_count
            
            st.markdown("**Live vs Sandbox Comparison**")
            comp_cols = st.columns(2)
            with comp_cols[0]:
                st.metric("Live Selected", live_count)
            with comp_cols[1]:
                st.metric("Sandbox Selected", sandbox_count)
            
            # Newly admitted candidates
            if sandbox_result.newly_admitted:
                st.markdown(f"**Newly Admitted Candidates ({len(sandbox_result.newly_admitted)})**")
                st.info("These candidates would be selected with sandbox parameters but were rejected in live selection.")
                
                newly_admitted_rows = []
                for nm in sandbox_result.newly_admitted:
                    if isinstance(nm, dict):
                        scored = nm.get("scored", {})
                        if isinstance(scored, dict):
                            candidate = scored.get("candidate", {})
                            score = scored.get("score", {})
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
                    st.dataframe(newly_admitted_rows, use_container_width=True)
            else:
                st.info("No newly admitted candidates. Sandbox selection matches live selection.")
            
            # Sandbox selected signals (if different from live)
            if sandbox_count != live_count or sandbox_result.newly_admitted:
                with st.expander("View all sandbox selected signals"):
                    if sandbox_result.selected_signals:
                        st.dataframe(_selected_signals_table(sandbox_result.selected_signals), use_container_width=True)
                    else:
                        st.info("No signals selected in sandbox.")
        
        except Exception as e:
            st.error(f"Sandbox evaluation failed: {e}")
            st.code(str(e))

    # Phase 7.6: Signal Viability Analysis
    st.subheader("Signal Viability Analysis")
    st.info(
        "This section explains upstream data availability issues that prevent candidates "
        "from reaching selection. Read-only observability only."
    )
    
    try:
        viability_list = analyze_signal_viability(snapshot)
        
        if viability_list:
            # Summary banner
            viable_count = sum(1 for v in viability_list if v.primary_blockage == "VIABLE")
            total_symbols = len(viability_list)
            
            if viable_count > 0:
                st.success(
                    f"**{viable_count} of {total_symbols} symbols** produced viable candidates that reached selection."
                )
            else:
                st.warning(
                    f"**0 of {total_symbols} symbols** produced viable candidates. "
                    "See blockage reasons below."
                )
            
            # Per-symbol table
            viability_rows = []
            for v in viability_list:
                blockage_display = v.primary_blockage.replace("_", " ").title()
                if v.primary_blockage == "VIABLE":
                    blockage_display = "✅ VIABLE"
                
                viability_rows.append({
                    "Symbol": v.symbol,
                    "Expiries in DTE Window": v.expiries_in_dte_window,
                    "PUTs Scanned": v.puts_scanned,
                    "CALLs Scanned": v.calls_scanned,
                    "IV Available": "Yes" if v.iv_available else "No",
                    "Primary Blockage": blockage_display,
                })
            
            st.dataframe(viability_rows, use_container_width=True)
        else:
            st.info("No symbol viability data available in this snapshot.")
    
    except Exception as e:
        st.error(f"Viability analysis failed: {e}")
        st.code(str(e))

    # WHY THIS
    st.subheader("WHY THIS (score components)")
    explanations = snapshot.get("explanations") or []
    if not isinstance(explanations, list):
        explanations = []

    if not explanations:
        st.info("No explainability payload present in this snapshot.")
    else:
        for expl in explanations:
            if not isinstance(expl, dict):
                continue
            symbol = expl.get("symbol", "N/A")
            signal_type = expl.get("signal_type", "N/A")
            rank = expl.get("rank", "N/A")
            total_score = expl.get("total_score", "N/A")
            selection_reason = expl.get("selection_reason", "N/A")
            comps = expl.get("score_components", []) if isinstance(expl.get("score_components", []), list) else []
            policy = expl.get("policy_snapshot", {}) if isinstance(expl.get("policy_snapshot", {}), dict) else {}

            with st.expander(f"{symbol} {signal_type} | rank {rank} | score {_fmt_float(total_score)}"):
                _render_kv("selection_reason", selection_reason)
                st.markdown("**score_components**")
                if comps:
                    st.dataframe(
                        [
                            {
                                "name": c.get("name"),
                                "value": c.get("value"),
                                "weight": c.get("weight"),
                            }
                            for c in comps
                            if isinstance(c, dict)
                        ],
                        use_container_width=True,
                    )
                else:
                    st.write("(no components)")
                st.markdown("**policy_snapshot**")
                st.write(policy)

    # WHY NOT
    st.subheader("WHY NOT (rejections)")
    st.markdown("**Gate-level blocks**")
    if gate_reasons:
        st.write(gate_reasons)
    else:
        st.write("(none)")

    # Phase 7.2: Check for detailed exclusions in snapshot first
    snapshot_exclusions = snapshot.get("exclusions") or []
    if isinstance(snapshot_exclusions, list) and len(snapshot_exclusions) > 0:
        st.markdown("**Detailed Exclusions (per symbol)**")
        # Group by symbol
        exclusions_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        for excl in snapshot_exclusions:
            if not isinstance(excl, dict):
                continue
            symbol = excl.get("symbol", "UNKNOWN")
            exclusions_by_symbol.setdefault(symbol, []).append(excl)
        
        # Sort symbols deterministically
        for symbol in sorted(exclusions_by_symbol.keys()):
            items = exclusions_by_symbol[symbol]
            with st.expander(f"{symbol} exclusions ({len(items)})"):
                st.dataframe(
                    [
                        {
                            "rule": e.get("rule", "N/A"),
                            "message": e.get("message", "N/A"),
                            "stage": e.get("stage", "N/A"),
                        }
                        for e in items
                        if isinstance(e, dict)
                    ],
                    use_container_width=True,
                )
    elif exclusions:
        # Fallback to legacy exclusions format (from artifact top-level)
        st.markdown("**Signal-generation exclusions (per symbol)**")
        grouped = _group_exclusions(exclusions)
        for symbol, items in grouped.items():
            with st.expander(f"{symbol} exclusions ({len(items)})"):
                st.dataframe(
                    [
                        {
                            "code": e.get("code"),
                            "message": e.get("message"),
                            "data": e.get("data"),
                        }
                        for e in items
                    ],
                    use_container_width=True,
                )
    else:
        st.info(
            "No exclusions payload present in this decision artifact. "
            "Only aggregate exclusion counts are available in snapshot stats."
        )

    # Execution plan
    st.subheader("Execution plan (what to manually place on Robinhood)")
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
        _render_kv("blocked_reason", plan_blocked_reason)
    if plan_orders:
        st.dataframe(_orders_table(plan_orders), use_container_width=True)

    # Dry-run
    st.subheader("Dry-run result (simulated, no trading)")
    dry_allowed = bool(dry_run.get("allowed", False))
    dry_blocked_reason = dry_run.get("blocked_reason")
    dry_executed_at = dry_run.get("executed_at")
    dry_orders = dry_run.get("orders", []) if isinstance(dry_run.get("orders", []), list) else []
    if dry_allowed:
        st.success(f"Dry-run status: ALLOWED ({len(dry_orders)} orders)")
    else:
        st.error("Dry-run status: BLOCKED")
    if dry_executed_at:
        _render_kv("executed_at", dry_executed_at)
    if dry_blocked_reason:
        _render_kv("blocked_reason", dry_blocked_reason)
    if dry_orders:
        st.dataframe(_orders_table(dry_orders), use_container_width=True)

    st.markdown("---")
    st.caption(
        "Audit note: This page is purely a renderer for the persisted JSON artifact. "
        "It does not recompute scores/selection or re-evaluate the gate."
    )


if __name__ == "__main__":
    main()

