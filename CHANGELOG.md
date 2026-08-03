## [v1.4.16] — 2026-08-03

### Changed
- Aligned version with OCP edition (v1.4.16)
- Fixed `login.html` version banner (was still v1.4.14)

---

## [v1.4.14] — 2026-08-02

### Changed — Restore: single panel + manual Validate gating + dest onchange (v1.4.9→v1.4.14)

**Single restoration panel** (no Form/YAML tabs):
- YAML always visible and editable; Load from form / Validate / Restore buttons
- Any form change regenerates the YAML immediately

**Manual Validate only** (v1.4.14):
- `markFormChanged()` no longer auto-validates — the Restore button stays disabled
  until the user clicks Validate and it succeeds
- Muted hints: "Select a source item to generate YAML" / "Form changed — click Validate to enable Restore"
- Manual YAML edit → "YAML modified — re-validate" (Restore disabled again)

**Destination changes re-validate** (v1.4.14):
- `#dest-ns` and `#dest-app` now fire `onchange="markFormChanged()"` — same behaviour
  as changing the source namespace (reset validation + regenerate YAML)

**CR generation fixes**:
- `metadata.namespace` = destination ns (cross-NS) / source ns (inplace) (v1.4.12)
- inline flow `namespaceMapping: [{"source": .., "destination": ..}]` matching the example YAMLs (v1.4.13)
- inplace restore CLI: pin `-n <source_namespace>` so the CR lands in the source ns

**Files changed (107 k8s)**:
- `app/trident_protect.py` — `-n` on inplace restore triggers
- `app/templates/restore.html` — single panel + validation gating + dest onchange

## [v1.4.8] — 2026-08-01

### Changed — Restore UX overhaul (mode radio first, no SC)

**New restore page layout** (mode radio picked FIRST, per user request):

```
1. Restore mode    ◉ Different namespace   ○ Same namespace — in place
2. Source          Type + Namespace + items list (no Source SC column)
3. Destination     Per-mode fields + auto-filled AppVault/AppArchivePath
4. Manifest        [Form]  [YAML] (editable + Validate + Apply)
5. History         4-kind types
```

The mode radio at the top drives which fields appear in Destination:
- **Different namespace** (default): Destination NS dropdown + optional App Name (Backup only).
- **Same namespace — in place**: just shows a note + the auto-filled AppVault/AppArchivePath.

**Removed everywhere**:
- SC mapping section (`sc-mapping-section`, `sc-mapping-rows`, `sc-mapping-status`)
- Default StorageClass dropdown
- Source SC column in items list
- Source Storage Classes row in view modals (Backups + Snapshots + Restores)
- `--storageclass-mapping` CLI flag from `trigger_backup_restore` / `trigger_snapshot_restore`
- `sourceStorageClasses` field from `serialize_backup` / `serialize_snapshot`
- Inline `restoreBackup` / `restoreSnap` functions and "Restore" buttons from
  Backups and Snapshots pages. All restore activity now happens on `/restore`
  only (via the Form or YAML tab).

**Form→YAML generator** now produces manifests matching the 4 example YAMLs
in `/root/example/*.yaml` exactly — no `storageclassMapping`, no extra fields:
- BackupRestore:         `appArchivePath, appVaultRef, destinationApplicationName?, namespaceMapping`
- BackupInplaceRestore:  `appArchivePath, appVaultRef`
- SnapshotRestore:       `appArchivePath, appVaultRef, namespaceMapping`
- SnapshotInplaceRestore: `appArchivePath, appVaultRef`

**Files changed (107 k8s)**:
- `app/trident_protect.py` — drop SC args/flags/fields from `trigger_*_restore`,
  drop `sourceStorageClasses` from serializers
- `app/main.py` — drop `storageclassMapping` body field from cross-NS endpoints
- `app/templates/restore.html` — full rewrite (596 lines, was 727)
- `app/templates/backups.html` — drop Source SC view row + JS + dead `restoreBackup` fn
- `app/templates/snapshots.html` — drop Source SC view row + dead `restoreSnap` fn

**Verified live on 107**:
- `GET /restore` (admin): mode radio visible, 17 references; (viewer): 5 references (admin-gated buttons hidden)
- `POST /api/backup/.../backuprestores` (admin): 200 OK
- `POST /api/snapshot/.../inplacerestore` (admin): 200 OK
- `POST /api/restore/validate`: accepts all 4 kinds
- `GET /api/restores`: all 4 kinds, no `sourceStorageClasses` field
- 12 page routes all return 200 ✓
- backups/snapshots pages: no inline Restore button, no Source SC row

## [v1.4.7] — 2026-08-01
## [v1.4.7] — 2026-08-01

### Added — Restore with all 4 kinds + Form/YAML tabs

