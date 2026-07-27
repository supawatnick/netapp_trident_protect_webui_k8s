"""High-level Trident Protect operations via tridentprotect-ctl CLI.

Supports both OpenShift (oc) and vanilla Kubernetes (kubectl) clusters.
Platform detection happens once at startup.
"""
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

log = logging.getLogger("tp-protect")

CLI_PATH = str(Path(__file__).parent.parent / "bin" / "tridentprotect-ctl")
TIMEOUT_SEC = 60

# Platform detection — active profile's `platform` field takes priority,
# falls back to auto-detect from binaries on disk.
_PLATFORM_AUTODETECTED = None  # cache for auto-detected value (binary check)


def _autodetect_platform() -> str:
    """Auto-detect platform from available binaries.

    Detection strategy:
      1. If 'oc' binary exists → 'ocp'
      2. Else if 'kubectl' binary exists → 'k8s'
      3. Else → 'unknown'
    """
    global _PLATFORM_AUTODETECTED
    if _PLATFORM_AUTODETECTED is not None:
        return _PLATFORM_AUTODETECTED
    if shutil.which("oc"):
        _PLATFORM_AUTODETECTED = "ocp"
    elif shutil.which("kubectl"):
        _PLATFORM_AUTODETECTED = "k8s"
    else:
        _PLATFORM_AUTODETECTED = "unknown"
    log.info(f"Auto-detected platform (from binaries): {_PLATFORM_AUTODETECTED}")
    return _PLATFORM_AUTODETECTED


def _get_active_profile() -> dict:
    """Read the currently active profile from config.yaml.

    Returns {} if no active profile or config unavailable.
    """
    try:
        from app.config import Config
        cfg = Config.instance()
        return cfg.active_profile or {}
    except Exception:
        return {}


def detect_platform() -> str:
    """Detect cluster platform: 'ocp' (OpenShift) or 'k8s' (vanilla Kubernetes).

    Resolution order:
      1. Active profile's `platform` field (manual override) — 'ocp' or 'k8s'
      2. Auto-detect from binaries (oc vs kubectl)
      3. 'unknown'
    """
    profile = _get_active_profile()
    explicit = profile.get("platform", "").strip().lower()
    if explicit in ("ocp", "k8s"):
        return explicit
    return _autodetect_platform()


def get_platform_cli() -> str:
    """Return the CLI binary to use for cluster operations: 'oc' or 'kubectl'."""
    platform = detect_platform()
    if platform == "ocp":
        return "oc"
    elif platform == "k8s":
        return "kubectl"
    return "oc"  # fallback; will fail if not installed


def _cli_path() -> str:
    """Resolve CLI path; allow override via env var."""
    p = os.environ.get("TRIDENTPROTECT_CTL", get_cli_path())
    return p


