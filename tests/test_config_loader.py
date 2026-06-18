from pathlib import Path

import pytest
from pydantic import ValidationError

from kimp3 import config_loader
from kimp3.settings import Settings


def test_config_search_dirs_prefers_xdg_then_etc_then_project(monkeypatch, tmp_path):
    xdg_root = tmp_path / "xdg"
    project_root = tmp_path / "project"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_root))

    assert config_loader.config_search_dirs("kimp3", cwd=project_root) == [
        xdg_root / "kimp3",
        Path("/etc") / "kimp3",
        project_root / "config",
    ]


def test_resolve_config_files_uses_discovery_order(monkeypatch, tmp_path):
    xdg_dir = tmp_path / "xdg" / "kimp3"
    etc_dir = tmp_path / "etc" / "kimp3"
    project_config_dir = tmp_path / "project" / "config"
    for directory in (xdg_dir, etc_dir, project_config_dir):
        directory.mkdir(parents=True)
        (directory / "config.yaml").write_text("interactive: false\n", encoding="utf-8")

    monkeypatch.setattr(
        config_loader,
        "config_search_dirs",
        lambda app_name, cwd=None: [xdg_dir, etc_dir, project_config_dir],
    )

    assert config_loader.resolve_config_files("kimp3", None) == [
        str(xdg_dir / "config.yaml"),
        str(etc_dir / "config.yaml"),
        str(project_config_dir / "config.yaml"),
    ]


def test_resolve_config_files_uses_project_example_fallback(monkeypatch, tmp_path):
    xdg_dir = tmp_path / "xdg" / "kimp3"
    etc_dir = tmp_path / "etc" / "kimp3"
    project_config_dir = tmp_path / "project" / "config"
    for directory in (xdg_dir, etc_dir, project_config_dir):
        directory.mkdir(parents=True)
    (project_config_dir / "config.example.yaml").write_text(
        "interactive: false\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        config_loader,
        "config_search_dirs",
        lambda app_name, cwd=None: [xdg_dir, etc_dir, project_config_dir],
    )

    assert config_loader.resolve_config_files("kimp3", None) == [
        str(project_config_dir / "config.example.yaml"),
    ]


def test_settings_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Settings.model_validate({"unexpected": True})


def test_settings_normalizes_scan_values():
    settings = Settings.model_validate(
        {"scan": {"dir_list": "~/Music", "operation": "none"}}
    )

    assert settings.scan.dir_list == [str(Path("~/Music").expanduser())]
    assert settings.scan.operation.value == "none"


def test_settings_normalizes_banned_artists_from_tags_case():
    settings = Settings.model_validate(
        {
            "tags": {
                "banned_tags": "Rock, Поп",
                "banned_artists_from_tags": {
                    "Post-Punk": ["ППВК", "Первый Полёт в Космос"]
                },
            }
        }
    )

    assert settings.tags.banned_tags == ["rock", "поп"]
    assert settings.tags.banned_artists_from_tags == {
        "post-punk": ["ппвк", "первый полёт в космос"]
    }


def test_settings_default_operation_is_auto():
    settings = Settings.model_validate({})

    assert settings.scan.operation.value == "auto"
    assert settings.scan.conflict_policy == "keep-best"


def test_old_move_or_copy_name_is_rejected():
    with pytest.raises(ValidationError):
        Settings.model_validate({"scan": {"move_or_copy": "copy"}})


def test_project_example_config_is_valid():
    settings = config_loader.load_settings(
        [str(config_loader.project_root() / "config" / "config.example.yaml")]
    )

    assert settings.scan.operation.value == "auto"
    assert settings.collection.directory == str(Path("~/Music").expanduser())
    assert settings.paths.cache_dir == str(Path("~/.cache/kimp3").expanduser())
    assert "Thumbs.db" in settings.scan.junk_files
    assert "rock" in settings.tags.genres
    assert "post-punk" in settings.tags.genres
    assert "post-punk" not in settings.tags.extended_genres
    assert "post-punk" not in settings.tags.genre_parents
    assert settings.tags.genre_parents["post-punk revival"] == "post-punk"
    assert settings.tags.genre_parents["coldwave"] == "dark wave"
    assert settings.tags.title_normalization == "title_case_safe"
    assert "AC/DC" in settings.tags.title_case_exceptions


def test_load_settings_merges_sibling_tags_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    tags_path = tmp_path / "tags.yaml"
    config_path.write_text(
        "tags:\n  use_llm: true\n  llm_url: http://ai.local:8000/v1/chat\n",
        encoding="utf-8",
    )
    tags_path.write_text(
        "tags:\n  genres: [rock]\n  extended_genres: [coldwave]\n  genre_parents:\n    coldwave: rock\n",
        encoding="utf-8",
    )

    settings = config_loader.load_settings([str(config_path)])

    assert settings.tags.use_llm is True
    assert settings.tags.llm_url == "http://ai.local:8000/v1/chat"
    assert settings.tags.genres == ["rock"]
    assert settings.tags.extended_genres == ["coldwave"]
    assert settings.tags.genre_parents == {"coldwave": "rock"}
    assert config_loader.get_active_config_files() == [config_path, tags_path]


def test_load_settings_accepts_raw_sibling_tags_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    tags_path = tmp_path / "tags.yaml"
    config_path.write_text("interactive: false\n", encoding="utf-8")
    tags_path.write_text("genres: [rock]\n", encoding="utf-8")

    settings = config_loader.load_settings([str(config_path)])

    assert settings.tags.genres == ["rock"]
