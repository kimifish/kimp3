#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
import os
import sys
from datetime import datetime
from rich.pretty import pretty_repr
import file_operations
from config import cfg, APP_NAME, HOME_DIR
from songdir import SongDir
from lastfm import init_lastfm

log = logging.getLogger(f"{APP_NAME}.{__name__}")
log.info('•' + str(datetime.today()) + ' Starting…')


class ScanDir:
    def __init__(self, scanpath: str):
        self.path = scanpath
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
        changes = {}
        for directory in self.directories_list:
            changes[str(directory.path)] = directory.check_tags()
        return changes

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
    
    for d in dirs_to_scan:
        log.debug("Scanning stats:")
        log.debug(f"{d.path}:\n" + pretty_repr(d.stats))

    if cfg.tags.check_tags:
        init_lastfm()
        for directory in dirs_to_scan:
            changes = directory.check_tags()
            log.debug("Tag changes:" + pretty_repr(changes))

    return

    file_operations.execute()

    if cfg.scan.delete_empty_dirs:
        for directory in dirs_to_scan:
            file_operations.delete_empty_dirs(directory)


if __name__ == '__main__':
    sys.exit(main())
