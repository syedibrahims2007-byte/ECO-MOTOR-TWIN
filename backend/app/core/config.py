"""Configuration loader with path resolution."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML config and resolve all relative paths to absolute."""
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "config.yaml"
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    _resolve_paths(cfg)
    logger.info("Config loaded from %s", config_path)
    return cfg


def _resolve_paths(cfg: dict[str, Any]) -> None:
    """Resolve path values relative to project root."""
    paths = cfg.get("paths", {})
    for key, val in paths.items():
        if isinstance(val, str) and ("/" in val or "\\" in val):
            paths[key] = str(PROJECT_ROOT / val)
    # Ensure directories exist
    for key in ("data_dir", "models_dir", "figures_dir", "logs_dir"):
        p = paths.get(key)
        if p:
            Path(p).mkdir(parents=True, exist_ok=True)


def get_motor_ids(cfg: dict[str, Any]) -> list[str]:
    """Return ordered list of motor IDs from config."""
    return list(cfg.get("motors", {}).keys())


def get_project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT
