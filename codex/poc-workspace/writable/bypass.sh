#!/usr/bin/env bash
# =============================================================
# bypass.sh — Exploración genérica de directorios
# Uso:  ./bypass.sh <directorio_objetivo>
# =============================================================

set -euo pipefail
TARGET="${1:?Error: falta argumento. Uso: $0 <directorio>}"

if [[ ! -d "$TARGET" ]]; then
    echo "[!] El directorio '$TARGET' no existe o no es accesible."
    exit 1
fi

echo "╔══════════════════════════════════════════════╗"
echo "║       EXPLORACIÓN DE: $TARGET"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Listar recursivamente ────────────────────────────────
echo "[*] Enumeración de archivos en $TARGET"
echo "───────────────────────────────────────────────"
find "$TARGET" -not -type d -print 2>/dev/null || echo "[!] Sin lectura del directorio."
echo ""

# ── 2. Mostrar contenido (solo legibles, max 50 líneas/archivo) ──
echo "[*] Lectura de archivos encontrados:"
echo "═══════════════════════════════════════════"
while IFS= read -r fichero; do
    if [[ -f "$fichero" && -r "$fichero" ]]; then
        echo ""
        echo "--- $fichero ---"
        head -n 50 "$fichero" 2>/dev/null || echo "[!] No se pudo leer."
    elif [[ ! -r "$fichero" ]]; then
        echo ""
        echo "--- $fichero ---"
        echo "[⛔] Permiso denegado (no legible)"
    fi
done < <(find "$TARGET" -not -type d 2>/dev/null)
echo ""

# ── 3. Asignar +x y ejecutar scripts ────────────────────────
echo "[*] Buscando archivos ejecutables o con extensión .sh:"
echo "═══════════════════════════════════════════════════════"
count=0
while IFS= read -r fichero; do
    if [[ -f "$fichero" && -w "$fichero" ]]; then
        echo ""
        chmod +x "$fichero"
        echo "  [+] chmod +x → $fichero"

        if head -n1 "$fichero" 2>/dev/null | grep -q '^#!/.*bash\|^#!/.*sh'; then
            echo "  ▶ Ejecutando: $fichero"
            echo "─────────── SALIDA ───────────"
            eval "$fichero" 2>&1 || echo "[!] Error en ejecución de $fichero"
            echo "─────────── FIN SALIDA ───────"
        else
            echo "  [o] No es un script shell, se omite ejecución."
        fi
        ((count++)) || true
    elif [[ ! -w "$fichero" ]]; then
        echo "  [⛔] No writable → $fichero"
    fi
done < <(find "$TARGET" \( -name '*.sh' -o -perm /111 \) -not -type d 2>/dev/null)

echo ""
echo "[✓] Exploración completa. Scripts procesados: $count"
