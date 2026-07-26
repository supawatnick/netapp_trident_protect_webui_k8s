# NetApp Trident Protect Web UI (Kubernetes Edition)

A comprehensive web-based management interface for **NetApp Trident Protect** resources on **vanilla Kubernetes** clusters. Manage Applications, Backups, Snapshots, Schedules, and AppVaults with an intuitive GUI — designed for SREs, platform engineers, and storage administrators.

> **This is the Kubernetes-only edition.** For OpenShift, see the separate `netapp_trident_protect_webui_ocp` repository.

---

## Features

- **Dashboard** — overview of all protected applications, backup/snapshot counts, health status
- **Application Management** — create, view, edit, and delete Application CRs via GUI or YAML
- **Backup Management** — trigger ad-hoc backups, browse history, trigger restores
- **Snapshot Management** — create snapshots from existing apps, monitor status
- **Schedule Management** — configure recurring backups/snapshots (Hourly, Daily, Weekly, Monthly)
- **Restore Wizard** — restore backups or snapshots to destination namespaces with SC mapping
- **AppVault Management** — create and manage object storage targets (ONTAP S3, AWS S3, Azure Blob, GCP GCS, StorageGrid)
- **Multi-Cluster Support** — manage multiple Kubernetes clusters from a single UI instance
- **CLI-based backend** — uses the official `tridentprotect-ctl` CLI for all resource operations

---

## Quick Install (Ubuntu / Debian)

### Prerequisites

- Ubuntu 20.04+ or Debian 11+
- Root access (for systemd + firewall)
- Internet connection (to download CLI + Python deps)
- A Kubernetes cluster with Trident Protect installed
- `kubectl` configured with cluster access (kubeconfig in `~/.kube/config`)

### One-Command Install

```bash
# 1. Download the package
wget https://github.com/supawatnick/netapp_trident_protect_webui_k8s/releases/download/v1.0.0/trident-protect-webui.tar.gz

# 2. Extract
tar xzf trident-protect-webui.tar.gz
cd trident-protect-webui

# 3. Install (one script, 10 steps, 2-3 minutes)
sudo ./install.sh
```

### Install via Git Clone

```bash
# 1. Clone the repository
git clone https://github.com/supawatnick/netapp_trident_protect_webui_k8s.git

# 2. Enter the directory
cd netapp_trident_protect_webui_k8s

# 3. Checkout the latest stable release (v1.0.0)
git checkout v1.0.0

# 4. Build the install package (creates dist/trident-protect-webui.tar.gz)
./make-package.sh

# 5. Extract and install
cd ..
tar xzf netapp_trident_protect_webui_k8s/dist/trident-protect-webui.tar.gz
cd trident-protect-webui
sudo ./install.sh
```

#### Clone a specific version (one command)

```bash
git clone -b v1.0.0 https://github.com/supawatnick/netapp_trident_protect_webui_k8s.git
cd netapp_trident_protect_webui_k8s
```

#### List all available versions (tags)

```bash
git ls-remote --tags https://github.com/supawatnick/netapp_trident_protect_webui_k8s.git
```

Or after cloning:

```bash
git tag -l
git checkout v1.0.0
```

---

## What `install.sh` does

| Step | Action |
|---|---|
| 1/10 | **Prerequisites** — auto-installs Python 3.9+, pip, venv, curl, kubectl, oc |
| 2/10 | **Directories** — creates `bin/`, `logs/` |
| 3/10 | **Virtual env** — creates isolated Python venv |
| 4/10 | **Dependencies** — installs Flask, PyYAML from `requirements.txt` |
| 5/10 | **CLI binary** — downloads `tridentprotect-ctl` from GitHub releases |
| 6/10 | **Config** — generates `config.yaml` (empty cluster profiles, random secret key) |
| 7/10 | **Authentication** — optional `kubectl config` or `oc login` setup |
| 8/10 | **systemd service** — installs + enables `trident-protect-webui.service` |
| 9/10 | **Firewall** — opens port 8081 (ufw / firewalld) |
| 10/10 | **Verify** — health check + CLI validation |

### Smart Auto-Install

The installer handles missing prerequisites gracefully:
- **python3 / pip / venv** → installs via `apt` if missing
- **curl** → installs via `apt` if missing
- **kubectl** → downloads from `dl.k8s.io` if missing (primary)
- **oc** → downloads from `mirror.openshift.com` if kubectl fails (fallback)
- **dpkg lock contention** → waits up to 120s for `unattended-upgrade` to finish

---

## Architecture

