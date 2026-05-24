#!/bin/bash
#
# deploy.sh — AI Agent Platform Linux Docker deployment script
#
# Usage:
#   ./deploy.sh                    # Build (cached) and start
#   ./deploy.sh --build            # Force rebuild with --no-cache
#   ./deploy.sh --pg               # Include PostgreSQL profile
#   ./deploy.sh --prod             # Load .env for production
#   ./deploy.sh --build --pg --prod  # All flags
#   ./deploy.sh --down             # Stop and remove containers (keep data)
#   ./deploy.sh --down-clean       # Stop containers AND remove all data volumes
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
BUILD=false
PG=false
PROD=false
DOWN=false
DOWN_CLEAN=false

for arg in "$@"; do
    case "$arg" in
        --build)      BUILD=true ;;
        --pg)         PG=true ;;
        --prod)       PROD=true ;;
        --down)       DOWN=true ;;
        --down-clean) DOWN_CLEAN=true ;;
        *)
            error "Unknown argument: $arg"
            echo "Usage: $0 [--build] [--pg] [--prod] [--down | --down-clean]"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Handle --down / --down-clean (stop and optionally remove data)
# ---------------------------------------------------------------------------
if [ "$DOWN" = true ] || [ "$DOWN_CLEAN" = true ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$SCRIPT_DIR"

    if [ "$DOWN_CLEAN" = true ]; then
        warn "==========================================="
        warn "  DESTRUCTIVE ACTION: --down-clean"
        warn "  This will DELETE all data volumes:"
        warn "    - Redis data"
        warn "    - Application data (workspace, logs, sessions)"
        warn "    - PostgreSQL data (if profile pg was used)"
        warn "==========================================="
        echo ""
        read -r -p "Type 'DELETE' to confirm: " CONFIRM
        if [ "$CONFIRM" != "DELETE" ]; then
            info "Aborted. No data was removed."
            exit 0
        fi
        info "Stopping containers and removing volumes ..."
        docker compose down -v
        success "All containers stopped and data volumes removed."
    else
        info "Stopping containers (data volumes preserved) ..."
        docker compose down
        success "All containers stopped. Data volumes are preserved."
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# Change to script directory (project root)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

info "Working directory: $(pwd)"

# ---------------------------------------------------------------------------
# Load environment variables (production mode)
# ---------------------------------------------------------------------------
if [ "$PROD" = true ]; then
    ENV_FILE="$SCRIPT_DIR/.env"
    if [ ! -f "$ENV_FILE" ]; then
        error ".env file not found at $ENV_FILE"
        error "Copy .env.example to .env and fill in required values before deploying with --prod."
        exit 1
    fi
    info "Loading .env file for production ..."
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
    success "Environment variables loaded from .env"
else
    info "Development mode: using default environment (no .env loaded)"
fi

# ---------------------------------------------------------------------------
# Validate critical environment variables
# ---------------------------------------------------------------------------
VALIDATION_FAILED=false

check_var() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    local default_warn="${2:-}"

    if [ -z "$var_value" ]; then
        warn "$var_name is not set. This may cause runtime failures."
        VALIDATION_FAILED=true
    elif [ -n "$default_warn" ] && [ "$var_value" = "$default_warn" ]; then
        warn "$var_name is still set to the default value '$default_warn'. Update it for production."
        VALIDATION_FAILED=true
    fi
}

check_var "AI_AGENT_DEEPSEEK_API_KEY" ""
check_var "AI_AGENT_JWT_SECRET" "change-this-in-production"

if [ "$VALIDATION_FAILED" = true ]; then
    warn "One or more environment variables need attention. Check the warnings above."
    if [ "$PROD" = true ]; then
        warn "Proceeding anyway in 5 seconds ... (press Ctrl+C to abort)"
        sleep 5
    fi
fi

# ---------------------------------------------------------------------------
# Check Docker availability
# ---------------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
    error "Docker is not installed or not found in PATH."
    exit 1
fi

if ! docker info &>/dev/null; then
    error "Docker daemon is not running or the current user lacks permissions."
    error "Try: sudo usermod -aG docker \$USER && newgrp docker"
    exit 1
fi

info "Docker is available."

# ---------------------------------------------------------------------------
# Build images
# ---------------------------------------------------------------------------
BUILD_CMD="docker compose build"
if [ "$BUILD" = true ]; then
    BUILD_CMD="docker compose build --no-cache"
    warn "Forcing full rebuild with --no-cache (this may take a while)..."
fi

info "Building Docker images ..."
if ! $BUILD_CMD; then
    error "Docker build failed. Check the build output above."
    exit 1
fi
success "Docker images built successfully."

# ---------------------------------------------------------------------------
# Start services
# ---------------------------------------------------------------------------
UP_CMD="docker compose up -d"
COMPOSE_PROFILE=""
if [ "$PG" = true ]; then
    UP_CMD="docker compose --profile pg up -d"
    info "Starting services with PostgreSQL profile ..."
else
    info "Starting services (without PostgreSQL) ..."
fi

if ! $UP_CMD; then
    error "Failed to start Docker services. Check 'docker compose logs' for details."
    exit 1
fi
success "All services started."

# ---------------------------------------------------------------------------
# Display running containers
# ---------------------------------------------------------------------------
echo ""
info "Running containers:"
docker compose ps
echo ""

# ---------------------------------------------------------------------------
# Wait for health endpoint
# ---------------------------------------------------------------------------
HEALTH_URL="http://localhost:8000/health"
TIMEOUT=60
INTERVAL=2
ELAPSED=0

info "Waiting for health endpoint at $HEALTH_URL (timeout: ${TIMEOUT}s) ..."

while [ $ELAPSED -lt $TIMEOUT ]; do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        echo ""
        success "Health check passed!"
        break
    fi
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
    if [ $((ELAPSED % 10)) -eq 0 ]; then
        info "Still waiting ... ${ELAPSED}s elapsed"
    fi
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo ""
    error "Health check did not pass within ${TIMEOUT}s."
    error "Possible issues:"
    error "  - The application failed to start. Check: docker compose logs app"
    error "  - The port mapping is different. Run: docker compose ps"
    error "  - Redis is unavailable. Check: docker compose logs redis"
    exit 1
fi

# ---------------------------------------------------------------------------
# Print success summary
# ---------------------------------------------------------------------------
echo ""
success "============================================"
success "  AI Agent Platform is now running!"
success "============================================"
echo ""
echo -e "  ${CYAN}Frontend:${NC}  http://localhost:8000"
echo -e "  ${CYAN}Health:${NC}    http://localhost:8000/health"
echo -e "  ${CYAN}API Docs:${NC}  http://localhost:8000/docs"
echo ""
info "Useful commands:"
info "  docker compose logs -f    # Follow all logs"
info "  docker compose ps         # List services"
info "  docker compose down       # Stop all services"
echo ""

# ---------------------------------------------------------------------------
# Show health response
# ---------------------------------------------------------------------------
info "Health endpoint response:"
curl -s "$HEALTH_URL" | python3 -m json.tool 2>/dev/null || curl -s "$HEALTH_URL"
echo ""
