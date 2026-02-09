# ChakraOps — Backlog & Technical Debt Ledger

**Purpose:** Single backlog and technical-debt ledger so we never lose improvements.  
**Source of truth for:** Critical fixes, high-priority work, enhancements, refactor targets, and architecture rules.

---

## Architecture Rules

These rules are non-negotiable for correctness and maintainability:

| Rule | Description |
|------|--------------|
| **One ORATS client** | All ORATS access goes through a single client layer. No ad-hoc HTTP or duplicate clients. |
| **One data contract validator** | Required/optional/derivable and instrument-type rules live in one validator; all callers use it. |
| **No direct ORATS from UI** | UI consumes backend results only (evaluation JSON, APIs). No UI → ORATS calls. |
| **No duplicate “required fields” logic** | Required fields are defined once (DATA_CONTRACT + validator). No copy-paste required-field lists in evaluator, ranking, or UI. |

---

## 1. Critical Fixes (Now)

Items required to restore or maintain correctness: ORATS unknown/missing handling, endpoint consistency, unified validation, removal of duplicate codepaths.

| # | Item | Owner | Status | Target phase |
|---|------|--------|--------|--------------|
| C1 | **ORATS unknown/missing handling** — Define and enforce behavior when ORATS returns empty, partial, or error responses (e.g. no options chain, missing quoteDate). Align with DATA_CONTRACT: missing required → FAIL; optional missing → WARN. | — | Open | Phase 8F |
| C2 | **Endpoint consistency** — All equity/chain data must flow from the same ORATS v2 endpoints (`/datav2/strikes/options`, `/datav2/ivrank`). Remove or deprecate any path that uses different endpoints for the same concept. | — | Done (manifest + audit; see “ORATS v2 consistency audit” below; legacy `app/data/orats_client` deprecated) | Phase 8F |
| C3 | **Unified validation** — All “required vs optional” and “instrument-type” checks must go through the single data contract validator (instrument_type + data_dependencies + DATA_CONTRACT). No ad-hoc required-field lists in staged_evaluator, ranking, or API. | — | In progress (Phase 8E done) | Phase 8E/8F |
| C4 | **Remove duplicate codepaths** — Identify and collapse duplicate logic for: (a) computing missing_fields, (b) data sufficiency status (PASS/WARN/FAIL), (c) staleness. Single code path per concept. | — | Open | Phase 8F |
| C5 | **Override rule enforcement** — Manual override MUST NOT override when `required_data_missing` is non-empty. Ensure API and UI never present a symbol as PASS in that case (per DATA_CONTRACT §4). | — | Open | Phase 8F |

*Seeded from DATA_CONTRACT.md (required/optional, override rules, ORATS health) and PHASE8E_VALIDATION_REPORT.md (unified instrument-type + required fields).*

---

### ORATS v2 consistency audit (done)

| Item | Detail |
|------|--------|
| **Endpoint manifest** | Single source: `app/core/orats/endpoints.py`. Defines `BASE_DATAV2`, `BASE_LIVE`, `PATH_STRIKES`, `PATH_STRIKES_OPTIONS`, `PATH_IVRANK`, `PATH_LIVE_STRIKES`, `PATH_LIVE_SUMMARIES`. |
| **Canonical ORATS client modules** | All v2 HTTP goes through: (1) `app/core/orats/orats_client.py` (live strikes/summaries), (2) `app/core/orats/orats_equity_quote.py` (strikes/options for underlying + ivrank), (3) `app/core/orats/orats_opra.py` (strikes + strikes/options for OCC). All three import base URLs and paths from `endpoints.py`. `app/core/options/orats_chain_pipeline.py` and `app/core/options/providers/orats_client.py` also import from `endpoints.py`. |
| **Runtime logging** | Each ORATS HTTP response logs one line: `[ORATS_CALL]` or `[ORATS_RESP]` with `endpoint=`, `symbol=`, `http_status=`, `quote_date=`, `fields=` (field presence: price, volume, iv_rank, bid, ask, open_interest). Implemented in `orats_client._orats_get_live` and `orats_equity_quote._fetch_equity_quotes_single_batch` / `_fetch_iv_ranks_single_batch`. |
| **Old / duplicate call sites** | **Removed:** None deleted (no duplicate v2 definitions left). **Deprecated:** `app/data/orats_client.py` — uses `api.orats.com` and `/chain/{symbol}` (v1-style). Only used by `main.py` (RollEngine). Marked DEPRECATED; migrate to core orats and remove. |
| **Consumers** | Stage 1 evaluation → `orats_equity_quote.fetch_full_equity_snapshots`. Live strikes/summaries → `orats_client.get_orats_live_strikes` / `get_orats_live_summaries` (data_health, server, universe_evaluator, orats_chain_provider, journal). Option chain → `orats_opra` + `orats_chain_pipeline`. All use v2 bases and paths from the manifest. |

