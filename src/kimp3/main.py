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
import song
from config import cfg, APP_NAME
from checks import test_is_album, test_is_compilation

log = logging.getLogger(f"{APP_NAME}.{__name__}")
log.info('•' + str(datetime.today()) + ' Starting…')


class SongDir:
    """Represents a directory containing audio files and manages their organization.
    
    Attributes:
        songs (list): List of Song objects in the directory
        is_album (bool): Whether directory represents an album
        is_compilation (bool): Whether directory is a compilation
        path (str): Directory path
        new_path (str): New path after organization
        album_title (str): Album title if is_album
        album_artist (str): Album artist if is_album
        track_count (int): Total number of tracks
        common_files (list): Common album-related files (artwork, etc)
    """
    
    def __init__(self, scan_path: str):
        """Initialize SongDir with path and scan for audio files.
        
        Args:
            scan_path (str): Directory path to scan
        """
        self.songs = []
        self.path = scan_path
        self.new_path = None
        
        # Album-related attributes
        self.is_album = False
        self.is_compilation = False
        self.album_title = None
        self.album_artist = None
        self.track_count = None
        self.common_files = []

        self._scan_directory()
        self._analyze_directory()
        self._process_files()

    def _scan_directory(self):
        """Scan directory for audio files and common album files."""
        try:
            for entry in os.scandir(self.path):
                if not entry.is_file():
                    continue
                    
                name = entry.name
                if os.path.splitext(name)[1] in cfg.scan.valid_extensions:
                    log.debug(f"Found audio file: {entry.path}")
                    self.songs.append(song.Song(entry.path, self))
                elif name in cfg.scan.common_files:
                    log.debug(f"Found common file: {entry.path}")
                    self.common_files.append(name)
                    
        except OSError as e:
            log.error(f"Error scanning directory {self.path}: {e}")

    def _analyze_directory(self):
        """Analyze directory contents to determine if it's an album/compilation."""
        if not self.songs:
            return

        self.is_album, self.album_title = test_is_album(self)
        
        if self.is_album and cfg.collection.compilation_test:
            self.is_compilation, self.album_artist = test_is_compilation(self)
            
        if self.is_album:
            self._count_tracks()

    def _count_tracks(self):
        """Count total tracks in album based on track numbers and file count."""
        max_track_num = 0
        for song in self.songs:
            try:
                track_num = int(song.tags.new['track_num'])
                max_track_num = max(max_track_num, track_num)
            except (ValueError, TypeError):
                continue
                
        self.track_count = max(max_track_num, len(self.songs))
        log.debug(f"Track count set to {self.track_count}")

    def _process_files(self):
        """Process files according to configuration."""
        if not self.songs:
            return
            
        if cfg.scan.move_or_copy == 'move':
            log.debug("Moving files...")
            self._move_files()
        elif cfg.scan.move_or_copy == 'copy':
            log.debug("Copying files...")
            self._copy_files()

    def _copy_files(self):
        """Copy all songs and common files to new location."""
        for song_file in self.songs:
            song_file.copy_to()
        self._copy_common_files(file_operations.files_to_copy)

    def _move_files(self):
        """Move all songs and common files to new location."""
        for song_file in self.songs:
            song_file.move_to()
        self._copy_common_files(file_operations.files_to_move)

    def _copy_common_files(self, operation_list):
        """Copy common album files to new location.
        
        Args:
            operation_list (list): List to append file operations to
        """
        if not self.common_files or not self.songs:
            return
            
        # Get target directory from first song's new path
        target_dir = os.path.dirname(self.songs[0].new_filepath)
        
        for common_file in self.common_files:
            usual_file = song.UsualFile(os.path.join(self.path, common_file))
            usual_file.new_path = target_dir
            usual_file.new_name = common_file
            usual_file.new_filepath = os.path.join(target_dir, common_file)
            operation_list.append(usual_file)

    def check_tags(self):
        """Check and correct tags for all songs in directory."""
        log.debug("Checking tags...")
        for song_file in self.songs:
            song_file.check_tags()

    def gather_tag(self, tag: str, as_list: bool = False):
        """Gather specific tag values from all songs.
        
        Args:
            tag (str): Tag name to gather
            as_list (bool): Return as list instead of set
            
        Returns:
            set or list: Collected tag values
        """
        values = [song.tags.new[tag] for song in self.songs]
        return values if as_list else set(values)

    @property
    def stats(self):
        """Get directory statistics.
        
        Returns:
            dict: Statistics about the directory
        """
        return {
            'path': self.path,
            'song_count': len(self.songs),
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
                   if item.is_dir() and item.name not in cfg.skip_dirs]
            
            audio_files = [item for item in items 
                          if item.is_file() and 
                          os.path.splitext(item.name)[1] in cfg.valid_extensions]
            
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
