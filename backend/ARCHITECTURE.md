# ChakraOps Architecture Documentation

## 1. Explicit State Transition Table

### Position States

| State | Description | Terminal? |
|-------|-------------|-----------|
| `NEW` | Position created but not yet opened | No |
| `OPEN` | Position is active and being managed | No |
| `HOLD` | Position is being held (no immediate action) | No |
| `ROLL_CANDIDATE` | Position identified as candidate for rolling | No |
| `ROLLING` | Position is in the process of being rolled | No |
| `CLOSED` | Position has been closed (terminal) | Yes |
| `ASSIGNED` | Position was assigned (shares received) | Yes |

### Allowed State Transitions

| From State | Allowed To States | Notes |
|------------|-------------------|-------|
| `NEW` | `OPEN`, `CLOSED` | Can open or close immediately |
| `OPEN` | `HOLD`, `ROLL_CANDIDATE`, `CLOSED`, `ASSIGNED` | Can hold, mark for roll, close, or get assigned |
| `HOLD` | `ROLL_CANDIDATE`, `CLOSED`, `ASSIGNED` | Can transition to roll candidate, close, or assignment |
| `ROLL_CANDIDATE` | `ROLLING`, `HOLD`, `CLOSED` | Can proceed to rolling, revert to hold, or close |
| `ROLLING` | `OPEN`, `HOLD`, `CLOSED`, `ASSIGNED` | After roll, becomes new OPEN position or other terminal states |
| `ASSIGNED` | `HOLD`, `CLOSED` | After assignment, can hold shares or close |
| `CLOSED` | *(none)* | Terminal state - no transitions allowed |

### Transition Matrix (Visual)

```
        NEW
        / \
    OPEN   CLOSED (terminal)
    / | \ \
HOLD ROLL_CANDIDATE CLOSED ASSIGNED
|   |              |      |
|   |              |      |
|   ROLLING        |      |
|   / | \ \        |      |
OPEN HOLD CLOSED ASSIGNED |
|   |              |      |
... ...            ...    ...
```

### State Transition Rules

1. **Terminal States**: `CLOSED` and `ASSIGNED` cannot transition to any other state
2. **One-Way Transitions**: Once `CLOSED`, position cannot be reopened
3. **Roll Flow**: `OPEN` → `ROLL_CANDIDATE` → `ROLLING` → `OPEN` (creates new position)
4. **Assignment Flow**: `OPEN` → `ASSIGNED` → `HOLD` (holding shares) or `CLOSED`

---

## 2. Action Resolution Function

### Function Signature

```python
def decide_position_action(
    position: Position,
    market_ctx: Dict[str, Any],
) -> ActionDecision:
    """
    Decide what action to take on a position based on its state and market context.
    
    Returns ActionDecision with:
    - action: ActionType (HOLD, CLOSE, ROLL, ALERT)
    - urgency: Urgency (LOW, MEDIUM, HIGH)
    - reasons: List[str]
    - next_steps: List[str]
    - roll_plan: Optional[RollPlan] (if action == ROLL)
    """
```

### Decision Tree (Priority Order)

