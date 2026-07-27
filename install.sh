#!/bin/bash
# Trident Protect Web UI Installer
# Installs Python deps, CLI binary, configures cluster connection, sets up systemd service
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Colors for status output ---
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m' # No Color
else
    GREEN=''; YELLOW=''; RED=''; BLUE=''; CYAN=''; BOLD=''; NC=''
fi

ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }
ask()  { echo -ne "  ${BLUE}[?]${NC} $1"; }

step() {
    echo ""
    echo -e "${BOLD}${BLUE}[$1/10]${NC} ${BOLD}$2${NC}"
}

# --- Header ---
clear
echo -e "${BOLD}${CYAN}========================================${NC}"
echo -e "${BOLD}${CYAN} Trident Protect Web UI Installer${NC}"
echo -e "${BOLD}${CYAN}========================================${NC}"
echo ""
echo "  This installer will:"
echo "    1. Check prerequisites (Python, curl, oc/kubectl)"
echo "    2. Set up installation directories"
echo "    3. Create a Python virtual environment"
echo "    4. Install Python dependencies (Flask, PyYAML)"
echo "    5. Download tridentprotect-ctl CLI from GitHub"
echo "    6. Configure cluster connection (interactive)"
echo "    7. Set up authentication (interactive)"
echo "    8. Install systemd service"
echo "    9. Configure firewall (open port 8081)"
echo "   10. Verify installation"
echo ""
echo "  Press Ctrl+C to abort at any time."
echo ""

CLI_VERSION_DEFAULT="26.06.0"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=9
REQUIRED_DISK_MB=500

# Helper: run apt-get with retry on lock contention
apt_install() {
    local MAX_WAIT=120  # max seconds to wait for dpkg lock
    local waited=0
    while fuser /var/lib/dpkg/lock-frontend > /dev/null 2>&1; do
        if [ "$waited" -ge "$MAX_WAIT" ]; then
            warn "dpkg lock held >${MAX_WAIT}s — aborting"
            return 1
        fi
        sleep 5
        waited=$((waited + 5))
    done
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

# Auto-detect latest CLI version from GitHub API (with fallback to default)
CLI_VERSION=$(curl -fsSL --max-time 10 "https://api.github.com/repos/NetApp/tridentctl-protect/releases/latest" 2>/dev/null \
    | grep -oP '"tag_name":\s*"\K[^"]+' | sed 's/^v//' || echo "$CLI_VERSION_DEFAULT")
CLI_VERSION=${CLI_VERSION:-$CLI_VERSION_DEFAULT}
CLI_URL="https://github.com/NetApp/tridentctl-protect/releases/download/v${CLI_VERSION}/tridentctl-protect-linux-amd64"

# ============================================================================
step "1/10" "Checking prerequisites"
# ============================================================================

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    info "OS: $PRETTY_NAME"
    IS_UBUNTU=0
    case "$ID" in
        ubuntu|debian) IS_UBUNTU=1 ;;
    esac
else
    warn "Cannot detect OS (no /etc/os-release)"
    IS_UBUNTU=0
fi

# Check Python
PYTHON=$(which python3 2>/dev/null || true)
if [ -z "$PYTHON" ]; then
    if [ "$IS_UBUNTU" -eq 1 ] && [ "$(id -u)" -eq 0 ]; then
        warn "python3 not found, installing..."
        apt_install python3 > /dev/null 2>&1 || {
            fail "Cannot install python3"
            exit 1
        }
        ok "python3 installed"
        PYTHON=$(which python3)
    else
        fail "python3 not found"
        echo "       Install with: sudo apt-get install -y python3 python3-venv python3-pip"
        exit 1
    fi
fi
PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt "$PYTHON_MIN_MAJOR" ] || { [ "$PY_MAJOR" -eq "$PYTHON_MIN_MAJOR" ] && [ "$PY_MINOR" -lt "$PYTHON_MIN_MINOR" ]; }; then
    fail "Python $PY_VERSION found but >= $PYTHON_MIN_MAJOR.$PYTHON_MIN_MINOR required"
    exit 1
fi
ok "Python $PY_VERSION"

# Check venv module — also test ensurepip (python3 -m venv needs both)
NEEDS_VENV_INSTALL=0
if ! $PYTHON -c 'import venv' > /dev/null 2>&1; then
    NEEDS_VENV_INSTALL=1