Restores the 4 example restore kinds from `/root/example/*.yaml`:
- `BackupRestore` (cross-NS)
- `BackupInplaceRestore` (in place)
- `SnapshotRestore` (cross-NS)
- `SnapshotInplaceRestore` (in place)

**New restore mode** — radio: "Different namespace" (default) or "Same namespace — in place".
When "Same namespace" selected, the destination NS / app name / SC mapping
sections are hidden (inplace uses the cluster's existing SC).

**Form + YAML tabs** in restore.html (like create-app / create-schedule):
- **Form tab**: existing form + new mode toggle + auto-filled readonly
  AppVault + AppArchivePath fields.
- **YAML tab**: editable textarea with **Load from form** / **Validate**
  / **Apply YAML** buttons. Edits to the YAML are applied as-is (raw
  `kubectl apply -f -`).

**New backend functions in `trident_protect.py`:**
- `trigger_backup_inplace()` + `trigger_snapshot_inplace()` —
  call `tridentprotect-ctl create backupinplacerestore / snapshotinplacerestore`
- `validate_restore_yaml()` — parses + checks apiVersion + kind + required
  fields per kind (uses the example YAML schema).
- `apply_restore_yaml()` — `kubectl apply -f -` for the raw YAML apply path.
- `list_restores()` rewritten to query all 4 CR kinds (was 2).

**New endpoints in `main.py`:**
- `POST /api/backup/<ns>/<name>/inplacerestore`
- `POST /api/snapshot/<ns>/<name>/inplacerestore`
- `POST /api/restore/validate`
- `POST /api/restore/apply`

All admin-gated (readonly gets 403 via the existing
`_READONLY_WRITE_ALLOWLIST` / `_ADMIN_ONLY_PATHS` mechanism).

**Audit log labels** for the new kinds:
- `kind="backupinplacerestore"`, `action="trigger"`
- `kind="snapshotinplacerestore"`, `action="trigger"`
- `kind="restore"`, `action="apply"` (for raw YAML apply)

**Verified live on 107 (clus1 + clus2):**
- `POST /api/backup/<ns>/<name>/inplacerestore` (admin) → 200, CR applied.
- `POST /api/snapshot/<ns>/<name>/inplacerestore` (admin) → 200, CR applied.
- `POST /api/restore/validate` accepts all 4 kinds + rejects unknown kinds.
- `POST /api/restore/apply` applies user-edited YAML via `kubectl apply -f -`.
- `GET /api/restores` returns 4 kinds in `type` field.
- viewer gets 403 on all mutating endpoints ✓
- 12 page routes all return 200 ✓

### Files affected
- `app/trident_protect.py` — 4 new functions, 1 list_restores rewrite
- `app/main.py` — 4 new routes, 3 audit map entries
- `app/templates/restore.html` — full rewrite (Form/YAML tabs + radio mode)
- CHANGELOG, README, base.html, login.html, make-package.sh — version bump

## [v1.4.6] — 2026-08-01
## [v1.4.6] — 2026-08-01

### Fixed — Schedules + Restore parity with OCP v1.4.3

- **Schedules page (`schedules.html`):** full copy of 105 OCP version.
  Restores:
  - Admin-gated `+ Add Schedule` button
  - `tpRequireAdmin()` guards in 4 functions (showAddScheduleModal,
    deleteSchedule, validateScheduleYAML, applyScheduleYAML)
  - `Delete` row button is `isAdmin() ? ... : ''`
  - Disable/Enable toggle button in each schedule row (calls
    `toggleSchedule(ns, name, enable)`)
  - **k8s-adapted**: `toggleSchedule` resolves cluster context from the
    **active profile's** `kubeconfig_context` (instead of the OCP
    `clus1-/clus2-` namespace prefix → `clus1-ocp/clus2-ocp` profile).
  - Backend `_resolve_schedule_context` (in `main.py`) was already active-
    profile-based; the JS now matches.
- **Restore page (`restore.html`):** full copy of 105 OCP version
  (byte-identical, 0 diff). Restores:
  - Single radio select (replaces k8s multi-checkbox)
  - "Source SC" column in items list (per-item `sourceStorageClasses`)
  - SC mapping section (`sc-mapping-section`, `sc-mapping-rows`,
    `sc-mapping-status`) that shows a row per distinct source SC with
    a destination dropdown
  - `rebuildScMapping()` / `refreshMappingStatus()` / `getSelectedItems()`
    helper functions
  - `doRestore()` uses `tpFetch` + `tpRequireAdmin` + sends
    `storageclassMapping: "src1:dst1,src2:dst2"` to the backend
  - Improved history table (Type, Name, Source, Dest NS, State, Age,
    Actions with admin-gated Del)

### Deep button-by-button compare (105 OCP v1.4.3 vs 107 k8s v1.4.6)