```
decide_position_action(position, market_ctx):
    
    // Rule 0: Terminal States (Highest Priority)
    IF position.state IN {CLOSED, ASSIGNED}:
        RETURN ActionDecision(
            action: HOLD,
            urgency: LOW,
            reasons: ["Position not actionable"],
            next_steps: ["No action required"]
        )
    
    // Risk Override 1: RISK_OFF Regime
    IF market_ctx.regime == "RISK_OFF":
        IF RISK_OFF_CLOSE_ENABLED AND position.state == "OPEN":
            RETURN ActionDecision(
                action: CLOSE,
                urgency: HIGH,
                reasons: ["RISK_OFF regime detected - automatic close enabled"],
                next_steps: ["Close position immediately", "Reduce portfolio exposure"]
            )
        ELSE:
            RETURN ActionDecision(
                action: ALERT,
                urgency: HIGH,
                reasons: ["RISK_OFF regime detected"],
                next_steps: ["Reduce exposure / tighten rolls", "Monitor market conditions"]
            )
    
    // Risk Override 2: Panic Drawdown
    entry_price = market_ctx.get("entry_underlying_price")
    current_price = market_ctx.get("underlying_price")
    IF entry_price IS NOT NULL AND current_price IS NOT NULL:
        drawdown_pct = (entry_price - current_price) / entry_price
        IF drawdown_pct >= PANIC_DRAWDOWN_PCT (default: 0.10 = 10%):
            RETURN ActionDecision(
                action: ALERT,
                urgency: HIGH,
                reasons: [f"Panic drawdown threshold hit ({drawdown_pct*100:.1f}%)"],
                next_steps: ["Consider defensive roll", "Review portfolio exposure"]
            )
    
    // Risk Override 3: EMA200 Break
    ema200 = market_ctx.get("ema200")
    current_price = market_ctx.get("underlying_price")
    IF ema200 IS NOT NULL AND current_price IS NOT NULL:
        ema200_break_threshold = ema200 * (1 - EMA200_BREAK_PCT)  // default: 0.02 = 2%
        IF current_price < ema200_break_threshold:
            RETURN ActionDecision(
                action: ALERT,
                urgency: HIGH,
                reasons: [f"EMA200 break detected (price < {ema200_break_threshold:.2f})"],
                next_steps: ["Review position risk", "Consider defensive actions"]
            )
    
    // Rule 1: DTE Check
    dte = calculate_dte(position.expiry)
    IF dte IS NOT NULL AND dte <= 7:
        roll_plan = build_roll_plan(position, market_ctx)
        RETURN ActionDecision(
            action: ROLL,
            urgency: HIGH,
            reasons: ["Expiry within 7 days"],
            next_steps: ["Consider rolling to new strike/expiry"],
            roll_plan: roll_plan
        )
    
    // Rule 2: Premium Capture Check
    premium_capture_pct = market_ctx.get("premium_collected_pct")
    IF premium_capture_pct IS NULL:
        premium_capture_pct = calculate_premium_pct(position)
    
    IF premium_capture_pct >= 65.0:  // 65% threshold
        RETURN ActionDecision(
            action: CLOSE,
            urgency: MEDIUM,
            reasons: [f"Premium >= 65% captured ({premium_capture_pct:.1f}%)"],
            next_steps: ["Consider closing position to lock in profit"]
        )
    
    // Rule 3: Default
    RETURN ActionDecision(
        action: HOLD,
        urgency: LOW,
        reasons: ["No action required at this time"],
        next_steps: ["Continue monitoring position"]
    )
```

### Roll Plan Generation

```python
def build_roll_plan(position: Position, market_ctx: Dict[str, Any]) -> RollPlan:
    """
    Build roll plan when action == ROLL.
    
    Rules:
    - suggested_expiry: today + 35 days (capped within 30-45 days window)
    - roll_type: "defensive" if underlying_price < position.strike, else "out"
    - suggested_strike:
        * defensive: max(underlying_price * 0.90, underlying_price - 2*ATR_proxy)
        * out: underlying_price * 0.95
    - ATR_proxy: market_ctx.get("atr_pct", 0.03) * underlying_price
    """
    underlying_price = market_ctx.get("underlying_price", position.strike or 0)
    atr_pct = market_ctx.get("atr_pct", 0.03)
    atr_proxy = underlying_price * atr_pct
    
    # Calculate suggested expiry (30-45 days window)
    suggested_expiry = date.today() + timedelta(days=35)
    # Ensure within bounds
    min_expiry = date.today() + timedelta(days=30)
    max_expiry = date.today() + timedelta(days=45)
    suggested_expiry = max(min_expiry, min(suggested_expiry, max_expiry))
    
    # Determine roll type
    if underlying_price < position.strike:
        roll_type = "defensive"
        suggested_strike = max(
            underlying_price * 0.90,
            underlying_price - 2 * atr_proxy
        )
    else:
        roll_type = "out"
        suggested_strike = underlying_price * 0.95
    
    # Round strike to nearest $0.50
    suggested_strike = round(suggested_strike * 2) / 2
    
    return RollPlan(
        roll_type=roll_type,
        suggested_expiry=suggested_expiry,
        suggested_strike=suggested_strike,
        notes=[f"Roll type: {roll_type}"]
    )
```

### Action Type Definitions

| Action | Urgency | When Triggered | Next Steps |
|--------|---------|----------------|------------|
| `HOLD` | LOW | Default state, no action needed | Continue monitoring |
| `CLOSE` | MEDIUM | Premium >= 65% captured | Close position to lock profit |
| `CLOSE` | HIGH | RISK_OFF with auto-close enabled | Close immediately |
| `ROLL` | HIGH | DTE <= 7 days | Roll to new strike/expiry |
| `ALERT` | HIGH | RISK_OFF regime, panic drawdown, EMA200 break | Review risk, consider defensive actions |

---

## 3. Capital Constraint Logic

### Configuration Constants

