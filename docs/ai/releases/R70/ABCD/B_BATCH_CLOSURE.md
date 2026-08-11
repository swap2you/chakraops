# B_BATCH_CLOSURE — Evaluation Safety

## Baseline SHA
cf21ada0ac149d4330f94b493cfb11912072b7e5 (post Batch A)

## Findings closed
- F-002 HIGH — market gate owned by exclusive coordinator; ops/ui refuse when closed unless allow_when_closed
- F-003 HIGH — orphan RUNNING → ABANDONED via STALE_RUN_TIMEOUT; startup sweep; coordinator save_failed_run on exception

## Root cause
Market gate lived on UI route only; ops evaluate aliases bypassed it. RUNNING stubs survived lock clear after crash; save_failed_run hardcoded source=scheduled.

## Paths
- app/core/eval/eval_coordinator.py
- app/core/eval/evaluation_store.py
- app/api/server.py
- app/api/ui_routes.py
- tests/test_r70_abcd_batch_b_eval_safety.py
- tests/test_r401_eval_concurrency.py

## Runtime
Abandoned Cowork orphan eval_20260811_175910_b68c5da5 → ABANDONED/STALE_RUN_TIMEOUT.

## Safety
manual_only · trade_execution=false · no broker writes
