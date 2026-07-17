#!/usr/bin/env bash
set -euo pipefail

LAB_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${1:-/home/f0ns1/Documentos/MASTER/Tools/Agent-lab}"

mkdir -p "$DEST"

rsync -a --delete \
  --exclude node_modules \
  --exclude bin \
  --exclude .env \
  --exclude '*.audit-bak-*' \
  "$LAB_SRC/scripts/" "$DEST/scripts/"

rsync -a --delete \
  --exclude node_modules \
  --exclude bin \
  --exclude .env \
  --exclude '*.audit-bak-*' \
  "$LAB_SRC/codex/" "$DEST/codex/"

chmod +x "$DEST/codex/scripts/"*.sh "$DEST/codex/docker/entrypoint.sh" 2>/dev/null || true
chmod +x "$DEST/scripts/agent-audit-cli.py" 2>/dev/null || true

echo "Agent-lab sincronizado en: $DEST"
echo "  $DEST/codex/     — PoC + Dockerfile"
echo "  $DEST/scripts/   — auditoría agéntica"
