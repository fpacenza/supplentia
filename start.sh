#!/usr/bin/env bash
# SubstManager v2 – Script di Avvio
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        SubstManager v2.0  – Avvio        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 non trovato."
  exit 1
fi

PYTHON=$(command -v python3)
echo "✓ Python: $($PYTHON --version)"
mkdir -p data

if [ ! -f "data/substmanager.db" ] || [ "$1" == "--reset" ]; then
  [ "$1" == "--reset" ] && rm -f data/substmanager.db
#  echo "📦 Inizializzazione database…"
#  $PYTHON scripts/init_db.py
#  echo ""
fi

PORTA=$(python3 -c "
import json
try:
  cfg=json.load(open('config.json'))
  print(cfg.get('sistema',{}).get('porta',8080))
except:
  print(8080)
")

echo "🌐 Frontend: http://localhost:$PORTA"
echo "🔌 API:      http://localhost:$PORTA/api/"
echo ""
echo "Premi Ctrl+C per fermare."
echo ""
$PYTHON scripts/server.py
