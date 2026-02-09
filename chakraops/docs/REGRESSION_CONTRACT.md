# Regression Contract — Nightly Definition

This document codifies what must never break. It defines the nightly regression set and the guarantees those tests enforce. No CI/CD automation is required at baseline; this is the contract that any future nightly job must satisfy.

---

## Tests That Run Nightly

The following test **files** (under `chakraops/tests/`) must be included in the nightly run. Running the full suite `pytest chakraops/tests/` satisfies this; the list below is the **minimum** critical set that must pass.

### Critical (must pass every night)

| Test file | Purpose |
|-----------|--------|
| `test_phase6_data_dependencies.py` | Required data missing → BLOCKED; override cannot force PASS; PASS only when required_data_missing and required_data_stale empty. |
| `test_ranking.py` | Band priority, only eligible, limit, structure; BLOCKED/HOLD excluded from ranked list. |
| `test_lifecycle_engine.py` | Lifecycle and alert behavior. |
| `test_evaluation_store.py` | Run save/load/list/delete; no run-file glob including data_completeness files. |
| `test_evaluation_consistency.py` | Capital hint serialization, verdict precedence, view consistency. |
| `test_decision_quality.py` | Decision quality summary and return_on_risk / outcome_tag semantics. |
| `test_exits.py` | Exit events, SCALE_OUT vs FINAL_EXIT, decision quality exclusion. |
| `test_verdict_resolver.py` | Verdict precedence (BLOCKED > FATAL > HOLD > ELIGIBLE). |
| `test_chain_provider.py` | Chain provider and staged evaluator (mocked ORATS). |
| `test_orats_summaries_mapping.py` | Stage 1 snapshot mapping (mocked fetch_full_equity_snapshots). |
| `test_alert_throttle.py` | Alert throttling. |
| `test_data_completeness_report.py` | Data completeness report structure. |
| `test_portfolio.py` | Portfolio and exposure. |

### Full suite

Nightly run **SHOULD** execute the full backend test suite:

```bash
cd chakraops && python -m pytest tests/ -v
```

Skipped tests (e.g. FastAPI not installed, zoneinfo, live fixtures) are acceptable. **Zero failures** on non-skipped tests is required.

---

## Guarantees (What Regression Validates)

1. **Required data missing → BLOCKED**  
   When any required field (price, iv_rank, bid, ask, volume, or candidate delta) is missing, the system sets risk_status BLOCKED and does not recommend. No inferred PASS. Covered by `test_phase6_data_dependencies.py` and related.

2. **No inferred PASS**  
   data_sufficiency never reports PASS when required_data_missing is non-empty. Manual override cannot override when required data is missing. Covered by Phase 6 data dependency tests.

3. **SCALE_OUT-only excluded from decision quality**  
   Positions with SCALE_OUT but no FINAL_EXIT are excluded from decision quality (return_on_risk, outcome_tag) until the position is fully closed. Covered by exits and decision quality tests.

4. **UNKNOWN remains explicit**  
   UI and API use UNKNOWN for band, risk, strategy, return_on_risk when data is missing or risk_amount_at_entry is not set. No blank or NA for decision-critical fields. Covered by view consistency and decision quality tests.

5. **Run storage and list/delete**  
   Only run JSON files (not `*_data_completeness.json`) are listed and deleted by list_runs/delete_old_runs. Run payload required keys (run_id, started_at, status, symbols) are validated. Covered by `test_evaluation_store.py`.

6. **No live ORATS in unit tests**  
   Unit tests patch ORATS (e.g. `fetch_full_equity_snapshots`, `get_orats_live_strikes` / `get_orats_live_summaries`). Regression does not call live ORATS. Missing ORATS token must not cause unit test failures.

---

## What Regression Does NOT Validate

- **Live ORATS:** No real ORATS API token or network calls. All ORATS-dependent paths are mocked in unit tests.
- **Brokers:** No broker integration; regression does not touch any broker API.
- **Slack:** No real Slack webhook. Notifications tests use mocks.
- **Real secrets:** Regression may use secrets injected via environment (e.g. in CI) for optional integration tests; unit tests must not require real secrets. See [SECRETS_AND_ENV.md](./SECRETS_AND_ENV.md).

---

## Optional: Pytest Marker

If desired, a marker can be used to run only the critical regression set:

```python
@pytest.mark.regression
def test_required_missing_blocks_when_required_missing(): ...
```

Then:

```bash
pytest chakraops/tests/ -m regression -v
```

This is **optional** at baseline; the contract is satisfied by running the full suite and ensuring the critical files above are part of it.
