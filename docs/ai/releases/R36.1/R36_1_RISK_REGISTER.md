# R36.1 Risk Register

| ID | Risk | Sev | Mitigation |
|----|------|-----|------------|
| R61-1 | Explainability layer accidentally changes a decision | H | Gate/strategy/engine emission NOT modified; explanation is a pure function over existing outputs; full backend suite as regression guard; compatibility tests assert unchanged item keys |
| R61-2 | Near-miss converts a rejection into a recommendation or bypasses a safety gate | H | Near-miss is descriptive only, never mutates status; returns not-near-miss when status=BLOCKED or any safety-critical reason present; boundary tests |
| R61-3 | Raw FAIL_/WARN_ codes leak into UI text | M | Registry returns human titles; unknown codes map to safe OTHER; frontend renders titles, not raw codes; test asserts no FAIL_/WARN_ in explanation text |
| R61-4 | Invented/misleading measured values | M | Only recompute from present fields (selected_contract/profile/data_freshness); None when unavailable; unit + comparator required; never fabricate |
| R61-5 | API item shape regression breaks existing consumers | M | Additive optional `explanation` key only; no whitelist removal; API contract test asserts legacy keys still present |
| R61-6 | Frontend type/render regression | L | Optional field; ExplanationPanel guards on missing explanation; component test + build |
| R61-7 | Scope creep into thresholds/universe/broker | H | Exact authorized-path manifest; forbidden list; docs-only authorization commit first |
| R61-8 | Registry drifts from real emitted codes | M | Registry seeded from verified emission audit; test enumerates known codes and asserts resolvable + classified |
