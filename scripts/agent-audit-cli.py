#!/usr/bin/env python3
"""Lanzador de la CLI de auditoría de agentes."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from agent_audit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
