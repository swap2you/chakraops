# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Data quality model for tracking field completeness.

This module provides a shared vocabulary for distinguishing:
- VALID: Field present and contains a valid value
- MISSING: Field not provided by the data source (NOT the same as 0)
- ERROR: Field fetch failed with an error

Usage:
    from app.core.models.data_quality import DataQuality, FieldValue, wrap_field

    # Wrap a potentially missing field
    price = wrap_field(orats_data.get("stockPrice"), "stockPrice")
    
    # Check quality
    if price.quality == DataQuality.MISSING:
        # Handle missing data explicitly
        pass
    elif price.quality == DataQuality.VALID:
        # Safe to use price.value
        pass
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


class DataQuality(str, Enum):
    """
    Data quality status for a field.
    
    VALID: Field was fetched and contains a valid value (including 0).
    MISSING: Field was not provided by the data source. Do NOT treat as 0.
    ERROR: Field fetch failed with an error.
    """
    VALID = "VALID"
    MISSING = "MISSING"
    ERROR = "ERROR"
    
    def __str__(self) -> str:
        return self.value


@dataclass
class FieldValue(Generic[T]):
    """
    Wrapper for a field value with quality metadata.
    
    Attributes:
        value: The actual value (None if MISSING or ERROR)
        quality: DataQuality status
        reason: Human-readable explanation (especially for MISSING/ERROR)
        field_name: Name of the field (for debugging)
    """
    value: Optional[T]
    quality: DataQuality
    reason: str = ""
    field_name: str = ""
    
    @property
    def is_valid(self) -> bool:
        """True if the field has a valid value."""
        return self.quality == DataQuality.VALID
    
    @property
    def is_missing(self) -> bool:
        """True if the field was not provided by the source."""
        return self.quality == DataQuality.MISSING
    
    @property
    def is_error(self) -> bool:
        """True if the field fetch failed."""
        return self.quality == DataQuality.ERROR
    
    def value_or(self, default: T) -> T:
        """Return value if VALID, otherwise return default."""
        if self.quality == DataQuality.VALID and self.value is not None:
            return self.value
        return default
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API serialization."""
        return {
            "value": self.value,
            "quality": str(self.quality),
            "reason": self.reason,
            "field_name": self.field_name,
        }


def wrap_field(
    raw_value: Any,
    field_name: str,
    *,
    coerce_to: type | None = None,
    allow_zero: bool = True,
) -> FieldValue:
    """
    Wrap a raw value with quality metadata.
    
    Args:
        raw_value: The raw value from the data source
        field_name: Name of the field (for debugging)
        coerce_to: Optional type to coerce to (float, int, str)
        allow_zero: If False, treat 0 as MISSING (default True)
    
    Returns:
        FieldValue with appropriate quality status
    
    Examples:
        >>> wrap_field(None, "bid")
        FieldValue(value=None, quality=MISSING, ...)
        
        >>> wrap_field(150.25, "price", coerce_to=float)
        FieldValue(value=150.25, quality=VALID, ...)
        
        >>> wrap_field(0, "volume", allow_zero=False)
        FieldValue(value=None, quality=MISSING, ...)
    """
    # None is always MISSING
    if raw_value is None:
        return FieldValue(
            value=None,
            quality=DataQuality.MISSING,
            reason=f"{field_name} not provided by source",
            field_name=field_name,
        )
    
    # Try to coerce if requested
    if coerce_to is not None:
        try:
            coerced = coerce_to(raw_value)
            # Check zero handling
            if not allow_zero and coerced == 0:
                return FieldValue(
                    value=None,
                    quality=DataQuality.MISSING,
                    reason=f"{field_name} is zero (treated as missing)",
                    field_name=field_name,
                )
            return FieldValue(
                value=coerced,
                quality=DataQuality.VALID,
                reason="",
                field_name=field_name,
            )
        except (ValueError, TypeError) as e:
            return FieldValue(
                value=None,
                quality=DataQuality.ERROR,
                reason=f"{field_name} coercion failed: {e}",
                field_name=field_name,
            )
    
    # No coercion, just wrap
    if not allow_zero and raw_value == 0:
        return FieldValue(
            value=None,
            quality=DataQuality.MISSING,
            reason=f"{field_name} is zero (treated as missing)",
            field_name=field_name,
        )
    
    return FieldValue(
        value=raw_value,
        quality=DataQuality.VALID,
        reason="",
        field_name=field_name,
    )


def wrap_field_float(raw_value: Any, field_name: str, allow_zero: bool = True) -> FieldValue[float]:
    """Convenience wrapper for float fields."""
    return wrap_field(raw_value, field_name, coerce_to=float, allow_zero=allow_zero)


def wrap_field_int(raw_value: Any, field_name: str, allow_zero: bool = True) -> FieldValue[int]:
    """Convenience wrapper for int fields."""
    return wrap_field(raw_value, field_name, coerce_to=int, allow_zero=allow_zero)


# Reason codes for data incompleteness
class ReasonCode:
    """Standard reason codes for data issues."""
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    DATA_STALE = "DATA_STALE"
    DATA_ERROR = "DATA_ERROR"
    FIELD_MISSING = "FIELD_MISSING"
    COERCION_FAILED = "COERCION_FAILED"


def compute_data_completeness(fields: dict[str, FieldValue]) -> tuple[float, list[str]]:
    """
    Compute data completeness percentage and list missing fields.
    
    Args:
        fields: Dict of field_name -> FieldValue
    
    Returns:
        Tuple of (completeness_pct, missing_field_names)
    
    Example:
        >>> fields = {"price": wrap_field(100.0, "price"), "bid": wrap_field(None, "bid")}
        >>> compute_data_completeness(fields)
        (0.5, ["bid"])
    """
    if not fields:
        return 1.0, []
    
    valid_count = sum(1 for f in fields.values() if f.quality == DataQuality.VALID)
    missing_names = [name for name, f in fields.items() if f.quality != DataQuality.VALID]
    
    completeness = valid_count / len(fields)
    return completeness, missing_names


def build_data_incomplete_reason(missing_fields: list[str]) -> str:
    """
    Build a human-readable reason for data incompleteness.
    
    Args:
        missing_fields: List of field names that are missing
    
    Returns:
        Human-readable reason string
    """
    if not missing_fields:
        return ""
    
    if len(missing_fields) == 1:
        return f"DATA_INCOMPLETE - {missing_fields[0]} not provided by source"
    
    if len(missing_fields) <= 3:
        return f"DATA_INCOMPLETE - missing: {', '.join(missing_fields)}"
    
    return f"DATA_INCOMPLETE - {len(missing_fields)} fields missing ({', '.join(missing_fields[:3])}, ...)"


__all__ = [
    "DataQuality",
    "FieldValue",
    "ReasonCode",
    "wrap_field",
    "wrap_field_float",
    "wrap_field_int",
    "compute_data_completeness",
    "build_data_incomplete_reason",
]
