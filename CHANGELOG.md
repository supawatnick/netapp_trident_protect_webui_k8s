# Changelog

All notable changes to the Trident Protect Web UI — Kubernetes Edition.

## [v1.4.3] — 2026-08-01

### Added — Feature parity with OCP edition (v1.4.3)
- **Login / RBAC**: dashboard authentication with local users + optional LDAP.
  - Default `admin / admin123` seeded on first run (change immediately).
  - Roles: `admin` (full access) and `readonly` (no mutating actions).
  - New page: `/login` + `/logout` + `/api/auth/login`.
  - Auth guard (`before_request`) blocks unauthenticated requests, restricts
    admin-only paths (`/api/credentials/`, `/api/audit/`), and denies writes
    for `readonly` outside the switch/login allowlist.
  - Session cookies (`HttpOnly`, `SameSite=Lax`).
- **Settings → Credentials** (admin only): local user CRUD + LDAP config
  (server, TLS, bind DN, user filter, admin group DNs) + LDAP test endpoint.
- **Logs menu** (admin only): JSON-lines audit trail at `logs/audit.log`
  covering every mutating action (login/logout, blocked 401/403 attempts,
  CRUD on apps/backups/snapshots/schedules/AppVaults, profile ops, DR ops).
  Filter by user/action/result/free-text, auto-refresh, paginated.
- **Disaster Recovery page**: full AppMirrorRelationship management — overview,
  create (Form + YAML), view, failover, resync, delete, and the 6-step
  Reverse (YAML) wizard. Supports 2 cluster profiles (source + destination).
- **Schedule enable/disable** (`/api/schedules/<ns>/<name>/enable|disable`):
  toggle `spec.enabled` via `kubectl patch`.
- **Trident version banner** (`/api/trident-version`): detects version on each
  profile, renders matched/mismatch badge in the sidebar; auto-refreshes
  every 10 minutes.
- **AppVault RBAC UI fix**: "+ Add AppVault" button hidden for readonly users;
  Del action hidden; tpRequireAdmin guards in JS.

### Changed — K8s-only edition
- **No `oc`**: cluster profile login is bearer-token only (writes a kubeconfig
  via `kubectl config set-cluster/set-credentials`); password auth removed.
  Import-kubeconfig path retained as alternative.
- **Settings → Clusters**: rewritten for K8s. Removed OCP-specific text,
  "Alternative: Username + Password" block, platform=ocp option in profile
  form, and the dual-platform platform display.
- **`/api/settings/login`**: now requires only a bearer token; `username`/
  `password` keys rejected.
- **CLI auto-detect simplified**: `detect_platform` still respects explicit
  per-profile override but the OCP-only install path is removed from
  `install.sh` (uses `kubectl` exclusively).
- **installer (`install.sh`)**:
  - `kubectl` is the only CLI installed (was `oc` or `kubectl`).
  - Drops the OCP `oc login` interactive auth step.
  - Default port: 8080 (was 8081 for k8s).
  - Writes a complete `config.yaml` with empty `clusters.profiles`,
    `logs:`, and `auth:` sections; admin user seeded on first run.
- **`config.yaml` schema**: gains `logs:` and `auth:` sections; `clusters.profiles[*]`
  no longer carries `platform` (always k8s); keeps `kubeconfig_context` and
  `token` for auto-login on switch.

### Security
- Session cookies HttpOnly + SameSite=Lax.
- All mutating endpoints (admin-only or role-gated) return 403 for readonly
  + 401 for unauthenticated (vs HTML redirect for unauthenticated pages).
- Audit log records 401/403 attempts with user, role, source, IP, path.
- Auth failure path has a 500 ms delay to slow brute force.
- LDAP bind password is masked on `/api/credentials/ldap` GET and only
  overwritten if a non-empty value is POSTed.

### Notes
- Branch: `main` (commit-on-main per user direction).
- Tested live on 10.10.101.107 (development host).
- Cluster profiles for k8s edition:
  - **clus1** → `https://10.10.10.41:6443`
  - **clus2** → `https://10.10.4.21:6443`
- Tokens for both clusters were created with cluster-admin scope and 10-year
  TTL (`kubectl -n kube-system create token k8s-ui-sa --duration=87600h`).
  Stored at `/root/token/clus1-token.txt` and `/root/token/clus2-token.txt`
  on 107 (mode 0600, gitignored).

## [v1.0.0] — 2026-07-26 (initial Kubernetes-only edition)
- Initial release derived from the OpenShift edition.
- K8s-only, with platform auto-detect, import-kubeconfig, context switch.