def _run(args, timeout=TIMEOUT_SEC) -> tuple[int, str, str]:
    """Run tridentprotect-ctl and return (rc, stdout, stderr)."""
    proc = subprocess.run(
        [get_cli_path()] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _list(resource: str, namespace: str = "") -> list[dict]:
    """List resources cluster-wide or in a namespace. Returns parsed JSON items."""
    args = ["get", resource, "-o", "json"]
    if namespace:
        args += ["-n", namespace]
    else:
        args += ["-A"]
    rc, out, err = _run(args)
    if rc != 0:
        return []
    try:
        data = json.loads(out)
        return data.get("items", []) or []
    except json.JSONDecodeError:
        return []


def _get(resource: str, name: str, namespace: str) -> dict | None:
    """Get a single resource."""
    rc, out, err = _run(["get", resource, name, "-n", namespace, "-o", "json"])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# --- Time formatting helpers ---

def _fmt_time(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


def _age(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo)
        diff = now - dt
        secs = int(diff.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return ts


def _fmt_bytes(b: int | None) -> str:
    if b is None:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(b)
    for u in units:
        if size < 1024:
            return f"{size:.1f} {u}"
        size /= 1024
    return f"{size:.1f} PB"


def _state_class(state: str) -> str:
    s = (state or "").lower()
    if s in ("completed", "success"):
        return "success"
    if s in ("failed", "error"):
        return "error"
    if s in ("running", "inprogress", "pending", ""):
        return "pending"
    return "unknown"


# --- Serializers ---

def serialize_application(app: dict) -> dict:
    md = app.get("metadata", {})
    st = app.get("status", {})
    return {
        "name": md.get("name"),
        "namespace": md.get("namespace"),
        "created": _fmt_time(md.get("creationTimestamp")),
        "age": _age(md.get("creationTimestamp")),
        "protectionState": st.get("protectionState", "Unknown"),
        "protectionHealthState": st.get("protectionHealthState", "Unknown"),
        "details": st.get("protectionStateDetails", []),
        "resourceCount": st.get("resourceCount", 0),
        "storageBytes": st.get("storageCapacityBytes"),
        "storageHuman": _fmt_bytes(st.get("storageCapacityBytes")),
    }


def serialize_backup(b: dict) -> dict:
    md = b.get("metadata", {})
    sp = b.get("spec", {})
    st = b.get("status", {})
    return {
        "name": md.get("name"),
        "namespace": md.get("namespace"),
        "created": _fmt_time(md.get("creationTimestamp")),
        "age": _age(md.get("creationTimestamp")),
        "applicationRef": sp.get("applicationRef"),
        "appVaultRef": sp.get("appVaultRef"),
        "state": st.get("state", "Unknown"),
        "stateClass": _state_class(st.get("state")),
        "appArchivePath": st.get("appArchivePath"),
        "error": st.get("error"),
        "completionTime": _fmt_time(st.get("completionTimestamp")),
    }


def serialize_snapshot(s: dict) -> dict:
    md = s.get("metadata", {})
    sp = s.get("spec", {})
    st = s.get("status", {})
    return {
        "name": md.get("name"),
        "namespace": md.get("namespace"),
        "created": _fmt_time(md.get("creationTimestamp")),
        "age": _age(md.get("creationTimestamp")),
        "applicationRef": sp.get("applicationRef"),
        "appVaultRef": sp.get("appVaultRef"),
        "state": st.get("state", "Unknown"),
        "stateClass": _state_class(st.get("state")),
        "appArchivePath": st.get("appArchivePath"),
        "error": st.get("error"),
    }


def serialize_schedule(s: dict) -> dict:
    md = s.get("metadata", {})
    sp = s.get("spec", {})
    st = s.get("status", {})
    lrp = st.get("lastRecoveryPoints", {}) or {}
    return {
        "name": md.get("name"),
        "namespace": md.get("namespace"),
        "created": _fmt_time(md.get("creationTimestamp")),
        "age": _age(md.get("creationTimestamp")),
        "applicationRef": sp.get("applicationRef"),
        "granularity": sp.get("granularity", "Unknown"),
        "enabled": sp.get("enabled", False),
        "backupRetention": sp.get("backupRetention"),
        "snapshotRetention": sp.get("snapshotRetention"),
        "lastScheduleTime": _fmt_time(st.get("lastScheduleTime")),
        "lastScheduleTimeAgo": _age(st.get("lastScheduleTime")),
        "lastBackup": (lrp.get("backup") or {}).get("name"),
        "lastSnapshot": (lrp.get("snapshot") or {}).get("name"),
    }


# --- List API ---

def get_active_appvault() -> tuple[str, str]:
    """Return (appvault_name, appvault_namespace) from active profile or legacy config."""
    from .config import Config
    cfg = Config.instance()
    if cfg.active_profile:
        return (
            cfg.active_profile.get("appvault", "ontap-s3-appvault"),
            cfg.active_profile.get("appvault_namespace", "trident-protect"),
        )
    return (
        cfg.appvault.get("name", "ontap-s3-appvault"),
        cfg.appvault.get("namespace", "trident-protect"),
    )


def get_cli_path() -> str:
    """Return path to tridentprotect-ctl CLI."""
    from .config import Config
    cfg = Config.instance()
    p = cfg.cli.get("path", "bin/tridentprotect-ctl")
    if not os.path.isabs(p):
        # Resolve relative to project root
        return str(Path(__file__).parent.parent / p)
    return p


def _get_active_kubeconfig_context() -> str:
    """Return the kubeconfig context name from the active profile's kubeconfig_context field.

    This is used to pass --context to tridentprotect-ctl so it queries
    the correct cluster when switching between multiple k8s profiles.
    Returns empty string if no context is set (use kubeconfig current-context).
    """
    try:
        profile = _get_active_profile()
        return profile.get("kubeconfig_context", "")
    except Exception:
        return ""


def oc_run(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run platform CLI (oc or kubectl) and return (rc, stdout, stderr).

    The CLI binary is determined per-call:
    - Active profile's `platform` field (manual override) — 'ocp' or 'k8s'
    - Auto-detect: 'oc' if available, else 'kubectl'

    For tridentprotect-ctl calls that need a specific cluster context,
    pass --context=<context_name> based on the active profile.

    Returns (127, "", "kubectl not found") if the binary doesn't exist.
    """
    cli = get_platform_cli()
    if not shutil.which(cli):
        return 127, "", f"{cli} not found in PATH"
    proc = subprocess.run(
        [cli] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def oc_login_with_token(api_url: str, token: str, insecure: bool = True) -> tuple[bool, str]:
    """Login to cluster using bearer token (updates kubeconfig).

    For OpenShift: uses `oc login --token=...`
    For vanilla Kubernetes: writes kubeconfig directly via `kubectl config`.
    """
    platform = detect_platform()
    if platform == "ocp":
        args = ["login", api_url, "--token", token]
        if insecure:
            args.append("--insecure-skip-tls-verify")
        rc, out, err = oc_run(args, timeout=30)
        if rc == 0:
            return True, (out or "Login successful").strip()
        return False, (err or out).strip()
    elif platform == "k8s":
        # Manually write kubeconfig via kubectl config subcommands
        import uuid
        cluster_name = f"webui-cluster-{uuid.uuid4().hex[:8]}"
        user_name = f"webui-user-{uuid.uuid4().hex[:8]}"
        context_name = f"webui@{cluster_name}"
        steps = [
            ["config", "set-cluster", cluster_name, f"--server={api_url}"]
            + (["--insecure-skip-tls-verify=true"] if insecure else []),
            ["config", "set-credentials", user_name, f"--token={token}"],
            ["config", "set-context", context_name, f"--cluster={cluster_name}", f"--user={user_name}"],
            ["config", "use-context", context_name],
        ]
        for step in steps:
            rc, out, err = oc_run(step, timeout=15)
            if rc != 0:
                return False, (err or out or f"kubectl {step[0]} failed").strip()
        return True, f"Logged in to {api_url}"
    else:
        return False, "No oc or kubectl binary available"


def oc_login_with_password(api_url: str, username: str, password: str, insecure: bool = True) -> tuple[bool, str]:
    """Login to cluster using username/password (updates kubeconfig).

    Only available on OpenShift. Vanilla Kubernetes clusters use
    OIDC tokens, not username/password, so this returns an error
    on k8s. Users should use a kubeconfig file or token auth.
    """
    platform = detect_platform()
    if platform != "ocp":
        return False, (
            "Username/password login is only supported on OpenShift. "
            "For vanilla Kubernetes, use a bearer token via 'Login with Token' or "
            "manually configure your kubeconfig."
        )
    args = ["login", api_url, "-u", username, "-p", password]
    if insecure:
        args.append("--insecure-skip-tls-verify")
    rc, out, err = oc_run(args, timeout=30)
    if rc == 0:
        return True, (out or "Login successful").strip()
    return False, (err or out).strip()


def oc_whoami() -> dict:
    """Return current user/server info from kubeconfig.

    For OpenShift: uses 'oc user' and 'oc server' for richer info.
    For vanilla Kubernetes: parses 'kubectl config view --minify' output.
    """
    info = {"user": "", "server": "", "context": "", "token_expires": ""}
    platform = detect_platform()

    if platform == "ocp":
        for field, key in [("user", "user"), ("server", "server")]:
            rc, out, err = oc_run([field, "-o", "json"], timeout=10)
            if rc == 0:
                try:
                    data = json.loads(out)
                    info[key] = data.get(key, "")
                except Exception:
                    info[key] = out.strip()
    elif platform == "k8s":
        # Use kubectl config view to get user, server, context
        rc, out, err = oc_run(["config", "view", "--minify", "-o", "json"], timeout=10)
        if rc == 0:
            try:
                data = json.loads(out)
                # Extract user
                users = data.get("users", [])
                if users:
                    info["user"] = users[0].get("name", "")
                # Extract server
                clusters = data.get("clusters", [])
                if clusters:
                    info["server"] = clusters[0].get("cluster", {}).get("server", "")
            except Exception:
                pass

    rc, out, _ = oc_run(["config", "current-context"], timeout=10)
    if rc == 0:
        info["context"] = out.strip()
    return info


def oc_get_token() -> str:
    """Get the current bearer token.

    For OpenShift: uses 'oc whoami -t'.
    For vanilla Kubernetes: parses the token from kubeconfig
    (only works if the user authenticated with a bearer token;
    x509 cert-based auth returns empty).
    """
    platform = detect_platform()
    if platform == "ocp":
        rc, out, _ = oc_run(["whoami", "-t"], timeout=10)
        if rc == 0:
            return out.strip()
        return ""
    elif platform == "k8s":
        # Try to extract token from kubeconfig
        rc, out, _ = oc_run(["config", "view", "--minify", "-o", "json"], timeout=10)
        if rc == 0:
            try:
                data = json.loads(out)
                users = data.get("users", [])
                if users:
                    token = users[0].get("user", {}).get("token", "")
                    if token:
                        return token
            except Exception:
                pass
        return ""
    return ""


def get_cluster_info() -> dict:
    """Get current cluster info (works for both OCP and k8s).

    Returns: {name, platform, api_url, version}

    For OpenShift:
      - name: from 'oc get infrastructure cluster'
      - platform: OCP platform (BareMetal, AWS, etc.)
      - version: openshiftVersion from 'oc version'
    For vanilla Kubernetes:
      - name: from 'kubectl config current-context' context name
      - platform: 'kubernetes'
      - version: gitVersion from 'kubectl version'
    """
    info = {"name": "", "platform": "", "api_url": "", "version": ""}
    platform = detect_platform()

    if platform == "ocp":
        try:
            rc, out, _ = oc_run(
                ["get", "infrastructure", "cluster", "-o", "json"],
                timeout=10,
            )
            if rc == 0:
                data = json.loads(out)
                st = data.get("status", {})
                info["name"] = st.get("infrastructureName", "")
                info["platform"] = st.get("platform", "")
                info["api_url"] = st.get("apiServerURL", "")
        except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.warning(f"get_cluster_info (OCP) failed: {e}")

        rc, out, _ = oc_run(["version", "-o", "json"], timeout=10)
        if rc == 0:
            try:
                v = json.loads(out)
                info["version"] = v.get("openshiftVersion", "")
            except Exception:
                pass
    elif platform == "k8s":
        info["platform"] = "kubernetes"
        # Get cluster name from current-context
        rc, out, _ = oc_run(["config", "current-context"], timeout=10)
        if rc == 0:
            info["name"] = out.strip()
        # Get API server URL
        rc, out, _ = oc_run(["config", "view", "--minify", "-o", "json"], timeout=10)
        if rc == 0:
            try:
                data = json.loads(out)
                clusters = data.get("clusters", [])
                if clusters:
                    info["api_url"] = clusters[0].get("cluster", {}).get("server", "")
            except Exception:
                pass
        # Get version
        rc, out, _ = oc_run(["version", "-o", "json"], timeout=10)
        if rc == 0:
            try:
                v = json.loads(out)
                info["version"] = v.get("serverVersion", {}).get("gitVersion", "")
            except Exception:
                pass

    return info


# Backward-compat alias (legacy name used in main.py)
get_ocp_cluster_info = get_cluster_info


def list_namespaces() -> list[dict]:
    """List all Active namespaces in the cluster via oc/kubectl CLI.

    tridentprotect-ctl does not support core v1 namespace resource,
    so we shell out to the platform CLI.
    """
    try:
        proc = subprocess.run(
            [get_platform_cli(), "get", "ns", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0:
            return []
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.error(f"list_namespaces failed: {e}")
        return []

    items = []
    for ns in data.get("items", []):
        phase = ns.get("status", {}).get("phase", "Unknown")
        if phase != "Active":
            continue
        items.append({
            "name": ns["metadata"]["name"],
            "status": phase,
        })
    items.sort(key=lambda x: x["name"])
    return items


def list_applications(namespace: str | None = None) -> list[dict]:
    items = [serialize_application(a) for a in _list("application", namespace or "")]
    if namespace:
        items = [i for i in items if i.get("namespace") == namespace]
    return items


def list_backups(namespace: str | None = None) -> list[dict]:
    return [serialize_backup(b) for b in _list("backup", namespace or "")]


def list_snapshots(namespace: str | None = None) -> list[dict]:
    return [serialize_snapshot(s) for s in _list("snapshot", namespace or "")]


def list_schedules() -> list[dict]:
    return [serialize_schedule(s) for s in _list("schedule")]


# --- AppVault management ---

def _get_appvault_error(av: dict) -> str:
    """Extract first error message from AppVault status.conditions."""
    conds = av.get("status", {}).get("conditions", []) or []
    for c in conds:
        if c.get("status", "").lower() == "false" or (c.get("type", "").startswith("error")):
            return c.get("message", c.get("reason", "Unknown error"))
    return ""


def serialize_appvault(av: dict) -> dict:
    md = av.get("metadata", {})
    sp = av.get("spec", {})
    st = av.get("status", {})
    pc = sp.get("providerConfig", {}).get("s3", {})
    return {
        "name": md.get("name"),
        "namespace": md.get("namespace"),
        "created": _fmt_time(md.get("creationTimestamp")),
        "age": _age(md.get("creationTimestamp")),
        "provider": sp.get("providerType", "Unknown"),
        "bucket": pc.get("bucketName", "—"),
        "endpoint": pc.get("endpoint", "—"),
        "state": st.get("state", "Unknown"),
        "stateClass": _state_class(st.get("state")),
        "error": _get_appvault_error(av),
    }


def get_appvault(namespace: str, name: str) -> dict | None:
    return _get("appvault", name, namespace)


def serialize_appvault_to_yaml(av: dict) -> str:
    """Convert AppVault CR dict to valid YAML string."""
    clean = {**av}
    if "apiVersion" not in clean:
        clean["apiVersion"] = "protect.trident.netapp.io/v1"
    if "kind" not in clean:
        clean["kind"] = "AppVault"
    ordered = {
        "apiVersion": clean.pop("apiVersion"),
        "kind": clean.pop("kind"),
        "metadata": {},
        "spec": {},
        "status": {},
    }
    if isinstance(clean.get("metadata"), dict):
        ordered["metadata"] = {
            k: v for k, v in clean["metadata"].items()
            if k not in ("managedFields",)
        }
        del clean["metadata"]
    ordered["spec"] = clean.pop("spec", {})
    ordered["status"] = clean.pop("status", {})
    for k, v in clean.items():
        ordered[k] = v
    return _yaml.dump(
        ordered,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        allow_unicode=True,
        width=4096,
    )


def list_appvaults(namespace: str = "") -> list[dict]:
    items = _list("appvault", namespace) if namespace else _list("appvault")
    items = [av for av in items if av.get("metadata", {}).get("namespace", "").startswith("trident")]
    return [serialize_appvault(av) for av in items]


# --- Application management ---

import yaml as _yaml

def validate_application_yaml(yaml_str: str) -> tuple[bool, str]:
    """Parse + validate Application YAML without applying."""
    try:
        doc = _yaml.safe_load(yaml_str)
    except _yaml.YAMLError as e:
        return False, f"YAML syntax error: {e}"
    if not isinstance(doc, dict):
        return False, "YAML must be a single document (mapping)"

    kind = doc.get("kind")
    if kind != "Application":
        return False, f"kind must be 'Application' (got '{kind}')"

    api_version = doc.get("apiVersion", "")
    if not api_version.startswith("protect.trident.netapp.io"):
        return False, f"apiVersion must start with 'protect.trident.netapp.io' (got '{api_version}')"

    metadata = doc.get("metadata", {}) or {}
    name = metadata.get("name")
    ns = metadata.get("namespace")
    if not name:
        return False, "metadata.name required"
    if not ns:
        return False, "metadata.namespace required"

    spec = doc.get("spec", {}) or {}
    if not spec.get("includedNamespaces"):
        return False, "spec.includedNamespaces required (list of namespace selectors)"

    return True, f"Valid — will create Application '{name}' in namespace '{ns}'"


def apply_application_yaml(yaml_str: str) -> tuple[bool, str]:
    """Apply Application YAML via `oc apply -f -` (stdin)."""
    proc = subprocess.run(
        [get_platform_cli(), "apply", "-f", "-"],
        input=yaml_str,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode == 0:
        return True, (proc.stdout or "Application applied").strip()
    return False, (proc.stderr or proc.stdout).strip()


def delete_application(namespace: str, name: str) -> tuple[bool, str]:
    rc, out, err = _run(["delete", "application", name, "-n", namespace])
    if rc == 0:
        return True, out.strip() or f"Deleted {namespace}/{name}"
    return False, (err or out).strip()


def create_appvault_secret(namespace: str, name: str, access_key: str, secret_key: str) -> tuple[bool, str]:
    """Create a Kubernetes Secret for AppVault credentials."""
    proc = subprocess.run(
        [
            get_platform_cli(), "create", "secret", "generic", name,
            f"--namespace={namespace}",
            f"--from-literal=accessKeyID={access_key}",
            f"--from-literal=secretAccessKey={secret_key}",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode == 0:
        return True, f"Secret {namespace}/{name} created"
    err = (proc.stderr or proc.stdout).strip()
    if "already exists" in err.lower():
        return True, f"Secret {namespace}/{name} already exists"
    return False, err


def create_appvault(
    name: str,
    namespace: str,
    provider: str,
    endpoint: str,
    bucket: str,
    skip_cert: bool,
    secret_name: str,
) -> tuple[bool, str]:
    """Create AppVault via CLI."""
    args = [
        "create", "appvault", provider, name,
        "-n", namespace,
        "--bucket", bucket,
        "--endpoint", endpoint,
        "--skip-cert-validation" if skip_cert else "",
        "-s", secret_name,
    ]
    args = [a for a in args if a]  # remove empty strings
    rc, out, err = _run(args)
    if rc == 0:
        return True, (out or f"AppVault {namespace}/{name} created").strip()
    return False, (err or out).strip()


def delete_appvault(namespace: str, name: str) -> tuple[bool, str]:
    rc, out, err = _run(["delete", "appvault", name, "-n", namespace])
    if rc == 0:
        return True, (out or f"Deleted AppVault {namespace}/{name}").strip()
    return False, (err or out).strip()


def list_dashboard() -> dict:
    apps = list_applications()
    backups = list_backups()
    snapshots = list_snapshots()
    schedules = list_schedules()

    healthy = sum(1 for a in apps if a["protectionState"] == "Protected")
    partial = sum(1 for a in apps if a["protectionState"] == "Partial")
    unprotected = sum(1 for a in apps if a["protectionState"] in ("Not Protected", "None"))
    completed_backups = sum(1 for b in backups if b["stateClass"] == "success")
    failed_backups = sum(1 for b in backups if b["stateClass"] == "error")
    completed_snapshots = sum(1 for s in snapshots if s["stateClass"] == "success")
    enabled_schedules = sum(1 for s in schedules if s["enabled"])

    return {
        "totals": {
            "applications": len(apps),
            "backups": len(backups),
            "snapshots": len(snapshots),
            "schedules": len(schedules),
        },
        "health": {
            "applicationsProtected": healthy,
            "applicationsPartial": partial,
            "applicationsUnprotected": unprotected,
            "backupsCompleted": completed_backups,
            "backupsFailed": failed_backups,
            "snapshotsCompleted": completed_snapshots,
            "schedulesEnabled": enabled_schedules,
        },
    }


def get_backup(namespace: str, name: str) -> dict | None:
    return _get("backup", name, namespace)


def get_snapshot(namespace: str, name: str) -> dict | None:
    return _get("snapshot", name, namespace)


def get_application(namespace: str, name: str) -> dict | None:
    return _get("application", name, namespace)


def get_backuprestore(namespace: str, name: str) -> dict | None:
    return _get("backuprestore", name, namespace)


def get_snapshotrestore(namespace: str, name: str) -> dict | None:
    return _get("snapshotrestore", name, namespace)


def serialize_app_to_yaml(app: dict) -> str:
    """Convert Application CR dict to valid YAML string.

    Removes noisy metadata (managedFields, annotations) and dumps
    with PyYAML so the output can be copied directly into `oc apply -f`.
    Adds apiVersion/kind if missing (CLI output omits them).
    """
    clean = {**app}
    # Ensure apiVersion and kind are present (CLI output may omit them)
    if "apiVersion" not in clean:
        clean["apiVersion"] = "protect.trident.netapp.io/v1"
    if "kind" not in clean:
        clean["kind"] = "Application"
    # Move apiVersion/kind to top for canonical order
    ordered = {
        "apiVersion": clean.pop("apiVersion"),
        "kind": clean.pop("kind"),
        "metadata": {},
        "spec": {},
        "status": {},
    }
    if isinstance(clean.get("metadata"), dict):
        ordered["metadata"] = {
            k: v for k, v in clean["metadata"].items()
            if k not in ("managedFields", "annotations")
        }
        del clean["metadata"]
    ordered["spec"] = clean.pop("spec", {})
    ordered["status"] = clean.pop("status", {})
    # Re-insert any extra top-level keys (shouldn't be any, but be safe)
    for k, v in clean.items():
        ordered[k] = v
    return _yaml.dump(
        ordered,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        allow_unicode=True,
        width=4096,
    )


# --- Backup management ---

def serialize_backup_to_yaml(b: dict) -> str:
    """Convert Backup CR dict to valid YAML string."""
    clean = {**b}
    if "apiVersion" not in clean:
        clean["apiVersion"] = "protect.trident.netapp.io/v1"
    if "kind" not in clean:
        clean["kind"] = "Backup"
    ordered = {
        "apiVersion": clean.pop("apiVersion"),
        "kind": clean.pop("kind"),
        "metadata": {},
        "spec": {},
        "status": {},
    }
    if isinstance(clean.get("metadata"), dict):
        ordered["metadata"] = {
            k: v for k, v in clean["metadata"].items()
            if k not in ("managedFields", "annotations")
        }
        del clean["metadata"]
    ordered["spec"] = clean.pop("spec", {})
    ordered["status"] = clean.pop("status", {})
    for k, v in clean.items():
        ordered[k] = v
    return _yaml.dump(
        ordered,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        allow_unicode=True,
        width=4096,
    )


def validate_backup_yaml(yaml_str: str) -> tuple[bool, str, str]:
    """Parse + validate Backup YAML without applying.

    Returns (ok, message, modified_yaml_str) where modified_yaml_str contains
    any auto-generated values (e.g. metadata.name if not provided).
    """
    try:
        doc = _yaml.safe_load(yaml_str)
    except _yaml.YAMLError as e:
        return False, f"YAML syntax error: {e}", yaml_str
    if not isinstance(doc, dict):
        return False, "YAML must be a single document (mapping)", yaml_str

    kind = doc.get("kind")
    if kind != "Backup":
        return False, f"kind must be 'Backup' (got '{kind}')", yaml_str

    api_version = doc.get("apiVersion", "")
    if not api_version.startswith("protect.trident.netapp.io"):
        return False, f"apiVersion must start with 'protect.trident.netapp.io' (got '{api_version}')", yaml_str

    metadata = doc.get("metadata", {}) or {}
    name = metadata.get("name")
    ns = metadata.get("namespace")
    if not name:
        # Auto-generate name if not provided
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"manual-backup-{ts}"
        if "metadata" not in doc:
            doc["metadata"] = {}
        doc["metadata"]["name"] = name
        metadata = doc["metadata"]
        yaml_str = _yaml.dump(doc, default_flow_style=False, sort_keys=False, width=4096)
    if not ns:
        return False, "metadata.namespace required", yaml_str

    spec = doc.get("spec", {}) or {}
    if not spec.get("applicationRef"):
        return False, "spec.applicationRef required", yaml_str

    return True, f"Valid — will create Backup '{name}' in namespace '{ns}'", yaml_str


def apply_backup_yaml(yaml_str: str) -> tuple[bool, str]:
    """Apply Backup YAML via `oc apply -f -` (stdin)."""
    proc = subprocess.run(
        [get_platform_cli(), "apply", "-f", "-"],
        input=yaml_str,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode == 0:
        return True, (proc.stdout or "Backup applied").strip()
    return False, (proc.stderr or proc.stdout).strip()


# --- Snapshot management ---

def serialize_snapshot_to_yaml(s: dict) -> str:
    """Convert Snapshot CR dict to valid YAML string."""
    clean = {**s}
    if "apiVersion" not in clean:
        clean["apiVersion"] = "protect.trident.netapp.io/v1"
    if "kind" not in clean:
        clean["kind"] = "Snapshot"
    ordered = {
        "apiVersion": clean.pop("apiVersion"),
        "kind": clean.pop("kind"),
        "metadata": {},
        "spec": {},
        "status": {},
    }
    if isinstance(clean.get("metadata"), dict):
        ordered["metadata"] = {
            k: v for k, v in clean["metadata"].items()
            if k not in ("managedFields",)
        }
        del clean["metadata"]
    ordered["spec"] = clean.pop("spec", {})
    ordered["status"] = clean.pop("status", {})
    for k, v in clean.items():
        ordered[k] = v
    return _yaml.dump(
        ordered,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        allow_unicode=True,
        width=4096,
    )


def serialize_restore_to_yaml(r: dict, kind: str) -> str:
    """Convert BackupRestore/SnapshotRestore CR dict to valid YAML string."""
    clean = {**r}
    if "apiVersion" not in clean:
        clean["apiVersion"] = "protect.trident.netapp.io/v1"
    if "kind" not in clean:
        clean["kind"] = kind
    ordered = {
        "apiVersion": clean.pop("apiVersion"),
        "kind": clean.pop("kind"),
        "metadata": {},
        "spec": {},
        "status": {},
    }
    if isinstance(clean.get("metadata"), dict):
        ordered["metadata"] = {
            k: v for k, v in clean["metadata"].items()
            if k not in ("managedFields",)
        }
        del clean["metadata"]
    ordered["spec"] = clean.pop("spec", {})
    ordered["status"] = clean.pop("status", {})
    for k, v in clean.items():
        ordered[k] = v
    return _yaml.dump(
        ordered,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        allow_unicode=True,
        width=4096,
    )


def validate_snapshot_yaml(yaml_str: str) -> tuple[bool, str, str]:
    """Parse + validate Snapshot YAML without applying.

    Returns (ok, message, modified_yaml_str) where modified_yaml_str contains
    any auto-generated values (e.g. metadata.name if not provided).
    """
    try:
        doc = _yaml.safe_load(yaml_str)
    except _yaml.YAMLError as e:
        return False, f"YAML syntax error: {e}", yaml_str
    if not isinstance(doc, dict):
        return False, "YAML must be a single document (mapping)", yaml_str

    kind = doc.get("kind")
    if kind != "Snapshot":
        return False, f"kind must be 'Snapshot' (got '{kind}')", yaml_str

    api_version = doc.get("apiVersion", "")
    if not api_version.startswith("protect.trident.netapp.io"):
        return False, f"apiVersion must start with 'protect.trident.netapp.io' (got '{api_version}')", yaml_str

    metadata = doc.get("metadata", {}) or {}
    name = metadata.get("name")
    ns = metadata.get("namespace")
    if not name:
        # Auto-generate name if not provided
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"manual-snap-{ts}"
        if "metadata" not in doc:
            doc["metadata"] = {}
        doc["metadata"]["name"] = name
        metadata = doc["metadata"]
        yaml_str = _yaml.dump(doc, default_flow_style=False, sort_keys=False, width=4096)
    if not ns:
        return False, "metadata.namespace required", yaml_str

    spec = doc.get("spec", {}) or {}
    if not spec.get("applicationRef"):
        return False, "spec.applicationRef required", yaml_str

    return True, f"Valid — will create Snapshot '{name}' in namespace '{ns}'", yaml_str


def apply_snapshot_yaml(yaml_str: str) -> tuple[bool, str]:
    """Apply Snapshot YAML via `oc apply -f -` (stdin)."""
    proc = subprocess.run(
        [get_platform_cli(), "apply", "-f", "-"],
        input=yaml_str,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode == 0:
        return True, (proc.stdout or "Snapshot applied").strip()
    return False, (proc.stderr or proc.stdout).strip()


# --- Schedule management ---

def get_schedule(namespace: str, name: str) -> dict | None:
    return _get("schedule", name, namespace)


def serialize_schedule_to_yaml(sch: dict) -> str:
    """Convert Schedule CR dict to valid YAML string."""
    clean = {**sch}
    if "apiVersion" not in clean:
        clean["apiVersion"] = "protect.trident.netapp.io/v1"
    if "kind" not in clean:
        clean["kind"] = "Schedule"
    ordered = {
        "apiVersion": clean.pop("apiVersion"),
        "kind": clean.pop("kind"),
        "metadata": {},
        "spec": {},
        "status": {},
    }
    if isinstance(clean.get("metadata"), dict):
        ordered["metadata"] = {
            k: v for k, v in clean["metadata"].items()
            if k not in ("managedFields", "annotations")
        }
        del clean["metadata"]
    ordered["spec"] = clean.pop("spec", {})
    ordered["status"] = clean.pop("status", {})
    for k, v in clean.items():
        ordered[k] = v
    return _yaml.dump(
        ordered,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        allow_unicode=True,
        width=4096,
    )


def validate_schedule_yaml(yaml_str: str) -> tuple[bool, str]:
    """Parse + validate Schedule YAML without applying."""
    try:
        doc = _yaml.safe_load(yaml_str)
    except _yaml.YAMLError as e:
        return False, f"YAML syntax error: {e}"
    if not isinstance(doc, dict):
        return False, "YAML must be a single document (mapping)"

    kind = doc.get("kind")
    if kind != "Schedule":
        return False, f"kind must be 'Schedule' (got '{kind}')"

    api_version = doc.get("apiVersion", "")
    if not api_version.startswith("protect.trident.netapp.io"):
        return False, f"apiVersion must start with 'protect.trident.netapp.io' (got '{api_version}')"

    metadata = doc.get("metadata", {}) or {}
    name = metadata.get("name")
    ns = metadata.get("namespace")
    if not name:
        return False, "metadata.name required"
    if not ns:
        return False, "metadata.namespace required"

    spec = doc.get("spec", {}) or {}
    if not spec.get("applicationRef"):
        return False, "spec.applicationRef required"

    return True, f"Valid — will create Schedule '{name}' in namespace '{ns}'"


def apply_schedule_yaml(yaml_str: str) -> tuple[bool, str]:
    """Apply Schedule YAML via `oc apply -f -` (stdin)."""
    proc = subprocess.run(
        [get_platform_cli(), "apply", "-f", "-"],
        input=yaml_str,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode == 0:
        return True, (proc.stdout or "Schedule applied").strip()
    return False, (proc.stderr or proc.stdout).strip()


def delete_schedule(namespace: str, name: str) -> tuple[bool, str]:
    rc, out, err = _run(["delete", "schedule", name, "-n", namespace])
    if rc == 0:
        return True, out.strip() or f"Deleted {namespace}/{name}"
    return False, (err or out).strip()


# --- Trigger actions ---

def trigger_backup(namespace: str, application_ref: str, appvault: str, backup_name: str) -> tuple[bool, str]:
    """Trigger on-demand Backup via CLI."""
    rc, out, err = _run([
        "create", "backup", backup_name,
        "--app", application_ref,
        "--appvault", appvault,
        "-n", namespace,
        "--data-mover", "Kopia",
        "--reclaim-policy", "Retain",
    ])
    if rc == 0:
        return True, out.strip() or f"Backup {backup_name} triggered in {namespace}"
    return False, (err or out).strip()


def trigger_backup_restore(
    destination_namespace: str,
    backup_name: str,
    source_namespace: str,
    appvault: str,
    app_archive_path: str,
    destination_app_name: str | None = None,
    storageclass_mapping: str | None = None,
) -> tuple[bool, str]:
    """Trigger BackupRestore via CLI.

    Uses --backup <ns>/<name> to let the CLI auto-resolve the AppVault +
    archive path. Explicit appvault/path are accepted for API symmetry but
    not needed when --backup is provided (mutually exclusive flags).
    """
    args = [
        "create", "backuprestore", f"restore-{backup_name}",
        "--backup", f"{source_namespace}/{backup_name}",
        "--namespace-mapping", f"{source_namespace}:{destination_namespace}",
        "-n", destination_namespace,
    ]
    if destination_app_name:
        args += ["--destination-app-name", destination_app_name]
    if storageclass_mapping:
        args += ["--storageclass-mapping", storageclass_mapping]

    rc, out, err = _run(args)
    if rc == 0:
        return True, out.strip() or f"BackupRestore triggered to {destination_namespace}"
    return False, (err or out).strip()


def trigger_snapshot_restore(
    destination_namespace: str,
    snapshot_name: str,
    source_namespace: str,
    appvault: str,
    app_archive_path: str,
    destination_app_name: str | None = None,
    storageclass_mapping: str | None = None,
) -> tuple[bool, str]:
    """Trigger SnapshotRestore via CLI.

    Uses --snapshot <ns>/<name> to let the CLI auto-resolve the AppVault +
    archive path. Explicit appvault/path are accepted for API symmetry but
    not needed when --snapshot is provided (mutually exclusive flags).
    """
    args = [
        "create", "snapshotrestore", f"snapshot-restore-{snapshot_name}",
        "--snapshot", f"{source_namespace}/{snapshot_name}",
        "--namespace-mapping", f"{source_namespace}:{destination_namespace}",
        "-n", destination_namespace,
    ]
    if destination_app_name:
        args += ["--destination-app-name", destination_app_name]
    if storageclass_mapping:
        args += ["--storageclass-mapping", storageclass_mapping]

    rc, out, err = _run(args)
    if rc == 0:
        return True, out.strip() or f"SnapshotRestore triggered to {destination_namespace}"
    return False, (err or out).strip()


def delete_backup(namespace: str, name: str) -> tuple[bool, str]:
    rc, out, err = _run(["delete", "backup", name, "-n", namespace])
    if rc == 0:
        return True, out.strip() or f"Deleted {namespace}/{name}"
    return False, (err or out).strip()


def delete_snapshot(namespace: str, name: str) -> tuple[bool, str]:
    rc, out, err = _run(["delete", "snapshot", name, "-n", namespace])
    if rc == 0:
        return True, out.strip() or f"Deleted {namespace}/{name}"
    return False, (err or out).strip()


def get_restore_source_namespaces() -> dict:
    """Return namespaces that have completed backups or snapshots, plus the items."""
    backups = [b for b in _list("backup") if b.get("status", {}).get("state", "").lower() in ("completed", "success")]
    snapshots = [s for s in _list("snapshot") if s.get("status", {}).get("state", "").lower() in ("completed", "success")]
    ns_set = set()
    for b in backups:
        ns_set.add(b.get("metadata", {}).get("namespace", ""))
    for s in snapshots:
        ns_set.add(s.get("metadata", {}).get("namespace", ""))
    return {
        "namespaces": sorted(ns_set),
        "backups": [serialize_backup(b) for b in backups],
        "snapshots": [serialize_snapshot(s) for s in snapshots],
    }


def list_restores() -> list[dict]:
    """List all BackupRestores and SnapshotRestores."""
    results = []
    for r in _list("backuprestore"):
        results.append(serialize_restore(r, "BackupRestore"))
    for r in _list("snapshotrestore"):
        results.append(serialize_restore(r, "SnapshotRestore"))
    return results


def serialize_restore(r: dict, restore_type: str) -> dict:
    md = r.get("metadata", {})
    sp = r.get("spec", {})
    st = r.get("status", {})
    conds = st.get("conditions", []) or []
    error_msg = ""
    for c in conds:
        if c.get("status", "").lower() == "false" or "error" in (c.get("type", "")).lower():
            error_msg = c.get("message", c.get("reason", ""))
            break
    if not error_msg:
        error_msg = st.get("error", "")
    return {
        "name": md.get("name"),
        "namespace": md.get("namespace"),
        "type": restore_type,
        "created": _fmt_time(md.get("creationTimestamp")),
        "age": _age(md.get("creationTimestamp")),
        "state": st.get("state", "Unknown"),
        "stateClass": _state_class(st.get("state")),
        "sourceRef": sp.get("backupRef") or sp.get("snapshotRef") or "",
        "destinationNamespace": sp.get("destinationNamespace", ""),
        "error": error_msg,
        "conditions": conds,
    }


def delete_restore(restore_type: str, namespace: str, name: str) -> tuple[bool, str]:
    resource = "backuprestore" if "Backup" in restore_type else "snapshotrestore"
    rc, out, err = _run(["delete", resource, name, "-n", namespace])
    if rc == 0:
        return True, out.strip() or f"Deleted {namespace}/{name}"
    return False, (err or out).strip()


def get_storageclasses() -> list[str]:
    """Return list of StorageClass names via oc/kubectl."""
    proc = subprocess.run(
        [get_platform_cli(), "get", "sc", "-o", "jsonpath={.items[*].metadata.name}"],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode == 0:
        return sorted(proc.stdout.strip().split())
    return []


def get_namespaces() -> list[str]:
    """Return list of non-system namespaces via oc/kubectl."""
    proc = subprocess.run(
        [get_platform_cli(), "get", "ns", "-o",
         "jsonpath={.items[?(@.status.phase==\"Active\")].metadata.name}"],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode == 0:
        all_ns = proc.stdout.strip().split()
        return sorted([n for n in all_ns if not n.startswith("openshift-")
                       and not n.startswith("kube-") and n != "trident-protect"])
    return []


def test_connection() -> tuple[bool, str]:
    """Check CLI works."""
    rc, out, err = _run(["version"], timeout=10)
    if rc == 0:
        return True, out.strip() or "Connected"
    return False, (err or out).strip() or "CLI failed"
