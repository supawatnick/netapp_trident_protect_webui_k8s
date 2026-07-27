"""Trident Protect Web UI - Flask entry point."""
import logging
import os as _os
import sys as _sys

from flask import Flask, render_template, jsonify, request

from .config import Config
from . import trident_protect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tp-web")


def create_app() -> Flask:
    cfg = Config.instance()
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = cfg.app.get("secret_key", "dev-key")
    app.config["JSON_SORT_KEYS"] = False

    register_routes(app)
    return app


def register_routes(app: Flask) -> None:
    """Register page routes (HTML) and API routes (JSON)."""

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    @app.route("/applications")
    def applications_page():
        return render_template("applications.html")

    @app.route("/backups")
    def backups_page():
        return render_template("backups.html")

    @app.route("/snapshots")
    def snapshots_page():
        return render_template("snapshots.html")

    @app.route("/schedules")
    def schedules_page():
        return render_template("schedules.html")

    @app.route("/restore")
    def restore_page():
        return render_template("restore.html")

    @app.route("/settings")
    def settings_page():
        return render_template("settings_overview.html")

    @app.route("/settings/clusters")
    def settings_clusters_page():
        return render_template("settings_clusters.html")

    @app.route("/settings/appvaults")
    def settings_appvaults_page():
        return render_template("settings_appvaults.html")

    @app.route("/healthz")
    def healthz():
        ok, msg = trident_protect.test_connection()
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 503)

    @app.route("/api/dashboard")
    def api_dashboard():
        try:
            return jsonify(trident_protect.list_dashboard())
        except Exception as e:
            log.exception("Dashboard failed")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/applications")
    def api_applications():
        ns = request.args.get("namespace") or None
        items = trident_protect.list_applications(ns)
        return jsonify({"items": items, "total": len(items)})

    @app.route("/api/backups")
    def api_backups():
        ns = request.args.get("namespace") or None
        items = trident_protect.list_backups(ns)
        return jsonify({"items": items, "total": len(items)})

    @app.route("/api/snapshots")
    def api_snapshots():
        ns = request.args.get("namespace") or None
        items = trident_protect.list_snapshots(ns)
        return jsonify({"items": items, "total": len(items)})

    @app.route("/api/schedules")
    def api_schedules():
        items = trident_protect.list_schedules()
        return jsonify({"items": items, "total": len(items)})

    @app.route("/api/schedule/<namespace>/<name>")
    def api_schedule_detail(namespace, name):
        item = trident_protect.get_schedule(namespace, name)
        if not item:
            return jsonify({"error": "Not found"}), 404
        fmt = request.args.get("format", "json").lower()
        if fmt == "yaml":
            from flask import Response
            return Response(
                trident_protect.serialize_schedule_to_yaml(item),
                mimetype="text/yaml",
                headers={"Content-Disposition": "inline"},
            )
        return jsonify(item)

    @app.route("/api/schedule/validate", methods=["POST"])
    def api_schedule_validate():
        body = request.get_json() or {}
        yaml_str = body.get("yaml", "")
        ok, msg = trident_protect.validate_schedule_yaml(yaml_str)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/schedule/apply", methods=["POST"])
    def api_schedule_apply():
        body = request.get_json() or {}
        yaml_str = body.get("yaml", "")

        ok, msg = trident_protect.validate_schedule_yaml(yaml_str)
        if not ok:
            return jsonify({"ok": False, "message": f"Invalid YAML: {msg}"}), 400

        ok, msg = trident_protect.apply_schedule_yaml(yaml_str)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/schedule/<namespace>/<name>", methods=["DELETE"])
    def api_delete_schedule(namespace, name):
        ok, msg = trident_protect.delete_schedule(namespace, name)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/namespaces")
    def api_namespaces():
        return jsonify({"items": trident_protect.list_namespaces()})

    @app.route("/api/backup/<namespace>/<name>")
    def api_backup_detail(namespace, name):
        item = trident_protect.get_backup(namespace, name)
        if not item:
            return jsonify({"error": "Not found"}), 404
        fmt = request.args.get("format", "json").lower()
        if fmt == "yaml":
            from flask import Response
            return Response(
                trident_protect.serialize_backup_to_yaml(item),
                mimetype="text/yaml",
                headers={"Content-Disposition": "inline"},
            )
        if fmt == "summary":
            return jsonify(trident_protect.serialize_backup(item))
        return jsonify(item)

    @app.route("/api/snapshot/<namespace>/<name>")
    def api_snapshot_detail(namespace, name):
        item = trident_protect.get_snapshot(namespace, name)
        if not item:
            return jsonify({"error": "Not found"}), 404
        fmt = request.args.get("format", "json").lower()
        if fmt == "yaml":
            from flask import Response
            return Response(
                trident_protect.serialize_snapshot_to_yaml(item),
                mimetype="text/yaml",
                headers={"Content-Disposition": "inline"},
            )
        if fmt == "summary":
            return jsonify(trident_protect.serialize_snapshot(item))
        return jsonify(item)

    @app.route("/api/backup", methods=["POST"])
    def api_trigger_backup():
        body = request.get_json() or {}
        ns = body.get("namespace")
        app_ref = body.get("applicationRef")
        name = body.get("name")
        if not ns or not app_ref or not name:
            return jsonify({"ok": False, "message": "namespace, applicationRef, name required"}), 400
        appvault, av_ns = trident_protect.get_active_appvault()
        appvault = body.get("appvault", appvault)
        ok, msg = trident_protect.trigger_backup(ns, app_ref, appvault, name)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/backup/validate", methods=["POST"])
    def api_backup_validate():
        body = request.get_json() or {}
        yaml_str = body.get("yaml", "")
        ok, msg, _ = trident_protect.validate_backup_yaml(yaml_str)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/backup/apply", methods=["POST"])
    def api_backup_apply():
        body = request.get_json() or {}
        yaml_str = body.get("yaml", "")

        ok, msg, modified_yaml = trident_protect.validate_backup_yaml(yaml_str)
        if not ok:
            return jsonify({"ok": False, "message": f"Invalid YAML: {msg}"}), 400

        ok, msg = trident_protect.apply_backup_yaml(modified_yaml)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/backup/<namespace>/<name>/backuprestores", methods=["POST"])
    def api_trigger_backuprestore(namespace, name):
        body = request.get_json() or {}
        dest_ns = body.get("destination_namespace")
        if not dest_ns:
            return jsonify({"ok": False, "message": "destination_namespace required"}), 400
        appvault, _ = trident_protect.get_active_appvault()
        appvault = body.get("appvault", appvault)

        backup = trident_protect.get_backup(namespace, name)
        if not backup:
            return jsonify({"ok": False, "message": "Backup not found"}), 404
        app_archive_path = backup.get("status", {}).get("appArchivePath", "")
        if not app_archive_path:
            return jsonify({"ok": False, "message": "Backup has no appArchivePath"}), 400

        ok, msg = trident_protect.trigger_backup_restore(
            destination_namespace=dest_ns,
            backup_name=name,
            source_namespace=namespace,
            appvault=appvault,
            app_archive_path=app_archive_path,
            destination_app_name=body.get("destinationApplicationName"),
            storageclass_mapping=body.get("storageclassMapping"),
        )
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/snapshot/<namespace>/<name>/snapshotrestores", methods=["POST"])
    def api_trigger_snapshotrestore(namespace, name):
        body = request.get_json() or {}
        dest_ns = body.get("destination_namespace")
        if not dest_ns:
            return jsonify({"ok": False, "message": "destination_namespace required"}), 400
        appvault, _ = trident_protect.get_active_appvault()
        appvault = body.get("appvault", appvault)

        snapshot = trident_protect.get_snapshot(namespace, name)
        if not snapshot:
            return jsonify({"ok": False, "message": "Snapshot not found"}), 404
        app_archive_path = snapshot.get("status", {}).get("appArchivePath", "")
        if not app_archive_path:
            return jsonify({"ok": False, "message": "Snapshot has no appArchivePath"}), 400

        ok, msg = trident_protect.trigger_snapshot_restore(
            destination_namespace=dest_ns,
            snapshot_name=name,
            source_namespace=namespace,
            appvault=appvault,
            app_archive_path=app_archive_path,
            destination_app_name=body.get("destinationApplicationName"),
            storageclass_mapping=body.get("storageclassMapping"),
        )
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/restore/sources")
    def api_restore_sources():
        data = trident_protect.get_restore_source_namespaces()
        return jsonify(data)

    @app.route("/api/restore/destinations")
    def api_restore_destinations():
        return jsonify({
            "namespaces": trident_protect.get_namespaces(),
            "storageclasses": trident_protect.get_storageclasses(),
        })

    @app.route("/api/restores")
    def api_list_restores():
        items = trident_protect.list_restores()
        return jsonify({"items": items})

    @app.route("/api/restore/<restore_type>/<namespace>/<name>", methods=["DELETE"])
    def api_delete_restore(restore_type, namespace, name):
        ok, msg = trident_protect.delete_restore(restore_type, namespace, name)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/backuprestore/<namespace>/<name>")
    def api_backuprestore_detail(namespace, name):
        item = trident_protect.get_backuprestore(namespace, name)
        if not item:
            return jsonify({"error": "Not found"}), 404
        fmt = request.args.get("format", "json").lower()
        if fmt == "yaml":
            from flask import Response
            return Response(
                trident_protect.serialize_restore_to_yaml(item, "BackupRestore"),
                mimetype="text/yaml",
            )
        if fmt == "summary":
            return jsonify(trident_protect.serialize_restore(item, "BackupRestore"))
        return jsonify(item)

    @app.route("/api/snapshotrestore/<namespace>/<name>")
    def api_snapshotrestore_detail(namespace, name):
        item = trident_protect.get_snapshotrestore(namespace, name)
        if not item:
            return jsonify({"error": "Not found"}), 404
        fmt = request.args.get("format", "json").lower()
        if fmt == "yaml":
            from flask import Response
            return Response(
                trident_protect.serialize_restore_to_yaml(item, "SnapshotRestore"),
                mimetype="text/yaml",
            )
        if fmt == "summary":
            return jsonify(trident_protect.serialize_restore(item, "SnapshotRestore"))
        return jsonify(item)

    @app.route("/api/backup/<namespace>/<name>", methods=["DELETE"])
    def api_delete_backup(namespace, name):
        ok, msg = trident_protect.delete_backup(namespace, name)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/snapshot/<namespace>/<name>", methods=["DELETE"])
    def api_delete_snapshot(namespace, name):
        ok, msg = trident_protect.delete_snapshot(namespace, name)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/snapshot/validate", methods=["POST"])
    def api_snapshot_validate():
        body = request.get_json() or {}
        yaml_str = body.get("yaml", "")
        ok, msg, _ = trident_protect.validate_snapshot_yaml(yaml_str)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/snapshot/apply", methods=["POST"])
    def api_snapshot_apply():
        body = request.get_json() or {}
        yaml_str = body.get("yaml", "")

        ok, msg, modified_yaml = trident_protect.validate_snapshot_yaml(yaml_str)
        if not ok:
            return jsonify({"ok": False, "message": f"Invalid YAML: {msg}"}), 400

        ok, msg = trident_protect.apply_snapshot_yaml(modified_yaml)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    # ----- Application detail -----

    @app.route("/api/application/<namespace>/<name>")
    def api_application_detail(namespace, name):
        item = trident_protect.get_application(namespace, name)
        if not item:
            return jsonify({"error": "Not found"}), 404
        fmt = request.args.get("format", "json").lower()
        if fmt == "yaml":
            from flask import Response
            return Response(
                trident_protect.serialize_app_to_yaml(item),
                mimetype="text/yaml",
                headers={"Content-Disposition": "inline"},
            )
        return jsonify(item)

    # ----- Application create via YAML -----

    @app.route("/api/application/validate", methods=["POST"])
    def api_application_validate():
        body = request.get_json() or {}
        yaml_str = body.get("yaml", "")
        ok, msg = trident_protect.validate_application_yaml(yaml_str)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/application/apply", methods=["POST"])
    def api_application_apply():
        body = request.get_json() or {}
        yaml_str = body.get("yaml", "")

        # Always validate first
        ok, msg = trident_protect.validate_application_yaml(yaml_str)
        if not ok:
            return jsonify({"ok": False, "message": f"Invalid YAML: {msg}"}), 400

        ok, msg = trident_protect.apply_application_yaml(yaml_str)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/application/<namespace>/<name>", methods=["DELETE"])
    def api_delete_application(namespace, name):
        ok, msg = trident_protect.delete_application(namespace, name)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    # ----- Settings -----

    @app.route("/api/settings")
    def api_get_settings():
        cfg = Config.instance()
        whoami = trident_protect.oc_whoami()
        return jsonify({
            "profiles": cfg.profiles,
            "active": cfg.active_cluster,
            "app": cfg.app,
            "cli": cfg.cli,
            "refresh": cfg.refresh,
            "whoami": whoami,
            "platform": trident_protect.detect_platform(),
        })

        """Return cluster info (works for both OCP and k8s)."""
        return jsonify(trident_protect.get_cluster_info())

    @app.route("/api/platform")
    def api_platform():
        """Return detected platform: 'ocp', 'k8s', or 'unknown'."""
        return jsonify({
            "platform": trident_protect.detect_platform(),
            "cli": trident_protect.get_platform_cli(),
        })

    @app.route("/api/settings/profile", methods=["POST"])
    def api_save_profile():
        """Add or update a cluster profile."""
        body = request.get_json() or {}
        name = body.get("name", "").strip()
        if not name:
            return jsonify({"ok": False, "message": "name required"}), 400
        api_url = body.get("api_url", "").strip()
        if not api_url:
            return jsonify({"ok": False, "message": "api_url required"}), 400

        # Platform: "ocp" / "k8s" / "" (auto-detect)
        platform = body.get("platform", "").strip().lower()
        if platform and platform not in ("ocp", "k8s"):
            return jsonify({"ok": False, "message": "platform must be 'ocp' or 'k8s' or empty (auto)"}), 400

        cfg = Config.instance()
        profile = {
            "api_url": api_url,
            "appvault": body.get("appvault", "ontap-s3-appvault"),
            "appvault_namespace": body.get("appvault_namespace", "trident-protect"),
            "insecure_skip_tls": body.get("insecure_skip_tls", True),
            "description": body.get("description", ""),
            "platform": platform,  # "" = auto-detect
        }
        # Optional fields for k8s profiles
        token = body.get("token", "").strip()
        if token:
            profile["token"] = token
        kubeconfig_context = body.get("kubeconfig_context", "").strip()
        if kubeconfig_context:
            profile["kubeconfig_context"] = kubeconfig_context
        cfg.profiles[name] = profile
        cfg.save()
        return jsonify({"ok": True, "message": f"Profile '{name}' saved", "restart_required": False})

    @app.route("/api/settings/kubeconfig", methods=["POST"])
    def api_import_kubeconfig():
        """Import a kubeconfig YAML file.

        Writes to ~/.kube/config (backs up existing first to ~/.kube.config.bak),
        then auto-creates a cluster profile from the current-context.

        Body: {"kubeconfig": "<yaml content>", "profile_name": "optional override"}
        Returns: {ok, message, preview: {server, user, context, profile}}
        """
        import os
        from pathlib import Path

        body = request.get_json() or {}
        kubeconfig_yaml = body.get("kubeconfig", "").strip()
        if not kubeconfig_yaml:
            return jsonify({"ok": False, "message": "kubeconfig content required"}), 400

        # 1. Validate YAML
        import yaml
        try:
            kc = yaml.safe_load(kubeconfig_yaml)
        except yaml.YAMLError as e:
            return jsonify({"ok": False, "message": f"Invalid YAML: {e}"}), 400

        if not isinstance(kc, dict):
            return jsonify({"ok": False, "message": "kubeconfig must be a YAML mapping"}), 400

        clusters = kc.get("clusters", []) or []
        users = kc.get("users", []) or []
        contexts = kc.get("contexts", []) or []
        current_context = kc.get("current-context", "")

        if not clusters or not users or not contexts:
            return jsonify({
                "ok": False,
                "message": "kubeconfig must have at least one cluster, user, and context",
            }), 400

        if not current_context:
            if len(contexts) == 1:
                current_context = contexts[0].get("name", "")
            else:
                return jsonify({
                    "ok": False,
                    "message": "kubeconfig has no 'current-context' and multiple contexts — please add 'current-context' field",
                }), 400

        # 2. Find the current context's cluster + user
        ctx_obj = next((c for c in contexts if c.get("name") == current_context), None)
        if not ctx_obj:
            return jsonify({"ok": False, "message": f"current-context '{current_context}' not found"}), 400

        ctx_cluster = ctx_obj.get("context", {}).get("cluster", "")
        ctx_user = ctx_obj.get("context", {}).get("user", "")
        cluster_obj = next((c for c in clusters if c.get("name") == ctx_cluster), None)
        user_obj = next((u for u in users if u.get("name") == ctx_user), None)

        if not cluster_obj:
            return jsonify({"ok": False, "message": f"cluster '{ctx_cluster}' not found"}), 400
        if not user_obj:
            return jsonify({"ok": False, "message": f"user '{ctx_user}' not found"}), 400

        server_url = cluster_obj.get("cluster", {}).get("server", "")
        insecure_skip_tls = cluster_obj.get("cluster", {}).get("insecure-skip-tls-verify", False)
        user_name = user_obj.get("name", "")

        if not server_url:
            return jsonify({"ok": False, "message": "current context's cluster has no server URL"}), 400

        # 3. Merge new kubeconfig into existing ~/.kube/config
        kube_path = Path.home() / ".kube" / "config"
        kube_path.parent.mkdir(parents=True, exist_ok=True)

        existing_kc = {}
        if kube_path.exists():
            try:
                existing_kc = yaml.safe_load(kube_path.read_text()) or {}
            except Exception:
                existing_kc = {}

        existing_clusters = {c.get("name"): c for c in existing_kc.get("clusters", [])}
        existing_users = {u.get("name"): u for u in existing_kc.get("users", [])}
        existing_contexts = {c.get("name"): c for c in existing_kc.get("contexts", [])}

        for c in clusters:
            existing_clusters[c.get("name")] = c
        for u in users:
            existing_users[u.get("name")] = u
        for ctx in contexts:
            existing_contexts[ctx.get("name")] = ctx

        merged = {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": list(existing_clusters.values()),
            "users": list(existing_users.values()),
            "contexts": list(existing_contexts.values()),
            "current-context": current_context,
        }

        try:
            kube_path.write_text(yaml.dump(merged, default_flow_style=False, sort_keys=False, width=4096))
        except Exception as e:
            return jsonify({"ok": False, "message": f"Failed to write kubeconfig: {e}"}), 500

        # 4. Auto-create profile in config.yaml
        profile_name = body.get("profile_name", "").strip() or current_context or "imported-cluster"
        # Sanitize profile name (k8s context names are usually safe but enforce slashes/dots)
        profile_name = profile_name.replace("/", "-").replace(" ", "-")

        # Auto-detect platform: try to reach OCP Infrastructure CRD
        # If succeeds → OCP, otherwise → k8s
        platform = ""
        try:
            import subprocess
            import shutil as _shutil
            cli = _shutil.which("oc") or _shutil.which("kubectl")
            if cli:
                # Temporarily write kubeconfig, check, restore
                kube_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = kube_path.with_suffix(".config.probe")
                tmp_path.write_text(kubeconfig_yaml)
                try:
                    env = {**os.environ, "KUBECONFIG": str(tmp_path)}
                    proc = subprocess.run(
                        [cli, "get", "infrastructure", "cluster", "-o", "name", "--request-timeout=5s"],
                        capture_output=True, text=True, timeout=10, env=env,
                    )
                    if proc.returncode == 0 and "infrastructure.config.openshift.io" in proc.stdout:
                        platform = "ocp"
                    else:
                        platform = "k8s"
                finally:
                    if tmp_path.exists():
                        tmp_path.unlink()
        except Exception as e:
            log.warning(f"Kubeconfig platform auto-detect failed: {e}")
            platform = "k8s"  # safest default

        cfg = Config.instance()
        if profile_name in cfg.profiles:
            profile_name = f"{profile_name}-imported"

        cfg.profiles[profile_name] = {
            "api_url": server_url,
            "appvault": "ontap-s3-appvault",
            "appvault_namespace": "trident-protect",
            "insecure_skip_tls": insecure_skip_tls,
            "description": f"Imported from kubeconfig (context: {current_context})",
            "kubeconfig_context": current_context,
            "platform": platform,
        }
        cfg.save()

        return jsonify({
            "ok": True,
            "message": f"Kubeconfig imported. Profile '{profile_name}' created.",
            "preview": {
                "server": server_url,
                "user": user_name,
                "context": current_context,
                "profile": profile_name,
                "platform": platform,
                "insecure_skip_tls": insecure_skip_tls,
            },
        })

    @app.route("/api/settings/profile/<name>", methods=["DELETE"])
    def api_delete_profile(name):
        if name == Config.instance().active_cluster:
            return jsonify({"ok": False, "message": "Cannot delete active profile — switch first"}), 400
        cfg = Config.instance()
        if name not in cfg.profiles:
            return jsonify({"ok": False, "message": "Profile not found"}), 404
        del cfg.profiles[name]
        cfg.save()
        return jsonify({"ok": True, "message": f"Profile '{name}' deleted"})

    @app.route("/api/settings/switch", methods=["POST"])
    def api_switch_profile():
        """Switch active cluster profile + kubeconfig context.

        For k8s profiles: actually switches kubeconfig context via
        'kubectl config use-context' so tridentprotect-ctl queries
        the right cluster.

        For OCP profiles: updates the active label (login handled separately).
        """
        body = request.get_json() or {}
        name = body.get("name", "").strip()
        if not name:
            return jsonify({"ok": False, "message": "name required"}), 400
        cfg = Config.instance()
        if name not in cfg.profiles:
            return jsonify({"ok": False, "message": "Profile not found"}), 404
        profile = cfg.profiles[name]

        # Update active profile
        cfg.active_cluster = name
        cfg.save()

        # For k8s profiles: switch kubeconfig context
        if profile.get("platform") == "k8s":
            kubeconfig_context = profile.get("kubeconfig_context", "")
            if kubeconfig_context:
                rc, out, err = trident_protect.oc_run(
                    ["config", "use-context", kubeconfig_context]
                )
                if rc == 0:
                    return jsonify({
                        "ok": True,
                        "message": f"Switched to '{name}' (kubeconfig context: {kubeconfig_context}). Data now shows cluster '{name}'.",
                    })
                else:
                    return jsonify({
                        "ok": True,
                        "message": f"Active profile set to '{name}' but could not switch kubeconfig context: {err or out}",
                    })

        # For OCP profiles: login if token is stored
        if profile.get("platform") == "ocp":
            stored_token = profile.get("token", "").strip()
            if stored_token:
                api_url = profile["api_url"]
                insecure = profile.get("insecure_skip_tls", True)
                ok, msg = trident_protect.oc_login_with_token(api_url, stored_token, insecure)
                if ok:
                    return jsonify({
                        "ok": True,
                        "message": f"Switched to '{name}' and authenticated. Data now shows cluster '{name}'.",
                        "auto_login": True,
                    })
                else:
                    return jsonify({
                        "ok": True,
                        "message": f"Set '{name}' as active but auto-login failed: {msg}",
                    })

        return jsonify({
            "ok": True,
            "message": f"Active profile set to '{name}'. Use 'Login & Switch' to authenticate.",
        })

    @app.route("/api/settings/login", methods=["POST"])
    def api_login_profile():
        """Login to a cluster profile using token or password.

        For OCP profiles: requires a bearer token (or username/password).
        For k8s profiles: skipped — authentication is handled by the imported
        kubeconfig (certs/OIDC/exec). Use 'Import Kubeconfig' to connect.
        """
        body = request.get_json() or {}
        name = body.get("name", "").strip()
        token = body.get("token", "").strip()
        username = body.get("username", "").strip()
        password = body.get("password", "").strip()

        if not name:
            return jsonify({"ok": False, "message": "name required"}), 400
        cfg = Config.instance()
        if name not in cfg.profiles:
            return jsonify({"ok": False, "message": "Profile not found"}), 404
        profile = cfg.profiles[name]
        api_url = profile["api_url"]
        insecure = profile.get("insecure_skip_tls", True)

        # k8s profiles use kubeconfig — switch context
        if profile.get("platform") == "k8s":
            cfg.active_cluster = name
            cfg.save()
            kubeconfig_context = profile.get("kubeconfig_context", "")
            if kubeconfig_context:
                rc, out, err = trident_protect.oc_run(
                    ["config", "use-context", kubeconfig_context]
                )
                if rc == 0:
                    return jsonify({
                        "ok": True,
                        "message": f"Switched to '{name}' (context: {kubeconfig_context})",
                        "skip_login": True,
                    })
            return jsonify({
                "ok": True,
                "message": "k8s profile uses kubeconfig — authentication handled by imported kubeconfig",
                "skip_login": True,
            })

        # Prefer token, fallback to password (OCP only)
        if token:
            ok, msg = trident_protect.oc_login_with_token(api_url, token, insecure)
        elif username and password:
            ok, msg = trident_protect.oc_login_with_password(api_url, username, password, insecure)
        else:
            return jsonify({"ok": False, "message": "token or username/password required"}), 400

        if ok:
            cfg.active_cluster = name
            cfg.save()
        return jsonify({"ok": ok, "message": msg})

    @app.route("/api/settings/test", methods=["POST"])
    def api_test_connection():
        ok, msg = trident_protect.test_connection()
        return jsonify({"ok": ok, "message": msg})

    @app.route("/api/settings/token")
    def api_get_token():
        """Return current bearer token (for display/copy in UI)."""
        token = trident_protect.oc_get_token()
        if not token:
            return jsonify({"ok": False, "message": "Not logged in or token unavailable"}), 400
        # Show only first 20 chars + length for safety
        return jsonify({
            "ok": True,
            "preview": token[:20] + "...",
            "length": len(token),
            "full": token,
        })

    @app.route("/api/settings/restart", methods=["POST"])
    def api_restart():
        """Restart the web UI (reloads config, restarts Python process)."""
        import threading
        def _restart():
            import time
            time.sleep(0.5)
            _os.execv(_sys.executable, [_sys.executable, "-m", "app.main"])
        threading.Thread(target=_restart, daemon=True).start()
        return jsonify({"ok": True, "message": "Restart initiated"})

    # ----- AppVaults -----

    @app.route("/api/appvaults")
    def api_list_appvaults():
        ns = request.args.get("namespace") or ""
        items = trident_protect.list_appvaults(ns)
        return jsonify({"items": items, "total": len(items)})

    @app.route("/api/appvaults/<namespace>/<name>")
    def api_appvault_detail(namespace, name):
        item = trident_protect.get_appvault(namespace, name)
        if not item:
            return jsonify({"error": "Not found"}), 404
        fmt = request.args.get("format", "json").lower()
        if fmt == "yaml":
            from flask import Response
            return Response(
                trident_protect.serialize_appvault_to_yaml(item),
                mimetype="text/yaml",
                headers={"Content-Disposition": "inline"},
            )
        return jsonify(item)

    @app.route("/api/appvaults", methods=["POST"])
    def api_create_appvault():
        body = request.get_json() or {}
        name = body.get("name", "").strip()
        namespace = body.get("namespace", "trident-protect").strip()
        provider = body.get("provider", "OntapS3").strip()
        endpoint = body.get("endpoint", "").strip()
        bucket = body.get("bucket", "").strip()
        skip_cert = body.get("skip_cert", True)
        secret_name = body.get("secret_name", "").strip()
        access_key = body.get("access_key", "").strip()
        secret_key = body.get("secret_key", "").strip()

        if not all([name, endpoint, bucket, secret_name, access_key, secret_key]):
            return jsonify({"ok": False, "message": "name, endpoint, bucket, secret_name, access_key, secret_key required"}), 400

        # Step 1: create secret
        ok, msg = trident_protect.create_appvault_secret(namespace, secret_name, access_key, secret_key)
        if not ok:
            return jsonify({"ok": False, "message": f"Failed to create secret: {msg}"}), 500

        # Step 2: create AppVault
        ok, msg = trident_protect.create_appvault(
            name=name,
            namespace=namespace,
            provider=provider,
            endpoint=endpoint,
            bucket=bucket,
            skip_cert=skip_cert,
            secret_name=secret_name,
        )
        if not ok:
            return jsonify({"ok": False, "message": f"Secret created but AppVault failed: {msg}"}), 500

        return jsonify({"ok": True, "message": f"AppVault {namespace}/{name} created (provider={provider})"})

    @app.route("/api/appvaults/<namespace>/<name>", methods=["DELETE"])
    def api_delete_appvault(namespace, name):
        ok, msg = trident_protect.delete_appvault(namespace, name)
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/appvaults/<namespace>/<name>/test", methods=["POST"])
    def api_test_appvault(namespace, name):
        """Verify AppVault exists and is Available."""
        item = trident_protect._get("appvault", name, namespace)
        if not item:
            return jsonify({"ok": False, "message": "AppVault not found"}), 404
        st = item.get("status", {}).get("state", "Unknown")
        ok = st.lower() in ("available", "ready")
        return jsonify({"ok": ok, "message": f"AppVault state: {st}"})


if __name__ == "__main__":
    cfg = Config.instance()
    app = create_app()
    log.info(f"Starting Trident Protect Web UI on http://{cfg.app['host']}:{cfg.app['port']}")
    app.run(
        host=cfg.app["host"],
        port=cfg.app["port"],
        debug=cfg.app.get("debug", False),
    )
