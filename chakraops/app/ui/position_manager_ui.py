# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Position Manager UI: list, detail, actions, Add Position form, monthly perf (Phase 6.7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from app.ui.safe_ui import ensure_dict, ensure_list, is_ui_mock
from app.ui_contracts.view_models import PositionView, PositionTimelineView
from app.ui_contracts.view_builders import build_position_view, build_position_timeline_view


def _positions_from_live(
    states: Tuple[str, ...] = ("OPEN", "PARTIALLY_CLOSED", "CLOSED", "ASSIGNED"),
    needs_attention_only: bool = False,
) -> List[PositionView]:
    """Load positions from DB and build PositionView list."""
    from app.core.persistence import get_positions_for_view, get_position_events_for_view
    positions = get_positions_for_view(states=states)
    views: List[PositionView] = []
    for pos in positions:
        events = get_position_events_for_view(str(getattr(pos, "id", "")))
        pv = build_position_view(pos, events)
        if needs_attention_only and not pv.needs_attention:
            continue
        views.append(pv)
    return views


def _safe_currency(val: Any, default: str = "—") -> str:
    if val is None:
        return default
    try:
        return f"${float(val):.2f}"
    except (TypeError, ValueError):
        return default


def render_positions_page(data: Optional[Dict[str, Any]] = None, parsed: Optional[Dict[str, Any]] = None) -> None:
    """Render full Positions tab: list, detail, Add Position form, monthly perf."""
    st.markdown("## Positions")
    use_mock = is_ui_mock()
    
    if use_mock:
        # C8: Clear labeling for demo/mock data with toggle to hide
        st.warning(
            "⚠️ **Demo Data Mode** — This is simulated data for UI demonstration. "
            "No broker integration is active. Set `UI_MODE=LIVE` to connect to real data.",
            icon="🎭"
        )
        
        # Toggle to hide demo data entirely
        hide_demo = st.checkbox(
            "Hide demo data (show empty state)",
            value=st.session_state.get("pm_hide_demo", False),
            key="pm_hide_demo_toggle",
        )
        st.session_state["pm_hide_demo"] = hide_demo
        
        if hide_demo:
            st.info("Demo data hidden. Enable the checkbox above or switch to LIVE mode to view positions.")
            _render_add_position_form(use_mock)  # Still show form instructions
            return
        
        _render_demo_controls()
        positions, selected_id = _render_positions_list_mock()
    else:
        positions, selected_id = _render_positions_list_live()
    
    if selected_id:
        _render_position_detail(selected_id, positions, use_mock)
    _render_add_position_form(use_mock)
    _render_monthly_performance(use_mock)


def _render_demo_controls() -> None:
    """Demo scenario selector for MOCK mode (Phase 6.7)."""
    from app.ui.mock_data import (
        mock_positions_empty,
        mock_positions_open,
        mock_positions_mixed,
    )
    scenarios = [
        ("No positions", mock_positions_empty()),
        ("Open only", mock_positions_open()),
        ("Mixed (6 states)", mock_positions_mixed()),
    ]
    idx = st.selectbox(
        "Demo scenario",
        range(len(scenarios)),
        index=2,
        format_func=lambda i: scenarios[i][0],
        key="pm_demo_scenario",
    )
    st.session_state["pm_mock_positions"] = scenarios[idx][1]


def _render_positions_list_mock() -> Tuple[List[PositionView], Optional[str]]:
    """Render positions table from mock; return (list, selected_position_id)."""
    from app.ui.mock_data import mock_positions_mixed
    positions: List[PositionView] = st.session_state.get("pm_mock_positions")
    if not isinstance(positions, list):
        positions = mock_positions_mixed()
        st.session_state["pm_mock_positions"] = positions
    return _render_positions_table(positions, "pm_sel_mock")