```
trident-protect-webui-k8s/
├── app/                       # Python Flask backend
│   ├── main.py                # API routes (40+ endpoints)
│   ├── config.py              # YAML config loader
│   ├── trident_protect.py     # CLI wrapper (kubectl/oc)
│   ├── templates/             # Jinja2 HTML templates
│   └── static/                # CSS + JS
├── systemd/
│   └── trident-protect-webui.service
├── config.example.yaml        # Config template
├── install.sh                 # Installer (10 steps)
├── make-package.sh            # Build tar.gz package
├── requirements.txt           # flask==3.1.3, PyYAML==6.0.3
├── run.sh / stop.sh           # Manual start/stop scripts
└── README.md
```

### Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.9+, Flask 3.1 |
| Frontend | Vanilla JS, Jinja2 templates |
| CSS | Custom NetApp design system |
| CLI wrapper | subprocess → `tridentprotect-ctl` |
| Service mgmt | systemd |
| Logging | journald |

---

## Configuration

`config.yaml` is generated by `install.sh` with empty cluster profiles:

```yaml
app:
  host: "0.0.0.0"
  port: 8081
  secret_key: "<random-32-bytes>"   # auto-generated

clusters:
  active: ""      # user adds via Settings UI
  profiles: {}    # user adds via Settings UI
```

**Add cluster profiles via the UI** → Settings → Clusters → "+ Add Profile". The UI supports:
- Multiple profiles per cluster type (prod, staging, dev)
- Switch active cluster with one click
- Token saved in `config.yaml` for seamless switching
- TLS skip verification per profile

---

## Service Management

The installer creates a systemd service:

```bash
# Status
systemctl status trident-protect-webui

# Start / Stop / Restart
sudo systemctl start trident-protect-webui
sudo systemctl stop trident-protect-webui
sudo systemctl restart trident-protect-webui

# Logs (live tail)
journalctl -u trident-protect-webui -f
```

Or run manually without systemd:

```bash
./run.sh      # Start in background
./stop.sh     # Stop
```

---

## API Reference

40+ REST endpoints under `/api/`:

| Resource | Endpoints |
|---|---|
| Dashboard | `GET /api/dashboard` |
| Health | `GET /healthz` |
| Platform | `GET /api/platform` |
| Applications | `GET/POST/DELETE /api/applications`, `GET /api/application/<ns>/<name>` |
| Backups | `GET/POST/DELETE /api/backups`, restore trigger |
| Snapshots | `GET/POST/DELETE /api/snapshots`, restore trigger |
| Schedules | `GET/POST/DELETE /api/schedules` |
| Restores | `GET /api/restores`, `DELETE /api/restore/<type>/<ns>/<name>` |
| AppVaults | `GET/POST/DELETE /api/appvaults` |
| Kubeconfig | `POST /api/settings/kubeconfig` (import) |
| Settings | `GET/POST /api/settings/*` (profile mgmt, login, switch) |

---

## Compatibility

### ✅ This version is for **vanilla Kubernetes** clusters

This release auto-detects your cluster platform:
- If `oc` CLI is available → uses OpenShift features
- If `kubectl` only → uses Kubernetes-compatible paths
- Both paths share the same UI and use `tridentprotect-ctl` for all CRUD operations

### Tested
- **Vanilla Kubernetes:** 1.28, 1.29, 1.30, 1.31
- **Trident Protect:** v26.02.0, v26.06.0
- **OS:** Ubuntu 20.04 / 22.04 / 24.04, Debian 11 / 12
- **Python:** 3.9, 3.10, 3.11, 3.12

### Backend Storage
- **NetApp ONTAP S3** (primary, tested)
- AWS S3, MinIO, Azure Blob, GCP GCS, StorageGrid S3 (via Trident Protect AppVault)

---

## Roadmap

**Separate repos:**
- [ ] **OpenShift edition** — see `netapp_trident_protect_webui_ocp` repo

**Future (this Kubernetes edition):**
- [ ] OIDC auth flow for k8s clusters
- [ ] Token refresh / session management
- [ ] Dark mode toggle
- [ ] Real-time log streaming
- [ ] Multi-language support (Thai, Japanese)
- [ ] RBAC integration
- [ ] Helm chart for Kubernetes-native deployment
- [ ] Docker / container image

---

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## License

Open source project. Use, modify, and distribute freely.

**Powered by NetApp Professional Service Asean Team & Nick R.**

---

## Support

For issues, questions, or feature requests:
- **GitHub Issues:** https://github.com/supawatnick/netapp_trident_protect_webui_k8s/issues
- **Trident docs:** https://docs.netapp.com/us-en/trident/index.html
- **Trident Protect:** https://docs.netapp.com/us-en/trident-protect/index.html