---

## 2. High Priority (Next)

Items that materially reduce risk or prevent regressions: single source of truth, diagnostics in UI, test coverage, health checks.

| # | Item | Owner | Status | Target phase |
|---|------|--------|--------|--------------|
| H1 | **Single source of truth for required fields** — Ensure `instrument_type.get_required_fields_for_instrument` and `data_dependencies.compute_required_missing` are the only sources; all other modules (staged_evaluator, ranking, data_sufficiency) call these. No local required-field tuples. | — | In progress (Phase 8E) | Phase 8E/8F |
| H2 | **Diagnostics surfaced to UI** — Expose `field_sources` (ORATS \| DERIVED \| CACHED) and data completeness details in the UI diagnostics panel. Evaluation JSON and `*_data_completeness.json` already have it; UI must consume and display. | — | Open | Phase 9 |
| H3 | **Test coverage for data trust** — Broader tests: (a) integration test that SPY/QQQ with valid ORATS payload never get DATA_INCOMPLETE for bid/ask/OI only; (b) EQUITY missing bid/ask still FAIL in ranking; (c) derivation promotion covered in Stage 1 path. | — | Partial (Phase 8E unit tests) | Phase 8F |
| H4 | **ORATS data health checks** — Health endpoint (`/api/ops/data-health`) and runbook semantics (UNKNOWN / OK / WARN / DOWN) documented and tested. Sticky status; no recompute on every request. See DATA_CONTRACT §8. | — | Open | Phase 8F |
| H5 | **Staleness single implementation** — Staleness (trading days from quote_date) computed in one place; all consumers use it. > 1 trading day → WARN; no duplicate staleness logic. | — | Open | Phase 8F |

*Seeded from DATA_CONTRACT.md (API/UI, health) and PHASE8E_VALIDATION_REPORT.md (diagnostics, tests).*

---

## 3. Nice-to-Have Enhancements (Later)

Scoring tweaks, UI improvements, additional strategy filters, reporting polish. Not required for correctness.

| # | Item | Owner | Status | Target phase |
|---|------|--------|--------|--------------|
| N1 | **Scoring tweaks** — Fine-tune composite score weights, band boundaries, or rank reasons. No change to data sufficiency or verdict logic. | — | Backlog | Later |
| N2 | **UI improvements** — Better presentation of verdicts, missing_fields, data_sufficiency, and regime. No new backend contracts. | — | Backlog | Later |
| N3 | **Additional strategy filters** — New filters (e.g. sector, DTE bands) as optional strategy constraints. | — | Backlog | Later |
| N4 | **Reporting polish** — Daily report formatting, export options, and readability. | — | Backlog | Later |
| N5 | **avg_volume from external source** — If a source is added for avg_volume, wire it optionally; DATA_CONTRACT keeps it optional and non-blocking. | — | Backlog | Later |

---

## 4. Technical Debt / Refactor Targets

Duplicate modules, legacy screens not using shared services, inconsistent ORATS mapping, data contract drift.

