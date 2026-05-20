#!/bin/bash
# AI Agent Platform — start backend + frontend
# Usage: bash start.sh

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT_DIR/.venv/Scripts/python.exe"
BACKEND_PID=""
FRONTEND_PID=""

echo "========================================"
echo "  AI Agent Platform — Starting..."
echo "========================================"

# --- Kill any existing instances ---
echo "Cleaning up existing processes..."

# Kill processes by port (more reliable than by image name)
for port in 8000 3000 3001 3002; do
    pid=$(netstat -aon 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $5}' | head -1)
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then
        echo "  Killing PID $pid on port $port"
        taskkill /F /PID "$pid" > /dev/null 2>&1 || true
    fi
done

# Fallback: kill by image name for any remaining instances
taskkill /F /IM python.exe > /dev/null 2>&1 || true
taskkill /F /IM node.exe > /dev/null 2>&1 || true
sleep 5

# --- Check dependencies ---
echo "[1/3] Checking dependencies..."

if [ ! -f "$PYTHON" ]; then
    echo "[ERROR] Python venv not found at $PYTHON"
    echo "Run: python -m venv .venv && .venv/Scripts/activate && pip install -e ."
    exit 1
fi
echo "  Python: $PYTHON"

if [ ! -d "$ROOT_DIR/web/node_modules" ]; then
    echo "  Installing frontend dependencies..."
    cd "$ROOT_DIR/web" && npm install && cd "$ROOT_DIR"
fi
echo "  Dependencies OK"

# --- Start backend ---
echo "[2/3] Starting backend (FastAPI on port 8000)..."
echo "  (single worker mode for development)"

cd "$ROOT_DIR"
"$PYTHON" -m gateway.server &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# Wait for backend health check (max 30s)
echo "  Waiting for backend to be ready..."
WAITED=0
while [ $WAITED -lt 30 ]; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  Backend ready!"
        break
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done

if [ $WAITED -ge 30 ]; then
    echo "[ERROR] Backend failed to start within 30s"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# --- Start frontend ---
echo "[3/3] Starting frontend (Vite on port 3000)..."

cd "$ROOT_DIR/web"
npm run dev 2>&1 &
FRONTEND_PID=$!
cd "$ROOT_DIR"

# Wait and detect frontend port
echo "  Waiting for frontend to be ready..."
sleep 6

FRONTEND_PORT=""
for port in 3000 3001 3002 3003; do
    if curl -sf http://localhost:$port > /dev/null 2>&1; then
        FRONTEND_PORT=$port
        echo "  Frontend ready on port $port!"
        break
    fi
done

if [ -z "$FRONTEND_PORT" ]; then
    FRONTEND_PORT="3000 (check browser)"
fi

# --- Done ---
echo ""
echo "========================================"
echo "  Platform started!"
echo "========================================"
echo ""
echo "  Frontend:   http://localhost:$FRONTEND_PORT"
echo "  Backend:    http://localhost:8000"
echo "  Health:     http://localhost:8000/health"
echo "  API Docs:   http://localhost:8000/docs"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# Cleanup on exit
cleanup() {
    echo ""
    echo "Stopping services..."
    taskkill /F /PID $BACKEND_PID > /dev/null 2>&1 || true
    taskkill /F /PID $FRONTEND_PID > /dev/null 2>&1 || true
    echo "Services stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

wait