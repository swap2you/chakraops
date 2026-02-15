from __future__ import annotations

import os
from pathlib import Path

# Load .env so ORATS_API_TOKEN is available when run via Streamlit
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

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
from typing import Any, Callable, Dict, List, Optional

import streamlit as st
from streamlit.components.v1 import html as st_html

from app.signals.decision_snapshot import _derive_operator_verdict
from app.ui.live_dashboard_utils import (
    compute_status_label,
    extract_exclusions,
    extract_snapshot_gate_plan_dryrun,
    list_decision_files,
    list_mock_files,
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
from app.core.observability.rejection_analytics import compute_rejection_heatmap, summarize_rejections
from app.core.persistence import (
    get_enabled_symbols,
    get_rejection_history,
    get_trade_proposal_by_decision_ts,
    update_trade_proposal_acknowledgment,
    get_latest_decision_artifact_metadata,
    get_latest_daily_trust_report,
    get_daily_run_cycle,
    get_config_freeze_state,
    get_positions_for_view,
    get_position_events_for_view,
    get_recent_position_events,
)
from app.db.universe_import import import_universe_from_csv, get_effective_universe_csv_path
try:
    from app.ui_contracts.view_builders import (
        build_daily_overview_view,
        build_alerts_view,
        build_position_view,
    )
    _UI_CONTRACTS_AVAILABLE = True
except ImportError:
    _UI_CONTRACTS_AVAILABLE = False
from app.ui.safe_ui import ensure_dict, ensure_list, is_ui_mock, safe_get
from app.ui.ui_theme import (
    NAV_ITEMS,
    badge,
    card_header,
    card_html,
    get_theme_palette,
    humanize_label,
    inject_global_css,
    metric_tile,
    icon_svg,
    dataframe_title_case,
    COLORS,
    STATUS_TONE,
)

try:
    from streamlit_elements import elements, mui, html
    _USE_ELEMENTS = True
except ImportError:
    _USE_ELEMENTS = False
    elements = mui = html = None

# Footer version/build (UI-only)
UI_VERSION = "1.0"


def _repo_root() -> Path:
    # chakraops/app/ui/live_decision_dashboard.py -> chakraops/
    return Path(__file__).resolve().parents[2]


def _default_out_dir() -> Path:
    return _repo_root() / "out"


LIVE_ARTIFACT_DIR = _repo_root() / "out"
MOCK_ARTIFACT_DIR = _repo_root() / "out" / "mock"


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


# Phase 3.4: default context gating thresholds for dashboard warnings
_CONTEXT_IV_RANK_MIN_SELL = 10.0
_CONTEXT_IV_RANK_MAX_SELL = 90.0
_CONTEXT_EVENT_WINDOW_DAYS = 7


def _context_warnings(cand: Dict[str, Any]) -> str:
    """Return comma-separated warning labels when option_context would trigger gating (Phase 3.4)."""
    ctx = cand.get("option_context") if isinstance(cand, dict) else None
    if not isinstance(ctx, dict):
        return ""
    warnings: List[str] = []
    iv_rank = ctx.get("iv_rank")
    if iv_rank is not None:
        try:
            r = float(iv_rank)
            if r < _CONTEXT_IV_RANK_MIN_SELL:
                warnings.append("IV low")
            elif r > _CONTEXT_IV_RANK_MAX_SELL:
                warnings.append("IV high")
        except (TypeError, ValueError):
            pass
    days_to_earnings = ctx.get("days_to_earnings")
    if days_to_earnings is not None and _CONTEXT_EVENT_WINDOW_DAYS > 0:
        try:
            d = int(days_to_earnings)
            if 0 <= d <= _CONTEXT_EVENT_WINDOW_DAYS:
                warnings.append("Event soon")
        except (TypeError, ValueError):
            pass
    if ctx.get("event_flags"):
        warnings.append("Event soon")
    expected_move = ctx.get("expected_move_1sd")
    underlying = cand.get("underlying_price")
    strike = cand.get("strike")
    if expected_move is not None and underlying is not None and strike is not None:
        try:
            move_dollars = float(expected_move) * float(underlying)
            dist = abs(float(underlying) - float(strike))
            if move_dollars > dist:
                warnings.append("Move>strike")
        except (TypeError, ValueError):
            pass
    return ", ".join(warnings) if warnings else "—"


def _selected_signals_table(selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in selected:
        scored = item.get("scored", {}) if isinstance(item, dict) else {}
        cand = scored.get("candidate", {}) if isinstance(scored, dict) else {}
        score = scored.get("score", {}) if isinstance(scored, dict) else {}
        ctx = cand.get("option_context") if isinstance(cand, dict) else None
        ctx_dict = ctx if isinstance(ctx, dict) else {}
        # Phase 3.4: IV rank, expected move %, term slope, skew, context warnings
        iv_rank = ctx_dict.get("iv_rank")
        expected_move_1sd = ctx_dict.get("expected_move_1sd")
        expected_move_pct = (float(expected_move_1sd) * 100.0) if expected_move_1sd is not None else None
        term_slope = ctx_dict.get("term_structure_slope")
        skew = ctx_dict.get("skew_metric")
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
                "iv_rank": iv_rank,
                "expected_move_pct": round(expected_move_pct, 2) if expected_move_pct is not None else None,
                "term_slope": round(term_slope, 4) if term_slope is not None else None,
                "skew": round(skew, 4) if skew is not None else None,
                "context_warnings": _context_warnings(cand),
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


def _render_views_beta() -> None:
    """Phase 6.5: Views (Beta) — DailyOverviewView, AlertsView (top 10), PositionView table for open positions.
    Phase 6.6: When UI_MODE=MOCK, use mock data (no DB)."""
    if not _UI_CONTRACTS_AVAILABLE:
        st.caption("UI contracts not available (install app.ui_contracts).")
        return
    try:
        if is_ui_mock():
            from app.ui.mock_data import (
                mock_daily_overview_no_trade,
                mock_alerts_no_trade,
                mock_positions_mixed,
            )
            daily_overview = mock_daily_overview_no_trade()
            alerts_view = mock_alerts_no_trade()
            positions = mock_positions_mixed()
            st.caption("*(Mock data — UI_MODE=MOCK)*")
        else:
            from datetime import date
            today = date.today().isoformat()
            cycle = get_daily_run_cycle(today)
            trust_report = get_latest_daily_trust_report(days_back=2)
            decision_meta = get_latest_decision_artifact_metadata()
            freeze_state = get_config_freeze_state()
            daily_overview = build_daily_overview_view(cycle, trust_report, decision_meta, freeze_state)
            recent_events = ensure_list(get_recent_position_events(days=7))
            alerts_view = build_alerts_view(None, recent_events, daily_overview)
            positions = ensure_list(get_positions_for_view(states=("OPEN", "PARTIALLY_CLOSED")))
        st.markdown("**Daily overview**")
        st.json(ensure_dict(daily_overview.to_dict() if daily_overview else {}))
        alerts_items = ensure_list(getattr(alerts_view, "items", []))[:10]
        st.markdown("**Alerts (top 10)**")
        st.json({"as_of": getattr(alerts_view, "as_of", ""), "items": alerts_items})
        st.markdown("**Open positions**")
        if not positions:
            st.caption("No open positions.")
        else:
            rows = []
            for pos in positions:
                try:
                    if hasattr(pos, "to_dict") and callable(getattr(pos, "to_dict", None)):
                        rows.append(ensure_dict(pos.to_dict()))
                    else:
                        pos_id = getattr(pos, "id", None)
                        events = ensure_list(get_position_events_for_view(pos_id) if pos_id else [])
                        pv = build_position_view(pos, events)
                        rows.append(ensure_dict(pv.to_dict()))
                except Exception:
                    continue
            if rows:
                st.dataframe(rows, use_container_width=True)
            else:
                st.caption("No open positions.")
    except Exception as e:
        st.caption(f"Views (Beta) could not load: {e}")


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


def _render_sidebar_nav(current_page: str) -> None:
    """Vertical sidebar nav: Dashboard, Diagnostics, Strategy, Configuration, About with icons and active highlight."""
    st.sidebar.markdown("**Navigation**")
    for label, page_id, icon_name in NAV_ITEMS:
        is_active = current_page == page_id
        if st.sidebar.button(
            f" {label}",
            key=f"nav_{page_id}",
            type="primary" if is_active else "secondary",
            width="stretch",
        ):
            st.session_state.nav_page = page_id
            st.rerun()


def _render_tab_signals(
    snapshot: Dict[str, Any],
    selected_signals_table: Callable,
    fmt_float: Callable,
    render_kv: Callable,
    dataframe_title_case_fn: Callable,
) -> None:
    """Signals tab: selected signals table and Why This (score components)."""
    selected_signals = snapshot.get("selected_signals") or []
    if not isinstance(selected_signals, list):
        selected_signals = []
    st.markdown("**Selected Signals (Ranked)**")
    if selected_signals:
        rows = dataframe_title_case_fn(selected_signals_table(selected_signals))
        st.dataframe(rows, width="stretch")
        # Phase 3.4: Options context and colour-coded warnings
        with st.expander("**Options context** (IV rank, expected move, skew, term structure)"):
            st.caption(
                "Metrics come from OptionContext per symbol. Warnings indicate when a metric would trigger "
                "context gating (IV rank &lt;10 or &gt;90, event within 7 days, expected move &gt; distance to strike)."
            )
            for item in selected_signals:
                scored = item.get("scored", {}) if isinstance(item, dict) else {}
                cand = scored.get("candidate", {}) if isinstance(scored, dict) else {}
                ctx = cand.get("option_context") if isinstance(cand, dict) else {}
                if not isinstance(ctx, dict):
                    continue
                symbol = cand.get("symbol", "N/A")
                warnings_str = _context_warnings(cand)
                iv_rank = ctx.get("iv_rank")
                exp_move = ctx.get("expected_move_1sd")
                exp_pct = (float(exp_move) * 100.0) if exp_move is not None else None
                term = ctx.get("term_structure_slope")
                skew_val = ctx.get("skew_metric")
                # Colour-coded warning badges: red = would gate, yellow = caution, green = OK
                if warnings_str and warnings_str != "—":
                    st.markdown(
                        f'<span style="background:#ffcccc;padding:2px 6px;border-radius:4px;margin-right:4px;">{symbol}</span> '
                        f'<span style="color:#c00;">⚠ {warnings_str}</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<span style="background:#e8f5e9;padding:2px 6px;border-radius:4px;">{symbol}</span> '
                        f'IV rank: {iv_rank if iv_rank is not None else "—"} | '
                        f'Expected move: {f"{exp_pct:.2f}%" if exp_pct is not None else "—"} | '
                        f'Term slope: {term if term is not None else "—"} | '
                        f'Skew: {skew_val if skew_val is not None else "—"}',
                        unsafe_allow_html=True,
                    )
    else:
        st.caption("No selected signals in this snapshot.")
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
            with st.expander(f"{symbol} {signal_type} · rank {rank} · score {fmt_float(total_score)}"):
                render_kv("Selection reason", expl.get("selection_reason", "N/A"))
                if comps:
                    st.dataframe(
                        dataframe_title_case_fn([{"name": c.get("name"), "value": c.get("value"), "weight": c.get("weight")} for c in comps if isinstance(c, dict)]),
                        width="stretch",
                    )
                if policy:
                    st.caption("Policy snapshot: see artifact for full details.")


def _render_tab_diagnostics(
    snapshot: Dict[str, Any],
    gate_allowed: bool,
    sandbox_enabled: bool,
    sandbox_min_score: float,
    sandbox_max_total: int,
    sandbox_max_per_symbol: int,
    sandbox_max_per_signal_type_val: Optional[int],
    SandboxParamsCls: type,
    evaluate_sandbox_fn: Callable,
    RecommendationSeverityCls: type,
    generate_operator_recommendations_fn: Callable,
    derive_operator_verdict_fn: Callable,
    dataframe_title_case_fn: Callable,
    fmt_float: Callable,
) -> None:
    """Diagnostics tab: operator recommendations, exclusion summary, coverage, signal viability."""
    try:
        sandbox_result_for_recommendations = None
        if sandbox_enabled:
            try:
                sandbox_params = SandboxParamsCls(
                    min_score=sandbox_min_score if sandbox_min_score > 0 else None,
                    max_total=sandbox_max_total,
                    max_per_symbol=sandbox_max_per_symbol,
                    max_per_signal_type=sandbox_max_per_signal_type_val,
                )
                sandbox_result_for_recommendations = evaluate_sandbox_fn(snapshot, sandbox_params)
            except Exception:
                pass
        recommendations = generate_operator_recommendations_fn(
            snapshot,
            sandbox_result=sandbox_result_for_recommendations,
        )
        if recommendations:
            high_recs = [r for r in recommendations if r.severity == RecommendationSeverityCls.HIGH]
            medium_recs = [r for r in recommendations if r.severity == RecommendationSeverityCls.MEDIUM]
            low_recs = [r for r in recommendations if r.severity == RecommendationSeverityCls.LOW]
            for rec in high_recs:
                with st.expander(f"**HIGH:** {rec.title}", expanded=True):
                    st.markdown(f"**Action:** {rec.action}")
                    st.markdown("**Evidence:**")
                    for evidence_line in rec.evidence:
                        st.markdown(f"- {evidence_line}")
                    st.caption(f"Category: {rec.category}")
            for rec in medium_recs:
                with st.expander(f"**MEDIUM:** {rec.title}", expanded=False):
                    st.markdown(f"**Action:** {rec.action}")
                    st.markdown("**Evidence:**")
                    for evidence_line in rec.evidence:
                        st.markdown(f"- {evidence_line}")
                    st.caption(f"Category: {rec.category}")
            for rec in low_recs:
                with st.expander(f"**LOW:** {rec.title}", expanded=False):
                    st.markdown(f"**Action:** {rec.action}")
                    st.markdown("**Evidence:**")
                    for evidence_line in rec.evidence:
                        st.markdown(f"- {evidence_line}")
                    st.caption(f"Category: {rec.category}")
        else:
            st.info("No recommendations. System operating normally.")
    except Exception as e:
        st.error(f"Recommendation generation failed: {e}")

    if not gate_allowed:
        exclusion_summary = ensure_dict(snapshot.get("exclusion_summary"))
        if exclusion_summary:
            st.subheader("Diagnostics (Why the system is blocked)")
            try:
                verdict = derive_operator_verdict_fn(exclusion_summary)
                st.info(f"**Operator Verdict:** {verdict}")
            except Exception:
                verdict = "—"
                st.info("**Operator Verdict:** —")
            rule_counts = ensure_dict(exclusion_summary.get("rule_counts"))
            symbols_by_rule = ensure_dict(exclusion_summary.get("symbols_by_rule"))
            if rule_counts:
                diagnostics_rows = []
                for rule, count in sorted(rule_counts.items(), key=lambda x: x[1], reverse=True):
                    stage = None
                    snapshot_exclusions = ensure_list(snapshot.get("exclusions"))
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
                st.dataframe(dataframe_title_case_fn(diagnostics_rows), width="stretch")
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
                    st.dataframe(dataframe_title_case_fn(funnel_rows), width="stretch")
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
                                "Score": fmt_float(nm.get("score")),
                                "Strike": nm.get("strike", "N/A"),
                                "Expiry": nm.get("expiry", "N/A"),
                            })
                    if near_miss_rows:
                        st.dataframe(dataframe_title_case_fn(near_miss_rows), width="stretch")
            elif isinstance(coverage_summary, dict):
                st.info("No near-misses identified.")

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
            st.dataframe(dataframe_title_case_fn(viability_rows), width="stretch")
        else:
            st.caption("No symbol viability data.")
    except Exception as e:
        st.error(f"Viability analysis failed: {e}")