def _render_positions_list_live() -> Tuple[List[PositionView], Optional[str]]:
    """Render positions table from DB; return (list, selected_position_id)."""
    states_key = st.session_state.get("pm_filter_states", ["OPEN", "PARTIALLY_CLOSED", "CLOSED", "ASSIGNED"])
    needs_only = st.session_state.get("pm_needs_attention_only", False)
    with st.expander("Filters", expanded=False):
        cols = st.columns(4)
        with cols[0]:
            open_chk = st.checkbox("OPEN", value="OPEN" in states_key, key="pm_chk_open")
        with cols[1]:
            part_chk = st.checkbox("PARTIALLY_CLOSED", value="PARTIALLY_CLOSED" in states_key, key="pm_chk_part")
        with cols[2]:
            closed_chk = st.checkbox("CLOSED", value="CLOSED" in states_key, key="pm_chk_closed")
        with cols[3]:
            assigned_chk = st.checkbox("ASSIGNED", value="ASSIGNED" in states_key, key="pm_chk_assigned")
        needs_only = st.checkbox("Needs attention only", value=needs_only, key="pm_needs_only")
        new_states = []
        if open_chk:
            new_states.append("OPEN")
        if part_chk:
            new_states.append("PARTIALLY_CLOSED")
        if closed_chk:
            new_states.append("CLOSED")
        if assigned_chk:
            new_states.append("ASSIGNED")
        if not new_states:
            new_states = ["OPEN", "PARTIALLY_CLOSED", "CLOSED", "ASSIGNED"]
        st.session_state["pm_filter_states"] = new_states
        st.session_state["pm_needs_attention_only"] = needs_only
    positions = _positions_from_live(tuple(new_states), needs_attention_only=needs_only)
    return _render_positions_table(positions, "pm_sel_live")


def _render_positions_table(positions: List[PositionView], key_prefix: str) -> Tuple[List[PositionView], Optional[str]]:
    """Render table of PositionView; return (positions, selected_position_id)."""
    if not positions:
        st.info("No positions. Add one below or run in MOCK to see demo data.")
        return [], None
    rows = []
    for pv in positions:
        rows.append({
            "symbol": pv.symbol,
            "strategy": pv.strategy_type,
            "lifecycle": pv.lifecycle_state,
            "opened": pv.opened,
            "expiry": pv.expiry or "—",
            "strike": pv.strike if pv.strike is not None else "—",
            "contracts": pv.contracts,
            "entry_credit": _safe_currency(pv.entry_credit),
            "dte": pv.dte if pv.dte is not None else "—",
            "unrealized": _safe_currency(pv.unrealized_pnl),
            "realized": _safe_currency(pv.realized_pnl),
            "max_loss_est": _safe_currency(pv.max_loss_estimate),
            "needs_attention": "Yes" if pv.needs_attention else "",
            "notes": (pv.notes or "")[:40] + ("…" if (pv.notes or "") and len(pv.notes or "") > 40 else ""),
        })
    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, key=f"{key_prefix}_df")
    ids = [str(pv.position_id) for pv in positions]
    selected_idx = st.selectbox(
        "Select position for detail",
        range(len(ids)),
        format_func=lambda i: f"{positions[i].symbol} {positions[i].lifecycle_state} ({positions[i].position_id})",
        key=f"{key_prefix}_select",
    )
    selected_id = ids[selected_idx] if ids else None
    return positions, selected_id


def _render_position_detail(
    position_id: str,
    positions: List[PositionView],
    use_mock: bool,
) -> None:
    """Detail panel: timeline, metrics, action buttons (with confirmation)."""
    pv = next((p for p in positions if str(p.position_id) == position_id), None)
    if not pv:
        st.warning("Position not found.")
        return
    st.markdown("---")
    st.markdown(f"### {pv.symbol} — {pv.lifecycle_state}")
    # Timeline
    if use_mock:
        from app.ui.mock_data import get_mock_position_events
        events = get_mock_position_events(position_id)
    else:
        from app.core.persistence import get_position_events_for_view
        events = get_position_events_for_view(position_id)
    timeline = build_position_timeline_view(position_id, pv.symbol, ensure_list(events))
    st.markdown("**Timeline**")
    for ev in timeline.events:
        st.caption(f"{ev.get('event_time', '')} — {ev.get('event_type', '')} — {ensure_dict(ev.get('metadata'))}")
    # Metrics
    st.markdown("**Metrics**")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Entry credit", _safe_currency(pv.entry_credit))
        st.metric("T1 / T2 / T3", f"{pv.profit_targets.get('t1', '—')} / {pv.profit_targets.get('t2', '—')} / {pv.profit_targets.get('t3', '—')}")
    with c2:
        st.metric("Realized PnL", _safe_currency(pv.realized_pnl))
        st.metric("Max loss est.", _safe_currency(pv.max_loss_estimate))
    with c3:
        st.metric("Needs attention", "Yes" if pv.needs_attention else "No")
        if pv.attention_reasons:
            st.caption("Reasons: " + ", ".join(pv.attention_reasons))
    if pv.notes:
        st.text_area("Notes", value=pv.notes, disabled=True, key=f"pm_notes_view_{position_id}")
    # Actions (LIVE only; with confirmation)
    if not use_mock and pv.lifecycle_state in ("OPEN", "PARTIALLY_CLOSED", "ASSIGNED"):
        _render_position_actions(position_id, pv)


