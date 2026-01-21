# Position Object Structure

## Overview

The ChakraOps repository uses **Python dataclasses** (not Pydantic, not plain dicts) for the Position model.

## Position Class Definition

**Location**: `app/core/models/position.py`

**Type**: `@dataclass(slots=True)` - Python dataclass with slots optimization

## Fields

```python
@dataclass(slots=True)
class Position:
    id: str                                    # UUID string
    symbol: str                                # Ticker symbol (e.g., "AAPL")
    position_type: PositionType                # Literal["CSP", "SHARES"]
    strike: Optional[float]                    # Option strike price (None for SHARES)
    expiry: Optional[str]                      # ISO date YYYY-MM-DD (None for SHARES)
    contracts: int                             # Number of contracts/shares
    premium_collected: float                   # Total premium collected
    entry_date: str                            # ISO datetime string
    status: PositionStatus = "OPEN"            # Deprecated: Literal["OPEN", "ASSIGNED", "CLOSED"]
    state: Optional[str] = None                 # PositionState enum value as string
    state_history: List[Any] = field(default_factory=list)  # List of transition event dicts
    notes: Optional[str] = None                # Optional notes
```

## Type Definitions

```python
PositionType = Literal["CSP", "SHARES"]
PositionStatus = Literal["OPEN", "ASSIGNED", "CLOSED"]  # Deprecated
```

## State Values

The `state` field stores PositionState enum values as strings:
- `"NEW"`
- `"OPEN"`
- `"HOLD"`
- `"ROLL_CANDIDATE"`
- `"ROLLING"`
- `"CLOSED"`
- `"ASSIGNED"`

## State History Structure

`state_history` is a list of dictionaries, each representing a state transition:

```python
{
    'from_state': str,      # Previous state
    'to_state': str,        # New state
    'reason': str,          # Human-readable reason
    'source': str,          # Source of transition (e.g., "system", "user", "risk_engine")
    'timestamp_iso': str,   # ISO datetime string
}
```

## Factory Methods

### Position.create_csp()
Creates a CSP position with:
- `state="NEW"` (initial state)
- `state_history=[]` (empty history)
- `status="OPEN"` (for backward compatibility)

### Position.create_shares()
Creates a shares position with:
- `state="NEW"` (initial state)
- `state_history=[]` (empty history)
- `status="OPEN"` (for backward compatibility)

## Migration Behavior

The `__post_init__` method automatically migrates old `status` values to `state`:
- `"OPEN"` → `"OPEN"`
- `"ASSIGNED"` → `"ASSIGNED"`
- `"CLOSED"` → `"CLOSED"`

## Serialization

- **Database**: Stored in SQLite with `state` and `state_history` (JSON) columns
- **JSON**: Can be serialized using `dataclasses.asdict()` or custom serialization
- **State History**: Stored as JSON string in database, parsed back to list of dicts

## Example Usage

```python
from app.core.models.position import Position

# Create position
position = Position.create_csp(
    symbol="AAPL",
    strike=150.0,
    expiry="2026-03-21",
    contracts=1,
    premium_collected=300.0,
)

# Access fields
print(position.state)  # "NEW"
print(position.state_history)  # []

# State transitions update both state and state_history
from app.core.state_machine.position_state_machine import transition_position, PositionState

position = transition_position(
    position,
    PositionState.OPEN,
    "Position opened",
    source="system"
)
# position.state is now "OPEN"
# position.state_history contains one transition event
```