def _render_tab_why_not(
    gate_reasons: List[str],
    snapshot: Dict[str, Any],
    exclusions: List[Dict[str, Any]],
    group_exclusions_fn: Callable,
    humanize_label_fn: Callable,
    dataframe_title_case_fn: Callable,
) -> None:
    """Why Not tab: gate-level blocks and exclusions grouped by rule/symbol."""
    st.markdown("**Gate-level blocks**")
    if gate_reasons:
        for r in gate_reasons:
            st.caption(f"• {r}")
    else:
        st.caption("(none)")
    snapshot_exclusions = snapshot.get("exclusions") or []
    if isinstance(snapshot_exclusions, list) and len(snapshot_exclusions) > 0:
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
            with st.expander(f"**{humanize_label_fn(rule)}** ({len(items)} exclusions, {len(symbols_in_rule)} symbols)", expanded=False):
                rows = []
                for e in items:
                    if isinstance(e, dict):
                        data = e.get("data") or {}
                        sym = data.get("symbol") if isinstance(data, dict) else e.get("symbol")
                        rows.append({"Rule": rule, "Symbol": sym, "Stage": e.get("stage"), "Message": e.get("message")})
                if rows:
                    st.dataframe(dataframe_title_case_fn(rows), width="stretch")
    elif exclusions:
        grouped = group_exclusions_fn(exclusions)
        symbol_filter_legacy = st.text_input("Filter by symbol", key="why_not_symbol_filter_legacy", placeholder="e.g. AAPL")
        for symbol, items in sorted(grouped.items()):
            if symbol_filter_legacy and symbol_filter_legacy.strip() and symbol_filter_legacy.strip().upper() not in str(symbol).upper():
                continue
            with st.expander(f"{symbol} ({len(items)} exclusions)", expanded=False):
                st.dataframe(dataframe_title_case_fn([{"code": e.get("code"), "message": e.get("message")} for e in items]), width="stretch")
    else:
        st.caption("No exclusions in this artifact.")


