"""Pytest configuration."""

import sys
from pathlib import Path

# Add parent directory to path to allow importing the main module
sys.path.insert(0, str(Path(__file__).parent.parent))
