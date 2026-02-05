#!/usr/bin/env python3
"""Inspect snapshot price data structure for heartbeat regime computation."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.market_snapshot import (
    get_latest_snapshot_id,
    get_snapshot_prices,
    normalize_symbol,
    load_snapshot_data,
)

def inspect_snapshot_prices():
    """Inspect snapshot price data structure."""
    print("=" * 80)
    print("Snapshot Price Data Inspection")
    print("=" * 80)
    
    # Get latest snapshot ID
    latest_id = get_latest_snapshot_id()
    print(f"\nLatest snapshot_id: {latest_id}")
    
    if not latest_id:
        print("\n⚠️  No snapshot found!")
        return
    
    # Get snapshot prices
    prices = get_snapshot_prices(latest_id)
    print(f"\nSnapshot prices structure:")
    print(f"  Type: {type(prices)}")
    print(f"  Total symbols: {len(prices)}")
    print(f"  Keys (normalized symbols): {sorted(list(prices.keys()))}")
    
    # Show sample entries
    print(f"\nSample entries (first 5):")
    for i, (sym, data) in enumerate(list(prices.items())[:5], 1):
        print(f"  {i}. {sym}:")
        print(f"     Type: {type(data)}")
        if isinstance(data, dict):
            for key, val in data.items():
                print(f"       {key}: {val} (type: {type(val).__name__})")
        else:
            print(f"     Value: {data}")
    
    # Check for benchmark symbols
    print(f"\nBenchmark symbol search:")
    benchmark_candidates = ["SPY", "QQQ", "SPX"]
    for bench in benchmark_candidates:
        norm = normalize_symbol(bench)
        found = norm in prices
        status = "FOUND" if found else "NOT FOUND"
        print(f"  {bench} -> {norm}: {status}")
        if found:
            bench_data = prices[norm]
            print(f"    Data: {bench_data}")
            if isinstance(bench_data, dict):
                price = bench_data.get("price")
                if price is not None and price > 0:
                    print(f"    [OK] Valid price: {price}")
                else:
                    print(f"    [INVALID] Price: {price}")
    
    # Inspect raw snapshot data structure
    print(f"\n" + "=" * 80)
    print("Raw snapshot data structure (from load_snapshot_data)")
    print("=" * 80)
    raw_data = load_snapshot_data(latest_id)
    print(f"  Type: {type(raw_data)}")
    print(f"  Total symbols: {len(raw_data)}")
    print(f"  Keys: {sorted(list(raw_data.keys()))}")
    
    # Check if benchmark symbols exist in raw data
    print(f"\nBenchmark symbols in raw snapshot data:")
    for bench in benchmark_candidates:
        norm = normalize_symbol(bench)
        found = norm in raw_data
        status = "FOUND" if found else "NOT FOUND"
        print(f"  {bench} -> {norm}: {status}")
        if found:
            bench_df = raw_data[norm]
            print(f"    DataFrame: {bench_df}")
            if bench_df is not None:
                print(f"    DataFrame shape: {bench_df.shape}")
                print(f"    DataFrame empty: {bench_df.empty}")
                print(f"    Columns: {list(bench_df.columns)}")
                if not bench_df.empty:
                    print(f"    Last row (latest data):")
                    last_row = bench_df.iloc[-1]
                    for col in bench_df.columns:
                        print(f"      {col}: {last_row[col]}")
            else:
                print(f"    DataFrame is None")

if __name__ == "__main__":
    inspect_snapshot_prices()
