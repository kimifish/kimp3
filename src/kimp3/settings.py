from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kimp3.models import FileOperation


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    console: Any | None = None


class ScanSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dir_list: list[str] = Field(default_factory=list)
    skip_dirs: list[str] = Field(default_factory=list)
    delete_empty_dirs: bool = False
    junk_files: list[str] = Field(
        default_factory=lambda: [
            ".DS_Store",
            "Thumbs.db",
            "desktop.ini",
            "ehthumbs.db",
            "AlbumArtSmall.jpg",
        ]
    )
    valid_extensions: list[str] = Field(default_factory=lambda: [".mp3", ".flac"])
    operation: FileOperation = FileOperation.AUTO
    force_external_move: bool = False
    force_replace: bool = False
    conflict_policy: Literal["keep-best", "fail", "skip", "suffix", "replace"] = (
        "keep-best"
    )
    create_symlinks_in_none: bool = False
    common_files: list[str] = Field(default_factory=list)

    @field_validator("dir_list", mode="before")
    @classmethod
    def normalize_dir_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [str(Path(value).expanduser())]
        return [str(Path(str(item)).expanduser()) for item in value]  # type: ignore[union-attr]

    @field_validator("operation", mode="before")
    @classmethod
    def normalize_file_operation(cls, value: object) -> FileOperation:
        if isinstance(value, FileOperation):
            return value
        return FileOperation.from_string(str(value))

    @field_validator("valid_extensions", mode="after")
    @classmethod
    def normalize_extensions(cls, value: list[str]) -> list[str]:
        return [
            item.lower() if item.startswith(".") else f".{item.lower()}"
            for item in value
        ]


class CollectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str = str(Path.home() / "Music")
    compilation_test: bool = True
    compilation_coef: float = 0.5
    create_genre_links: bool = False
    clean_symlinks: bool = False

    @field_validator("directory", mode="before")
    @classmethod
    def normalize_directory(cls, value: object) -> str:
        return str(Path(str(value)).expanduser())


class PathPatternsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    album: str = "%album_artist/%year - %album_title/%track_num. %song_title.mp3"
    compilation: str = (
        "_Compilations/%album_title/%track_num. %song_artist - %song_title.mp3"
    )
    genre: str = "_Genres/%genre/%year. %song_artist - %song_title.mp3"


class PathsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patterns: PathPatternsSettings = Field(default_factory=PathPatternsSettings)
    cache_dir: str = str(Path.home() / ".cache" / "kimp3")

    @field_validator("cache_dir", mode="before")
    @classmethod
    def normalize_cache_dir(cls, value: object) -> str:
        return str(Path(str(value)).expanduser())


class TagsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fetch_tags: bool = True
    fetch_workers: int = 4
    fetch_album_cover: bool = True
    fetch_lyrics: bool = True
    skip_existing_tags: bool = True
    skip_existing_cover: bool = True
    skip_existing_lyrics: bool = True
    lastfm_api_key: str | None = None
    lastfm_api_secret: str | None = None
    genius_token: str | None = None
    lastfm_username: str | None = None
    lastfm_password_hash: str | None = None
    max_length: int = 50
    the_the: Literal["leave", "move", "remove"] = "leave"
    genres: list[str] = Field(default_factory=list)
    extended_genres: list[str] = Field(default_factory=list)
    genre_parents: dict[str, str] = Field(default_factory=dict)
    max_genres: int = 3
    max_tags: int = 30
    banned_tags: list[str] = Field(default_factory=list)
    banned_tags_patterns: list[Any] = Field(default_factory=list)
    banned_artists_from_tags: dict[str, list[str]] = Field(default_factory=dict)
    similar_tags: list[list[str]] = Field(default_factory=list)
    similar_tags_patterns: list[list[Any]] = Field(default_factory=list)
    genius_replacements: list[list[str]] = Field(default_factory=list)
    use_llm: bool = False
    llm_url: str = ""
    llm_timeout: int = 30

    @field_validator("banned_tags", mode="before")
    @classmethod
    def normalize_banned_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [
                item.strip().casefold() for item in value.split(",") if item.strip()
            ]
        return value  # type: ignore[return-value]

    @field_validator("banned_artists_from_tags", mode="before")
    @classmethod
    def normalize_banned_artists_from_tags(cls, value: object) -> dict[str, list[str]]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            return value  # type: ignore[return-value]
        return {
            str(tag)
            .strip()
            .casefold(): [
                str(artist).strip().casefold()
                for artist in artists
                if str(artist).strip()
            ]
            for tag, artists in value.items()
        }


class LoggerSuppressSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suppress: list[str] = Field(default_factory=list)
    suppress_level: str = "WARNING"


class LoggingSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    level: str = "INFO"
    loggers: LoggerSuppressSettings | dict[str, str] = Field(
        default_factory=LoggerSuppressSettings
    )


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interactive: bool = True
    dry_run: bool = False
    scan: ScanSettings = Field(default_factory=ScanSettings)
    collection: CollectionSettings = Field(default_factory=CollectionSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    tags: TagsSettings = Field(default_factory=TagsSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)

    def update(self, dotted_key: str, value: object) -> None:
        parts = dotted_key.split(".")
        target: object = self
        for part in parts[:-1]:
            target = getattr(target, part)
        object.__setattr__(target, parts[-1], value)

    def print_config(self) -> None:
        print(self.model_dump())
