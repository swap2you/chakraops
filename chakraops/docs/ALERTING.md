# Alerting (Phase 6)

This document describes the alert system: stage-aware, deduplicated, and actionable. Slack is only a delivery channel; all alert logic lives in core code.

## Design principles

- **Actionable, not noisy:** Alerts include a one-line summary and an action hint for the operator. No per-symbol spam.
- **Deduplicated:** Same fingerprint is suppressed for a configurable cooldown (default 6h). Regime and signal alerts fire only on actual changes.
- **No alerts during RUNNING:** Alerts are built only after a run completes (COMPLETED or FAILED).
- **No evaluation logic changes:** The evaluation pipeline is unchanged; alerts consume run results only.

## Alert taxonomy

| Type | Description | When it fires |
|------|-------------|----------------|
| **DATA_HEALTH** | Data quality or pipeline errors | Run had errors, or many symbols with low data completeness |
| **REGIME_CHANGE** | Market regime transition | Regime value changed vs previous COMPLETED run |
| **SIGNAL** | Eligible/shortlist set change | Set of eligible or shortlisted symbols changed vs previous run |
| **SYSTEM** | Run or system failure | Run status is FAILED |

## Severity

- **INFO** — Informational (e.g. signal set changed).
- **WARN** — Needs attention (e.g. regime change, some run errors).
- **CRITICAL** — Immediate attention (run failed, many errors).

## Alert model (core)

Each alert has:

- **alert_type** — DATA_HEALTH | REGIME_CHANGE | SIGNAL | SYSTEM
- **severity** — INFO | WARN | CRITICAL
- **stage** — Optional pipeline stage
- **symbol** — Optional (aggregate alerts usually have no symbol)
- **reason_code** — Machine-readable code (e.g. REGIME_TRANSITION, SET_CHANGE)
- **summary** — One-line human summary
- **action_hint** — What the operator should do
- **fingerprint** — Hash used for deduplication
- **created_at** — ISO timestamp

## Deduplication rules

1. **Same fingerprint → cooldown**  
   If this fingerprint was already sent within the cooldown window (default 6 hours), the alert is suppressed and logged as “cooldown”. Configurable in `config/alerts.yaml` via `cooldown_hours`.

2. **Regime change**  
   REGIME_CHANGE alerts are built only when the current run’s regime differs from the **previous COMPLETED** run’s regime. No repeat for unchanged regime.

3. **SIGNAL**  
   SIGNAL alerts are built only when the eligible set or shortlist set **changed** compared to the previous COMPLETED run. No alert if the sets are unchanged.

4. **Per-type enable/disable**  
   `config/alerts.yaml` lists `enabled_alert_types`. Alerts whose type is not in that list are not sent and are logged as “alert_type_disabled”.

## When alerts are built

- **After a run completes** (COMPLETED or FAILED): the store persists the run, and the alert engine runs.
- **Input:** Current run (just saved) and “previous COMPLETED run” (from run history, for diffing).
- **Output:** List of candidate alerts → cooldown filter → send via Slack (if configured) → persist to `out/alerts/alerts_log.jsonl`.

No alerts are emitted while a run is in RUNNING state.

## Persistence and audit

- **Path:** `out/alerts/alerts_log.jsonl` (one JSON object per line).
- Each record includes: fingerprint, created_at, alert_type, severity, summary, action_hint, and either **sent** (true) + **sent_at**, or **sent** (false) + **suppressed_reason** (e.g. `cooldown`, `slack_not_configured`, `alert_type_disabled`).
- Used for audit and for cooldown checks (recent “sent” events by fingerprint).

## Configuration: config/alerts.yaml

```yaml
# Which alert types to generate and send
enabled_alert_types:
  - DATA_HEALTH
  - REGIME_CHANGE
  - SIGNAL
  - SYSTEM

# Cooldown in hours (same fingerprint not sent again within this window)
cooldown_hours: 6

# Slack: default webhook from env SLACK_WEBHOOK_URL
# Optional: per-alert-type webhook URLs (each posts to one channel)
slack:
  channels:
    # DATA_HEALTH: "https://hooks.slack.com/..."
    # REGIME_CHANGE: "https://hooks.slack.com/..."
```

- **enabled_alert_types** — Only these types are sent; others are logged as suppressed.
- **cooldown_hours** — Fingerprint cooldown (default 6). Set to 0 to disable cooldown (not recommended).
- **slack.channels** — Optional map of alert_type → webhook URL. If a type is not listed, the default `SLACK_WEBHOOK_URL` is used.

## Slack delivery

- **Default:** `SLACK_WEBHOOK_URL` (environment variable). If unset, alerts are still generated and written to the log but **not** sent; the UI shows “Alerts suppressed (Slack not configured)”.
- **Per-type routing:** In `alerts.yaml`, under `slack.channels`, you can set a different webhook URL per alert type (e.g. DATA_HEALTH → #data-health, SYSTEM → #ops).
- **Message format:** Slack Block Kit: header (type + severity), summary, action hint, context (reason_code, created_at).

## UI (Notifications page)

- **Banner:** When Slack is not configured, a banner explains that alerts are suppressed.
- **System Alerts section:** Lists recent alert log records: alert_type, severity, summary, action_hint, and either “Sent at &lt;time&gt;” or “Suppressed: &lt;reason&gt;”.
- Data comes from `GET /api/view/alert-log` and `GET /api/ops/alerting-status`.

## How to tune

- **Reduce noise:** Increase `cooldown_hours` or remove an alert type from `enabled_alert_types`.
- **More visibility:** Add a type to `enabled_alert_types`, or add a dedicated webhook under `slack.channels` for that type.
- **Regime/SIGNAL only on change:** Logic is in code; no config. REGIME_CHANGE fires only on transition; SIGNAL only when eligible/shortlist set changes.

## Examples

- **Regime changed from BULL to NEUTRAL** → REGIME_CHANGE, WARN, action: “Review strategy suitability for new regime.”
- **Eligible set changed; 3 eligible, 2 shortlisted** → SIGNAL, INFO, action: “Review Dashboard and History for current eligible/shortlist.”
- **Run had 2 error(s). First: Symbol XYZ missing quote** → DATA_HEALTH, WARN, action: “Check symbol diagnostics and data sources.”
- **Evaluation run failed: ORATS timeout** → SYSTEM, CRITICAL, action: “Check logs and data sources; re-run evaluation.”

## Implementation locations

- **Alert model and engine:** `app/core/alerts/` (models.py, alert_engine.py, slack_notifier.py).
- **Config:** `config/alerts.yaml`.
- **Invocation:** After `save_run` / `update_latest_pointer` in API evaluate-now and in scheduler background thread (`universe_evaluator.trigger_evaluation`); also after `save_failed_run` (load run from store and run alert engine).
- **API:** `GET /api/view/alert-log`, `GET /api/ops/alerting-status`.
