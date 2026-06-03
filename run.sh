#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
START_OLLAMA="${START_OLLAMA:-true}"

echo "[SAGE] Iniciando entorno..."
echo "[SAGE] API_HOST=$API_HOST"
echo "[SAGE] API_PORT=$API_PORT"
echo "[SAGE] START_OLLAMA=$START_OLLAMA"
echo "[SAGE] OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434}"

if [ "$START_OLLAMA" = "true" ]; then
    if ! pgrep -x "ollama" > /dev/null; then
        echo "[SAGE] Iniciando Ollama..."
        ollama serve &
        sleep 2
    else
        echo "[SAGE] Ollama ya está corriendo."
    fi
else
    echo "[SAGE] No se inicia Ollama desde run.sh."
fi

echo "[SAGE] Iniciando EVA en http://$API_HOST:$API_PORT"
cd app
python3 -m uvicorn main:app --reload --host "$API_HOST" --port "$API_PORT"