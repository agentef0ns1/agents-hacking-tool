#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi

MODEL="$(printf '%s' "${OLLAMA_MODEL:-phi4-mini:latest}" | tr -d '\r' | xargs)"
BASE_URL="$(printf '%s' "${OLLAMA_BASE_URL:-http://127.0.0.1:11434}" | tr -d '\r' | xargs)"
LAB_CONFIG="$ROOT/config/config.lab.toml"
PROJECT_CONFIG="$ROOT/.codex/config.toml"

echo "==> Instalando Codex CLI local (npm)..."
if [[ ! -x "$ROOT/node_modules/.bin/codex" ]]; then
  npm install --no-fund --no-audit
fi

mkdir -p "$ROOT/bin" "$ROOT/.codex"
ln -sfn "../node_modules/.bin/codex" "$ROOT/bin/codex"
export PATH="$ROOT/bin:$PATH"

echo "==> Codex: $(codex --version)"

echo "==> Generando perfil Ollama remoto (~/.codex/ollama-launch.config.toml)..."
echo "    base_url: $BASE_URL"
python3 "$ROOT/scripts/generate-codex-profile.py" "$MODEL" "$BASE_URL" "$ROOT"

echo "==> Sincronizando config de laboratorio → .codex/config.toml"
if [[ ! -f "$LAB_CONFIG" ]]; then
  echo "Error: no existe $LAB_CONFIG" >&2
  exit 1
fi

sed "s|^model = .*|model = \"${MODEL}\"|" "$LAB_CONFIG" > "$PROJECT_CONFIG"

echo "==> Preparando workspace PoC..."
"$ROOT/scripts/prepare-workspace.sh"

echo
echo "Setup Docker completado."
echo "  Ollama remoto : $BASE_URL"
echo "  Modelo        : $MODEL"
echo "  Perfil        : ~/.codex/ollama-launch.config.toml"
echo "  Config lab    : $PROJECT_CONFIG"
