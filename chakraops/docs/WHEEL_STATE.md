# Wheel Page and Wheel State Repair

## What the Wheel page does

- **Route**: Wheel page (e.g. `/wheel`).
- **Data**: Uses `GET /api/ui/wheel/overview` to load:
  - **Wheel state** per symbol: from `wheel_state.json` (state: EMPTY | OPEN | ASSIGNED, linked_position_ids, last_updated_utc).
  - **Next action** per symbol: from `compute_next_action` (action_type, suggested_contract_key, reasons, blocked_by) using latest decision artifact and open positions.
  - **Risk status**, last decision score, links (e.g. run_id to Symbol Diagnostics), and open position summary.
- **Display**: Table/cards per symbol showing state, next action, risk, and links to Symbol Diagnostics and trade ticket. If the overview returns no symbols, the UI shows “no wheel symbols” (e.g. when wheel state is empty and no open positions or manual actions have been repaired yet).

---

## What “Repair wheel state” does

- **Endpoint**: `POST /api/ui/wheel/repair`.
- **Behavior**: Rebuilds `wheel_state.json` from:
  1. **Open positions** (primary): For each symbol with at least one open (or partial-exit) position, sets state = OPEN and `linked_position_ids` = list of position IDs for that symbol. This includes **equity-only** positions (no contract_key/option_symbol); they still have symbol and status OPEN.
  2. **Wheel actions** (secondary): For symbols with no open position but with recent ASSIGNED/UNASSIGNED/RESET in the wheel actions store, sets state from the last action (ASSIGNED or removes from state for UNASSIGNED/RESET).
- **Result**: Returns `repaired_symbols`, `removed_symbols`, `status: "OK"`. No separate “equity” path; equity positions are just open positions and get OPEN state like any other.

---

## When to use it

- After restoring or fixing the positions store so that open positions are correct but wheel_state.json is out of sync.
- When the Wheel page shows “no wheel symbols” but you have open positions (e.g. CSP or equity) that should appear.
- After manual edits to positions or wheel_state.json, to realign state with current open positions and recent manual wheel actions.

---

## What it changes

- **On disk**: Overwrites `wheel_state.json` (via atomic save) with the rebuilt state. Backup is not automatic; ensure positions and wheel actions are correct before repairing.
- **Wheel page**: After repair, the overview will include symbols that have open positions or a recent ASSIGNED state from actions. Equity-only positions will show as OPEN for that symbol.
- **Mark refresh**: Mark refresh skips positions without contract_key/option_symbol (e.g. equity) and does **not** add them to the error list, so refresh succeeds and wheel repair is not blocked by equity positions.

---

## Equity positions

- **Mark refresh**: Equity positions (no contract_key/option_symbol) are skipped for mark updates; they do not cause refresh to fail or append to `errors`.
- **Wheel repair**: Repair does not require contract_key. Any open position with a symbol and status OPEN or PARTIAL_EXIT is counted; the symbol gets state OPEN and its position_id(s) in `linked_position_ids`. So portfolio with e.g. NVDA equity holdings will have NVDA in wheel state as OPEN after repair.
