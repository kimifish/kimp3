#  -*- coding: utf-8 -*-
#!/usr/bin/python3
#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import os
import sys
from datetime import datetime

import file_operations
from song import Song
from config import cfg, APP_NAME
from checks import test_is_album, test_is_compilation

log = logging.getLogger(f"{APP_NAME}.{__name__}")
log.info('•' + str(datetime.today()) + ' Starting…')


from pathlib import Path
from typing import List, Set, Optional, Dict
from mutagen._file import File as MutaFile


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
    
    def __init__(self, scan_path: str | Path):
        """Initialize SongDir with path and scan for audio files.
        
        Args:
            scan_path: Directory path to scan
        """
        self.path = Path(scan_path)
        self.audio_files: List[Song] = []
        self.common_files: List[Path] = []
        
        # Album-related attributes
        self.is_album: bool = False
        self.is_compilation: bool = False
        self.album_title: Optional[str] = None
        self.album_artist: Optional[str] = None
        self.track_count: Optional[int] = None

        self._scan_directory()
        self._analyze_directory()

    def _scan_directory(self) -> None:
        """Scan directory for audio files and common album files."""
        try:
            for entry in self.path.iterdir():
                if not entry.is_file():
                    continue
                    
                if entry.suffix.lower() in cfg.scan.valid_extensions:
                    log.debug(f"Found audio file: {entry}")
                    audio_file = self._create_audio_file(entry)
                    if audio_file:
                        self.audio_files.append(audio_file)
                elif entry.name.lower() in [f.lower() for f in cfg.scan.common_files]:
                    log.debug(f"Found common file: {entry}")
                    self.common_files.append(entry)
                    
        except OSError as e:
            log.error(f"Error scanning directory {self.path}: {e}")

    def _create_audio_file(self, path: Path) -> Optional[Song]:
        """Create AudioFile object from path.
        
        Args:
            path: Path to audio file
            
        Returns:
            AudioFile object if successful, None otherwise
        """
        try:
            mutagen_file = MutaFile(path)
            if mutagen_file is None:
                log.warning(f"Could not read tags from {path}")
                return None
                
            tags = AudioTags.from_mutagen(mutagen_file)
            return AudioFile(path=path, tags=tags)
            
        except Exception as e:
            log.error(f"Error creating AudioFile for {path}: {e}")
            return None

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
                audio_file.copy_to(audio_file.new_path)
            else:
                audio_file.move_to(audio_file.new_path)

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
            usual_file = song.UsualFile(str(common_file))
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

    def _analyze_directory(self) -> None:
        """Analyze directory contents to determine if it's an album/compilation."""
        if not self.audio_files:
            return

        # Check if all files have same album name
        album_names = self.gather_tag_values('album')
        if len(album_names) == 1 and "" not in album_names:
            self.is_album = True
            self.album_title = next(iter(album_names))
            
            # Check for compilation
            if cfg.collection.compilation_test:
                artist_names = self.gather_tag_values('artist')
                if len(artist_names) > 1:
                    self.is_compilation = True
                    self.album_artist = "Various Artists"
                else:
                    self.album_artist = next(iter(artist_names))
            
            self._count_tracks()

    def _count_tracks(self) -> None:
        """Count total tracks in album based on track numbers and file count."""
        max_track_num = 0
        for audio_file in self.audio_files:
            if audio_file.tags.track_number:
                max_track_num = max(max_track_num, audio_file.tags.track_number)
                
        self.track_count = max(max_track_num, len(self.audio_files))
        log.debug(f"Track count set to {self.track_count}")

    def check_tags(self):
        """Check and correct tags for all songs in directory."""
        log.debug("Checking tags...")
        for audio_file in self.audio_files:
            audio_file.check_tags()

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


class ScanDir:
    def __init__(self, scanpath):
        self.directories_list = []
        self.scan_directory(scanpath)

    def scan_directory(self, scanpath):
        """Recursively scan directory for audio files and add them to directories_list.
        
        Args:
            scanpath (str): Path to scan for audio files
        """
        log.debug(f"Scanning {scanpath}…")
        
        try:
            # Get all items in directory at once
            items = list(os.scandir(scanpath))
            
            # Split into dirs and files
            dirs = [item for item in items 
                   if item.is_dir() and item.name not in cfg.scan.skip_dirs]
            
            audio_files = [item for item in items 
                          if item.is_file() and 
                          os.path.splitext(item.name)[1] in cfg.scan.valid_extensions]
            
            # If audio files found, create SongDir
            if audio_files:
                self.directories_list.append(SongDir(scanpath))
                log.info(f"Added {scanpath} to directory list ({len(audio_files)} audio files)")
                
            # Recursively scan subdirectories
            for dir_entry in dirs:
                self.scan_directory(dir_entry.path)
                
        except PermissionError:
            log.warning(f"Permission denied accessing {scanpath}")
        except OSError as e:
            log.error(f"Error scanning {scanpath}: {e}")

    def check_tags(self):
        for directory in self.directories_list:
            directory.check_tags()

    def copy_all_dirs(self):
        for i in self.directories_list:
            i.copy_all_songs()

    def move_all_dirs(self):
        for i in self.directories_list:
            i.move_all_songs()

    @property
    def stats(self):
        """Return scanning statistics.
        
        Returns:
            dict: Statistics about scanned directories and files
        """
        total_dirs = len(self.directories_list)
        total_files = sum(len(d.songList) for d in self.directories_list)
        albums = sum(1 for d in self.directories_list if d.is_album)
        compilations = sum(1 for d in self.directories_list if d.is_compilation)
        
        return {
            'total_directories': total_dirs,
            'total_files': total_files,
            'albums': albums,
            'compilations': compilations
        }


def main():
    dirs_to_scan = []
    cfg.print_config()
    for directory in cfg.scan.dir_list:
        if os.path.isdir(directory):
            if os.access(directory, os.R_OK):
                dirs_to_scan.append(ScanDir(directory))
            else:
                log.critical('Access to ' + directory + ' denied.')
        else:
            log.critical('Directory ' + directory + ' doesn\'t exist.')

    if cfg.tags.check_tags:
        for directory in dirs_to_scan:
            directory.check_tags()

    file_operations.execute()

    if cfg.scan.delete_empty_dirs:
        for directory in dirs_to_scan:
            file_operations.delete_empty_dirs(directory)


if __name__ == '__main__':
    sys.exit(main())

    # config_vars[u'scan_dir_list'] = ['/home/kimifish/Музыка/--Music/Медвежий Угол']
    # config_vars[u'scan_dir_list'] = ['/home/kimifish/Музыка/Deep Purple']
