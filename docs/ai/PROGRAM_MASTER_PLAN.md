# ChakraOps Five-Release Recovery and Product Program

## Program objective

Move ChakraOps from a strong but difficult-to-operate baseline into a reliable daily decision-support product within five major releases.

The releases are deliberately broad enough to produce meaningful outcomes, but each release has strict internal workstreams, gates, review rules, and stop points.

## Release map

| Release | Outcome | Risk |
|---|---|---|
| R31.0 | Full repository, product, live-data, and defect baseline | Level 2 |
| R32.0 | ORATS, earnings/events, universe refresh, freshness, and data reliability | Level 4 |
| R33.0 | Decision engine, strategy profiles, ranking, sizing, and calculation correctness | Level 4 |
| R34.0 | Dashboard/UI consolidation, backtest, database retention, and reporting | Level 3 |
| R35.0 | Scheduling, notifications, UAT, runbooks, and operational readiness | Level 3 |

## Program dependencies

- R31.0 produces the approved defect register and execution blueprint.
- R32.0 must stabilize data before strategy logic is trusted.
- R33.0 must stabilize decisions before UI/backtest claims are trusted.
- R34.0 presents and retains trusted information.
- R35.0 makes the product usable as an ongoing operating system.

## Program non-goals

- No automatic broker orders.
- No unattended execution.
- No margin expansion logic.
- No read-write brokerage integration.
- No broad technology rewrite without audit evidence.
- No provider fallback that can silently substitute for ORATS.
- No production deployment before R35.0 acceptance.

## Completion definition

The five-release program is complete when:

- ORATS and derived data are observable, fresh, and failure-classified.
- Earnings/event risk is available or explicitly unavailable with a visible reason.
- Universe refresh is deterministic and auditable.
- CSP, CC, share-buy, cash, ranking, and position sizing are validated.
- Conservative, Balanced, Aggressive, and Custom profiles are configurable.
- The operator can use one consolidated product flow.
- Backtest and reports distinguish simulation from live/manual decisions.
- Scheduled jobs and notifications are observable and recoverable.
- Full regression gates and UAT pass.
- Manual-only trading safety remains intact.
