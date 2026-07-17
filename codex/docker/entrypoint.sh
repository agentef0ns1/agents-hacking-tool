#!/usr/bin/env bash
set -euo pipefail

LAB_ROOT="${LAB_ROOT:-/opt/lab}"
CODEX_ROOT="${CODEX_ROOT:-$LAB_ROOT/codex}"

cd "$CODEX_ROOT"

if [[ ! -x "$CODEX_ROOT/node_modules/.bin/codex" ]] || [[ ! -f "$HOME/.codex/ollama-launch.config.toml" ]]; then
  echo "==> Ejecutando setup inicial..."
  "$CODEX_ROOT/scripts/setup-docker.sh"
fi

export PATH="$CODEX_ROOT/bin:$PATH"

if [[ $# -eq 0 ]]; then
  exec "$CODEX_ROOT/scripts/launch-ollama.sh"
fi

exec "$@"
