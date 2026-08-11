# C_BATCH_CLOSURE — Notifications / Health

## Baseline SHA
54cbfb378096be922a2f4d4ea318f0db35d0a749

## Findings closed
- F-004 HIGH — stop ORATS notify-on-read; durable dedupe retained; recovery flap no longer floods JOB_* 
- F-005 HIGH — recovery_reconciliation excludes self job_id; no self RECOVERED→FAILED flap
- F-009 MEDIUM — ORATS age escalates past WARN to ERROR after ORATS_ERROR_MINUTES (default 1d); provider vs effective clocks exposed

## Paths
- app/core/operations/jobs/recovery_job.py
- app/core/operations/job_run_store.py
- app/api/data_health.py
- app/api/notifications_store.py
- tests/test_r70_abcd_batch_c_notify_health.py

## Safety
manual_only · trade_execution=false · no broker writes
