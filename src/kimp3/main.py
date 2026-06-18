#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Tuple, Callable
from rich.pretty import pretty_repr
from kimp3.config import cfg, APP_NAME, HOME_DIR
from kimp3.config_loader import load_logging_config
from kimp3.executor import OperationExecutor
from kimp3.logging_setup import setup_logging
from kimp3.reporting import ExecutionReporter, PlanReporter
from kimp3.songdir import SongDir
from kimp3.tags import init_lastfm, get_cache_stats, clear_cache
from kimp3.interface.utils import sep_with_header

setup_logging(load_logging_config(cfg, APP_NAME))
log = logging.getLogger(f"{APP_NAME}.{__name__}")
log.info("`startup`" + str(datetime.today()) + " Starting...")


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
        log.debug(f"`scan`Scanning {scanpath}…")

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
                log.info(f'`scan`Added "{scanpath.replace(HOME_DIR, "~")}" to directory list ({len(audio_files)} audio files)')
                log.debug("`scan`" + "─" * 90)

            # Recursively scan subdirectories
            for dir_entry in dirs:
                self.scan_directory(dir_entry.path)

        except PermissionError:
            log.warning(f"`scan,files`Permission denied accessing {scanpath}")
        except OSError as e:
            log.error(f"`scan,files`Error scanning {scanpath}: {e}")

    def check_tags(self):
        """Check tags in all found directories.
        
        Returns:
            dict: Mapping of directory paths to their tag check results
        """
        changes = {}
        for directory in self.directories_list:
            changes[str(directory.path)] = directory.fetch_tags()
        return changes
    
    def process_by_one(self) -> Dict[str, List[int]]:
        """Process each directory one by one.
        
        For each directory:
        1. Fetches tags if configured
        2. Processes files (move/copy)
        3. Executes pending file operations
        4. Writes updated tags
        """
        stats: Dict[str, List[int]] = {"write_tags": [0, 0]}
        for d in self.directories_list:
            print(sep_with_header(f"Processing {str(d.path)}"))
            if cfg.tags.fetch_tags:
                changes = d.fetch_tags()
            d.process_missing_tags_from_local_data()
            d.process_files(cfg.scan.operation)
            validation_errors = d.validate_plans()
            plans = [audio_file.operation_plan for audio_file in d.audio_files if audio_file.operation_plan]
            if validation_errors:
                for error in validation_errors:
                    log.error(f"`files`{error}")
                if cfg.scan.conflict_policy == "fail":
                    if plans:
                        PlanReporter().print_interesting_details(plans)
                    continue
            if plans and not cfg.dry_run:
                PlanReporter().print_interesting_details(plans)
            result = OperationExecutor().execute_song_dir(d)
            ExecutionReporter().print_result(result, title=f"Execution: {d.path}")
            stats["write_tags"][0] += result.successes
            stats["write_tags"][1] += result.failures
        return stats

    @staticmethod
    def _update_stats(func: Callable, stats: Dict[str, List[int]]) -> Dict[str, List[int]]:
        """Update statistics based on function results.
        
        Args:
            func: Function that was executed
            stats: Dictionary to update with results
        """
        successes, failures, skips = func()
        stats[func.__name__][0] += successes
        stats[func.__name__][1] += failures
        return stats

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
                log.critical('`scan,files`Access to ' + str(directory) + ' denied.')
        else:
            log.critical('`scan,files`Directory ' + str(directory) + ' doesn\'t exist.')
    
    for d in dirs_to_scan:
        log.debug("`scan`Scanning stats:")
        log.debug(f"`scan`{d.path}:\n" + pretty_repr(d.stats))

    if cfg.tags.fetch_tags:
        init_lastfm()

    for directory in dirs_to_scan:
        directory.process_by_one()

    OperationExecutor().cleanup_collection([directory.path for directory in dirs_to_scan])

    log.debug(f"`state`Cache stats: {pretty_repr(get_cache_stats())}")
    clear_cache()
    return 0


if __name__ == '__main__':
    sys.exit(main())