def _render_position_actions(position_id: str, pv: PositionView) -> None:
    """Action buttons: Add Note, Partial Close, Close, Mark Assigned (with confirmation)."""
    from app.core.persistence import (
        update_position_notes,
        record_partial_close,
        record_close,
        record_assignment,
    )
    from app.core.position_lifecycle import InvalidLifecycleTransitionError
    st.markdown("**Actions**")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("Add note", key=f"pm_act_note_{position_id}"):
            st.session_state[f"pm_confirm_note_{position_id}"] = True
    if st.session_state.get(f"pm_confirm_note_{position_id}"):
        note_text = st.text_input("Note text", key=f"pm_note_input_{position_id}")
        if st.button("Save note", key=f"pm_save_note_{position_id}"):
            try:
                update_position_notes(position_id, note_text or "")
                st.success("Note saved.")
                del st.session_state[f"pm_confirm_note_{position_id}"]
                st.rerun()
            except Exception as e:
                st.error(str(e))
        if st.button("Cancel", key=f"pm_cancel_note_{position_id}"):
            del st.session_state[f"pm_confirm_note_{position_id}"]
            st.rerun()
    with c2:
        if pv.lifecycle_state in ("OPEN", "PARTIALLY_CLOSED") and st.button("Partial close", key=f"pm_act_part_{position_id}"):
            st.session_state[f"pm_confirm_part_{position_id}"] = True
    if st.session_state.get(f"pm_confirm_part_{position_id}"):
        delta = st.number_input("Realized PnL delta", value=0.0, step=10.0, key=f"pm_part_delta_{position_id}")
        part_notes = st.text_input("Notes", key=f"pm_part_notes_{position_id}")
        if st.button("Confirm partial close", key=f"pm_save_part_{position_id}"):
            try:
                record_partial_close(position_id, float(delta), part_notes or None)
                st.success("Partial close recorded.")
                del st.session_state[f"pm_confirm_part_{position_id}"]
                st.rerun()
            except Exception as e:
                st.error(str(e))
        if st.button("Cancel", key=f"pm_cancel_part_{position_id}"):
            del st.session_state[f"pm_confirm_part_{position_id}"]
            st.rerun()
    with c3:
        if pv.lifecycle_state in ("OPEN", "PARTIALLY_CLOSED") and st.button("Close", key=f"pm_act_close_{position_id}"):
            st.session_state[f"pm_confirm_close_{position_id}"] = True
    if st.session_state.get(f"pm_confirm_close_{position_id}"):
        close_delta = st.number_input("Realized PnL delta", value=0.0, step=10.0, key=f"pm_close_delta_{position_id}")
        close_notes = st.text_input("Notes", key=f"pm_close_notes_{position_id}")
        if st.button("Confirm close", key=f"pm_save_close_{position_id}"):
            try:
                record_close(position_id, float(close_delta), close_notes or None)
                st.success("Position closed.")
                del st.session_state[f"pm_confirm_close_{position_id}"]
                st.rerun()
            except InvalidLifecycleTransitionError:
                st.error("Invalid transition (e.g. already closed).")
            except Exception as e:
                st.error(str(e))
        if st.button("Cancel", key=f"pm_cancel_close_{position_id}"):
            del st.session_state[f"pm_confirm_close_{position_id}"]
            st.rerun()
    with c4:
        if pv.lifecycle_state == "OPEN" and st.button("Mark assigned", key=f"pm_act_assign_{position_id}"):
            st.session_state[f"pm_confirm_assign_{position_id}"] = True
    if st.session_state.get(f"pm_confirm_assign_{position_id}"):
        assign_notes = st.text_input("Notes", key=f"pm_assign_notes_{position_id}")
        if st.button("Confirm assign", key=f"pm_save_assign_{position_id}"):
            try:
                record_assignment(position_id, assign_notes or None)
                st.success("Marked assigned.")
                del st.session_state[f"pm_confirm_assign_{position_id}"]
                st.rerun()
            except Exception as e:
                st.error(str(e))
        if st.button("Cancel", key=f"pm_cancel_assign_{position_id}"):
            del st.session_state[f"pm_confirm_assign_{position_id}"]
            st.rerun()