elif ! $PYTHON -c 'import ensurepip' > /dev/null 2>&1; then
    NEEDS_VENV_INSTALL=1
fi

if [ "$NEEDS_VENV_INSTALL" -eq 1 ]; then
    if [ "$IS_UBUNTU" -eq 1 ] && [ "$(id -u)" -eq 0 ]; then
        warn "python3-venv module missing, installing..."
        apt_install python3-venv python${PY_MAJOR}.${PY_MINOR}-venv > /dev/null 2>&1 || {
            fail "Cannot install python3-venv"
            exit 1
        }
        ok "python3-venv installed"
    else
        fail "python3-venv module not installed"
        echo "       Install with: sudo apt-get install -y python3-venv"
        exit 1
    fi
else
    ok "python3-venv available"
fi

# Check pip
if ! $PYTHON -m pip --version > /dev/null 2>&1; then
    if [ "$IS_UBUNTU" -eq 1 ] && [ "$(id -u)" -eq 0 ]; then
        warn "pip not found, installing python3-pip..."
        apt_install python3-pip || {
            fail "Cannot install pip"
            exit 1
        }
        ok "pip installed"
    else
        fail "pip not found. Install with: sudo apt-get install -y python3-pip"
        exit 1
    fi
else
    PIP_VERSION=$($PYTHON -m pip --version | awk '{print $2}')
    ok "pip $PIP_VERSION"
fi

# Check curl
if ! which curl > /dev/null 2>&1; then
    if [ "$IS_UBUNTU" -eq 1 ] && [ "$(id -u)" -eq 0 ]; then
        warn "curl not found, installing..."
        apt_install curl > /dev/null 2>&1 || {
            fail "Cannot install curl"
            exit 1
        }
        ok "curl installed"
    else
        fail "curl not found. Install with: sudo apt-get install -y curl"
        exit 1
    fi
else
    ok "curl available"
fi

# Check kubectl (primary) and oc (optional, for OpenShift login)
if which kubectl > /dev/null 2>&1; then
    KUBE_VERSION=$(kubectl version --client -o json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('gitVersion','?'))" 2>/dev/null || echo "?")
    ok "kubectl found ($KUBE_VERSION)"
