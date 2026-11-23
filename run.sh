#!/usr/bin/env bash
# exam2md - Start script for Linux/macOS

set -e

echo "Iniciando exam2md..."

# Verifica se venv existe
if [ ! -d ".venv" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# Ativa venv
source .venv/bin/activate

echo ""
echo "[1/2] Iniciando API (FastAPI) na porta 8000..."
python api.py &
API_PID=$!

# Aguarda API subir
sleep 3

echo ""
echo "[2/2] Abrindo interface no navegador..."
if command -v xdg-open >/dev/null; then
    xdg-open http://localhost:8000
elif command -v open >/dev/null; then
    open http://localhost:8000
else
    echo "Abra manualmente: http://localhost:8000"
fi

echo ""
echo "================================="
echo "exam2md rodando!"
echo "API:     http://localhost:8000"
echo "Web:     http://localhost:8000"
echo "Parar:   Ctrl+C"
echo "================================="

# Cleanup on exit
trap "kill $API_PID 2>/dev/null; exit" INT TERM EXIT
wait $API_PID