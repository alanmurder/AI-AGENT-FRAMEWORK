#!/usr/bin/env bash
# =============================================================================
#  AI Agent Platform — Linux Fresh-System Install Script
# =============================================================================
#  Supports: Ubuntu/Debian (apt) and RHEL/Fedora/CentOS (dnf/yum)
#
#  Usage:
#    bash install.sh              # full install
#    bash install.sh --no-frontend  # skip frontend build
#    bash install.sh --no-sandbox   # skip sandbox (Docker) extras
#    bash install.sh --help         # show this message
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# Constants & Helpers
# ---------------------------------------------------------------------------
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "  ${GREEN}•${NC} $1"; }
log_warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "  ${RED}✖${NC} $1"; }
fatal()     { log_error "$1"; exit 1; }

NO_FRONTEND=false
NO_SANDBOX=false

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        --help)
            echo "Usage: bash install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --help           Show this help message"
            echo "  --no-frontend    Skip frontend dependencies and build"
            echo "  --no-sandbox     Skip sandbox (Docker) optional dependencies"
            echo ""
            echo "Installs system packages, creates Python venv, installs Python"
            echo "dependencies, builds the frontend, and prepares data directories."
            exit 0
            ;;
        --no-frontend)
            NO_FRONTEND=true
            shift
            ;;
        --no-sandbox)
            NO_SANDBOX=true
            shift
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: bash install.sh [--help] [--no-frontend] [--no-sandbox]"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  AI Agent Platform — Install Script"
echo "============================================"
echo ""

# ---------------------------------------------------------------------------
# OS Detection
# ---------------------------------------------------------------------------
OS_ID=""
OS_LIKE=""

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_LIKE="$ID_LIKE"
elif [ -f /etc/centos-release ]; then
    OS_ID="centos"
else
    fatal "Cannot detect OS. /etc/os-release not found."
fi

log_info "Detected OS: $OS_ID ${VERSION_ID:-}"

is_debian_like() {
    [[ "$OS_ID" == "ubuntu" || "$OS_ID" == "debian" || "$OS_LIKE" == *"debian"* ]]
}

is_rhel_like() {
    [[ "$OS_ID" == "rhel" || "$OS_ID" == "fedora" || "$OS_ID" == "centos" || "$OS_LIKE" == *"rhel"* || "$OS_LIKE" == *"fedora"* ]]
}

# ---------------------------------------------------------------------------
# Phase 1: System packages
# ---------------------------------------------------------------------------
echo ""
echo "  Phase 1/5: Installing system packages..."
echo "  -----------------------------------------"

if is_debian_like; then
    log_info "Updating apt cache..."
    sudo apt-get update -qq

    log_info "Installing Python 3, Node.js, and build tools..."
    sudo apt-get install -y -qq \
        python3 \
        python3-venv \
        python3-dev \
        nodejs \
        npm \
        curl \
        git \
        2>&1 | sed 's/^/    /'

elif is_rhel_like; then
    # Enable EPEL and PowerTools/CRB if available
    if command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
    else
        PKG_MGR="yum"
    fi

    log_info "Enabling EPEL repository..."
    sudo $PKG_MGR install -y -q epel-release 2>/dev/null || log_warn "EPEL not available; some packages may be missing."

    # Enable CodeReady Builder / PowerTools for redis on RHEL 9+
    if [[ "$OS_ID" == "rhel" || "$OS_ID" == "centos" ]]; then
        sudo $PKG_MGR config-manager --set-enabled crb 2>/dev/null || \
        sudo $PKG_MGR config-manager --set-enabled powertools 2>/dev/null || true
    fi

    # Install Node.js via NodeSource if node is not available
    if ! command -v node &>/dev/null; then
        log_info "Installing Node.js via NodeSource..."
        if [[ "$OS_ID" == "fedora" ]]; then
            sudo $PKG_MGR install -y -q nodejs npm 2>/dev/null || {
                curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
                sudo $PKG_MGR install -y -q nodejs
            }
        else
            curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
            sudo $PKG_MGR install -y -q nodejs
        fi
    fi

    log_info "Installing Python 3, curl, git..."
    sudo $PKG_MGR install -y -q \
        python3 \
        python3-devel \
        curl \
        git \
        2>&1 | sed 's/^/    /'
else
    fatal "Unsupported OS: $OS_ID. This script supports Debian/Ubuntu and RHEL/Fedora/CentOS."
fi

log_info "System packages installed successfully."

log_info "Note: Redis is optional (only needed for chat/memory features)."
log_info "      Install it later with: sudo apt-get install redis-server"
log_info "      (or the equivalent for your package manager)."

