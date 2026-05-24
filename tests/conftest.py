"""Ensure repo root is importable when pytest collects from tests/."""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
_root_str = str(_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)
