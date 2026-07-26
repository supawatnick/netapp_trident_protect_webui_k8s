"""Configuration loader for Trident Protect Web UI."""
import os
import yaml
from pathlib import Path


class Config:
    """Singleton config object loaded from config.yaml."""

    _instance = None

    def __init__(self):
        config_path = os.environ.get("TP_CONFIG", str(Path(__file__).parent.parent / "config.yaml"))
        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"Config not found at {config_path}. "
                f"Copy config.example.yaml to {config_path} and edit it."
            )
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

        self.app = data.get("app", {})
        self.cli = data.get("cli", {})
        self.refresh = data.get("refresh", {})
        self.appvault = data.get("appvault", {})

        # Multi-cluster profiles
        self.clusters = data.get("clusters", {})
        self.active_cluster = self.clusters.get("active", "")
        self.profiles = self.clusters.get("profiles", {}) or {}

        # Active profile (or empty if no profiles)
        self.active_profile = self.profiles.get(self.active_cluster, {})

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls):
        """Reload config from disk (after Settings save)."""
        cls._instance = None
        return cls.instance()

    @staticmethod
    def config_path() -> Path:
        return Path(os.environ.get("TP_CONFIG", str(Path(__file__).parent.parent / "config.yaml")))

    def save(self) -> None:
        """Save current state back to config.yaml."""
        data = {
            "app": self.app,
            "cli": self.cli,
            "refresh": self.refresh,
            "appvault": self.appvault,
            "clusters": {
                "active": self.active_cluster,
                "profiles": self.profiles,
            },
        }
        path = self.config_path()
        with open(path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        Config.reload()


def get_active_profile() -> dict:
    """Return currently active cluster profile."""
    cfg = Config.instance()
    if cfg.active_profile:
        return cfg.active_profile
    # Fallback to legacy appvault section if no profile set
    return {
        "api_url": "",
        "appvault": cfg.appvault.get("name", "ontap-s3-appvault"),
        "appvault_namespace": cfg.appvault.get("namespace", "trident-protect"),
    }
