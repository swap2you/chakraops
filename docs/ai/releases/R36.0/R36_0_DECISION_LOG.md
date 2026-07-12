# R36.0 Decision Log — Owner Decisions Required

These are policy choices the design deliberately does NOT invent. Each needs an explicit owner answer before the related implementation is authorized. (DQR: do not resolve owner-policy by inventing an answer.)

| ID | Decision | Options | Design recommendation | Blocks |
|----|----------|---------|----------------------|--------|
| D-1 | Canonical scoring stack | (a) decision_engine only; (b) keep scoring/* diagnostics; (c) keep legacy ranking | (a) canonical decision_engine; demote others to diagnostic/deprecated | Explainability unification, RR-11 |
| D-2 | Threshold consolidation approach | (a) single YAML source; (b) keep per-module | (a) `strategy_profiles.yaml` single source, others derive | RR-1, Wheel V2 |
| D-3 | Regime-neutral share eligibility | keep False `[INHERITED]` / allow True `[HYPOTHESIS]` | Keep False until backtested | Share V2 |
| D-4 | Watch vs Quarantine severity mapping | per-reason-code TEMPORARY/SAFETY_CRITICAL table | Approve mapping table (design draft provided) | Universe V2 §8–13 |
| D-5 | Aggressive-mode compensation parameters | sizing/allocation/concentration multipliers | Owner sets ranges; `[PENDING-BACKTEST]` | Profiles §25–27 |
| D-6 | Robinhood read-only adapter | build design→later / never | Design only now; default OFF; separate future release | §35–38, RR-7 |
| D-7 | Observation-week duration & promotion N | 1wk surface only; N recurrences to promote | ≥1 week observation; N=5 `[HYPOTHESIS]`; promotion needs backtest | Observation model |
| D-8 | CSP-vs-share arbitration inputs/weights | EV/trust/capital-efficiency weighting | Explainable comparison; weights `[PENDING-BACKTEST]` | §22 |
| D-9 | Slack contract pruning | keep all / prune noisy | Prune per observation usefulness | §39 |
| D-10 | Universe removal window | weeks in quarantine before REMOVED | 4 weeks `[HYPOTHESIS]` | §11 |
| D-11 | Trust factor in scoring | annotation-only vs weighted | Annotation-only first; weighting `[PENDING-BACKTEST]` | §15 |
