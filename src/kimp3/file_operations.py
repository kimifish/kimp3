#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import errno
from typing import Optional
from kimp3.interface.utils import yes_or_no
import os
import logging
# from shutil import copyfile
# from shutil import move, rmtree
import shutil
from kimp3.config import cfg, APP_NAME
from pathlib import Path
from kimp3.models import FileOperation

log = logging.getLogger(f"{APP_NAME}.{__name__}")


dirs_to_create = []
files_to_copy = []
files_to_move = []
dirs_to_remove = []
files_to_create_link = []


def create_dirs():
    all_files_list = files_to_copy + files_to_move
    all_paths_list = []
    # Adding paths from copy-move lists
    for future_file in all_files_list:
        all_paths_list.append(os.path.split(future_file.new_filepath)[0])
    # Adding paths from genre links list
    for action in files_to_create_link:
        all_paths_list.append(os.path.split(action[1])[0])

    for future_path in all_paths_list:
        if not os.path.exists(future_path):
            try:
                os.makedirs(future_path, mode=0o755)
                log.info("Creating directory " + future_path)
                if cfg.dry_run:
                    os.rmdir(future_path)
            except OSError as e:
                if e != errno.EEXIST:
                    raise


def copy_files():
    move_copy_operation(files_to_copy, FileOperation.COPY)


def move_files():
    move_copy_operation(files_to_move, FileOperation.MOVE)


def move_copy_operation(file_list, operation_to_process: FileOperation):
    if operation_to_process == FileOperation.MOVE:
        operation = shutil.move
        log_text = 'Moving '
    elif operation_to_process == FileOperation.COPY:
        operation = shutil.copyfile
        log_text = 'Copying '
    else:
        log_text = 'Dunno wat to do'

    # Create a copy of the list to safely remove items while iterating
    files_to_process = file_list.copy()
    
    proceed_all = False
    for song_file in files_to_process:
        try:
            if cfg.interactive and proceed_all is False:
                song_file.print_changes()
                proceed, proceed_all = yes_or_no("Proceed? (y/a/n)")
                if not proceed:
                    continue

            if song_file.filepath == song_file.new_filepath:
                log.info(f"File {song_file.new_name} already in place. Skipping...")
                file_list.remove(song_file)
                continue

            if os.path.isdir(song_file.new_filepath):
                log.warning("File's destination path is occupied by directory. Skipping...")
                file_list.remove(song_file)
                continue

            if os.access(song_file.new_path, os.W_OK):
                log.info(f"{log_text}{song_file.filepath} to {song_file.new_path}")
                if not cfg.dry_run:
                    dst = operation(song_file.filepath, song_file.new_filepath)
                    song_file.filepath = Path(dst)
                    song_file.operation_processed = operation_to_process
                file_list.remove(song_file)
            else:
                log.warning(f"No write access to {song_file.new_path}. Skipping...")
                file_list.remove(song_file)
                
        # except Exception as e:
        except NotImplementedError as e:
            log.error(f"Error processing file {song_file.filepath}: {e}")
            log.debug(f"File details:\n"
                     f"Original path: {song_file.filepath} ({type(song_file.filepath)})\n"
                     f"New path: {song_file.new_filepath} ({type(song_file.new_filepath)})")
            if song_file in file_list:
                file_list.remove(song_file)


def create_symlinks():
    for action in files_to_create_link:
        log.debug(f"Creating symlink {action[0]} → {action[1]}")
        if cfg.dry_run:
            continue
        # If link exists, delete it
        if os.path.islink(action[1]):
            os.remove(action[1])
        os.symlink(action[0], action[1])


def execute():
    log.debug(f'Copy files list consists of {len(files_to_copy)} entries.')
    log.debug(f'Move files list consists of {len(files_to_move)} entries.')
    create_dirs()
    copy_files()
    move_files()
    create_symlinks()


def delete_empty_dirs(root_dir):
    for current_dir, subdirs, files in os.walk(root_dir):
        # Remove junk files and directories
        for filename in files:
            if filename in cfg.scan.skip_files:  # Updated path
                log.info(f'Removing junky {filename} from {current_dir}')
                if cfg.dry_run:
                    continue
                os.remove(os.path.join(current_dir, filename))
                files.remove(filename)
        for dirname in subdirs:
            if dirname in cfg.scan.skip_dirs:  # Updated path
                log.info(f'Removing junky {dirname} from {current_dir}')
                if cfg.dry_run:
                    continue
                shutil.rmtree(os.path.join(current_dir, dirname))
                subdirs.remove(dirname)

        if len(files) == 0 and len(subdirs) == 0:
            log.info(f"Deleting empty {current_dir}")
            if cfg.dry_run:
                return
            os.rmdir(current_dir)


def clean_broken_symlinks(root_dir: Optional[str | Path] = None) -> None:
    """Recursively checks and removes broken symlinks in music collection.
    
    Args:
        root_dir: Starting directory. If None, uses collection directory from config.
    """
    if root_dir is None:
        root_dir = Path(cfg.collection.directory)
    else:
        root_dir = Path(root_dir)
        
    # Get genre directory pattern and split into parts
    genre_pattern = cfg.paths.patterns.genre
    genre_base = genre_pattern.split('/')[0]  # Should get '_Жанры'
    genre_dir = root_dir / genre_base
    
    broken_links = []
    
    # First scan main collection
    log.info(f"Scanning {root_dir} for broken symlinks...")
    for path in root_dir.rglob('*'):
        if path.is_symlink():
            target = Path(os.readlink(path))
            # Convert relative target to absolute if needed
            if not target.is_absolute():
                target = (path.parent / target).resolve()
                
            if not target.exists():
                broken_links.append(path)
                log.warning(f"Found broken symlink: {path} -> {target}")
    
    # Then specifically check genre directory if it exists
    if genre_dir.exists():
        log.info(f"Scanning genre directory {genre_dir} for broken symlinks...")
        for path in genre_dir.rglob('*'):
            if path.is_symlink():
                target = Path(os.readlink(path))
                # Convert relative target to absolute if needed
                if not target.is_absolute():
                    target = (path.parent / target).resolve()
                    
                if not target.exists():
                    broken_links.append(path)
                    log.warning(f"Found broken symlink: {path} -> {target}")
    
    # Remove broken links if any found
    if broken_links:
        log.info(f"Found {len(broken_links)} broken symlinks")
        if not cfg.dry_run:
            for link in broken_links:
                try:
                    os.remove(link)
                    log.info(f"Removed broken symlink: {link}")
                except OSError as e:
                    log.error(f"Failed to remove symlink {link}: {e}")
                    
            # After removing links, clean up empty directories
            if genre_dir.exists():
                delete_empty_dirs(genre_dir)
        else:
            log.info("Dry run - no symlinks were actually removed")
    else:
        log.info("No broken symlinks found")
