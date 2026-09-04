#!/usr/bin/env bash
# Impronte SHA-256 dei binari di una release.
#
# L'installer Windows riceve il suo .sha256 dal workflow (build-windows.yml);
# .dmg, .AppImage e .deb si costruiscono a mano, quindi le loro impronte si
# generano qui e si allegano alla release insieme ai file.
#
#   scripts/checksums.sh dist/*.dmg dist/*.AppImage
#   scripts/checksums.sh --check dist/AnonimAI-2.0.0-macOS-arm64.dmg
#
# Chi scarica verifica con:
#   shasum -a 256 -c AnonimAI-2.0.0-macOS-arm64.dmg.sha256     (macOS/Linux)
#   Get-FileHash AnonimAI-2.0.0-Windows-Setup.exe              (Windows)
set -euo pipefail

# if/else e non "A && B || C": con l'operatore, un check FALLITO (exit != 0) farebbe
# partire anche il secondo comando, stampando l'errore due volte.
if command -v shasum >/dev/null; then SHA=(shasum -a 256); else SHA=(sha256sum); fi
sha() { "${SHA[@]}" "$1"; }

if [ "${1:-}" = "--check" ]; then
  shift
  for f in "$@"; do
    [ -f "$f.sha256" ] || { echo "manca $f.sha256"; exit 1; }
    (cd "$(dirname "$f")" && "${SHA[@]}" -c "$(basename "$f").sha256")
  done
  exit 0
fi

[ $# -gt 0 ] || { echo "uso: $0 <file...>  |  $0 --check <file...>"; exit 2; }
for f in "$@"; do
  [ -f "$f" ] || { echo "non trovato: $f"; exit 1; }
  (cd "$(dirname "$f")" && sha "$(basename "$f")" > "$(basename "$f").sha256")
  echo "$(cat "$f.sha256")"
done
