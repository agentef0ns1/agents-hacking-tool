#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi

# Normalizar (quitar CR de .env en Windows y espacios)
MODEL="$(printf '%s' "${OLLAMA_MODEL:-qwen3.6:27b}" | tr -d '\r' | xargs)"
BASE_URL="$(printf '%s' "${OLLAMA_BASE_URL:-http://192.168.1.43:11434}" | tr -d '\r' | xargs)"
PROFILE="${CODEX_PROFILE:-ollama-launch}"
LAB_CONFIG="$ROOT/config/config.lab.toml"
PROJECT_CONFIG="$ROOT/.codex/config.toml"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Error: ollama no está instalado" >&2
  exit 1
fi

echo "==> Instalando Codex CLI local (npm)..."
if [[ ! -x "$ROOT/node_modules/.bin/codex" ]]; then
  npm install --no-fund --no-audit
fi

mkdir -p "$ROOT/bin" "$ROOT/.codex"
ln -sfn "../node_modules/.bin/codex" "$ROOT/bin/codex"
export PATH="$ROOT/bin:$PATH"

echo "==> Codex: $(codex --version)"

echo "==> Comprobando modelo Ollama: $MODEL"
if ollama show "$MODEL" >/dev/null 2>&1; then
  echo "    Modelo encontrado."
else
  echo "Aviso: el modelo '$MODEL' no está disponible en Ollama." >&2
  echo "       Descárguelo con: ollama pull $MODEL" >&2
fi

echo "==> Generando perfil Ollama (~/.codex/ollama-launch.config.toml)..."
python3 "$ROOT/scripts/generate-codex-profile.py" "$MODEL" "$BASE_URL" "$ROOT"

echo "==> Sincronizando config de laboratorio → .codex/config.toml"
if [[ ! -f "$LAB_CONFIG" ]]; then
  echo "Error: no existe $LAB_CONFIG" >&2
  exit 1
fi

# Copiar config lab sustituyendo el modelo por el de .env
sed "s|^model = .*|model = \"${MODEL}\"|" "$LAB_CONFIG" > "$PROJECT_CONFIG"

echo "==> Preparando workspace PoC (si no existe)..."
"$ROOT/scripts/prepare-workspace.sh"

echo
echo "Setup completado."
echo
echo "Archivos generados/actualizados:"
echo "  ~/.codex/ollama-launch.config.toml   (perfil Ollama + trust del proyecto)"
echo "  ~/.codex/model.json                  (catálogo del modelo)"
echo "  $PROJECT_CONFIG                      (sandbox, skills, permisos lab)"
echo
echo "Para lanzar:"
echo "  ./scripts/launch-ollama.sh"
