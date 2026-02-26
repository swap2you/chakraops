# Project status bookmark (through R22.7)

Short operator/dev reference. Not marketing.

---

## Completed releases (R21.1 – R22.3)

- **R21.1:** Account + Holdings (SQLite, API, Portfolio page).
- **R21.2:** CSP realized PnL sign.
- **R21.5:** Notifications / Slack / Scheduler observability.
- **R21.3:** Universe add/remove via UI.
- **R21.4:** Symbol technical details (computed_values, diagnostics API).
- **R21.6:** System Status UI cleanup (backlog).
- **R22.1:** Release engineering + Preflight build gate.
- **R22.2:** Slack + Scheduler set-and-forget; ORATS as_of/threshold_triggered; friendly skip labels.
- **R22.3:** Wheel page mode (admin/advanced/hidden); Admin/Recovery copy; no raw codes in Wheel UI.

---

## R22.4 / R22.5 verification status

- **R22.4 (Multi-timeframe S/R + hold-time):** Marked DONE in checklist; request-time MTF levels, targets, hold-time; no prose in decision JSON.
- **R22.5 (Shares evaluation pipeline):** Marked DONE; Shares candidates and plan (recommendation-only); Dashboard Shares card, Symbol Shares plan section.

---

## R22.7 goals (current)

- **Truth:** Decision artifact code-only (no prose, no FAIL_*/WARN_* in persisted values).
- **Consistency:** Run evaluation vs single-symbol recompute deterministic and aligned.
- **MTF S/R:** Proper weekly/monthly resampling (not reusing daily).
- **Targets/hold-time:** Sensible vs spot; ATR-based hold-time; clear tooltips.
- **Shares:** Symbol Shares tab; record shares position; show in Portfolio.
- **Technical details:** Score breakdown and indicators (request-time).
- **ORATS/notifications:** Safe labels (OK/DELAYED/WARN/ERROR); no raw “ORATS WARN”.
- **Trade ticket:** Contract identity always present for options candidates.
- **UX:** Full-width MTF/Targets; info tooltips; consistent badges.

---

## What remains after R22.7

- R21.6 (System Status compact table) — backlog.
- Phase 23 premium backlog per `docs/enhancements/phase_23_premium_trading_backlog.md`.
- Any follow-up UAT and production hardening.

---

## Canonical artifacts

- Decision: `out/decision_latest.json` (and `out/decision_frozen.json` when frozen). Written only by EvaluationStoreV2.
- Verification: `out/verification/<Release>/notes.md`.
- Allowed `out/` contents: decision_latest.json, slack_status.json, universe_overrides.json, verification/, evaluations/, alerts/, lifecycle/.
