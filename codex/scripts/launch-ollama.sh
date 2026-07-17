#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi

MODEL="$(printf '%s' "${OLLAMA_MODEL:-qwen2.5:latest}" | tr -d '\r' | xargs)"
PROFILE="${CODEX_PROFILE:-ollama-launch}"
PROFILE_FILE="$HOME/.codex/ollama-launch.config.toml"
PROJECT_CONFIG="$ROOT/.codex/config.toml"

if [[ ! -x "$ROOT/node_modules/.bin/codex" ]]; then
  echo "Codex no instalado localmente. Ejecute primero: ./scripts/setup-ollama.sh" >&2
  exit 1
fi

mkdir -p "$ROOT/bin"
ln -sfn "../node_modules/.bin/codex" "$ROOT/bin/codex"
export PATH="$ROOT/bin:$PATH"

if [[ ! -f "$PROFILE_FILE" ]]; then
  echo "Perfil no encontrado. Ejecute: ./scripts/setup-ollama.sh" >&2
  exit 1
fi

if [[ ! -f "$PROJECT_CONFIG" ]]; then
  echo "Config de proyecto no encontrada. Ejecute: ./scripts/setup-ollama.sh" >&2
  exit 1
fi

profile_model="$MODEL"
if grep -q '^model = ' "$PROFILE_FILE"; then
  profile_model="$(grep '^model = ' "$PROFILE_FILE" | head -1 | sed 's/^model = "\(.*\)"/\1/')"
  if [[ "$profile_model" != "$MODEL" ]]; then
    echo "Aviso: OLLAMA_MODEL en .env ($MODEL) ≠ perfil ($profile_model)." >&2
    echo "       Ejecute ./scripts/setup-ollama.sh para regenerar sin perder config lab." >&2
  fi
fi

echo "Lanzando Codex + Ollama"
echo "  modelo : $profile_model"
echo "  perfil : $PROFILE → $PROFILE_FILE"
echo "  config : $PROJECT_CONFIG"
echo "  codex  : $(command -v codex)"
echo
echo "Nota: no se usa 'ollama launch' aquí para no sobrescribir el perfil."
echo

# Usar el perfil generado por setup; ollama launch lo regeneraría y borraría customizaciones.
exec codex --profile "$PROFILE"
