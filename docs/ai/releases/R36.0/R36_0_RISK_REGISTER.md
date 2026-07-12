# R36.0 Risk Register (Design Phase)

Severity: L/M/H. Status: OPEN unless noted. All mitigations are design-level (no code in this mission).

| ID | Risk | Sev | Likelihood | Mitigation | Owner |
|----|------|-----|-----------|------------|-------|
| RR-1 | Threshold consolidation (4 config files, G9) changes behavior unexpectedly | H | M | Consolidate behind `strategy_profiles.yaml`; golden-vector + backtest parity gate before any change; `[PENDING-BACKTEST]` | Eng+Strategy |
| RR-2 | Aggressive mode interpreted as "fewer safeguards" | H | M | DQR-4 contract; safeguards immutable; compensation params required | Strategy |
| RR-3 | Anecdotal one-week tuning of thresholds | H | M | DQR-1; promotion gate needs aggregated evidence + backtest | Strategy |
| RR-4 | Reason-code unification breaks existing UI mappings | M | M | Seed registry from existing literals + `REASON_CODES.md`; back-compat shim + tests | Eng |
| RR-5 | Near-miss wiring floods UI / auto-promotes | M | M | Near-miss never actionable; epsilon-bounded; explainable only | Eng+Product |
| RR-6 | Universe V2 quarantine over-restricts (false safety-critical) | M | M | severity_class mapping owner-approved (D-4); WATCH default for ambiguous | Strategy |
| RR-7 | Robinhood read-only scope creep into writes | H | L | Hard write-denylist, code-enforced + tested; default OFF; owner gate (D-6) | Eng+Owner |
| RR-8 | Backtest look-ahead / survivorship / unrealistic fills | H | M | Walk-forward + out-of-sample + conservative slippage + assignment modeling (§46–48) | Strategy |
| RR-9 | Optimizing only for win rate | M | M | §49 metric suite; win rate never sole objective | Strategy |
| RR-10 | Macro event calendar stays a stub → false "all clear" | M | H | Keep honest `NO_PROVIDER_CONFIGURED`; do not fake events | Eng |
| RR-11 | Three scoring stacks cause divergent numbers (trust erosion) | M | H | Canonicalize on `decision_engine`; deprecate others behind flags | Eng |
| RR-12 | Explainability/observability modules untested (G13) | M | H | Add tests as part of unification | Eng |
| RR-13 | ORATS rate limits during Universe V2 admission scans | M | M | Reuse rate limiter/backoff; batch; no persistent cache but bounded fan-out | Eng |
| RR-14 | Scope bleed into implementation before approval | H | L | Design-only mission; no authorization commit; owner checklist gate | All |
| RR-15 | Portfolio accuracy gaps (no live broker balances) mislead sizing | M | M | Trust/staleness on manual snapshots; optional read-only design (§35) | Eng |
