# R46 Acceptance

## IDs
| ID | Status |
|----|--------|
| System Diagnostics: scheduler master false | PASS |
| System Diagnostics: legacy schedulers false | PASS |
| Slack CODE_READY vs UNCONFIGURED | PASS |
| Copilot UNCONFIGURED when no key | PASS |
| Notifications persistence regression | PASS |
| Manual-only / scheduler off by default | PASS |

## Tests
- `frontend/src/pages/SystemDiagnosticsPage.operations.test.tsx`
- `chakraops/tests/test_r46_notifications_persist.py`
- `chakraops/tests/test_r283_notifications_safe_labels.py`
- `chakraops/tests/test_r350_notification_atomic_incidents.py`
