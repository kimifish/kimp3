#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import os
import sys
from datetime import datetime
from typing import List
from rich.pretty import pretty_repr
import kimp3.file_operations as file_operations
from kimp3.config import cfg, APP_NAME, HOME_DIR
from kimp3.songdir import SongDir
from kimp3.tags import init_lastfm, get_cache_stats, clear_cache
from kimp3.interface.utils import sep_with_header

log = logging.getLogger(f"{APP_NAME}.{__name__}")
log.info('•' + str(datetime.today()) + ' Starting…')


class ScanDir:
    """Directory scanner that recursively finds and processes audio files.
    
    This class handles the recursive scanning of directories for audio files,
    organizing them into SongDir objects, and providing methods for processing
    and managing the found files.
    
    Attributes:
        path: Base directory path to scan
        directories_list: List of SongDir objects containing found audio files
    """

    def __init__(self, scanpath: str):
        """Initialize scanner with a base directory path.
        
        Args:
            scanpath: Directory path to start scanning from
        """
        self.path = scanpath
        self.directories_list: List[SongDir] = []
        self.scan_directory(scanpath)

    def scan_directory(self, scanpath):
        """Recursively scan directory for audio files and add them to directories_list.
        
        Walks through the directory tree, identifying audio files and creating
        SongDir objects for directories containing them. Skips directories and files
        specified in configuration.

        Args:
            scanpath: Path to scan for audio files
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
                self.directories_list.append(SongDir(scanpath, self))
                log.info(f'Added "{scanpath.replace(HOME_DIR, "~")}" to directory list ({len(audio_files)} audio files)')
                log.debug("─" * 90)

            # Recursively scan subdirectories
            for dir_entry in dirs:
                self.scan_directory(dir_entry.path)

        except PermissionError:
            log.warning(f"Permission denied accessing {scanpath}")
        except OSError as e:
            log.error(f"Error scanning {scanpath}: {e}")

    def check_tags(self):
        """Check tags in all found directories.
        
        Returns:
            dict: Mapping of directory paths to their tag check results
        """
        changes = {}
        for directory in self.directories_list:
            changes[str(directory.path)] = directory.check_tags()
        return changes
    
    def process_by_one(self):
        """Process each directory one by one.
        
        For each directory:
        1. Fetches tags if configured
        2. Processes files (move/copy)
        3. Executes pending file operations
        4. Writes updated tags
        """
        for d in self.directories_list:
            print(sep_with_header(f"Processing {str(d.path)}"))
            if cfg.tags.fetch_tags:
                changes = d.fetch_tags()
            d.process_files(cfg.scan.move_or_copy)
            file_operations.execute()
            d.write_tags()

    @property
    def stats(self):
        """Get scanning statistics.
        
        Returns:
            dict: Statistics including:
                - total_directories: Number of directories with audio files
                - total_files: Total number of audio files found
                - albums: Number of album directories
                - compilations: Number of compilation directories
        """
        total_dirs = len(self.directories_list)
        total_files = sum(len(d.audio_files) for d in self.directories_list)
        albums = sum(1 for d in self.directories_list if d.is_album)
        compilations = sum(1 for d in self.directories_list if d.is_compilation)
        
        return {
            'total_directories': total_dirs,
            'total_files': total_files,
            'albums': albums,
            'compilations': compilations
        }


def main():
    """Main program entry point.
    
    Performs the following steps:
    1. Scans configured directories for audio files
    2. Initializes LastFM if tag fetching is enabled
    3. Processes each directory (tag fetching, file operations)
    4. Cleans up broken symlinks
    5. Optionally deletes empty directories
    
    Returns:
        int: Exit code (0 for success)
    """
    dirs_to_scan = []
    for directory in cfg.scan.dir_list:
        if os.path.isdir(directory):
            if os.access(directory, os.R_OK):
                dirs_to_scan.append(ScanDir(directory))
            else:
                log.critical('Access to ' + directory + ' denied.')
        else:
            log.critical('Directory ' + directory + ' doesn\'t exist.')
    
    for d in dirs_to_scan:
        log.debug("Scanning stats:")
        log.debug(f"{d.path}:\n" + pretty_repr(d.stats))

    if cfg.tags.fetch_tags:
        init_lastfm()

    for directory in dirs_to_scan:
        directory.process_by_one()

    file_operations.clean_broken_symlinks()
    log.debug(f"Cache stats: {pretty_repr(get_cache_stats())}")
    clear_cache()
    return

    file_operations.execute()

    if cfg.scan.delete_empty_dirs:
        for directory in dirs_to_scan:
            file_operations.delete_empty_dirs(directory)


if __name__ == '__main__':
    sys.exit(main())
