# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Utility functions for type conversion and serialization."""

from __future__ import annotations

from typing import Any


def to_native(value: Any) -> Any:
    """Convert numpy/pandas types to native Python types for JSON serialization.
    
    This function handles common numpy and pandas types that are not directly
    JSON serializable, such as:
    - np.bool_ -> bool
    - np.int64, np.int32 -> int
    - np.float64, np.float32 -> float
    - pandas Timestamp -> str (ISO format)
    - numpy arrays -> list
    
    Parameters
    ----------
    value:
        Value to convert (can be any type).
    
    Returns
    -------
    Any
        Native Python type that is JSON serializable.
    """
    # Handle numpy scalar types
    try:
        import numpy as np
        
        if isinstance(value, (np.bool_, bool)):
            return bool(value)
        elif isinstance(value, (np.integer, int)):
            return int(value)
        elif isinstance(value, (np.floating, float)):
            return float(value)
        elif isinstance(value, np.ndarray):
            return value.tolist()
    except ImportError:
        pass  # numpy not available
    
    # Handle pandas Timestamp
    try:
        import pandas as pd
        
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
    except ImportError:
        pass  # pandas not available
    
    # Return as-is if no conversion needed
    return value


def safe_json(obj: Any) -> Any:
    """Recursively convert numpy/pandas types in nested structures to native Python types.
    
    This function traverses dictionaries and lists recursively, converting all
    numpy/pandas types to native Python types that are JSON serializable.
    
    This is necessary because pandas DataFrames and numpy arrays often contain
    types like np.int64, np.float64, np.bool_, and pandas Timestamp objects that
    cannot be directly serialized to JSON. This function ensures all such types
    are converted before calling json.dumps().
    
    Parameters
    ----------
    obj:
        Object to convert (dict, list, or any other type).
    
    Returns
    -------
    Any
        Object with all numpy/pandas types converted to native Python types.
    
    Examples
    --------
    >>> safe_json({"value": np.int64(42), "flag": np.bool_(True)})
    {"value": 42, "flag": True}
    
    >>> safe_json([np.float64(3.14), {"nested": np.int32(10)}])
    [3.14, {"nested": 10}]
    """
    if isinstance(obj, dict):
        return {key: safe_json(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [safe_json(item) for item in obj]
    else:
        return to_native(obj)


__all__ = ["safe_json", "to_native"]