else
    warn "kubectl not found, downloading from dl.k8s.io..."
    KUBE_TMP=$(mktemp -d)
    KUBE_STABLE=$(curl -fsSL --max-time 10 https://dl.k8s.io/release/stable.txt 2>/dev/null || echo "v1.30.0")
    if curl -fsSL -o "$KUBE_TMP/kubectl" "https://dl.k8s.io/release/${KUBE_STABLE}/bin/linux/amd64/kubectl" 2>/dev/null; then
        if [ "$(id -u)" -eq 0 ]; then
            mv "$KUBE_TMP/kubectl" /usr/local/bin/kubectl
            chmod +x /usr/local/bin/kubectl
            ok "kubectl installed to /usr/local/bin/kubectl ($KUBE_STABLE)"
        else
            mv "$KUBE_TMP/kubectl" "$SCRIPT_DIR/bin/kubectl"
            chmod +x "$SCRIPT_DIR/bin/kubectl"
            ok "kubectl installed to $SCRIPT_DIR/bin/kubectl ($KUBE_STABLE)"
        fi
        rm -rf "$KUBE_TMP"
    else
        fail "Cannot download kubectl"
        echo "       Install kubectl: https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/"
        exit 1
    fi
fi

# Check oc (optional — for OpenShift login features like username/password)
if which oc > /dev/null 2>&1; then
    OC_VERSION=$(oc version --client -o json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('openshiftVersion','?'))" 2>/dev/null || echo "?")
    ok "oc client found (OpenShift $OC_VERSION)"
else
    info "oc not found — OpenShift-specific features (username/password login) will be unavailable"
    info "To enable, install oc from: https://mirror.openshift.com/pub/openshift-v4/clients/oc/"
fi

# Check disk space
AVAIL_MB=$(df -m "$SCRIPT_DIR" | awk 'NR==2 {print $4}')
if [ "$AVAIL_MB" -lt "$REQUIRED_DISK_MB" ]; then
    fail "Insufficient disk space: ${AVAIL_MB}MB available, ${REQUIRED_DISK_MB}MB required"
    exit 1
fi
ok "Disk space: ${AVAIL_MB}MB available"

# Check if root (needed for systemd + firewall)
IS_ROOT=0
if [ "$(id -u)" -eq 0 ]; then
    IS_ROOT=1
    ok "Running as root (systemd + firewall available)"
else
    warn "Not running as root (systemd install + firewall will be skipped)"
fi

# ============================================================================
step "2/10" "Setting up directories"
# ============================================================================

mkdir -p bin
mkdir -p logs
ok "Created bin/ and logs/"

if [ ! -f "$SCRIPT_DIR/app/main.py" ]; then
    fail "app/main.py not found. Are you running this from the extracted package?"
    exit 1
fi
ok "Application source present"

# ============================================================================
step "3/10" "Creating Python virtual environment"
# ============================================================================

if [ -d ".venv" ]; then
    warn "Existing .venv found, recreating..."
    rm -rf .venv
fi

$PYTHON -m venv .venv
ok "Created .venv/"

# ============================================================================
step "4/10" "Installing Python dependencies"
# ============================================================================

.venv/bin/pip install --upgrade pip > /dev/null 2>&1
ok "pip upgraded"

.venv/bin/pip install -r requirements.txt 2>&1 | tail -5

if .venv/bin/python -c "import flask, yaml; print(f'flask {flask.__version__}, PyYAML {yaml.__version__}')"; then
    ok "Python dependencies installed"
else
    fail "Failed to install Python dependencies"
    exit 1
fi

# ============================================================================
step "5/10" "Downloading tridentprotect-ctl CLI"
# ============================================================================

if [ -x bin/tridentprotect-ctl ]; then
    CURRENT_VER=$(./bin/tridentprotect-ctl version 2>/dev/null || echo "unknown")
    ask "Existing CLI found: $CURRENT_VER. Re-download? [y/N]: "
    read -r REPLY
    if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
        info "Keeping existing CLI"
    else
        rm -f bin/tridentprotect-ctl
    fi
fi

if [ ! -x bin/tridentprotect-ctl ]; then
    info "Downloading tridentprotect-ctl v${CLI_VERSION} from GitHub..."
    if curl -fsSL -o bin/tridentprotect-ctl "$CLI_URL"; then
        chmod +x bin/tridentprotect-ctl
        ok "CLI downloaded"
    else
        fail "Failed to download CLI"
        echo "       URL: $CLI_URL"
        echo "       Manual fix: place tridentprotect-ctl at bin/tridentprotect-ctl"
        exit 1
    fi
fi

CLI_VER=$(./bin/tridentprotect-ctl version 2>/dev/null | head -1 || echo "unknown")
ok "CLI ready: $CLI_VER"

# ============================================================================
step "6/10" "Generating config.yaml"
# ============================================================================

if [ -f config.yaml ]; then
    warn "Existing config.yaml found"
    ask "Overwrite with new (empty) config? [y/N]: "
    read -r REPLY
    if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
        info "Keeping existing config.yaml"
        SKIP_CONFIG=1
    fi
fi

if [ -z "$SKIP_CONFIG" ]; then
    # Generate random secret key
    SECRET_KEY=$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')

    # Only ask for listen port — cluster profiles are added later via Settings UI
    ask "Listen port [default: 8081]: "
    read -r LISTEN_PORT
    # Accept default if empty OR non-numeric (e.g. user typed "N" or pressed Enter)
    if [ -z "$LISTEN_PORT" ] || ! [[ "$LISTEN_PORT" =~ ^[0-9]+$ ]]; then
        LISTEN_PORT=8081
    fi

    # Write config.yaml with empty cluster profiles
    cat > config.yaml <<EOF
app:
  host: "0.0.0.0"
  port: ${LISTEN_PORT}
  debug: false
  secret_key: "${SECRET_KEY}"

cli:
  path: "bin/tridentprotect-ctl"

refresh:
  interval_sec: 30

appvault:
  default: ""
  namespace: "trident-protect"

clusters:
  active: ""
  profiles: {}
EOF
    ok "config.yaml created (empty cluster profiles)"
    info "Secret key generated (32-byte random)"
    info "Add cluster profiles via Settings → Clusters after first login"
fi

# ============================================================================
step "7/10" "Setting up authentication"
# ============================================================================

# Detect which CLI to use for auth
PLATFORM_CLI=""
if which oc > /dev/null 2>&1; then
    PLATFORM_CLI="oc"
elif which kubectl > /dev/null 2>&1; then
    PLATFORM_CLI="kubectl"
fi

if [ -n "$PLATFORM_CLI" ]; then
    # Check if already logged in
    if $PLATFORM_CLI whoami > /dev/null 2>&1 || [ "$PLATFORM_CLI" = "kubectl" ] && kubectl cluster-info > /dev/null 2>&1; then
        if [ "$PLATFORM_CLI" = "oc" ]; then
            WHOAMI_USER=$(oc whoami 2>/dev/null || echo "unknown")
        else
            WHOAMI_USER=$(kubectl config view --minify -o jsonpath='{.users[0].user.name}' 2>/dev/null || echo "configured")
        fi
        ok "Already authenticated as: $WHOAMI_USER"
        ask "Re-authenticate with a new token? [y/N]: "
        read -r REPLY
        if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
            SKIP_AUTH=1
        fi
    fi

    if [ -z "$SKIP_AUTH" ]; then
        ask "Paste bearer token (or press Enter to skip): "
        read -r TOKEN
        if [ -n "$TOKEN" ]; then
            # Get active cluster URL from config (if profile is set)
            if [ -f config.yaml ]; then
                ACTIVE=$(.venv/bin/python -c "import yaml; print(yaml.safe_load(open('config.yaml')).get('clusters', {}).get('active', ''))" 2>/dev/null || echo "")
                API_URL=$(.venv/bin/python -c "import yaml; print(yaml.safe_load(open('config.yaml'))['clusters']['profiles'].get('${ACTIVE}', {}).get('api_url', ''))" 2>/dev/null || echo "")
            fi
            if [ -n "$API_URL" ]; then
                if [ "$PLATFORM_CLI" = "oc" ]; then
                    if oc login "$API_URL" --token="$TOKEN" --insecure-skip-tls-verify=true > /dev/null 2>&1; then
                        ok "Logged in successfully (oc)"
                        WHOAMI_USER=$(oc whoami 2>/dev/null || echo "unknown")
                        info "Current user: $WHOAMI_USER"
                    else
                        warn "oc login failed, you may need to authenticate manually later"
                    fi
                else
                    # kubectl: write kubeconfig via config subcommands
                    CLUSTER_NAME="webui-cluster"
                    USER_NAME="webui-user"
                    CTX_NAME="webui-context"
                    if kubectl config set-cluster "$CLUSTER_NAME" --server="$API_URL" --insecure-skip-tls-verify=true > /dev/null 2>&1 \
                       && kubectl config set-credentials "$USER_NAME" --token="$TOKEN" > /dev/null 2>&1 \
                       && kubectl config set-context "$CTX_NAME" --cluster="$CLUSTER_NAME" --user="$USER_NAME" > /dev/null 2>&1 \
                       && kubectl config use-context "$CTX_NAME" > /dev/null 2>&1; then
                        ok "Logged in successfully (kubectl)"
                        WHOAMI_USER=$(kubectl config view --minify -o jsonpath='{.users[0].user.name}' 2>/dev/null || echo "webui-user")
                        info "Current user: $WHOAMI_USER"
                    else
                        warn "kubectl config set failed, you may need to configure kubeconfig manually"
                    fi
                fi
            else
                info "No active cluster profile in config.yaml — skipping login"
                info "Add a cluster profile via Settings → Clusters, then login through the UI"
            fi
        else
            info "Skipped token authentication"
            info "Run later: $PLATFORM_CLI login <api-url> --token=<your-token>"
        fi
    fi
else
    warn "Neither oc nor kubectl installed, skipping authentication setup"
    info "Install oc or kubectl, then login manually"
fi

# ============================================================================
step "8/10" "Installing systemd service"
# ============================================================================

if [ "$IS_ROOT" -eq 0 ]; then
    warn "Not running as root, skipping systemd install"
    info "Use 'nohup ./run.sh' to start manually"
else
    # Update systemd unit file with actual install path
    SERVICE_FILE="/etc/systemd/system/trident-protect-webui-k8s.service"
    USER_NAME="${SUDO_USER:-root}"
    INSTALL_PATH="$SCRIPT_DIR"

    sed -e "s|WorkingDirectory=.*|WorkingDirectory=${INSTALL_PATH}|" \
        -e "s|ExecStart=.*|ExecStart=${INSTALL_PATH}/.venv/bin/python3 -m app.main|" \
        -e "s|User=.*|User=${USER_NAME}|" \
        systemd/trident-protect-webui-k8s.service > "$SERVICE_FILE"

    ok "Service file installed: $SERVICE_FILE"

    systemctl daemon-reload
    ok "systemd daemon reloaded"

    systemctl enable trident-protect-webui > /dev/null 2>&1
    ok "Service enabled on boot"

    systemctl restart trident-protect-webui
    sleep 2

    if systemctl is-active --quiet trident-protect-webui; then
        ok "Service started"
        info "Status: systemctl status trident-protect-webui"
        info "Logs:   journalctl -u trident-protect-webui -f"
    else
        warn "Service failed to start, check logs:"
        systemctl status trident-protect-webui --no-pager || true
    fi
fi

# ============================================================================
step "9/10" "Configuring firewall"
# ============================================================================

if [ "$IS_ROOT" -eq 0 ]; then
    warn "Not running as root, skipping firewall config"
elif which ufw > /dev/null 2>&1; then
    if ufw status | grep -q "Status: active"; then
        ufw allow "${LISTEN_PORT}/tcp" > /dev/null 2>&1
        ok "ufw: opened port ${LISTEN_PORT}/tcp"
    else
        info "ufw not active, skipping"
    fi
elif which firewall-cmd > /dev/null 2>&1; then
    firewall-cmd --permanent --add-port="${LISTEN_PORT}/tcp" > /dev/null 2>&1
    firewall-cmd --reload > /dev/null 2>&1
    ok "firewalld: opened port ${LISTEN_PORT}/tcp"
else
    info "No firewall detected, manual config may be needed"
    info "Open port ${LISTEN_PORT}/tcp in your firewall"
fi

# ============================================================================
step "10/10" "Verifying installation"
# ============================================================================

# Config validation
if .venv/bin/python -c "from app.config import Config; Config.instance()"; then
    ok "Config valid"
else
    fail "Config validation failed"
    exit 1
fi

# CLI test
if ./bin/tridentprotect-ctl version > /dev/null 2>&1; then
    ok "CLI binary works"
else
    fail "CLI binary not executable"
    exit 1
fi

# Health check (only if service is running)
sleep 1
if curl -fsS --max-time 5 "http://127.0.0.1:${LISTEN_PORT}/healthz" > /dev/null 2>&1; then
    HEALTH=$(curl -fsS --max-time 5 "http://127.0.0.1:${LISTEN_PORT}/healthz")
    ok "Health check: $HEALTH"
else
    warn "Health check failed (service may still be starting up)"
    info "Wait a few seconds and check: curl http://localhost:${LISTEN_PORT}/healthz"
fi

# ============================================================================
# Summary
# ============================================================================

SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo ""
echo -e "${BOLD}${GREEN}========================================${NC}"
echo -e "${BOLD}${GREEN} Installation Complete!${NC}"
echo -e "${BOLD}${GREEN}========================================${NC}"
echo ""
echo -e "  ${BOLD}Web UI URL:${NC}     http://${SERVER_IP}:${LISTEN_PORT}"
echo -e "  ${BOLD}Local URL:${NC}      http://localhost:${LISTEN_PORT}"
echo ""
echo -e "  ${BOLD}Service:${NC}        systemctl status trident-protect-webui"
echo -e "  ${BOLD}Logs:${NC}           journalctl -u trident-protect-webui -f"
echo -e "  ${BOLD}Restart:${NC}        systemctl restart trident-protect-webui"
echo -e "  ${BOLD}Stop:${NC}           systemctl stop trident-protect-webui"
echo -e "  ${BOLD}Start:${NC}          systemctl start trident-protect-webui"
echo ""
echo -e "  ${BOLD}Manual start:${NC}   ./run.sh"
echo -e "  ${BOLD}Manual stop:${NC}    ./stop.sh"
echo ""
echo -e "  ${BOLD}Install path:${NC}   ${SCRIPT_DIR}"
echo ""