```python
# From app/core/config/trade_rules.py

CSP_MIN_DTE: int = 30          # Minimum days to expiration
CSP_MAX_DTE: int = 45          # Maximum days to expiration
CSP_TARGET_DELTA_LOW: float = 0.25   # Lower bound delta (25%)
CSP_TARGET_DELTA_HIGH: float = 0.35   # Upper bound delta (35%)
MAX_CAPITAL_PER_SYMBOL_PCT: float = 0.15  # Max 15% per symbol
```

### Capital Calculation Logic

```python
def generate_trade_plan(candidate, portfolio_value, regime):
    """
    Generate CSP trade plan with capital constraints.
    
    Steps:
    1. Validate regime == "RISK_ON"
    2. Check no existing open position for symbol
    3. Extract contract details (strike, expiry, premium_estimate)
    4. Calculate capital required per contract = strike * 100
    5. Calculate max capital for symbol = portfolio_value * MAX_CAPITAL_PER_SYMBOL_PCT
    6. Calculate max contracts = floor(max_capital / capital_per_contract)
    7. Ensure contracts >= 1, else return None
    """
    
    # Step 1: Regime check
    IF regime != "RISK_ON":
        RETURN None
    
    # Step 2: Existing position check
    IF position_engine.has_open_position(symbol):
        RETURN None
    
    # Step 3: Extract contract
    strike = candidate.contract.strike
    expiry = candidate.contract.expiry
    premium_estimate = candidate.contract.premium_estimate
    
    # Step 4: Calculate capital per contract
    capital_per_contract = strike * 100  # CSP requires strike * 100 per contract
    
    # Step 5: Calculate max capital for this symbol
    max_capital_for_symbol = portfolio_value * MAX_CAPITAL_PER_SYMBOL_PCT
    
    # Step 6: Calculate max contracts
    max_contracts = floor(max_capital_for_symbol / capital_per_contract)
    
    # Step 7: Validate
    IF max_contracts < 1:
        RETURN None  # Not enough capital
    
    contracts = max_contracts  # Use maximum allowed
    
    # Calculate total capital required
    capital_required = contracts * capital_per_contract
    
    # Calculate estimated premium
    estimated_premium = contracts * premium_estimate if premium_estimate else 0
    
    RETURN {
        "symbol": symbol,
        "strike": strike,
        "expiry": expiry,
        "contracts": contracts,
        "capital_required": capital_required,
        "estimated_premium": estimated_premium,
        "rationale": [...]
    }
```

### Capital Constraint Examples

**Example 1: Portfolio = $100,000**
- Max capital per symbol: $100,000 × 0.15 = $15,000
- Strike = $150 → Capital per contract = $15,000
- Max contracts = floor($15,000 / $15,000) = 1 contract
- Capital required = $15,000

**Example 2: Portfolio = $200,000, Strike = $100**
- Max capital per symbol: $200,000 × 0.15 = $30,000
- Capital per contract = $100 × 100 = $10,000
- Max contracts = floor($30,000 / $10,000) = 3 contracts
- Capital required = $30,000

**Example 3: Portfolio = $50,000, Strike = $200**
- Max capital per symbol: $50,000 × 0.15 = $7,500
- Capital per contract = $200 × 100 = $20,000
- Max contracts = floor($7,500 / $20,000) = 0 contracts
- Result: Trade blocked (insufficient capital)

### Position Sizing Rules

1. **One Position Per Symbol**: Only one open CSP position allowed per symbol
2. **Capital Limit**: Maximum 15% of portfolio per symbol
3. **Minimum Contracts**: Must be able to afford at least 1 contract
4. **Regime Requirement**: Only generate trades in RISK_ON regime

---

## 4. Slack Payload Schema for ACTION Events

### Base Slack Webhook Payload

```json
{
  "text": "[LEVEL] message content"
}
```

Where `LEVEL` is one of: `INFO`, `WATCH`, `URGENT`

### ACTION REQUIRED - CSP Trade Plan

**Channel**: `#chakra-daily-plan`  
**Level**: `URGENT`

**Payload Example**:
```json
{
  "text": "[URGENT] [ACTION REQUIRED] SELL CSP\nSymbol: AAPL\nStrike: 150\nExpiry: 2026-02-21 (31 DTE)\nContracts: 1\nCapital Required: $15,000\nRationale:\n- Delta ~0.28\n- Uptrend above EMA200\n- Pullback near EMA50"
}
```

**Schema**:
```
[URGENT] [ACTION REQUIRED] SELL CSP
Symbol: {symbol}
Strike: {strike}
Expiry: {expiry} ({dte} DTE)
Contracts: {contracts}
Capital Required: ${capital_required:,.0f}
Rationale:
- {rationale_item_1}
- {rationale_item_2}
...
```

