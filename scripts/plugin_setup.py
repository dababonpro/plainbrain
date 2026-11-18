"""Compatibility shim; implementation lives in plainbrain.plugin_setup."""
import importlib
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_mod = importlib.import_module("plainbrain.plugin_setup")
if __name__ == "__main__":
    raise SystemExit(_mod.main())
sys.modules[__name__] = _mod