def _render_tab_rejection_analytics(
    snapshot: Optional[Dict[str, Any]],
    gate: Optional[Dict[str, Any]],
    dataframe_title_case_fn: Callable,
) -> None:
    """Rejection Analytics tab (Phase 5.2): bar chart by reason/stage + symbol-frequency table."""
    from types import SimpleNamespace
    snapshot = ensure_dict(snapshot)
    gate = ensure_dict(gate)
    gate_result = SimpleNamespace(allowed=gate.get("allowed", False), reasons=ensure_list(gate.get("reasons")))
    try:
        summary = summarize_rejections(snapshot, gate_result)
    except Exception:
        summary = {}
    summary = ensure_dict(summary)
    by_reason = ensure_dict(summary.get("by_reason"))
    by_stage = ensure_dict(summary.get("by_stage"))
    symbol_freq = ensure_list(summary.get("symbol_frequency"))

    st.markdown("**Count by reason**")
    if by_reason:
        import pandas as pd
        df_reason = pd.DataFrame([{"Reason": k, "Count": v} for k, v in sorted(by_reason.items(), key=lambda x: -x[1])])
        st.bar_chart(df_reason.set_index("Reason")["Count"])
        st.dataframe(dataframe_title_case_fn(df_reason.to_dict("records")), use_container_width=True)
    else:
        st.caption("No rejection reasons in this snapshot.")

    st.markdown("**Count by stage**")
    if by_stage:
        import pandas as pd
        df_stage = pd.DataFrame([{"Stage": k, "Count": v} for k, v in by_stage.items() if v])
        if not df_stage.empty:
            st.bar_chart(df_stage.set_index("Stage")["Count"])
            st.dataframe(dataframe_title_case_fn(df_stage.to_dict("records")), use_container_width=True)
        else:
            st.caption("No stage counts.")
    else:
        st.caption("No stage data.")

    st.markdown("**Symbol–reason frequency**")
    if symbol_freq:
        st.dataframe(dataframe_title_case_fn(symbol_freq[:200]), use_container_width=True)
    else:
        st.caption("No symbol-frequency data.")

    st.markdown("**History (last 30 days)**")
    try:
        history = get_rejection_history(30)
    except Exception:
        history = []
    history = ensure_list(history)
    if history:
        try:
            heatmap = compute_rejection_heatmap(history)
        except Exception:
            heatmap = {}
        heatmap = ensure_dict(heatmap)
        reason_totals = ensure_dict(heatmap.get("reason_totals"))
        if reason_totals:
            import pandas as pd
            df_hist = pd.DataFrame([{"Reason": k, "Total": v} for k, v in sorted(reason_totals.items(), key=lambda x: -x[1])])
            st.dataframe(dataframe_title_case_fn(df_hist.to_dict("records")), use_container_width=True)
        else:
            st.caption("No aggregated reasons in history.")
    else:
        st.caption("No rejection history in DB yet.")