| # | Item | Owner | Status | Target phase |
|---|------|--------|--------|--------------|
| T1 | **Duplicate “required fields” logic** — Before Phase 8E, required fields appeared in multiple places (e.g. MARKET_SNAPSHOT_REQUIRED_FIELDS, REQUIRED_EVALUATION_FIELDS). Phase 8E moved to instrument-aware validator; audit and remove any remaining duplicate definitions. | — | In progress | Phase 8F |
| T2 | **Legacy screens not using shared services** — Any screen or view that computes data sufficiency, missing_fields, or required fields locally must be refactored to use backend APIs and shared validator. | — | Open | Phase 9 |
| T3 | **Inconsistent ORATS mapping** — Single mapping document (e.g. ORATS_FIELD_TO_ENDPOINT_MAPPING.md) and one code path that maps ORATS response → internal model. No divergent field names or endpoints per feature. | — | Open | Phase 8F |
| T4 | **Data contract drift** — Establish a lightweight check (e.g. test or script) that runtime required-field sets match DATA_CONTRACT.md. Run on CI or pre-commit to prevent drift. | — | Open | Phase 8F |
| T5 | **Legacy data_dependencies vs data_sufficiency** — Clarify boundary: data_dependencies = required/optional/stale lists; data_sufficiency = derived status (PASS/WARN/FAIL) and API shape. Avoid overlapping responsibilities. | — | Open | Phase 8F |

*Seeded from PHASE8E_VALIDATION_REPORT.md (files touched, single source of truth) and DATA_CONTRACT.md (single source of truth for required vs optional).*

---

## 5. Reference: Phase 8E Fix Summary (Data Trust Baseline)

Completed work that established the data trust baseline (for context and to avoid rework):

- **Instrument classification** — `InstrumentType` (EQUITY, ETF, INDEX); SPY, QQQ, IWM, DIA → ETF; no fundamentals → INDEX; cached.
- **Conditional required fields** — EQUITY: price, volume, iv_rank, bid, ask, quote_date. ETF/INDEX: price, volume, iv_rank, quote_date only; bid, ask, open_interest optional.
- **Derived field promotion** — mid_price, synthetic_bid_ask; derivable → treated as present; provenance ORATS | DERIVED | CACHED.
- **DATA_CONTRACT.md** — Instrument-specific liquidity table, derivable fields section, truth statement: *DATA_INCOMPLETE only when ORATS data missing AND field non-derivable for that instrument type.*
- **Diagnostics** — `field_sources` on Stage1Result, FullEvaluationResult, evaluation JSON, and `*_data_completeness.json`.

See [DATA_CONTRACT.md](./DATA_CONTRACT.md) and [PHASE8E_VALIDATION_REPORT.md](./PHASE8E_VALIDATION_REPORT.md) for full detail.

---

## 6. Remaining Improvements (Deferred)

Items we discussed but are **not** implementing in the current refactor. Each has acceptance criteria and estimated risk for when they are scheduled.