| Template | 105 buttons | 107 buttons | Match |
| --- | --- | --- | --- |
| `schedules.html` | 13 | 13 | **exact** |
| `restore.html` | 6 | 6 | **exact** |
| `restore.html` diff lines | — | 0 | **byte-identical** |
| `schedules.html` diff lines | — | 8 (only the toggleSchedule context-resolution JS) | **k8s-adapted** |

### Verified live on 107
- Schedule enable/disable: admin → 200, viewer → 403 ✓
- Restore sources: 3 backups + 3 snapshots ✓
- Restore destinations: 9 namespaces + 4 storage classes ✓
- Restore history: 1 item ✓
- Restore trigger: admin can submit, viewer → 403 ✓

### Notes
- 105 OCP v1.4.3 was not modified (per user request); only read as source.
- No backend (`main.py`, `trident_protect.py`) changes needed — endpoints
  already support schedule enable/disable and storageclassMapping.

## [v1.4.5] — 2026-08-01

### Fixed — Credentials tab + Switch button

- **Settings → Credentials tab:** added admin-gated
  `<a href="/settings/credentials">Credentials</a>` in `settings_base.html`
  (105 had it, k8s was missing).
- **Switch button bug:** `async function switchToProfile(name)` was missing
  in k8s `settings.js` (the button's `onclick` was a JS error, so users
  were forced to click "Login" each time). Ported from 105.
- Version bump.

## [v1.4.4] — 2026-08-01
## [v1.4.4] — 2026-08-01

### Fixed — button-by-button parity with OCP v1.4.3 + auto-login

- **Cluster profile switch auto-login (item #1):**
  - Backend `api_switch_profile` now uses the stored `profile.token` to call
    `oc_login_with_token` automatically, so switching between clusters no
    longer requires pasting the bearer token every time.
  - `oc_login_with_token` (k8s branch) rewritten to use a **stable** cluster
    name derived from the api_url host (e.g. `webui-10-10-10-41`) instead
    of a random `webui-cluster-<hex8>`. Prevents kubeconfig pollution and
    makes `find_kubecontext_for_api` work reliably.
  - `settings.js` `renderProfiles` now shows a one-click "Switch" button
    when the profile has a stored token (and a "Login" re-auth button),
    matching 105.
  - Returns `auto_login:true` on success, `needs_reauth:true` on token
    failure (so the UI can show a "Login" button instead of looping).
- **Applications page (item #2):** admin-gated `+ Add Application`,
  admin-gated `Del` button, `tpRequireAdmin()` guard in
  `deleteApplication` / `validateAppYAML` / `applyAppYAML`.
- **Backups + Snapshots tables (item #3):**
  - Added "Schedule Source" + "Reclaim Policy" columns (matching 105;
    bumped table `colspan` 8→10).
  - Admin-gated `+ Add Backup/Snapshot`, `Del` row button, and the YAML
    validate/apply handlers.
  - Added "Source Storage Classes" row to the view modal.
  - `trident_protect.serialize_backup` / `serialize_snapshot` now return
    `reclaimPolicy`, `scheduleSource`, `sourceStorageClasses`.
  - Ported `_resolve_schedule_source` + `_derive_schedule_map` +
    `get_source_storageclasses` from 105.
- **DR page (item #4):** byte-identical to 105 (verified — 0 diff on
  `disaster_recovery.html`). Cluster switch on the DR page now works
  thanks to item #1.
- **Restore page:** added admin/readonly button split for
  "Restore Selected" (matching 105).

### Deep button-by-button compare (105 OCP v1.4.3 vs 107 k8s v1.4.4)

| Template | <button> | inline onclick | Match |
| --- | --- | --- | --- |
| `applications.html` | 11 | 9 | exact |
| `backups.html` | 11 | 9 | exact |
| `snapshots.html` | 11 | 9 | exact |
| `disaster_recovery.html` | 28 | 27 | exact |
| `settings_appvaults.html` | 5 | 6 | exact |
| `settings_credentials.html` | 5 | 5 | exact |
| `restore.html` | 6 | 5 | exact |
| `settings_clusters.html` | 9 vs 8 | 11 vs 9 | intentional (k8s has kubeconfig import, no password login) |
| `schedules.html` | 11 vs 13 | 9 | intentional gap (out of scope for this release) |

Cluster profile switch: admin and readonly both confirmed
`auto_login: true` on round-trip clus1 → clus2 → clus1 (no token paste).

### Notes
- 105 OCP v1.4.3 was not modified at any point (per user request).
- All work performed on 10.10.101.107.
- Stale `webui-cluster-<random8>` entries in `/root/.kube/config` on 107
  were cleaned up; only the 2 stable `webui-<host>` entries remain.

## [v1.4.3] — 2026-08-01
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
