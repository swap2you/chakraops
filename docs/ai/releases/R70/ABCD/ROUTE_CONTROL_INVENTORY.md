# R70-ABCD Route / Control Inventory

Generated as part of Batch D cleanup. Classifications are for safe local UAT.

| Route / control | Status | Notes |
|---|---|---|
| `/` Command Center | PASS | Live count from broker lenses |
| `/portfolio` + tabs | PASS | Distinct tab content |
| `/positions` → holdings | PASS_WITH_NOTE | Redirect lands on holdings tab |
| Run Evaluation | PASS | Server market gate |
| Symbol Diagnostics | PASS_WITH_NOTE | Deep-dive cards covered by route smoke; market-closed data may DATA_BLOCK |
| Opportunities / Stocks / Options / ETF-Hedge | PASS_WITH_NOTE | Workspace smoke via existing Playwright pack |
| Strategy Builder / Lab / Paper | PASS_WITH_NOTE | Smoke only |
| Copilot ask | PASS_WITH_NOTE | Grounding tests; live model requires key |
| System / Notifications | PASS | Scheduler vs monitor labeled |
| Auth production-like | PASS | Session/CSRF tests; local mode remains disabled |
| Broker write tools | PASS | Denylist; never invoked |

No unexplained NOT_EXECUTED for normal safe controls in this remediation pass.