### ACTION REQUIRED - Position Alert

**Channel**: `#chakra-alerts-urgent`  
**Level**: `URGENT`

**Payload Example**:
```json
{
  "text": "[URGENT] [ACTION REQUIRED]\nSymbol: AAPL\nPosition: CSP 150 exp 2026-02-21\nStatus: ACTION_REQUIRED\nReasons:\n- Premium captured 78%\n- Price below EMA200\n\nSuggested next step:\n- Roll forward or accept assignment"
}
```

**Schema**:
```
[URGENT] [ACTION REQUIRED]
Symbol: {symbol}
Position: {position_type} {strike} exp {expiry}
Status: {status}
Reasons:
- {reason_1}
- {reason_2}
...

Suggested next step:
- {next_step_1}
```

### ROLL SUGGESTION

**Channel**: `#chakra-alerts-urgent`  
**Level**: `URGENT`

**Payload Example**:
```json
{
  "text": "[URGENT] [ROLL SUGGESTION]\nSymbol: AAPL\nCurrent: CSP 150 exp 2026-02-21\nSuggested: CSP 155 exp 2026-03-21\nNet Credit: +$45.00\nReasons:\n- Regime RISK_ON\n- Strike above EMA50\n- Expiry within 7 days"
}
```

**Schema**:
```
[URGENT] [ROLL SUGGESTION]
Symbol: {symbol}
Current: {position_type} {current_strike} exp {current_expiry}
Suggested: {position_type} {suggested_strike} exp {suggested_expiry}
Net Credit: {net_credit_str}
Reasons:
- {reason_1}
- {reason_2}
...
```

### Daily Plan Message

**Channel**: `#chakra-daily-plan`  
**Level**: `INFO`

**Payload Example**:
```json
{
  "text": "*ChakraOps Daily Plan*\n\n*Market Regime:* RISK_ON (Confidence: 85%)\n\n🔥 *Action Alerts*\n\n*AAPL* | OPEN | ROLL | HIGH | Expiry within 7 days\n   → Roll: 155 @ 2026-03-21 (defensive)\n\n📌 *Open Positions Decisions*\n\nAAPL | OPEN | ROLL | HIGH | Expiry within 7 days\n   → Roll: 155 @ 2026-03-21 (defensive)\nMSFT | OPEN | HOLD | LOW | No action required at this time\n\n*Top CSP Candidates:*\n1. *NVDA* (Score: 90/100)\n   • Uptrend above EMA200\n   • Pullback near EMA50"
}
```

**Schema**:
```
*ChakraOps Daily Plan*

*Market Regime:* {regime} (Confidence: {confidence}%)

🔥 *Action Alerts*
{high_urgency_items}

📌 *Open Positions Decisions*
{all_position_decisions}

*Top CSP Candidates:*
{top_5_candidates}
```

### Action Alert Format (High Urgency)

**Format**:
```
*{symbol}* | {state} | {action} | {urgency} | {key_reason}
   → Roll: {strike} @ {expiry} ({roll_type})  [if action == ROLL]
```

### Position Decision Format

**Format**:
```
{symbol} | {state} | {action} | {urgency} | {key_reason}
   → Roll: {strike} @ {expiry} ({roll_type})  [if action == ROLL]
```

### Message Level Mapping

| Action | Urgency | Slack Level | Channel |
|--------|---------|-------------|---------|
| HOLD | LOW | INFO | `#chakra-daily-plan` |
| CLOSE | MEDIUM | INFO | `#chakra-daily-plan` |
| CLOSE | HIGH | URGENT | `#chakra-alerts-urgent` |
| ROLL | HIGH | URGENT | `#chakra-alerts-urgent` |
| ALERT | HIGH | URGENT | `#chakra-alerts-urgent` |

### Alert Deduplication

Before sending, check `AlertDedupeEngine.should_notify()`:
- If fingerprint unchanged and urgency != HIGH → suppress
- If urgency == HIGH and fingerprint unchanged:
  - Notify only if `last_sent_at` older than 60 minutes (cooldown)
- Record notification after successful send

---

## Summary

This architecture document provides:

1. **State Transition Table**: Complete mapping of allowed position state transitions
2. **Action Resolution Function**: Detailed decision tree with priority ordering
3. **Capital Constraint Logic**: Position sizing rules and examples
4. **Slack Payload Schema**: Complete message formats for all ACTION events

All implementations follow these specifications exactly.