# ---------------------------------------------------------------------------
# Phase 2: Python virtual environment
# ---------------------------------------------------------------------------
echo ""
echo "  Phase 2/5: Creating Python virtual environment..."
echo "  -------------------------------------------------"

PYTHON_BIN=""
for candidate in python3.11 python3.12 python3.13 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON_BIN="$candidate"
        break
    fi
done

[ -z "$PYTHON_BIN" ] && fatal "Python 3.11+ not found after package installation."

log_info "Using Python: $PYTHON_BIN ($($PYTHON_BIN --version))"

if [ -d "$ROOT_DIR/.venv" ]; then
    log_warn ".venv already exists. Skipping creation."
else
    "$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
    log_info "Virtual environment created at .venv"
fi

# ---------------------------------------------------------------------------
# Phase 3: Python dependencies
# ---------------------------------------------------------------------------
echo ""
echo "  Phase 3/5: Installing Python dependencies..."
echo "  --------------------------------------------"

PYTHON="$ROOT_DIR/.venv/bin/python"

# Upgrade pip (non-fatal if it fails — e.g. due to proxy)
log_info "Upgrading pip..."
"$PYTHON" -m pip install --upgrade pip --default-timeout=120 2>&1 | tail -1 || log_warn "Pip upgrade had issues — continuing anyway."

if [ "$NO_SANDBOX" = true ]; then
    INSTALL_SPEC=".[dev,prod]"
    log_info "Installing base + dev + prod dependencies (skipping sandbox)..."
else
    INSTALL_SPEC=".[dev,prod,sandbox]"
    log_info "Installing base + dev + prod + sandbox dependencies..."
fi

log_info "(This may take several minutes — downloading packages...)"
"$PYTHON" -m pip install -e "$ROOT_DIR[$INSTALL_SPEC]" --default-timeout=120 || {
    log_error "Failed to install Python dependencies. Check network/proxy and retry."
    exit 1
}
log_info "Python dependencies installed."

# ---------------------------------------------------------------------------
# Phase 4: Frontend (optional)
# ---------------------------------------------------------------------------
if [ "$NO_FRONTEND" = false ]; then
    echo ""
    echo "  Phase 4/5: Building frontend..."
    echo "  -------------------------------"

    if [ ! -d "$ROOT_DIR/web" ]; then
        log_warn "web/ directory not found. Skipping frontend build."
    else
        log_info "Installing frontend npm dependencies..."
        cd "$ROOT_DIR/web"
        npm ci 2>&1 | sed 's/^/    /'
        log_info "Building frontend..."
        npm run build 2>&1 | sed 's/^/    /'
        cd "$ROOT_DIR"

        if [ -f "$ROOT_DIR/web/dist/index.html" ]; then
            log_info "Frontend build successful — web/dist/index.html"
        else
            log_warn "Frontend build completed but web/dist/index.html not found."
        fi
    fi
else
    echo ""
    log_info "Phase 4/5: Frontend build skipped (--no-frontend)."
fi

# ---------------------------------------------------------------------------
# Phase 5: Data directories & configuration
# ---------------------------------------------------------------------------
echo ""
echo "  Phase 5/5: Creating data directories and configuration..."
echo "  ---------------------------------------------------------"

mkdir -p "$ROOT_DIR/data/workspace"
mkdir -p "$ROOT_DIR/data/logs"
mkdir -p "$ROOT_DIR/data/sessions"
log_info "Data directories created under data/"

if [ ! -f "$ROOT_DIR/.env" ]; then
    if [ -f "$ROOT_DIR/.env.example" ]; then
        cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
        log_info "Copied .env.example -> .env"
        log_warn "Please edit .env with your API keys and settings."
    else
        log_warn ".env.example not found. Create .env manually."
    fi
else
    log_info ".env already exists. Skipping copy."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo -e "  ${GREEN}Installation complete!${NC}"
echo "============================================"
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your API keys:"
echo "       vi .env"
echo ""
echo "    2. (Optional) Start Redis if you need chat/memory features:"
echo "       sudo systemctl start redis-server"
echo "       sudo systemctl enable redis-server"
echo ""
echo "    3. Run the platform:"
echo "       bash run.sh"
echo ""
echo "  Other commands:"
echo "       bash run.sh --daemon    (background mode)"
echo "       bash run.sh --status    (check running status)"
echo "       bash build.sh           (rebuild frontend)"
echo ""

if [ "$NO_FRONTEND" = true ]; then
    echo -e "  ${YELLOW}Note: Frontend was not built. Run 'bash build.sh' when ready.${NC}"
    echo ""
fi
