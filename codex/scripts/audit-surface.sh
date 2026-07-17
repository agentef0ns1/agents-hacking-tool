#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB_ROOT="$(cd "$ROOT/.." && pwd)"

python3 "$LAB_ROOT/scripts/agent-audit-cli.py" codex --workspace "$ROOT" --no-interactive "$@"
