# R36.0 — Observation-Week Evidence Model

Purpose: Define a **structured, testable** observation model so that the operator's real usage during an observation week produces evidence that can validate or reject R36 design hypotheses. This is the empirical input that gates any future threshold change. No thresholds are tuned from anecdote (see Design Quality Rules).

## 1. Principles
- Every manual disagreement records a **testable reason**, never "I like this stock."
- Observations are **append-only** and **timestamped**; no back-editing.
- Each observation is classified with exactly one **primary category** (taxonomy below) and optional secondary tags.
- Numbers observed are evidence, not thresholds. Threshold changes require aggregated multi-week evidence + backtest (see `R36_0_DESIGN_PACK.md` §Design Quality Rules).

## 2. Observation dimensions (what to capture daily)
| Dimension | Field | Type | Notes |
|-----------|-------|------|-------|
| ORATS freshness | `orats_freshness` | FRESH/STALE/MISSING + age_seconds | from `data_reliability/freshness.py` |
| Universe membership | `universe_size`, `universe_delta` | int | added/removed since last obs |
| Candidate counts | `candidates_total`, `candidates_by_strategy` | int/map | CSP/CC/SHARE |
| Actionable recs | `actionable_count` | int | status ACTIONABLE |
| Blocked recs | `blocked_count`, `blocked_by_reason` | int/map | reason_code histogram |
| Stay-in-Cash | `stay_in_cash` | bool + reason | valid outcome |
| Rejection frequency | `rejection_histogram` | map | reason_code -> count |
| Near misses | `near_miss_count`, `near_miss_detail` | int/list | which single rule failed |
| Manual false negative | `mfn` | list | system rejected, operator would take (with testable reason) |
| Manual false positive | `mfp` | list | system suggested, operator would skip (with testable reason) |
| CSP vs share preference | `csp_vs_share_pref` | enum + reason | per candidate where both viable |
| Earnings effects | `earnings_blocked`, `earnings_near` | int/list | blackout hits |
| Liquidity | `liquidity_rejects` | int | OI/volume/spread |
| Assignment affordability | `assignment_afford` | OK/TIGHT/FAIL | from stress simulator |
| Portfolio concentration | `concentration_flags` | list | symbol/sector caps hit |
| Calculation discrepancies | `calc_discrepancies` | list | observed value vs expected (with source) |
| Slack usefulness | `slack_useful` | 1-5 + note | signal-to-noise |
| UI redundancy | `ui_redundant` | list | duplicated/confusing surfaces |
| Trust gaps | `trust_gaps` | list | places the operator distrusts a number |
| Operational defects | `ops_defects` | list | crashes/timeouts/slow-universe |

## 3. Manual-disagreement testable-reason contract
Each `mfn`/`mfp`/`csp_vs_share_pref` entry MUST include:
- `symbol`, `strategy`, `system_decision`, `operator_decision`
- `reason_category` (taxonomy)
- `testable_claim` — a falsifiable statement (e.g., "delta 0.28 is acceptable for balanced on this liquidity tier" — testable against profile + backtest), NOT a preference
- `evidence_pointer` — the metric/source that would confirm/deny (e.g., ORATS delta, IV rank, spread%)
- `proposed_rule_impact` — which rule/threshold it would affect, if validated

Entries without a `testable_claim` + `evidence_pointer` are recorded as `RESEARCH_REQUIRED`, not as a design input.

## 4. Classification taxonomy (primary category)
| Code | Meaning | Typical owner |
|------|---------|---------------|
| `DEFECT` | Software bug / wrong behavior | Engineering |
| `DATA_RELIABILITY` | ORATS freshness/missing/provider | Engineering + Data |
| `CALCULATION_TRACE` | Value computed differently than expected | Engineering |
| `UNIVERSE_POLICY` | Admission/removal/watch/quarantine policy | Product/Strategy |
| `WHEEL_POLICY` | CSP/CC eligibility/management rule | Strategy |
| `SHARE_POLICY` | Share-buy rule | Strategy |
| `PORTFOLIO_ACCURACY` | Position/valuation/concentration accuracy | Engineering |
| `NOTIFICATION` | Slack/in-app usefulness/noise | Product |
| `UX_INFORMATION_ARCHITECTURE` | Navigation/redundancy/clarity | Product/UX |
| `OPERATIONAL` | Startup/scheduler/timeout/slow-universe | Engineering/Ops |
| `RESEARCH_REQUIRED` | No testable claim yet; needs study/backtest | Strategy/Research |

## 5. Aggregation & promotion rules
- A single week of observations can **surface hypotheses**, never **set production thresholds**.
- A hypothesis is promoted to a design change only when: (a) recurring across ≥ N observations (N is a `design hypothesis`, proposed 5), AND (b) supported by backtest/out-of-sample evidence, AND (c) categorized as a policy (not `RESEARCH_REQUIRED`).
- `DEFECT`/`DATA_RELIABILITY`/`CALCULATION_TRACE`/`OPERATIONAL` findings are triaged immediately (bug track), independent of the strategy-design promotion gate.

## 6. Machine-readable schema
See `docs/ai/validation/R36_0_OBSERVATION_SCHEMA.json` for the canonical JSON schema draft that a future observation-capture tool (or manual log) must conform to.
