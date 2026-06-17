from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Pattern

import rich.console
from dotenv import load_dotenv

from kimp3.config_loader import load_settings, resolve_config_files


APP_NAME = "kimp3"
HOME_DIR = os.path.expanduser("~")
DEFAULT_CONFIG_DIR = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"

load_dotenv(DEFAULT_CONFIG_DIR / ".env")

console = rich.console.Console(color_system="truecolor", width=120)


def _parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Search, sort MP3 files and process tags. Default values are read from config.yaml"
    )
    parser.add_argument("-c", "--config", dest="config_file", help="Configuration file location.")
    parser.add_argument("-s", "--scan_dir", type=str, help="Directory to search for MP3 files")
    parser.add_argument("-D", "--dry", help="Dry run", action="store_true")
    return parser.parse_known_args()


def _resolve_env(value: str | None, env_name: str) -> str | None:
    if value == ".env":
        return os.getenv(env_name)
    return value


def _compile_patterns() -> None:
    if cfg.tags.banned_tags_patterns:
        patterns: list[Pattern[str]] = []
        for pattern in cfg.tags.banned_tags_patterns:
            if hasattr(pattern, "match"):
                patterns.append(pattern)
                continue
            try:
                patterns.append(re.compile(str(pattern)))
            except re.error:
                pass
        cfg.update("tags.banned_tags_patterns", patterns)

    if cfg.tags.similar_tags_patterns:
        compiled_patterns_lists: list[list[object]] = []
        for pattern_list in cfg.tags.similar_tags_patterns:
            if not pattern_list:
                continue
            compiled_patterns: list[object] = [pattern_list[0]]
            for pattern in pattern_list[1:]:
                if hasattr(pattern, "match"):
                    compiled_patterns.append(pattern)
                    continue
                try:
                    compiled_patterns.append(re.compile(str(pattern)))
                except re.error:
                    pass
            compiled_patterns_lists.append(compiled_patterns)
        cfg.update("tags.similar_tags_patterns", compiled_patterns_lists)


args, unknown = _parse_args()
config_files = resolve_config_files(APP_NAME, args.config_file)
cfg = load_settings(config_files)

if args.scan_dir:
    cfg.update("scan.dir_list", [args.scan_dir])
if args.dry:
    cfg.update("dry_run", True)

cfg.update("tags.lastfm_api_key", _resolve_env(cfg.tags.lastfm_api_key, "LASTFM_API_KEY"))
cfg.update("tags.lastfm_api_secret", _resolve_env(cfg.tags.lastfm_api_secret, "LASTFM_API_SECRET"))
cfg.update("tags.lastfm_password_hash", _resolve_env(cfg.tags.lastfm_password_hash, "LASTFM_PASSWORD_HASH"))
cfg.update("tags.lastfm_username", _resolve_env(cfg.tags.lastfm_username, "LASTFM_USERNAME"))
cfg.update("tags.genius_token", _resolve_env(cfg.tags.genius_token, "GENIUS_TOKEN"))
cfg.update("runtime.console", console)

_compile_patterns()


if __name__ == "__main__":
    sys.exit(0)
