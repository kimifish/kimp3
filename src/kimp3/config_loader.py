from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from kimp3.settings import Settings


ACTIVE_CONFIG_FILES: list[Path] = []


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def config_search_dirs(app_name: str, cwd: Path | None = None) -> list[Path]:
    xdg_root = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    current_dir = cwd or project_root()
    return [xdg_root / app_name, Path("/etc") / app_name, current_dir / "config"]


def discover_config_files(app_name: str, filename: str = "config.yaml", cwd: Path | None = None) -> list[str]:
    result = []
    search_dirs = config_search_dirs(app_name, cwd=cwd)
    for index, path in enumerate(search_dirs):
        config_path = path / filename
        if config_path.exists():
            result.append(str(config_path))
            continue
        if index == len(search_dirs) - 1 and filename == "config.yaml":
            example_path = path / "config.example.yaml"
            if example_path.exists():
                result.append(str(example_path))
    return result


def resolve_config_files(app_name: str, config_file: str | None, cwd: Path | None = None) -> list[str]:
    if config_file:
        return [str(Path(config_file).expanduser())]
    return discover_config_files(app_name, cwd=cwd)


def set_active_config_files(files: list[str]) -> None:
    global ACTIVE_CONFIG_FILES
    ACTIVE_CONFIG_FILES = [Path(file).expanduser() for file in files]


def get_active_config_files() -> list[Path]:
    return list(ACTIVE_CONFIG_FILES)


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(config_files: list[str]) -> Settings:
    raw_config: dict[str, Any] = {}
    for config_file in config_files:
        config_path = Path(config_file).expanduser()
        if not config_path.exists():
            continue
        with config_path.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
        raw_config = merge_dicts(raw_config, loaded)
    set_active_config_files(config_files)
    return Settings.model_validate(raw_config)


def default_logging_config() -> dict[str, Any]:
    return {
        "level": "INFO",
        "console": True,
        "file_enabled": False,
        "show_time": True,
        "time_format": "%H:%M:%S",
        "show_level": False,
        "show_path": False,
        "logs_width": 140,
        "tags_width": 14,
        "tag_filter_mode": "any",
        "unknown_tags": "hide",
        "show_all_tags_errors": True,
        "show_all_tags_warnings": True,
        "loggers": {
            "httpx": "WARNING",
            "httpcore": "WARNING",
            "mutagen": "WARNING",
            "pylast": "WARNING",
            "urllib3.connectionpool": "WARNING",
            "PIL": "WARNING",
        },
        "tags": {
            "startup": {"show": True, "icon": "S", "tag_color": "#5f875f", "icon_color": "#ffffff"},
            "config": {"show": True, "icon": "cfg", "tag_color": "#5f5f87", "icon_color": "#ffffff"},
            "scan": {"show": True, "icon": "scan", "tag_color": "#005f87", "icon_color": "#ffffff"},
            "tags": {"show": True, "icon": "tag", "tag_color": "#875f00", "icon_color": "#ffffff"},
            "files": {"show": True, "icon": "file", "tag_color": "#5f5f5f", "icon_color": "#ffffff"},
            "network": {"show": False, "icon": "net", "tag_color": "#444444", "icon_color": "#ffffff"},
            "state": {"show": True, "icon": "st", "tag_color": "#875f00", "icon_color": "#ffffff"},
        },
    }


def _normalize_logger_overrides(value: object) -> dict[str, str]:
    if isinstance(value, dict) and "suppress" in value:
        level = str(value.get("suppress_level", "WARNING"))
        return {str(logger_name): level for logger_name in value.get("suppress", [])}
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    return {}


def resolve_logging_config_file(app_name: str, cwd: Path | None = None) -> Path | None:
    for config_file in ACTIVE_CONFIG_FILES:
        logging_path = config_file.parent / "logging.yaml"
        if logging_path.exists():
            return logging_path

    search_dirs = config_search_dirs(app_name, cwd=cwd)
    for index, candidate in enumerate(search_dirs):
        logging_path = candidate / "logging.yaml"
        if logging_path.exists():
            return logging_path
        if index == len(search_dirs) - 1:
            example_path = candidate / "logging.example.yaml"
            if example_path.exists():
                return example_path
    return None


def load_logging_config(settings: Settings, app_name: str, cwd: Path | None = None) -> dict[str, Any]:
    config = default_logging_config()
    inline_logging = settings.logging.model_dump()
    inline_logging["loggers"] = _normalize_logger_overrides(inline_logging.get("loggers", {}))
    config = merge_dicts(config, inline_logging)

    logging_path = resolve_logging_config_file(app_name, cwd=cwd)
    if logging_path and logging_path.exists():
        with logging_path.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
        if "loggers" in loaded:
            loaded["loggers"] = _normalize_logger_overrides(loaded["loggers"])
        config = merge_dicts(config, loaded)
    return config
