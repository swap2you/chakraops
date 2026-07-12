# R36.0 Owner-Approval Checklist

Before ANY R36 implementation begins, the owner confirms:

## Policy decisions (from Decision Log)
- [ ] D-1 Canonical scoring stack = decision_engine? (recommend YES)
- [ ] D-2 Threshold single source = strategy_profiles.yaml? (recommend YES)
- [ ] D-3 Regime-neutral shares: keep False? (recommend YES until backtest)
- [ ] D-4 Approve Watch/Quarantine severity_class mapping table
- [ ] D-5 Set aggressive-mode compensation parameter ranges
- [ ] D-6 Robinhood read-only: design-only now / never (recommend design-only, default OFF)
- [ ] D-7 Observation-week duration + promotion N (recommend ≥1wk, N=5)
- [ ] D-8 CSP-vs-share arbitration inputs (weights PENDING-BACKTEST)
- [ ] D-9 Slack contract pruning policy
- [ ] D-10 Universe removal window (recommend 4wk)
- [ ] D-11 Trust factor: annotation-only first?

## Scope & sequencing
- [ ] Approve release sequencing (R36.1 → R36.6)
- [ ] Confirm which sub-releases are in-scope for the first implementation authorization
- [ ] Confirm exact authorized paths per sub-release (from Proposed Paths, finalized)

## Safety confirmations (must remain true)
- [ ] Advisory-only; manual_only=true; trade_execution=false
- [ ] No broker write / order routing (Robinhood read-only design does not change this)
- [ ] CHAKRAOPS_SCHEDULER_ENABLED=false; legacy schedulers off; recurring jobs off
- [ ] ORATS remains sole provider; no silent fallback
- [ ] No threshold change ships without backtest + out-of-sample + this checklist
- [ ] Never commit .env / frontend/.env.development / prompt library

## Governance
- [ ] R36 gets its own release branch(es); PR + owner-approved merge; tag after merge
- [ ] Evidence recorded under out/verification/R36.x/
- [ ] Independent architecture + adversarial + investment-strategy review per sub-release

Owner sign-off: ______________________   Date: ____________
