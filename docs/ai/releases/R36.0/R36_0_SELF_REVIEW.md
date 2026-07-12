# R36.0 Design Self-Review (B6)

Three independent review lenses over the design pack. Document defects were resolved in-place; owner-policy choices are NOT invented (left in Decision Log).

## A. Architecture review
- Over-engineering: AVOIDED. R36 reuses existing seams (decision_engine, universe stores, data_reliability, observability) rather than new subsystems. Universe V2 = state + policy layer over existing gates/stores. PASS.
- Inconsistent rule definitions: ADDRESSED via DQR-3 rule template + single reason-code registry (§28). Threshold duplication (G9) explicitly consolidated in R36.5 with parity gate. PASS.
- Duplicated UI/backend decision logic: ADDRESSED — one explainability builder (§30); UI consumes backend contract, does not re-decide. PASS.
- Data fields unavailable from ORATS: CHECKED — trust/calc-trace use fields already sourced (delta/IV/OI/spread/earnings); macro events kept honest as NO_PROVIDER_CONFIGURED (no invented data). PASS.
- Poor rejection-code stability: ADDRESSED — registry seeded from existing literals + back-compat shim (RR-4). PASS.

## B. Investment-strategy review
- Dangerous aggressive-mode assumptions: BLOCKED by DQR-4 (safeguards immutable; compensation mandatory). PASS.
- Optimizing only for win rate: BLOCKED by §49 metric suite. PASS.
- Survivorship / look-ahead bias, unrealistic fills: ADDRESSED §46–48 (walk-forward, out-of-sample, conservative slippage, realistic assignment). PASS.
- Assignment-risk blindness: ADDRESSED — assignment affordability in admission (§9,§18) + stress simulator reuse. PASS.
- Portfolio concentration risk: ADDRESSED — profile caps + guardrails consolidation (§27). PASS.
- Excessive universe breadth: ADDRESSED — admission gates + tiered cadence retained; breadth is policy (D-4/D-10). PASS.
- Inability to backtest: ADDRESSED — every threshold change is `[PENDING-BACKTEST]`; harness reuses existing engines (§42–43). PASS.

## C. Adversarial review
- Hidden broker-write exposure: NONE. §35–38 read-only design + hard write-denylist + enforced test (R36.6); default OFF; broker code absent today. PASS.
- Weak explainability: ADDRESSED — single per-recommendation contract + near-miss + calc trace + no FAIL_/WARN_ leakage. PASS.
- Insufficient owner-decision clarity: ADDRESSED — 11 explicit owner decisions (D-1..D-11) + checklist; no invented policy. PASS.
- Inability to enforce safety: ADDRESSED — manifest assertions + owner checklist; scheduler/manual-only/ORATS invariants restated. PASS.
- Evidence manipulation / unbacktested numbers slipping in: BLOCKED — zero `[APPROVED]` values; DQR-1/DQR-2 enforced; manifest `approved_threshold_count=0`. PASS.

## Residual (owner-policy, intentionally unresolved)
D-1..D-11 remain open by design. No document defects outstanding.

## Verdict
Design pack is internally consistent, backtest-gated, safety-preserving, and honest about gaps. Ready for owner review. No implementation authorized.
