#!/usr/bin/env python3
"""Run ChakraOps pipeline once."""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import and run main
from main import main

if __name__ == "__main__":
    sys.exit(main())