def _render_add_position_form(use_mock: bool) -> None:
    """Add Position Manually form (LIVE only; MOCK shows disabled message)."""
    st.markdown("---")
    st.markdown("### Add position manually")
    if use_mock:
        st.info("Mock mode: no DB writes. Use LIVE mode to add positions.")
        return
    from app.core.persistence import create_manual_position
    with st.form("pm_add_position_form"):
        symbol = st.text_input("Symbol", value="", placeholder="AAPL").strip().upper()
        strategy_type = st.selectbox("Strategy", ["CSP", "SHARES"], key="pm_add_strategy")
        expiry = st.text_input("Expiry (YYYY-MM-DD)", value="", placeholder="2026-04-18") if strategy_type == "CSP" else None
        strike = st.number_input("Strike", value=0.0, step=1.0) if strategy_type == "CSP" else None
        contracts = st.number_input("Contracts", value=1, min_value=1, step=1)
        entry_credit = st.number_input("Entry credit", value=0.0, step=10.0)
        open_date = st.text_input("Open date (YYYY-MM-DD)", value=datetime.now().strftime("%Y-%m-%d"))
        notes = st.text_area("Notes", value="")
        if st.form_submit_button("Save"):
            if not symbol:
                st.error("Symbol is required.")
            elif strategy_type == "CSP" and (not expiry or not strike):
                st.error("Expiry and strike required for CSP.")
            else:
                try:
                    pos = create_manual_position(
                        symbol=symbol,
                        strategy_type=strategy_type,
                        expiry=expiry if strategy_type == "CSP" else None,
                        strike=float(strike) if strategy_type == "CSP" and strike is not None else None,
                        contracts=int(contracts),
                        entry_credit=float(entry_credit),
                        open_date=open_date or datetime.now().strftime("%Y-%m-%d"),
                        notes=notes or None,
                    )
                    st.success(f"Position created: {pos.id}")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def _render_monthly_performance(use_mock: bool) -> None:
    """Monthly Performance panel (read-only): MTD PnL, capital deployed, last 3 months."""
    st.markdown("---")
    st.markdown("### Monthly performance")
    if use_mock:
        st.caption("Mock: showing placeholder. Use LIVE for real ledger data.")
        st.metric("MTD realized PnL", "$0.00")
        st.metric("Capital deployed today", "$0.00")
        return
    from app.core.persistence import get_mtd_realized_pnl, get_capital_deployed_today, get_monthly_summaries
    mtd = get_mtd_realized_pnl()
    deployed = get_capital_deployed_today()
    st.metric("MTD realized PnL", _safe_currency(mtd))
    st.metric("Capital deployed today", _safe_currency(deployed))
    summaries = get_monthly_summaries(last_n=3)
    if summaries:
        st.markdown("**Last 3 months**")
        import pandas as pd
        rows = [
            {
                "Month": f"{s['year']}-{s['month']:02d}",
                "Credit": _safe_currency(s["total_credit_collected"]),
                "Realized PnL": _safe_currency(s["realized_pnl"]),
                "Win rate": f"{s.get('win_rate', 0) * 100:.1f}%",
            }
            for s in summaries
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
