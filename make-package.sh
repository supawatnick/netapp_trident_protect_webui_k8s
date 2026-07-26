#!/bin/bash
# Build the Trident Protect Web UI installation package (tar.gz)
# Excludes: the large CLI binary, runtime artifacts, secrets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CLI_VERSION="26.02.0"
PACKAGE_NAME="trident-protect-webui-v${CLI_VERSION}"
OUTPUT_DIR="${SCRIPT_DIR}/dist"
OUTPUT_FILE="${OUTPUT_DIR}/${PACKAGE_NAME}.tar.gz"

# --- Pre-flight checks ---
echo "=== Trident Protect Web UI — Package Builder ==="
echo ""

if [ ! -d app ] || [ ! -f install.sh ] || [ ! -f requirements.txt ]; then
    echo "ERROR: Must be run from the web/ directory"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

# --- Clean previous package ---
rm -rf "${OUTPUT_DIR:?}/${PACKAGE_NAME}"
rm -f "$OUTPUT_FILE"

# --- Build staging directory ---
STAGING="/tmp/${PACKAGE_NAME}"
rm -rf "$STAGING"
mkdir -p "$STAGING"

echo "Staging files..."

# Application source (Python + templates + static)
# Exclude __pycache__ and other runtime artifacts
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' app "$STAGING/"
echo "  ✓ app/"

# Scripts
cp install.sh "$STAGING/"
cp run.sh "$STAGING/"
cp stop.sh "$STAGING/"
echo "  ✓ install.sh, run.sh, stop.sh"

# Config template
cp config.example.yaml "$STAGING/"
echo "  ✓ config.example.yaml"

# Requirements
cp requirements.txt "$STAGING/"
echo "  ✓ requirements.txt"

# systemd unit
mkdir -p "$STAGING/systemd"
cp systemd/trident-protect-webui.service "$STAGING/systemd/"
echo "  ✓ systemd/trident-protect-webui.service"

# Make scripts executable
chmod +x "$STAGING/install.sh" "$STAGING/run.sh" "$STAGING/stop.sh"

# Create README for the package
cat > "$STAGING/README.md" <<'EOF'
# Trident Protect Web UI

Web UI for managing Trident Protect resources (Applications, Backups, Snapshots, Schedules, Restores, AppVaults) on OpenShift / Kubernetes clusters.

## Quick Install

```bash
tar xzf trident-protect-webui-v*.tar.gz
cd trident-protect-webui
sudo ./install.sh
```

The installer will:
1. Check prerequisites (Python 3.9+, pip, curl, oc/kubectl)
2. Set up directories
3. Create a Python virtual environment
4. Install Python dependencies
5. Download `tridentprotect-ctl` CLI from GitHub
6. Configure cluster connection (interactive)
7. Set up authentication (interactive)
8. Install systemd service
9. Configure firewall (open port 8080)
10. Verify installation

## After Install

| Action | Command |
|---|---|
| Open UI | `http://<server-ip>:8080` |
| Service status | `systemctl status trident-protect-webui` |
| View logs | `journalctl -u trident-protect-webui -f` |
| Restart | `systemctl restart trident-protect-webui` |
| Stop | `systemctl stop trident-protect-webui` |
| Manual start | `./run.sh` |
| Manual stop | `./stop.sh` |

## Requirements

- **OS:** Ubuntu 20.04+ / Debian 11+ (other Linux distros work with minor tweaks)
- **Python:** 3.9 or higher
- **Internet:** Required during install (to download CLI binary + Python deps)
- **OpenShift client (oc):** Required for token-based login + cluster queries
  - Download: https://mirror.openshift.com/pub/openshift-v4/clients/oc/
- **Trident Protect:** Must be installed on the target cluster (operator + CRDs)
- **AppVault:** Object storage target (ONTAP S3, AWS S3, MinIO, etc.)

## Configuration

Edit `config.yaml` after install to customize:

- **app:** host/port/secret_key
- **cli:** path to `tridentprotect-ctl`
- **appvault:** default backup/snapshot storage
- **clusters:** profiles (API URL, AppVault, TLS settings)

You can manage multiple clusters via the **Settings → Clusters** page in the UI.

## Architecture

```
trident-protect-webui/
├── install.sh            # Single-file installer
├── run.sh                # Manual start
├── stop.sh               # Manual stop
├── config.example.yaml   # Config template
├── requirements.txt      # flask, PyYAML
├── app/                  # Flask backend
│   ├── main.py          # Routes
│   ├── config.py        # Config loader
│   ├── trident_protect.py # CLI wrapper
│   ├── templates/       # HTML pages
│   └── static/          # CSS + JS
├── systemd/
│   └── trident-protect-webui.service
├── bin/
│   └── tridentprotect-ctl  # Downloaded by installer
└── .venv/               # Created by installer
```

## License

Internal NetApp tool.
EOF

echo "  ✓ README.md"

# --- Create .gitignore for the package ---
cat > "$STAGING/.gitignore" <<'EOF'
.venv/
bin/
config.yaml
logs/
*.log
.web.pid
__pycache__/
*.pyc
EOF

echo "  ✓ .gitignore"

# --- Compute package size ---
SIZE_KB=$(du -sk "$STAGING" | awk '{print $1}')
echo ""
echo "Staged package size: ${SIZE_KB}KB ($(($SIZE_KB / 1024))MB)"

# --- Create tarball ---
echo ""
echo "Creating ${OUTPUT_FILE}..."
tar czf "$OUTPUT_FILE" -C /tmp "$PACKAGE_NAME"

PACKAGE_SIZE=$(du -h "$OUTPUT_FILE" | awk '{print $1}')
echo ""
echo "=== Package built successfully ==="
echo ""
echo "  File:     $OUTPUT_FILE"
echo "  Size:     $PACKAGE_SIZE"
echo ""
echo "To install on target server:"
echo ""
echo "  scp ${OUTPUT_FILE} user@target:"
echo "  ssh user@target 'tar xzf ${PACKAGE_NAME}.tar.gz && cd ${PACKAGE_NAME} && sudo ./install.sh'"
echo ""

# --- Clean up staging ---
rm -rf "$STAGING"
