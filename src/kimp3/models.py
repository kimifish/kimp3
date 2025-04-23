"""
Data models for audio metadata and file operations.

This module contains the core data structures used throughout the application
for representing audio metadata, file operations, and configuration options.
"""

from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Set, Dict
import logging
from abc import ABC, abstractmethod

from mutagen.id3 import ID3
from mutagen.easyid3 import EasyID3

#from kimp3.config import APP_NAME
APP_NAME = 'kimp3'

log = logging.getLogger(f"{APP_NAME}.{__name__}")


class FileOperation(Enum):
    """Enum for file operations."""
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

@dataclass
class AudioTags:
    """Model for storing audio file tags."""
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    disc_number: Optional[int] = None
    total_discs: Optional[int] = None
    year: Optional[int] = None
    genre: str = ""
    lastfm_tags: str = ""
    comment: str = ""
    compilation: bool = False
    rating: str = ""
    album_cover: Optional[bytes] = None
    album_cover_mime: str = "image/jpeg"
    lyrics: Optional[str] = None

    @classmethod
    def from_mutagen(cls, easy_tags: EasyID3, id3: ID3) -> 'AudioTags':
        """Creates AudioTags object from EasyID3 and ID3."""
        def get_tag_value(key: str) -> str:
            try:
                return easy_tags.get(key, [''])[0]
            except (IndexError, KeyError):
                return ''

        # Extract all needed frames in one pass
        lyrics = None
        cover_data = None
        cover_mime = "image/jpeg"
        comments = {}

        # Get frames directly
        uslt_frames = id3.getall('USLT')
        apic_frames = id3.getall('APIC')
        comm_frames = id3.getall('COMM')

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
            compilation=bool(get_tag_value('compilation')),
            lastfm_tags=comments.get('LastFM tags', '').replace('LastFM tags: ', ''),
            rating=comments.get('Rating', '').replace('Rating: ', ''),
            album_cover=cover_data,
            album_cover_mime=cover_mime,
            lyrics=lyrics
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
