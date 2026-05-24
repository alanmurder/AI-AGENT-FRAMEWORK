#!/usr/bin/env bash
# =============================================================================
#  AI Agent Platform — Build Script (Linux)
# =============================================================================
#  Builds the frontend and optionally creates a Python wheel.
#
#  Usage:
#    bash build.sh              # build frontend only
#    bash build.sh --wheel      # build frontend + Python wheel
#    bash build.sh --help       # show this message
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

BUILD_WHEEL=false

for arg in "$@"; do
    case "$arg" in
        --help)
            echo "Usage: bash build.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --help       Show this help message"
            echo "  --wheel      Also build a Python wheel package"
            echo ""
            echo "Builds the frontend and optionally creates a Python distribution."
            exit 0
            ;;
        --wheel)
            BUILD_WHEEL=true
            shift
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: bash build.sh [--help] [--wheel]"
            exit 1
            ;;
    esac
done

# Ensure we start from the project root
cd "$ROOT_DIR"

# ---------------------------------------------------------------------------
# Frontend build
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  AI Agent Platform — Build"
echo "============================================"
echo ""

echo "  Step 1/2: Building frontend..."
echo "  ------------------------------"

if [ ! -d "$ROOT_DIR/web" ]; then
    fatal "web/ directory not found at $ROOT_DIR/web"
fi

log_info "Installing frontend dependencies (npm ci)..."
cd "$ROOT_DIR/web"
npm ci 2>&1 | sed 's/^/    /'
if [ $? -ne 0 ]; then
    log_warn "npm ci failed, falling back to npm install..."
    npm install 2>&1 | sed 's/^/    /'
fi

log_info "Building frontend (npm run build)..."
npm run build 2>&1 | sed 's/^/    /'
cd "$ROOT_DIR"

echo ""
echo "  Verifying output..."
echo "  -------------------"

if [ -f "$ROOT_DIR/web/dist/index.html" ]; then
    log_info "Frontend build: OK"
    log_info "  Output: web/dist/index.html"
    # Count built assets
    ASSET_COUNT=$(find "$ROOT_DIR/web/dist" -type f | wc -l)
    log_info "  Assets: $ASSET_COUNT files in web/dist/"
else
    fatal "web/dist/index.html not found — frontend build may have failed."
fi

# ---------------------------------------------------------------------------
# Python wheel (optional)
# ---------------------------------------------------------------------------
if [ "$BUILD_WHEEL" = true ]; then
    echo ""
    echo "  Step 2/2: Building Python wheel..."
    echo "  ----------------------------------"

    # Ensure build tool is available
    if [ ! -f "$ROOT_DIR/.venv/bin/python" ]; then
        log_warn "Virtual environment not found. Creating one..."
        python3.11 -m venv "$ROOT_DIR/.venv" || python3 -m venv "$ROOT_DIR/.venv"
    fi

    log_info "Installing build tool..."
    "$ROOT_DIR/.venv/bin/pip" install build -q

    log_info "Building wheel..."
    "$ROOT_DIR/.venv/bin/python" -m build --wheel "$ROOT_DIR" 2>&1 | sed 's/^/    /'

    WHEEL_FILE=$(ls -t "$ROOT_DIR/dist/"*.whl 2>/dev/null | head -1)
    if [ -n "$WHEEL_FILE" ]; then
        log_info "Python wheel built: $WHEEL_FILE"
    else
        log_warn "Wheel build may have failed — no .whl found in dist/"
    fi
else
    echo ""
    echo "  Step 2/2: Skipping Python wheel (use --wheel to build it)."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
log_info "Build complete!"
echo "============================================"
echo ""
echo "  Frontend output:  $ROOT_DIR/web/dist/"
echo "  Frontend entry:   $ROOT_DIR/web/dist/index.html"
if [ "$BUILD_WHEEL" = true ]; then
    WHEEL_FILE=$(ls -t "$ROOT_DIR/dist/"*.whl 2>/dev/null | head -1)
    if [ -n "$WHEEL_FILE" ]; then
        echo "  Python wheel:     $WHEEL_FILE"
    fi
fi
echo ""
