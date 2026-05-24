#!/bin/bash
#
# uninstall.sh — AI Agent Platform Linux uninstall script
#
# Usage:
#   ./uninstall.sh                 # Remove virtualenv + node_modules + build artifacts
#   ./uninstall.sh --all           # Also remove data/ directory (workspace, logs, sessions)
#   ./uninstall.sh --full          # Above + uninstall system packages (Python, Node, Redis)
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ALL=false
FULL=false

for arg in "$@"; do
    case "$arg" in
        --all)  ALL=true ;;
        --full) FULL=true ;;
        --help)
            echo "Usage: $0 [--all] [--full]"
            echo ""
            echo "  (no flag)  Remove Python venv, node_modules, and frontend build"
            echo "  --all      Also remove data/ directory (workspace, logs, sessions)"
            echo "  --full     Above + prompt to uninstall system packages (Python, Node, Redis)"
            exit 0
            ;;
        *)
            error "Unknown argument: $arg"
            echo "Usage: $0 [--all] [--full]"
            exit 1
            ;;
    esac
done

# Summary
echo ""
info "============================================"
info "  AI Agent Platform — Uninstall"
info "============================================"
echo ""
if [ "$FULL" = true ]; then
    warn "Mode: FULL (project files + data + system packages)"
elif [ "$ALL" = true ]; then
    warn "Mode: ALL (project files + data directory)"
else
    info "Mode: standard (project files only, data/ preserved)"
fi
echo ""

# Confirmation
if [ "$FULL" = true ]; then
    read -r -p "Proceed with full uninstall? [y/N] " CONFIRM
else
    read -r -p "Proceed with uninstall? [y/N] " CONFIRM
fi
if [ "${CONFIRM,,}" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    info "Aborted."
    exit 0
fi

REMOVED=()

# --- Remove Python virtual environment ---
if [ -d ".venv" ]; then
    rm -rf .venv
    REMOVED+=(".venv/")
    success "Removed .venv/"
else
    info "No .venv/ found, skipping"
fi

# --- Remove frontend build artifacts ---
if [ -d "web/dist" ]; then
    rm -rf web/dist
    REMOVED+=("web/dist/")
    success "Removed web/dist/"
else
    info "No web/dist/ found, skipping"
fi

# --- Remove node_modules ---
if [ -d "web/node_modules" ]; then
    rm -rf web/node_modules
    REMOVED+=("web/node_modules/")
    success "Removed web/node_modules/"
else
    info "No web/node_modules/ found, skipping"
fi

# --- Remove Python caches ---
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
info "Cleaned __pycache__ and *.egg-info"

# --- Remove dist/ (python wheel) ---
if [ -d "dist" ]; then
    rm -rf dist
    REMOVED+=("dist/")
    success "Removed dist/"
fi

# --- Remove data directory (--all or --full) ---
if [ "$ALL" = true ] || [ "$FULL" = true ]; then
    if [ -d "data" ]; then
        warn "==========================================="
        warn "  About to remove data/ directory"
        warn "  This includes:"
        warn "    - User workspaces"
        warn "    - Session history"
        warn "    - Application logs"
        warn "==========================================="
        read -r -p "Type 'DELETE' to confirm removal of data/: " DATA_CONFIRM
        if [ "$DATA_CONFIRM" = "DELETE" ]; then
            rm -rf data
            REMOVED+=("data/")
            success "Removed data/ (workspace, logs, sessions)"
        else
            info "data/ preserved (confirmation did not match)"
        fi
    else
        info "No data/ found, skipping"
    fi
fi

# --- Remove system packages (--full only) ---
if [ "$FULL" = true ]; then
    echo ""
    warn "System package removal requires manual confirmation per package."
    echo ""

    # Detect OS
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            ubuntu|debian)
                PKG_MGR="apt"
                REMOVE_CMD="sudo apt purge -y"
                ;;
            rhel|centos|fedora|rocky|almalinux)
                PKG_MGR="yum"
                REMOVE_CMD="sudo yum remove -y"
                ;;
            *)
                info "Unknown OS. Skipping system package removal."
                PKG_MGR=""
                ;;
        esac

        if [ -n "$PKG_MGR" ]; then
            # Python
            read -r -p "Remove python3.11 and development packages? [y/N] " ANS
            if [ "${ANS,,}" = "y" ]; then
                $REMOVE_CMD python3.11 python3.11-venv python3.11-dev 2>/dev/null || true
                success "Python packages removed"
            else
                info "Python packages preserved"
            fi

            # Node.js
            read -r -p "Remove Node.js? [y/N] " ANS
            if [ "${ANS,,}" = "y" ]; then
                $REMOVE_CMD nodejs npm 2>/dev/null || true
                success "Node.js removed"
            else
                info "Node.js preserved"
            fi

            # Redis
            read -r -p "Remove Redis server? [y/N] " ANS
            if [ "${ANS,,}" = "y" ]; then
                sudo systemctl stop redis-server 2>/dev/null || true
                $REMOVE_CMD redis-server 2>/dev/null || true
                success "Redis removed"
            else
                info "Redis preserved"
            fi
        fi
    fi
fi

# --- Summary ---
echo ""
success "============================================"
success "  Uninstall complete"
success "============================================"
echo ""
if [ ${#REMOVED[@]} -gt 0 ]; then
    info "Removed: ${REMOVED[*]}"
else
    info "Nothing was removed."
fi
echo ""
info "The following remain on disk (not managed by this script):"
info "  - Source code (git repository)"
info "  - .env file (contains your API keys)"
info "  - config/ directory"
echo ""
info "To remove everything, delete the project directory:"
info "  rm -rf $SCRIPT_DIR"
echo ""
