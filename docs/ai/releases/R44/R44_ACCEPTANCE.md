# R44 Acceptance

## IDs
| ID | Status |
|----|--------|
| CSP collateral = strike x 100 x contracts | PASS |
| Premium dollars = premium x 100 x contracts | PASS |
| CSP/CC breakeven math | PASS |
| CC requires 100 shares per contract | PASS |
| Zero cash stays zero (≠ total capital / BP) | PASS |
| Portfolio UI: cash vs total capital vs buying power | PASS |
| Wheel lifecycle labels remain manual-only | PASS |

## Tests
- `chakraops/tests/test_r44_finance_invariants.py`
- `chakraops/tests/test_r380_manual_plan.py`
- `chakraops/tests/test_r401_wheel_cash.py`
- `chakraops/tests/test_r330_sizing_invariants.py`
- `frontend/src/pages/PortfolioPage.test.tsx`
- `frontend/src/pages/WheelPage.test.tsx`
