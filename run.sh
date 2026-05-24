#!/usr/bin/env bash
# =============================================================================
#  AI Agent Platform — Production Run Script (Linux)
# =============================================================================
#  Usage:
#    bash run.sh                    # foreground mode (Ctrl+C to stop)
#    bash run.sh --daemon           # background mode (nohup)
#    bash run.sh --foreground       # explicit foreground (default)
#    bash run.sh --status           # check if the platform is running
#    bash run.sh --help             # show this message
# =============================================================================

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "  ${GREEN}•${NC} $1"; }
log_warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "  ${RED}✖${NC} $1"; }
fatal()     { log_error "$1"; exit 1; }

ACTIVATE="$ROOT_DIR/.venv/bin/activate"
PYTHON="$ROOT_DIR/.venv/bin/python"
GUNICORN="$ROOT_DIR/.venv/bin/gunicorn"

# Defaults
MODE="foreground"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        --help)
            echo "Usage: bash run.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --help           Show this help message"
            echo "  --foreground     Run in foreground (default)"
            echo "  --daemon         Run in background (nohup)"
            echo "  --status         Check if the platform is running"
            exit 0
            ;;
        --foreground) MODE="foreground" ;;
        --daemon)     MODE="daemon" ;;
        --status)     MODE="status" ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: bash run.sh [--foreground] [--daemon] [--status] [--help]"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# --status mode
# ---------------------------------------------------------------------------
if [ "$MODE" = "status" ]; then
    PID_FILE="$ROOT_DIR/data/.run.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo ""
            echo "  AI Agent Platform is running."
            echo "  PID: $PID"
            echo "  Port: ${AI_AGENT_GATEWAY_PORT:-8000}"
            echo ""
            exit 0
        else
            log_warn "PID file found but process not running. Stale PID: $PID"
            rm -f "$PID_FILE"
            exit 1
        fi
    else
        echo ""
        log_warn "AI Agent Platform is not running (no PID file)."
        echo ""
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Check .env
# ---------------------------------------------------------------------------
if [ -f "$ROOT_DIR/.env" ]; then
    log_info "Loading configuration from .env"
    set -a
    source "$ROOT_DIR/.env"
    set +a
else
    log_warn ".env file not found. Using environment defaults."
    log_warn "Copy .env.example to .env and configure it."
fi

# ---------------------------------------------------------------------------
# Check Redis
# ---------------------------------------------------------------------------
echo ""
echo "  Checking Redis..."
echo "  -----------------"

if command -v redis-cli &>/dev/null; then
    if redis-cli ping 2>/dev/null | grep -q "PONG"; then
        log_info "Redis is running."
    else
        log_warn "Redis is not running. The server will start but chat and memory features will be unavailable until Redis is started."
    fi
else
    log_warn "redis-cli not found. Skipping Redis connectivity check."
    log_warn "Redis is optional — needed only for chat/memory features."
fi

# ---------------------------------------------------------------------------
# Check frontend build
# ---------------------------------------------------------------------------
if [ ! -d "$ROOT_DIR/web/dist" ]; then
    fatal "Frontend build not found at web/dist/. Run 'bash build.sh' first."
fi

if [ ! -f "$ROOT_DIR/web/dist/index.html" ]; then
    fatal "Frontend build incomplete — web/dist/index.html missing. Run 'bash build.sh'."
fi
log_info "Frontend build found at web/dist/"

# ---------------------------------------------------------------------------
# Check virtual environment
# ---------------------------------------------------------------------------
if [ ! -f "$ACTIVATE" ]; then
    fatal "Virtual environment not found at .venv/. Run 'bash install.sh' first."
fi

# Activate (needed for PATH resolution)
# shellcheck disable=SC1090
source "$ACTIVATE"
log_info "Virtual environment activated."

# ---------------------------------------------------------------------------
# Set production mode
# ---------------------------------------------------------------------------
export AI_AGENT_SERVE_STATIC=true

# ---------------------------------------------------------------------------
# Determine host and port
# ---------------------------------------------------------------------------
HOST="${AI_AGENT_GATEWAY_HOST:-0.0.0.0}"
PORT="${AI_AGENT_GATEWAY_PORT:-8000}"
WORKERS="${AI_AGENT_GATEWAY_WORKERS:-4}"

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  Starting AI Agent Platform"
echo "  Mode:     $MODE"
echo "  Host:     $HOST"
echo "  Port:     $PORT"
echo "  Workers:  $WORKERS"
echo "============================================"
echo ""

start_uvicorn() {
    exec "$PYTHON" -m gateway.server
}

start_gunicorn() {
    exec "$GUNICORN" \
        gateway.server:app \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind "$HOST:$PORT" \
        --workers "$WORKERS" \
        --timeout 120 \
        --access-logfile - \
        --error-logfile - \
        --log-level "${AI_AGENT_LOG_LEVEL:-info}"
}

cleanup() {
    echo ""
    log_info "Shutting down gracefully..."
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

PID_FILE="$ROOT_DIR/data/.run.pid"

case "$MODE" in
    foreground)
        log_info "Starting in foreground (Ctrl+C to stop)..."
        if [ -x "$GUNICORN" ]; then
            log_info "Using gunicorn with $WORKERS workers..."
            start_gunicorn
        else
            log_info "gunicorn not found, using uvicorn directly..."
            log_warn "For production, install gunicorn: pip install '.[prod]'"
            start_uvicorn
        fi
        ;;

    daemon)
        log_info "Starting in background (nohup)..."
        LOG_FILE="$ROOT_DIR/data/logs/platform.log"
        mkdir -p "$(dirname "$LOG_FILE")"

        if [ -x "$GUNICORN" ]; then
            log_info "Using gunicorn with $WORKERS workers..."
            nohup "$GUNICORN" \
                gateway.server:app \
                --worker-class uvicorn.workers.UvicornWorker \
                --bind "$HOST:$PORT" \
                --workers "$WORKERS" \
                --timeout 120 \
                --access-logfile "$ROOT_DIR/data/logs/access.log" \
                --error-logfile "$ROOT_DIR/data/logs/error.log" \
                --log-level "${AI_AGENT_LOG_LEVEL:-info}" \
                > "$LOG_FILE" 2>&1 &
            BGPID=$!
        else
            log_info "gunicorn not found, using uvicorn directly..."
            log_warn "For production, install gunicorn: pip install '.[prod]'"
            nohup "$PYTHON" -m gateway.server > "$LOG_FILE" 2>&1 &
            BGPID=$!
        fi

        echo "$BGPID" > "$PID_FILE"
        log_info "Platform started in background (PID: $BGPID)"
        echo ""
        echo "  Logs:      $LOG_FILE"
        echo "  URL:       http://localhost:$PORT"
        echo "  Health:    http://localhost:$PORT/health"
        echo "  API Docs:  http://localhost:$PORT/docs"
        echo ""
        log_info "To stop: kill $BGPID"
        echo ""
        ;;
esac
