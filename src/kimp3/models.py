"""
Data models for audio metadata and file operations.

This module contains the core data structures used throughout the application
for representing audio metadata, file operations, and configuration options.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

#from kimp3.config import APP_NAME
APP_NAME = 'kimp3'

log = logging.getLogger(f"{APP_NAME}.{__name__}")


class FileOperation(Enum):
    """Enum for file operations."""
    AUTO = "auto"
    COPY = "copy"
    MOVE = "move"
    NONE = "none"

    @classmethod
    def from_string(cls, value: str) -> 'FileOperation':
        """Creates FileOperation from string.
        
        Args:
            value: String value of operation ('copy', 'move' or 'none')
            
        Returns:
            Corresponding FileOperation value
            
        Raises:
            ValueError: If invalid value provided
        """
        try:
            return cls(value.lower())
        except ValueError:
            valid_values = [op.value for op in cls]
            raise ValueError(
                f"Invalid operation '{value}'. Must be one of: {', '.join(valid_values)}"
            )

class TrackNumber(BaseModel):
    """Track number and optional total."""

    model_config = ConfigDict(validate_assignment=True)

    number: int | None = None
    total: int | None = None

    @field_validator("number", "total")
    @classmethod
    def normalize_positive(cls, value: int | None) -> int | None:
        return value if value is not None and value > 0 else None


class DiscNumber(BaseModel):
    """Disc number and optional total."""

    model_config = ConfigDict(validate_assignment=True)

    number: int | None = None
    total: int | None = None

    @field_validator("number", "total")
    @classmethod
    def normalize_positive(cls, value: int | None) -> int | None:
        return value if value is not None and value > 0 else None


class Artwork(BaseModel):
    """Embedded front-cover artwork."""

    model_config = ConfigDict(validate_assignment=True)

    data: bytes
    mime: str = "image/jpeg"
    kind: Literal["front"] = "front"


class Lyrics(BaseModel):
    """Embedded lyrics."""

    model_config = ConfigDict(validate_assignment=True)

    text: str
    language: str = "eng"
    description: str = ""


class LyricsLookup(BaseModel):
    """Embedded state for lyrics lookup attempts."""

    model_config = ConfigDict(validate_assignment=True)

    status: Literal["not_found"] = "not_found"
    checked_at: date
    artist: str = ""
    title: str = ""


def _split_tag_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace("/", ",").split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


class AudioTags(BaseModel):
    """Model for storing audio file tags."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track: TrackNumber = Field(default_factory=TrackNumber)
    disc: DiscNumber = Field(default_factory=DiscNumber)
    year: Optional[int] = None
    genres: list[str] = Field(default_factory=list)
    lastfm_tags: list[str] = Field(default_factory=list)
    comment: str = ""
    compilation: bool = False
    rating: int | None = None
    artwork: Artwork | None = None
    lyrics: Lyrics | None = None
    lyrics_lookup: LyricsLookup | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if any(key in data for key in ("track_number", "total_tracks")):
            data.setdefault("track", {})
            if not isinstance(data["track"], dict):
                data["track"] = {}
            data["track"].setdefault("number", data.pop("track_number", None))
            data["track"].setdefault("total", data.pop("total_tracks", None))
        if any(key in data for key in ("disc_number", "total_discs")):
            data.setdefault("disc", {})
            if not isinstance(data["disc"], dict):
                data["disc"] = {}
            data["disc"].setdefault("number", data.pop("disc_number", None))
            data["disc"].setdefault("total", data.pop("total_discs", None))
        if "genre" in data and "genres" not in data:
            data["genres"] = data.pop("genre")
        if "album_cover" in data and data.get("album_cover") is not None and "artwork" not in data:
            data["artwork"] = {
                "data": data.pop("album_cover"),
                "mime": data.pop("album_cover_mime", "image/jpeg") or "image/jpeg",
            }
        else:
            data.pop("album_cover", None)
            data.pop("album_cover_mime", None)
        if isinstance(data.get("lyrics"), str):
            text = data["lyrics"].strip()
            data["lyrics"] = {"text": text} if text else None
        if isinstance(data.get("lyrics_lookup"), str):
            text = data["lyrics_lookup"].strip()
            if text:
                try:
                    data["lyrics_lookup"] = LyricsLookup.model_validate(json.loads(text))
                except (json.JSONDecodeError, ValidationError):
                    data["lyrics_lookup"] = None
            else:
                data["lyrics_lookup"] = None
        return data

    @field_validator("title", "artist", "album", "album_artist", "comment", mode="before")
    @classmethod
    def normalize_string(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("genres", "lastfm_tags", mode="before")
    @classmethod
    def normalize_tag_list(cls, value: object) -> list[str]:
        return _split_tag_list(value)

    @field_validator("year", mode="before")
    @classmethod
    def normalize_year(cls, value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            year = int(str(value)[:4])
        except (TypeError, ValueError):
            return None
        return year if 1000 <= year <= 2100 else None

    @field_validator("compilation", mode="before")
    @classmethod
    def normalize_bool(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y"}

    @field_validator("rating", mode="before")
    @classmethod
    def normalize_rating(cls, value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            rating = int(str(value).replace("Rating:", "").strip())
        except (TypeError, ValueError):
            return None
        return rating if 0 <= rating <= 100 else None

    @property
    def track_number(self) -> Optional[int]:
        return self.track.number

    @track_number.setter
    def track_number(self, value: Optional[int]) -> None:
        self.track.number = value

    @property
    def total_tracks(self) -> Optional[int]:
        return self.track.total

    @total_tracks.setter
    def total_tracks(self, value: Optional[int]) -> None:
        self.track.total = value

    @property
    def disc_number(self) -> Optional[int]:
        return self.disc.number

    @disc_number.setter
    def disc_number(self, value: Optional[int]) -> None:
        self.disc.number = value

    @property
    def total_discs(self) -> Optional[int]:
        return self.disc.total

    @total_discs.setter
    def total_discs(self, value: Optional[int]) -> None:
        self.disc.total = value

    @property
    def genre(self) -> str:
        return ", ".join(self.genres)

    @genre.setter
    def genre(self, value: str | list[str]) -> None:
        self.genres = _split_tag_list(value)

    @property
    def lastfm_tags_text(self) -> str:
        return ", ".join(self.lastfm_tags)

    @property
    def album_cover(self) -> Optional[bytes]:
        return self.artwork.data if self.artwork else None

    @album_cover.setter
    def album_cover(self, value: Optional[bytes]) -> None:
        self.artwork = Artwork(data=value, mime=self.album_cover_mime) if value else None

    @property
    def album_cover_mime(self) -> str:
        return self.artwork.mime if self.artwork else "image/jpeg"

    @album_cover_mime.setter
    def album_cover_mime(self, value: str) -> None:
        if self.artwork:
            self.artwork.mime = value or "image/jpeg"

    @property
    def lyrics_text(self) -> Optional[str]:
        return self.lyrics.text if self.lyrics else None

    @property
    def lyrics_legacy(self) -> Optional[str]:
        return self.lyrics_text

    def managed_fingerprint(self) -> tuple[object, ...]:
        """Return KiMP3-managed fields used for no-op detection and verify."""
        return (
            self.title,
            self.artist,
            self.album,
            self.album_artist,
            self.track_number,
            self.total_tracks,
            self.disc_number,
            self.total_discs,
            self.year,
            tuple(self.genres),
            self.comment,
            self.compilation,
            self.rating,
            tuple(self.lastfm_tags),
            self.album_cover,
            self.album_cover_mime if self.album_cover else None,
            self.lyrics.model_dump() if self.lyrics else None,
            self.lyrics_lookup.model_dump() if self.lyrics_lookup else None,
        )

    def managed_equals(self, other: 'AudioTags') -> bool:
        """Compare only fields KiMP3 intentionally manages."""
        return self.managed_fingerprint() == other.managed_fingerprint()

    @classmethod
    def from_mutagen(cls, easy_tags: EasyID3 | object | None, id3: ID3 | None = None) -> 'AudioTags':
        """Creates AudioTags object from EasyID3 and ID3."""
        if easy_tags is None:
            return cls()
        if id3 is None and hasattr(easy_tags, "tags"):
            easy_tags = easy_tags.tags

        def get_tag_value(key: str) -> str:
            try:
                return easy_tags.get(key, [''])[0]
            except (AttributeError, IndexError, KeyError, TypeError):
                return ''

        # Extract all needed frames in one pass
        lyrics = None
        cover_data = None
        cover_mime = "image/jpeg"
        comments = {}

        # Get frames directly when full ID3 data is available.
        uslt_frames = id3.getall('USLT') if id3 is not None else []
        apic_frames = id3.getall('APIC') if id3 is not None else []
        comm_frames = id3.getall('COMM') if id3 is not None else []

        # Get lyrics from first USLT frame if exists
        if uslt_frames:
            lyrics = uslt_frames[0].text

        # Get cover from first APIC frame if exists
        if apic_frames:
            cover = apic_frames[0]
            cover_data = cover.data
            cover_mime = cover.mime

        # Process comments
        for comm in comm_frames:
            if comm.desc:  # Only process comments with descriptions
                comments[comm.desc] = comm.text[0]

        track_info = cls._parse_track_number(get_tag_value('tracknumber'))
        disc_info = cls._parse_track_number(get_tag_value('discnumber'))

        return cls(
            title=get_tag_value('title'),
            artist=get_tag_value('artist'),
            album=get_tag_value('album'),
            album_artist=get_tag_value('albumartist'),
            track_number=track_info[0],
            total_tracks=track_info[1],
            disc_number=disc_info[0],
            total_discs=disc_info[1],
            year=cls._parse_year(get_tag_value('date')),
            genre=get_tag_value('genre'),
            comment=get_tag_value('comment'),
            compilation=cls._parse_bool(get_tag_value('compilation')),
            lastfm_tags=comments.get('LastFM tags', '').replace('LastFM tags: ', ''),
            rating=comments.get('Rating', '').replace('Rating: ', ''),
            album_cover=cover_data,
            album_cover_mime=cover_mime,
            lyrics=lyrics,
            lyrics_lookup=comments.get('KiMP3 lyrics lookup') or None,
        )

    @staticmethod
    def _parse_track_number(value: str) -> tuple[Optional[int], Optional[int]]:
        """Parses track/disc number string in format 'number/total'."""
        if not value:
            return None, None
        parts = value.split('/')
        try:
            number = int(parts[0]) if parts[0] else None
            total = int(parts[1]) if len(parts) > 1 and parts[1] else None
            if number is not None and number <= 0:
                number = None
            if total is not None and total <= 0:
                total = None
            return number, total
        except (ValueError, IndexError):
            return None, None

    @staticmethod
    def _parse_year(value: str) -> Optional[int]:
        """Extracts year from date string."""
        if not value:
            return None
        try:
            # Take first 4 characters as year
            return int(value[:4])
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parse_bool(value: str) -> bool:
        """Parse tag booleans without treating '0' as true."""
        return value.strip().lower() in {"1", "true", "yes", "y"}


class UsualFile:
    """Base class for handling regular files."""
    def __init__(self, filepath: str | Path, song_dir: 'AbstractSongDir'):
        self._filepath = Path(filepath)
        self.path = self._filepath.parent
        self.name = self._filepath.name
        self._new_filepath: Path = Path()
        self.new_name: str = ''
        self.new_path: Path = Path()
        self.song_dir = song_dir
        self.operation_processed = FileOperation.NONE

    @property
    def filepath(self) -> Path:
        return self._filepath

    @filepath.setter
    def filepath(self, value: str | Path) -> None:
        self._filepath = Path(value)
        self.path = self._filepath.parent
        self.name = self._filepath.name

    @property
    def new_filepath(self) -> Path:
        return self._new_filepath

    @new_filepath.setter
    def new_filepath(self, value: str | Path) -> None:
        self._new_filepath = Path(value)
        self.new_path = self._new_filepath.parent
        self.new_name = self._new_filepath.name

    def print_changes(self) -> None:
        print(f"{self.filepath} ---> {self.new_filepath}")


class AbstractSongDir(ABC):
    """Abstract base class for directory containing audio files.
    
    Defines the interface that all song directory implementations must follow.
    
    Attributes:
        path (Path): Directory path
        audio_files (list[AudioFile]): List of audio files in the directory
        common_files (list[UsualFile]): Common album-related files (artwork, etc)
        is_album (bool): Whether directory represents an album
        is_compilation (bool): Whether directory is a compilation
        album_title (str): Album title if is_album
        album_artist (str): Album artist if is_album
        track_count (int): Total number of tracks
    """
    
    def __init__(self, scan_path: str | Path):
        self.path = Path(scan_path)
        self.audio_files: List['AudioFile'] = []
        self.common_files: List['UsualFile'] = []
        
        # Album-related attributes
        self.is_album: bool = False
        self.is_compilation: bool = False
        self.album_title: Optional[str] = None
        self.album_artist: Optional[str] = None
        self.track_count: Optional[int] = None

    @abstractmethod
    def _scan_directory(self) -> None:
        """Scan directory for audio files and common album files."""
        pass

    @abstractmethod
    def _analyze_directory(self) -> None:
        """Analyze directory contents to determine if it's an album/compilation."""
        pass

    @abstractmethod
    def _count_tracks(self) -> None:
        """Count total tracks in album based on track numbers and file count."""
        pass

    @abstractmethod
    def process_files(self, operation: 'FileOperation') -> None:
        """Process all files in directory."""
        pass

    @abstractmethod
    def fetch_tags(self) -> Dict:
        """Check and correct tags for all songs in directory."""
        pass

    @abstractmethod
    def gather_tag_values(self, tag_name: str) -> Set[str]:
        """Gather unique values of specified tag from all audio files."""
        pass

    @abstractmethod
    def write_tags(self) -> tuple:
        """Write tags to all audio files in directory."""
        pass

    @property
    @abstractmethod
    def stats(self) -> Dict:
        """Get directory statistics."""
        pass
