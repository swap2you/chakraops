#!/usr/bin/env python3
"""
ChakraOps - Main entry point
"""

import os
import sys
from pathlib import Path

# Try to load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Try to load config.yaml
config = None
config_path = Path("config.yaml")
example_path = Path("config.yaml.example")

if config_path.exists():
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except ImportError:
        print("Warning: pyyaml not installed. Cannot load config.yaml", file=sys.stderr)
    except Exception as e:
        print(f"Error loading config.yaml: {e}", file=sys.stderr)
        sys.exit(1)
elif example_path.exists():
    print("Info: config.yaml not found. Using config.yaml.example as reference only.", file=sys.stderr)

def main():
    """Main entry point"""
    print("ChakraOps boot OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
