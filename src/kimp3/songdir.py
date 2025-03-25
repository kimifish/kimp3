#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import file_operations
from song import AudioFile, UsualFile
from pathlib import Path
from rich.pretty import pretty_repr
from typing import List, Set, Optional, Dict
from config import cfg, APP_NAME
from checks import test_is_album, test_is_compilation
from models import FileOperation

log = logging.getLogger(f"{APP_NAME}.{__name__}")


class SongDir:
    """Represents a directory containing audio files and manages their organization.
    
    Attributes:
        path (Path): Directory path
        audio_files (list[AudioFile]): List of audio files in the directory
        common_files (list[Path]): Common album-related files (artwork, etc)
        is_album (bool): Whether directory represents an album
        is_compilation (bool): Whether directory is a compilation
        album_title (str): Album title if is_album
        album_artist (str): Album artist if is_album
        track_count (int): Total number of tracks
    """
    
    def __init__(self, scan_path: str | Path, parent=None):
        """Initialize SongDir with path and scan for audio files.
        
        Args:
            scan_path: Directory path to scan
        """
        self.path = Path(scan_path)
        self.parent = parent
        self.audio_files: List[AudioFile] = []
        self.common_files: List[UsualFile] = []
        
        # Album-related attributes
        self.is_album: bool = False
        self.is_compilation: bool = False
        self.album_title: Optional[str] = None
        self.album_artist: Optional[str] = None
        self.track_count: Optional[int] = None

        self._scan_directory()
        self._analyze_directory()
        if self.is_album:
            self._count_tracks()

        if cfg.logging.level == 'DEBUG':
            log.debug(pretty_repr(self.stats))

    def _scan_directory(self) -> None:
        """Scan directory for audio files and common album files."""
        try:
            for entry in self.path.iterdir():
                if not entry.is_file():
                    continue
                    
                if entry.suffix.lower() in cfg.scan.valid_extensions:
                    log.debug(f"+ {str(entry).replace(str(self.path), '…')}")
                    audio_file = AudioFile(filepath=entry, song_dir=self)
                    if audio_file:
                        self.audio_files.append(audio_file)
                elif entry.name.lower() in [f.lower() for f in cfg.scan.common_files]:
                    log.debug(f"+ {str(entry).replace(str(self.path), '…')}")
                    self.common_files.append(UsualFile(filepath=entry, song_dir=self))

        except OSError as e:
            log.error(f"Error scanning directory {self.path}: {e}")

    def _analyze_directory(self) -> None:
        """Analyze directory contents to determine if it's an album/compilation."""
        if not self.audio_files:
            return

        # Проверяем, является ли каталог альбомом
        is_album, album_title = test_is_album(self)
        self.is_album = is_album
        self.album_title = album_title

        if self.is_album and cfg.collection.compilation_test:
            # Проверяем, является ли альбом сборником
            is_compilation, album_artist = test_is_compilation(self)
            self.is_compilation = is_compilation
            self.album_artist = album_artist

    def _count_tracks(self) -> None:
        """Count total tracks in album based on track numbers and file count."""
        max_track_num = 0
        for audio_file in self.audio_files:
            if audio_file.tags.track_number:
                max_track_num = max(max_track_num, audio_file.tags.track_number)
                
        self.track_count = max(max_track_num, len(self.audio_files))
        log.debug(f"Track count set to {self.track_count}")

    def process_audio_files(self, operation: FileOperation) -> None:
        """Process audio files according to specified operation.

        Args:
            operation: FileOperation enum value (COPY/MOVE)
        """
        if not self.audio_files:
            return

        for audio_file in self.audio_files:
            audio_file.new_path = self._calculate_new_path(audio_file)
            if operation == FileOperation.COPY:
                audio_file.copy_to()
            else:
                audio_file.move_to()

    def _process_common_files(self, operation: FileOperation) -> None:
        """Process common album files like artwork.
        
        Args:
            operation: FileOperation enum value (COPY/MOVE)
        """
        if not self.common_files or not self.audio_files:
            return
            
        # Get target directory from first audio file that has new_path
        target_dir = None
        for audio_file in self.audio_files:
            if hasattr(audio_file, 'new_path') and audio_file.new_path:
                target_dir = audio_file.new_path.parent
                break
                
        if not target_dir:
            log.warning("Could not determine target directory for common files")
            return
        
        for common_file in self.common_files:
            usual_file = UsualFile(str(common_file))
            usual_file.new_path = str(target_dir)
            usual_file.new_name = common_file.name
            usual_file.new_filepath = str(target_dir / common_file.name)
            
            if operation == FileOperation.COPY:
                file_operations.files_to_copy.append(usual_file)
            else:
                file_operations.files_to_move.append(usual_file)

    def process_files(self, operation: FileOperation) -> None:
        """Process all files in directory.
        
        Args:
            operation: FileOperation enum value (COPY/MOVE)
        """
        # First process audio files to calculate new paths
        self.process_audio_files(operation)
        # Then process common files using the calculated paths
        self._process_common_files(operation)

    def _calculate_new_path(self, audio_file: AudioFile) -> Path:
        """Calculate new path for audio file based on tags and configuration.
        
        Args:
            audio_file: AudioFile object
            
        Returns:
            New path for the file
        """
        base_dir = Path(cfg.collection.music_dir)
        
        if self.is_compilation:
            pattern = cfg.collection.compilation_pattern
        else:
            pattern = cfg.collection.album_pattern
            
        # Replace template variables with actual values
        path_parts = []
        for part in pattern.split('/'):
            if part.startswith('%'):
                tag_name = part[1:]  # Remove '%' prefix
                value = getattr(audio_file.tags, tag_name, None)
                path_parts.append(value or "Unknown")
            else:
                path_parts.append(part)
                
        return base_dir.joinpath(*path_parts) / audio_file.path.name

    def check_tags(self):
        """Check and correct tags for all songs in directory."""
        log.debug("Checking tags...")
        changes = {}
        for audio_file in self.audio_files:
            changes[str(audio_file.filepath).replace(str(self.path.parent), '')] = audio_file.check_tags()
        return changes

    def gather_tag_values(self, tag_name: str) -> Set[str]:
        """Gather unique values of specified tag from all audio files.
        
        Args:
            tag_name: Name of the tag to gather
            
        Returns:
            Set of unique tag values
        """
        values = set()
        for audio_file in self.audio_files:
            value = getattr(audio_file.tags, tag_name)
            if value:
                values.add(value)
        return values

    @property
    def stats(self) -> Dict:
        """Get directory statistics.
        
        Returns:
            Dictionary with directory statistics
        """
        return {
            'path': str(self.path),
            'audio_files': len(self.audio_files),
            'is_album': self.is_album,
            'is_compilation': self.is_compilation,
            'album_title': self.album_title,
            'album_artist': self.album_artist,
            'track_count': self.track_count,
            'common_files': len(self.common_files)
        }