| # | Item | Acceptance criteria | Estimated risk |
|---|------|---------------------|----------------|
| **D1** | **Data freshness rules (quote_date staleness thresholds)** | (1) Single definition of “stale” (e.g. quote_date older than N trading days). (2) Thresholds documented in DATA_CONTRACT (e.g. &gt; 1 trading day → WARN). (3) All consumers (evaluator, API, UI) use the same staleness logic; no per-screen thresholds. (4) Staleness surfaced in evaluation JSON and diagnostics. | **Medium** — Staleness today is ad-hoc or missing; wrong thresholds could over-block or under-warn. |
| **D2** | **Better fallback logic for missing fields** | (1) Documented fallback order (e.g. ORATS → derived → cached → default). (2) Fallbacks implemented in one place (e.g. contract_validator or a dedicated fallback module). (3) No silent substitution of critical required fields (price, quote_date) without explicit override. (4) Fallback path logged and visible in field_sources/diagnostics. | **Medium** — Over-aggressive fallbacks can hide data issues; under-use leaves avoidable DATA_INCOMPLETE. |
| **D3** | **Evaluation gating improvements (separate “data health” vs “strategy score”)** | (1) Clear separation: “data health” gate (required fields, completeness, staleness) vs “strategy score” (regime, IV, liquidity, selection). (2) API and UI can show both: e.g. “Data: PASS / Strategy score: 72”. (3) Blocking rules: data health FAIL blocks strategy eligibility; strategy score only ranks. (4) No single blended score that conflates data quality with strategy quality. | **Medium** — Reduces confusion when a symbol is blocked for data vs strategy; avoids “score” hiding data problems. |
| **D4** | **Consistent diagnostics surfaced in UI (field_sources, required_missing, instrument_type)** | (1) Every evaluation view that shows a symbol exposes: field_sources (ORATS \| DERIVED \| CACHED), required_missing (list), instrument_type (EQUITY \| ETF \| INDEX). (2) Same fields come from backend evaluation JSON; UI does not recompute. (3) Diagnostics panel or tooltip available on all relevant screens (dashboard, premium, live decision). | **Low** — Improves debuggability and trust; risk is mainly UI consistency and copy. |
| **D5** | **Regression suite expansion + nightly smoke test gating** | (1) Regression suite covers: Stage 1 with full/missing/derived snapshot, ETF vs EQUITY required fields, verdict resolution (FATAL / INTRADAY / NONE), and contract_validator behavior. (2) Nightly (or pre-release) run: smoke test that hits ORATS (or fixture) and asserts no regression in verdict/completeness for a small symbol set. (3) Failing smoke blocks release or is clearly flagged. (4) Tests documented in a TESTING or RUNBOOK doc. | **Medium** — Prevents silent regressions; risk is flakiness if smoke depends on live ORATS. |
| **D6** | **Remove legacy screens or legacy endpoints that bypass core services** | (1) Audit: list every UI screen and API endpoint that fetches ORATS, computes missing_fields, or applies required-field logic outside core (orats_client + contract_validator + staged_evaluator). (2) Each such path either removed or refactored to use core services. (3) Lint/guard: no direct ORATS or duplicate validation from UI (already in place); extend to “no endpoint that bypasses evaluation API for symbol-level data”. (4) Deprecation notice and migration path for any removed screen/endpoint. | **Medium** — Reduces drift and duplicate bugs; risk is breaking existing callers if migration is incomplete. |
| **D7** | **Documentation updates: DATA_CONTRACT.md in sync + “How to debug ORATS unknown” runbook** | (1) **DATA_CONTRACT sync:** A check (test or script) ensures runtime required-field sets and instrument rules match DATA_CONTRACT.md; run in CI or pre-commit; doc updated when contract code changes. (2) **Runbook:** A single runbook “How to debug ORATS unknown” (or similar): when evaluation shows UNKNOWN or DATA_INCOMPLETE, step-by-step (check quote_date, required_missing, field_sources, ORATS health, endpoint used). Link from DATA_CONTRACT and THESIS. | **Low** — Reduces drift and speeds up debugging; risk is doc getting stale if process not followed. |

---

## Document history

| Date | Change |
|------|--------|
| 2025-02-09 | Initial THESIS.md: backlog + tech debt ledger; Architecture Rules; seeded from DATA_CONTRACT and PHASE8E_VALIDATION_REPORT. |
| 2025-02-09 | ORATS v2 consistency audit: added `app/core/orats/endpoints.py` manifest; all clients import from it; runtime log line (endpoint, symbol, http_status, quote_date, field presence); deprecated `app/data/orats_client`; Critical Fixes C2 marked done. |
| 2025-02-09 | Added §6 Remaining Improvements (Deferred): D1–D7 (data freshness, fallback logic, evaluation gating, UI diagnostics, regression/smoke, legacy removal, DATA_CONTRACT sync + ORATS debug runbook) with acceptance criteria and estimated risk. Documentation only; no code changes. |
