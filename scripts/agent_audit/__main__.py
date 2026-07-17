"""Punto de entrada: python3 -m agent_audit."""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from agent_audit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