def _render_tab_sandbox(
    snapshot: Dict[str, Any],
    sandbox_enabled: bool,
    sandbox_min_score: float,
    sandbox_max_total: int,
    sandbox_max_per_symbol: int,
    sandbox_max_per_signal_type_val: Optional[int],
    SandboxParamsCls: type,
    evaluate_sandbox_fn: Callable,
    selected_signals: List[Dict[str, Any]],
    selected_signals_table_fn: Callable,
    candidate_key_fn: Callable,
    fmt_float: Callable,
    dataframe_title_case_fn: Callable,
) -> None:
    """Sandbox tab: hypothetical selection and comparison."""
    if sandbox_enabled:
        st.subheader("Operator Calibration Sandbox")
        st.warning(
            "**Sandbox Mode – Hypothetical Analysis Only**\n\n"
            "This sandbox allows you to test different selection parameters without modifying:\n"
            "- Live DecisionSnapshot (source of truth)\n"
            "- Execution gate evaluation\n"
            "- Execution plans\n"
            "- Slack alerts\n"
            "- Any persisted artifacts\n\n"
            "All sandbox evaluation runs entirely in memory. No changes are saved."
        )
        try:
            sandbox_params = SandboxParamsCls(
                min_score=sandbox_min_score if sandbox_min_score > 0 else None,
                max_total=sandbox_max_total,
                max_per_symbol=sandbox_max_per_symbol,
                max_per_signal_type=sandbox_max_per_signal_type_val,
            )
            sandbox_result = evaluate_sandbox_fn(snapshot, sandbox_params)
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
                        key = candidate_key_fn(nm)
                        reason = sandbox_result.rejected_reasons.get(str(key), "UNKNOWN")
                        newly_admitted_rows.append({
                            "Symbol": candidate.get("symbol", "N/A"),
                            "Strategy": candidate.get("signal_type", "N/A"),
                            "Strike": candidate.get("strike", "N/A"),
                            "Expiry": candidate.get("expiry", "N/A"),
                            "Score": fmt_float(score.get("total")),
                            "Why Rejected Live": reason,
                        })
                if newly_admitted_rows:
                    st.dataframe(dataframe_title_case_fn(newly_admitted_rows), width="stretch")
            else:
                st.caption("No newly admitted candidates.")
            if sandbox_count != live_count or sandbox_result.newly_admitted:
                with st.expander("View all sandbox selected signals"):
                    if sandbox_result.selected_signals:
                        st.dataframe(dataframe_title_case_fn(selected_signals_table_fn(sandbox_result.selected_signals)), width="stretch")
                    else:
                        st.caption("No signals selected in sandbox.")
        except Exception as e:
            st.error(f"Sandbox evaluation failed: {e}")
    else:
        st.caption("Enable sandbox mode in the sidebar to run hypothetical selection.")


def _readiness_color(status: str) -> str:
    """Phase 4.3: color for execution readiness (READY=green, REVIEW=amber, BLOCKED=red)."""
    if status == "READY":
        return "#22c55e"
    if status == "REVIEW":
        return "#eab308"
    return "#ef4444"


