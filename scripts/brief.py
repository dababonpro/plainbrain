"""Compatibility shim; implementation lives in plainbrain.brief."""
import importlib
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

sys.modules[__name__] = importlib.import_module("plainbrain.brief")