def _trust_first_hero_state(
    artifact: Optional[Dict[str, Any]],
    snapshot: Optional[Dict[str, Any]],
    gate: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase 5.4: Compute trust-first hero headline and trust section data.
    Phase 6.1: run_mode, config_frozen.
    Returns: headline, hero_tone ('safe'|'warning'), why_summary, top_reasons, risk_posture, run_mode, config_frozen.
    """
    artifact = ensure_dict(artifact)
    snapshot = ensure_dict(snapshot)
    gate = ensure_dict(gate)
    daily = ensure_dict(artifact.get("daily_trust_report"))
    proposal = ensure_dict(snapshot.get("trade_proposal"))
    why = ensure_dict(snapshot.get("why_no_trade"))
    metadata = ensure_dict(artifact.get("metadata"))
    trades_ready = int(daily.get("trades_ready", 0))
    if trades_ready == 0 and proposal.get("execution_status") == "READY":
        trades_ready = 1
    headline = "NO TRADE — CAPITAL PROTECTED"
    if trades_ready >= 1:
        headline = "1 SAFE TRADE AVAILABLE" if trades_ready == 1 else f"{trades_ready} SAFE TRADES AVAILABLE"
    hero_tone = "safe"  # Green for safety (capital protected or safe trade)
    why_summary = why.get("summary") or daily.get("summary") or ""
    top_reasons = ensure_list(daily.get("top_blocking_reasons"))
    primary_reasons = ensure_list(why.get("primary_reasons"))
    if not top_reasons and primary_reasons:
        top_reasons = [{"code": ensure_dict(r).get("code", ""), "count": ensure_dict(r).get("count", 0)} for r in primary_reasons[:5]]
    risk_posture = (metadata.get("risk_posture") or "CONSERVATIVE").strip().upper()
    run_mode = (metadata.get("run_mode") or daily.get("run_mode") or "DRY_RUN").strip().upper()
    config_frozen = metadata.get("config_frozen") if "config_frozen" in metadata else daily.get("config_frozen")
    return {
        "headline": headline,
        "hero_tone": hero_tone,
        "why_summary": why_summary,
        "top_reasons": top_reasons,
        "risk_posture": risk_posture,
        "run_mode": run_mode,
        "config_frozen": config_frozen,
    }


def _render_trust_section(
    artifact: Optional[Dict[str, Any]],
    snapshot: Optional[Dict[str, Any]],
    gate: Optional[Dict[str, Any]],
    humanize_label_fn: Callable,
) -> None:
    """Phase 5.4: Why-No-Trade summary, top blocking reasons, risk posture badge (trust-first). Phase 6.1: Config Frozen."""
    state = _trust_first_hero_state(artifact, snapshot, gate)
    rp = state.get("risk_posture") or "CONSERVATIVE"
    rp_tone = "success" if rp == "CONSERVATIVE" else ("warning" if rp == "BALANCED" else "danger")
    st.markdown(
        f'<div style="margin-bottom:10px;"><span style="font-size:0.75rem;color:var(--chakra-text-muted);">Risk posture</span> '
        f'{badge(rp, rp_tone)}</div>',
        unsafe_allow_html=True,
    )
    if state.get("config_frozen") is not None:
        frozen_text = "YES" if state["config_frozen"] else "NO"
        st.markdown(f"**Config frozen:** {frozen_text}")
    daily = ensure_dict(artifact).get("daily_trust_report") if artifact is not None else {}
    daily = ensure_dict(daily)
    freeze_keys = ensure_list(daily.get("freeze_violation_changed_keys"))
    if freeze_keys:
        st.caption(f"Changed keys (freeze violated): {', '.join(freeze_keys)}")
    if state.get("why_summary"):
        st.markdown("**Why no trade**")
        st.caption(state["why_summary"])
    top_reasons = ensure_list(state.get("top_reasons"))
    if top_reasons:
        st.markdown("**Top blocking reasons**")
        for item in top_reasons[:5]:
            code = ensure_dict(item).get("code", "UNKNOWN")
            count = ensure_dict(item).get("count", 0)
            st.caption(f"• {humanize_label_fn(code)}: {count}")


def _render_trade_proposal_readiness(snapshot: Dict[str, Any]) -> None:
    """Phase 4.3: Trade proposal execution readiness; color-code; require acknowledgment for READY."""
    proposal = snapshot.get("trade_proposal")
    if not proposal or not isinstance(proposal, dict):
        st.caption("No trade proposal for this snapshot.")
        return
    status = proposal.get("execution_status", "BLOCKED")
    symbol = proposal.get("symbol", "—")
    strategy_type = proposal.get("strategy_type", "—")
    rejected = proposal.get("rejected", True)
    pipeline_ts = snapshot.get("pipeline_timestamp")
    # Merge persisted ack/notes from DB
    db_proposal: Optional[Dict[str, Any]] = None
    if pipeline_ts:
        try:
            db_proposal = get_trade_proposal_by_decision_ts(pipeline_ts)
        except Exception:
            pass
    user_ack = proposal.get("user_acknowledged", False)
    execution_notes = proposal.get("execution_notes", "")
    skipped = proposal.get("skipped", False)
    proposal_id = None
    if db_proposal:
        user_ack = db_proposal.get("user_acknowledged", user_ack)
        execution_notes = db_proposal.get("execution_notes", execution_notes)
        skipped = db_proposal.get("skipped", skipped)
        proposal_id = db_proposal.get("_id")

    color = _readiness_color(status)
    st.markdown(
        f'<div style="padding:10px;border-radius:8px;border-left:4px solid {color};background:var(--chakra-bg-subtle);margin-bottom:12px;">'
        f'<strong>Trade Proposal</strong> · {symbol} · {strategy_type} · '
        f'<span style="color:{color};font-weight:600;">{status}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if rejected and proposal.get("rejection_reason"):
        st.caption(f"Rejection: {proposal.get('rejection_reason')}")
    if status == "READY":
        st.caption("Manual acknowledgment required before execution.")
        if proposal_id is not None and not user_ack and not skipped:
            notes_key = "exec_notes_trade_proposal"
            notes = st.text_area("Execution notes (optional)", value=execution_notes, key=notes_key, max_chars=500)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Acknowledge", key="ack_trade_proposal"):
                    try:
                        update_trade_proposal_acknowledgment(proposal_id, user_acknowledged=True, execution_notes=notes or "")
                        st.success("Acknowledged.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with col2:
                if st.button("Skip", key="skip_trade_proposal"):
                    try:
                        update_trade_proposal_acknowledgment(proposal_id, user_acknowledged=False, execution_notes=notes or "", skipped=True)
                        st.info("Skipped.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        elif user_ack:
            st.success("Acknowledged by operator.")
        elif skipped:
            st.info("Skipped by operator.")
    if execution_notes and (user_ack or skipped):
        st.caption(f"Notes: {execution_notes}")


def _render_tab_execution_plan(
    plan: Dict[str, Any],
    dry_run: Dict[str, Any],
    orders_table_fn: Callable,
    render_kv: Callable,
    dataframe_title_case_fn: Callable,
    snapshot: Optional[Dict[str, Any]] = None,
) -> None:
    """Execution Plan tab: trade proposal readiness (Phase 4.3), plan status, orders, dry-run result."""
    if snapshot:
        _render_trade_proposal_readiness(snapshot)
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
        render_kv("Blocked reason", plan_blocked_reason)
    if plan_orders:
        st.dataframe(dataframe_title_case_fn(orders_table_fn(plan_orders)), width="stretch")
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
        render_kv("Executed at", dry_executed_at)
    if dry_blocked_reason:
        render_kv("Blocked reason", dry_blocked_reason)
    if dry_orders:
        st.dataframe(dataframe_title_case_fn(orders_table_fn(dry_orders)), width="stretch")


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
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "dashboard"
    if "out_dir" not in st.session_state:
        st.session_state.out_dir = str(_default_out_dir())
    if "dashboard_tab_index" not in st.session_state:
        st.session_state.dashboard_tab_index = 0
    current_page = st.session_state.nav_page
    dark = st.session_state.dark_mode
    inject_global_css(dark)

    # Sidebar: dark/light toggle, then nav, then controls
    st.sidebar.checkbox("Dark mode", value=dark, key="dark_mode")
    st.sidebar.markdown("---")
    _render_sidebar_nav(current_page)
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Controls**")
    artifact_mode = st.sidebar.radio("Mode", ["LIVE", "MOCK"], index=0, key="artifact_mode", horizontal=True)
    use_mock_artifact = artifact_mode == "MOCK"

    if use_mock_artifact:
        out_dir = MOCK_ARTIFACT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        decision_files = list_mock_files(out_dir)
    else:
        out_dir = LIVE_ARTIFACT_DIR
        decision_files = list_decision_files(out_dir, exclude_mock=True)

    out_dir_resolved = out_dir.resolve() if out_dir.exists() else out_dir

    st.markdown(
        f"<div style='background:#1e3a5f;color:#fff;padding:10px 14px;border-radius:8px;margin-bottom:12px;"
        f"font-weight:600;font-size:14px;'>"
        f"{'MOCK' if use_mock_artifact else 'LIVE'} mode — {out_dir_resolved}</div>",
        unsafe_allow_html=True,
    )

    if not decision_files and current_page in ("dashboard", "diagnostics"):
        st.error(f"No {'scenario' if use_mock_artifact else 'decision'} files found in: {out_dir}")
        if use_mock_artifact:
            st.info("Place scenario JSON files (e.g. scenario_*.json) in out/mock/ for MOCK mode.")
        else:
            st.info(
                "Generate a decision artifact, then rerun Streamlit:\n\n"
                "`python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out`"
            )
        _render_footer()
        return

    # Phase UI-1: Run Results page (does not need decision artifact)
    if current_page == "run_results":
        st.subheader("Universe Run Results")
        from app.ui.run_results_ui import render_run_results_tab, render_diagnostics_tab
        rr_tab, diag_tab = st.tabs(["Ranked Candidates", "System Diagnostics"])
        with rr_tab:
            render_run_results_tab()
        with diag_tab:
            render_diagnostics_tab()
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
    if current_page == "strategy":
        st.subheader("Strategy")
        card_html(
            "Principles",
            "<ul style='margin:0;padding-left:1.2rem;font-size:0.875rem;'>"
            "<li>Curated universe from database (enabled symbols only)</li>"
            "<li>Options expirations and chains from ORATS</li>"
            "<li>CSP (Cash-Secured Put) and CC (Covered Call) candidates scored and ranked</li>"
            "<li>Selection policy: max total, max per symbol, min score</li>"
            "<li>Execution gate blocks unless selected signals exist and snapshot is fresh</li>"
            "<li>No trades placed by this system; execution is manual only</li>"
            "</ul>",
            icon="shield",
        )
        card_html(
            "Pipeline (text)",
            "<p style='margin:0;font-size:0.875rem;'><strong>1.</strong> Load universe from DB → <strong>2.</strong> Fetch options (ORATS) → "
            "<strong>3.</strong> Build CSP/CC candidates → <strong>4.</strong> Score & select → <strong>5.</strong> Evaluate gate → "
            "<strong>6.</strong> Build execution plan (read-only). No JSON dumps in UI.</p>",
        )
        _render_footer()
        return
    if current_page == "configuration":
        st.subheader("Configuration")
        # Advanced: output directory (moved from sidebar)
        card_header("Output Directory", icon="database")
        st.caption("Decision JSON files are loaded from this path. Change and rerun to use a different folder.")
        st.text_input("Output Directory", key="out_dir", label_visibility="visible")
        st.caption("Resolved path (select to copy):")
        st.code(str(out_dir_resolved), language=None)
        try:
            db_path = get_db_path()
            enabled_symbols = get_enabled_symbols()
            csv_path_effective = get_effective_universe_csv_path()
            card_header("Database", icon="database")
            st.caption("Path (select to copy)")
            st.code(str(db_path.resolve()), language=None)
            metric_tile("Enabled Symbols", len(enabled_symbols))
            card_header("Universe CSV", icon="database")
            st.caption("Path (select to copy)")
            st.code(str(csv_path_effective), language=None)
            if st.button("Import Universe From CSV"):
                n = import_universe_from_csv(notes="core_watchlist", enabled=True)
                st.success(f"Imported {n} symbols")
                st.rerun()
        except Exception as e:
            st.warning(str(e))
        card_header("Slack", icon="alert")
        slack_ok, slack_msg = slack_webhook_available()
        st.caption(slack_msg)
        st.caption("Notifications are sent only on: gate state change, advisory severity change, or manual send.")
        if st.button("Send Slack Now (Manual)"):
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
        with st.expander("Debug Paths"):
            st.caption("Output Dir")
            st.code(str(out_dir_resolved), language=None)
            st.caption("Glob: decision_*.json")
            if selected_path:
                st.caption("Selected File")
                st.code(str(selected_path.resolve()), language=None)
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

    try:
        artifact = load_decision_artifact(selected_path)
    except Exception as e:
        st.error(f"Failed to load JSON: {selected_path}")
        st.code(str(e))
        _render_footer()
        return

    if not use_mock_artifact:
        meta = artifact.get("metadata") or {}
        snap = artifact.get("decision_snapshot") or {}
        ds = str(meta.get("data_source") or snap.get("data_source") or "").lower()
        if ds in ("mock", "scenario"):
            st.error(
                "LIVE mode must never load mock data. This file has data_source indicating mock. "
                "Switch to MOCK mode or load a live artifact from out/."
            )
            _render_footer()
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
    if selected_path and selected_path.exists():
        modified_ts = datetime.fromtimestamp(selected_path.stat().st_mtime)
    else:
        modified_ts = datetime.now()
    modified_str = modified_ts.strftime("%Y-%m-%d %H:%M")

    # Check data source from snapshot (pipeline annotation)
    # data_source: "live", "snapshot", or "unavailable"
    snapshot_data_source = snapshot.get("data_source") or artifact.get("metadata", {}).get("data_source") or "live"
    is_offline_data = snapshot_data_source == "snapshot"

    # Check chain health (symbols without options)
    symbols_without_options = snapshot.get("symbols_without_options") or {}
    has_missing_chains = len(symbols_without_options) > 0
    missing_chain_count = len(symbols_without_options)

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
    regime = artifact.get("regime")
    regime_reason = artifact.get("regime_reason")
    reason_line = "; ".join(gate_reasons[:2]) if gate_reasons else ("—" if gate_allowed else "No selected signals")
    if regime_reason:
        reason_line = f"Regime: {regime_reason}. " + reason_line
    selected_count = len(snapshot.get("selected_signals") or []) if isinstance(snapshot.get("selected_signals"), list) else 0
    selected_signals = snapshot.get("selected_signals") or []
    if not isinstance(selected_signals, list):
        selected_signals = []
    palette = get_theme_palette(dark)
    trust_state = _trust_first_hero_state(artifact, snapshot, gate)

    if _USE_ELEMENTS and elements is not None and mui is not None:
        # Option Alpha–style layout: streamlit-elements header, status bar, grid, MUI Tabs
        def _on_tab_change(ev, val):
            st.session_state.dashboard_tab_index = int(val) if val is not None else 0

        with elements("chakra_dashboard"):
            with mui.Box(sx={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "mb": 2, "p": 2, "bgcolor": palette["surface"], "borderRadius": 1, "border": f"1px solid {palette['border']}"}):
                with mui.Stack(direction="row", spacing=2, sx={"alignItems": "center"}):
                    mui.Typography("ChakraOps — Live Decision Monitor", variant="h6", sx={"fontWeight": 600, "color": palette["text_primary"]})
                    # Offline Data badge when using snapshot fallback
                    if is_offline_data:
                        mui.Chip(label="Offline Data", size="small", sx={"bgcolor": "#6b7280", "color": "#fff", "fontWeight": 500, "fontSize": "0.75rem"})
                    # Chain health warning badge
                    if has_missing_chains:
                        mui.Chip(label=f"{missing_chain_count} Missing Chains", size="small", sx={"bgcolor": "#d97706", "color": "#fff", "fontWeight": 500, "fontSize": "0.75rem"})
                with mui.Stack(direction="row", spacing=2):
                    mui.Typography(f"Market: {live_str}", variant="body2", sx={"color": palette["text_secondary"]})
                    mui.Typography("Theta Terminal", variant="body2", sx={"color": palette["text_secondary"]})
                    mui.Typography(f"Snapshot: {as_of}", variant="body2", sx={"color": palette["text_secondary"]})
            with mui.Grid(container=True, spacing=2, sx={"mb": 2}):
                with mui.Grid(item=True, xs=12, md=6):
                    # Phase 5.4: trust-first hero — green for safety (capital protected or safe trade)
                    border_color = palette["success"] if trust_state["hero_tone"] == "safe" else (palette["warning"] if status == "REVIEW" else palette["danger"])
                    with mui.Paper(elevation=0, sx={"p": 2, "borderLeft": f"4px solid {border_color}", "bgcolor": palette["surface"], "border": f"1px solid {palette['border']}"}):
                        with mui.Stack(direction="row", spacing=1, sx={"alignItems": "center", "mb": 1}):
                            mui.Typography(trust_state["headline"], variant="subtitle1", sx={"fontWeight": 700, "color": palette["text_primary"]})
                            if is_offline_data:
                                mui.Chip(label="Offline", size="small", sx={"bgcolor": "#6b7280", "color": "#fff", "fontSize": "0.65rem"})
                            mui.Chip(label=trust_state.get("run_mode", "DRY_RUN"), size="small", sx={"bgcolor": "#475569", "color": "#fff", "fontSize": "0.65rem"})
                        mui.Chip(label=status, sx={"bgcolor": border_color, "color": "#fff", "fontWeight": 600, "mt": 1})
                        mui.Typography(reason_line, variant="body2", sx={"mt": 1, "color": palette["text_secondary"]})
                        mui.Typography(f"Timestamp: {modified_str}", variant="caption", sx={"display": "block", "mt": 1, "color": palette["text_secondary"]})
                with mui.Grid(item=True, xs=12, md=6):
                    with mui.Stack(direction="row", spacing=2, sx={"flexWrap": "wrap"}):
                        with mui.Paper(elevation=0, sx={"p": 1.5, "minWidth": 100, "bgcolor": palette["surface"], "border": f"1px solid {palette['border']}"}):
                            mui.Typography("Market", variant="caption", sx={"color": palette["text_secondary"]})
                            mui.Typography(live_str, variant="body2", sx={"fontWeight": 600})
                        with mui.Paper(elevation=0, sx={"p": 1.5, "minWidth": 100, "bgcolor": palette["surface"], "border": f"1px solid {palette['border']}"}):
                            mui.Typography("Provider", variant="caption", sx={"color": palette["text_secondary"]})
                            mui.Typography("ORATS", variant="body2", sx={"fontWeight": 600})
                        with mui.Paper(elevation=0, sx={"p": 1.5, "minWidth": 100, "bgcolor": palette["surface"], "border": f"1px solid {palette['border']}"}):
                            mui.Typography("Snapshot Age", variant="caption", sx={"color": palette["text_secondary"]})
                            mui.Typography(str(as_of), variant="body2", sx={"fontWeight": 600})
                        with mui.Paper(elevation=0, sx={"p": 1.5, "minWidth": 100, "bgcolor": palette["surface"], "border": f"1px solid {palette['border']}"}):
                            mui.Typography("Symbols Evaluated", variant="caption", sx={"color": palette["text_secondary"]})
                            mui.Typography(str(stats.get("symbols_evaluated", 0)), variant="body2", sx={"fontWeight": 600})
                        with mui.Paper(elevation=0, sx={"p": 1.5, "minWidth": 100, "bgcolor": palette["surface"], "border": f"1px solid {palette['border']}"}):
                            mui.Typography("Candidates", variant="caption", sx={"color": palette["text_secondary"]})
                            mui.Typography(str(stats.get("total_candidates", 0)), variant="body2", sx={"fontWeight": 600})
                        with mui.Paper(elevation=0, sx={"p": 1.5, "minWidth": 100, "bgcolor": palette["surface"], "border": f"1px solid {palette['border']}"}):
                            mui.Typography("Selected", variant="caption", sx={"color": palette["text_secondary"]})
                            mui.Typography(str(selected_count), variant="body2", sx={"fontWeight": 600})
            tab_index = st.session_state.dashboard_tab_index
            with mui.Tabs(value=tab_index, onChange=_on_tab_change, sx={"borderBottom": f"1px solid {palette['border']}", "mb": 2}):
                mui.Tab(label="Signals")
                mui.Tab(label="Diagnostics")
                mui.Tab(label="Why Not")
                mui.Tab(label="Sandbox")
                mui.Tab(label="Execution Plan")

        # Phase 5.4: trust section (Why-No-Trade summary, top rejection reasons, risk posture badge)
        with st.expander("**Trust & discipline**", expanded=True):
            _render_trust_section(artifact, snapshot, gate, humanize_label)
        with st.expander("**Views (Beta)**", expanded=False):
            _render_views_beta()

        # Tab content (Streamlit) keyed by dashboard_tab_index
        tab_index = st.session_state.dashboard_tab_index
        if tab_index == 0:
            _render_tab_signals(snapshot, _selected_signals_table, _fmt_float, _render_kv, dataframe_title_case)
        elif tab_index == 1:
            _render_tab_diagnostics(snapshot, gate_allowed, sandbox_enabled, sandbox_min_score, sandbox_max_total, sandbox_max_per_symbol, sandbox_max_per_signal_type_val, SandboxParams, evaluate_sandbox, RecommendationSeverity, generate_operator_recommendations, _derive_operator_verdict, dataframe_title_case, _fmt_float)
        elif tab_index == 2:
            _render_tab_why_not(gate_reasons, snapshot, exclusions, _group_exclusions, humanize_label, dataframe_title_case)
        elif tab_index == 3:
            _render_tab_sandbox(snapshot, sandbox_enabled, sandbox_min_score, sandbox_max_total, sandbox_max_per_symbol, sandbox_max_per_signal_type_val, SandboxParams, evaluate_sandbox, selected_signals, _selected_signals_table, _candidate_key, _fmt_float, dataframe_title_case)
        else:
            _render_tab_execution_plan(plan, dry_run, _orders_table, _render_kv, dataframe_title_case, snapshot)
    else:
        # Fallback: native Streamlit layout (hero + metrics + trust section + st.tabs)
        # Phase 5.4: trust-first hero — green for safety, amber for review, red only for actual risk
        hero_tone = "safe" if trust_state["hero_tone"] == "safe" else ("warning" if status == "REVIEW" else "blocked")
        gate_badge_html = badge(status, "danger" if not gate_allowed else ("warning" if status == "REVIEW" else "success"))
        offline_badge_html = '<span class="chakra-theme-badge" style="background:#6b7280;color:#fff;margin-left:8px;font-size:0.7rem;">Offline Data</span>' if is_offline_data else ""
        chain_badge_html = f'<span class="chakra-theme-badge" style="background:#d97706;color:#fff;margin-left:8px;font-size:0.7rem;">{missing_chain_count} Missing Chains</span>' if has_missing_chains else ""
        run_mode_html = f'<span class="chakra-theme-badge" style="background:#475569;color:#fff;margin-left:8px;font-size:0.7rem;">{trust_state.get("run_mode", "DRY_RUN")}</span>'
        st.markdown(
            f'<div class="chakra-theme-card chakra-theme-hero hero-{hero_tone}">'
            f'<h4 style="margin:0 0 8px 0;">{trust_state["headline"]}{offline_badge_html}{chain_badge_html}{run_mode_html}</h4><div style="margin-bottom:6px;">{gate_badge_html}</div>'
            f'<p style="margin:0;font-size:0.875rem;color:var(--chakra-text-muted);">{reason_line}</p>'
            f'<p style="margin:6px 0 0 0;font-size:0.8rem;color:var(--chakra-text-muted);">Timestamp: {modified_str}</p></div>',
            unsafe_allow_html=True,
        )
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        for col, (label, val) in zip([m1, m2, m3, m4, m5, m6], [
            ("Market Status", live_str), ("Provider", "ORATS"), ("Snapshot Age", as_of),
            ("Symbols Evaluated", stats.get("symbols_evaluated", 0)), ("Candidates", stats.get("total_candidates", 0)), ("Selected", selected_count)]):
            with col:
                metric_tile(label, val)
        with st.expander("**Trust & discipline**", expanded=True):
            _render_trust_section(artifact, snapshot, gate, humanize_label)
        with st.expander("**Views (Beta)**", expanded=False):
            _render_views_beta()
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Signals", "Diagnostics", "Why Not", "Sandbox", "Execution Plan", "Rejection Analytics"])
        with tab1:
            _render_tab_signals(snapshot, _selected_signals_table, _fmt_float, _render_kv, dataframe_title_case)
        with tab2:
            _render_tab_diagnostics(
                snapshot, gate_allowed, sandbox_enabled, sandbox_min_score, sandbox_max_total,
                sandbox_max_per_symbol, sandbox_max_per_signal_type_val, SandboxParams, evaluate_sandbox,
                RecommendationSeverity, generate_operator_recommendations, _derive_operator_verdict,
                dataframe_title_case, _fmt_float,
            )
        with tab3:
            _render_tab_why_not(gate_reasons, snapshot, exclusions, _group_exclusions, humanize_label, dataframe_title_case)
        with tab4:
            _render_tab_sandbox(
                snapshot, sandbox_enabled, sandbox_min_score, sandbox_max_total, sandbox_max_per_symbol,
                sandbox_max_per_signal_type_val, SandboxParams, evaluate_sandbox, selected_signals,
                _selected_signals_table, _candidate_key, _fmt_float, dataframe_title_case,
            )
        with tab5:
            _render_tab_execution_plan(plan, dry_run, _orders_table, _render_kv, dataframe_title_case, snapshot)
        with tab6:
            _render_tab_rejection_analytics(snapshot, gate, dataframe_title_case)

    st.markdown("---")
    _render_footer()


if __name__ == "__main__":
    main()

