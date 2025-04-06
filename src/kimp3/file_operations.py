#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import errno
from typing import Optional, Dict, List
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

# Global variable to store genre links mapping
genre_links_map: Dict[str, List[Path]] = {}

def build_genre_links_map() -> Dict[str, List[Path]]:
    """Builds a mapping of target files to their genre symlinks.
    
    Scans the genre directory (first part of genre pattern) and creates a dictionary
    where keys are absolute paths to target files and values are lists of paths to
    corresponding genre symlinks.
    
    Returns:
        Dictionary mapping target files to lists of their genre symlinks
    """
    global genre_links_map
    genre_links_map.clear()
    
    # Get base collection directory
    base_dir = Path(cfg.collection.directory)
    
    # Get genre directory pattern and split into parts
    genre_pattern = cfg.paths.patterns.genre
    genre_parts = genre_pattern.split('/')
    
    # If first part contains patterns, return empty dict
    if '%' in genre_parts[0]:
        log.warning("Genre pattern starts with a variable, cannot determine genre directory")
        return genre_links_map
        
    genre_base = genre_parts[0]  # Should get '_Жанры' or similar
    genre_dir = base_dir / genre_base
    
    if not genre_dir.exists():
        log.debug(f"Genre directory {genre_dir} does not exist")
        return genre_links_map
        
    # Scan all symlinks in genre directory recursively
    for path in genre_dir.rglob('*'):
        if path.is_symlink():
            target = Path(os.readlink(path))
            # Convert relative target to absolute if needed
            if not target.is_absolute():
                target = (path.parent / target).resolve()
            
            # Add to mapping
            if str(target) not in genre_links_map:
                genre_links_map[str(target)] = []
            genre_links_map[str(target)].append(path)
            
    log.debug(f"Built genre links map with {len(genre_links_map)} entries")
    return genre_links_map

dirs_to_create = []
files_to_copy = []
files_to_move = []
dirs_to_remove = []
files_to_create_link = []
links_to_remove = []


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
        log_text = 'Keeping in place '

    # Create a copy of the list to safely remove items while iterating
    files_to_process = file_list.copy()
    
    proceed_all = False
    successes = 0
    failures = 0
    skips = 0
    for song_file in files_to_process:
        try:
            if song_file.filepath == song_file.new_filepath:
                log.debug(f"File {song_file.new_name} already in place. Skipping...")
                skips += 1
                file_list.remove(song_file)
                continue

            if os.path.isdir(song_file.new_filepath):
                log.warning("File's destination path is occupied by directory. Skipping...")
                failures += 1
                file_list.remove(song_file)
                continue

            if cfg.interactive and proceed_all is False:
                song_file.print_changes(show_path=True, show_genre_links=True)
                proceed = yes_or_no("Proceed?", "yna")
                if proceed == 'n':
                    skips += 1
                    continue
                if proceed == 'a':
                    proceed_all = True

            if os.access(song_file.new_path, os.W_OK):
                log.debug(f"{log_text}{song_file.filepath} to {song_file.new_path}")
                if not cfg.dry_run:
                    dst = operation(song_file.filepath, song_file.new_filepath)
                    song_file.filepath = Path(dst)
                    song_file.operation_processed = operation_to_process
                file_list.remove(song_file)
                successes += 1
            else:
                log.warning(f"No write access to {song_file.new_path}. Skipping...")
                failures += 1
                file_list.remove(song_file)
                
        except Exception as e:
        # except NotImplementedError as e:
            log.error(f"Error processing file {song_file.filepath}: {e}")
            log.debug(f"File details:\n"
                     f"Original path: {song_file.filepath} ({type(song_file.filepath)})\n"
                     f"New path: {song_file.new_filepath} ({type(song_file.new_filepath)})")
            failures += 1
            if song_file in file_list:
                file_list.remove(song_file)
    if successes > 0:
        log.info(f"Operation: {operation_to_process.value}. [green]Successfully processed {successes} files[/green]")
    if failures > 0:
        log.error(f"Operation: {operation_to_process.value}. [red]Failed to process {failures} files[/red]")
    if skips > 0:
        log.info(f"Operation: {operation_to_process.value}. [yellow]Skipped {skips} files[/yellow]")


def create_symlinks():
    """Creates symlinks for genre organization.
    
    Creates all symlinks from files_to_create_link list, handling existing links
    and logging results. In dry-run mode only logs intended actions.
    """
    if not files_to_create_link:
        log.debug("No symlinks to create")
        return
        
    successes = 0
    failures = 0
    skips = 0
    
    for target, link_path in files_to_create_link:
        try:
            log.debug(f"Creating symlink {link_path} → {target}")
            
            if cfg.dry_run:
                successes += 1
                continue
                
            # Check if target exists
            if not os.path.exists(target):
                log.error(f"Target file does not exist: {target}")
                failures += 1
                continue
                
            # Handle existing link
            if os.path.exists(link_path):
                if os.path.islink(link_path):
                    current_target = os.readlink(link_path)
                    if current_target == target:
                        log.debug(f"Symlink already exists and points to correct target: {link_path}")
                        skips += 1
                        continue
                    log.debug(f"Removing existing symlink: {link_path}")
                    os.remove(link_path)
                else:
                    log.error(f"Path exists and is not a symlink: {link_path}")
                    failures += 1
                    continue
                    
            # Create the symlink
            os.symlink(target, link_path)
            successes += 1
            
        except OSError as e:
            log.error(f"Failed to create symlink {link_path}: {e}")
            failures += 1
        except Exception as e:
            log.error(f"Unexpected error creating symlink {link_path}: {e}")
            failures += 1
            
    if successes > 0:
        log.info(f"[green]Successfully created {successes} symlinks[/green]")
    if skips > 0:
        log.info(f"[yellow]Skipped {skips} existing symlinks[/yellow]")
    if failures > 0:
        log.error(f"[red]Failed to create {failures} symlinks[/red]")
        
    # Clear the list after processing
    files_to_create_link.clear()


def execute():
    log.debug(f'Copy files list consists of {len(files_to_copy)} entries.')
    log.debug(f'Move files list consists of {len(files_to_move)} entries.')
    create_dirs()
    copy_files()
    move_files()
    create_symlinks()


def delete_empty_dirs(root_dir):
    if cfg.scan.delete_empty_dirs is False:
        return
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
    if cfg.collection.clean_symlinks is False:
        return

    if root_dir is None:
        root_dir = Path(cfg.collection.directory)
    else:
        root_dir = Path(root_dir)
        
    # Get genre directory pattern and split into parts
    genre_pattern = cfg.paths.patterns.genre
    genre_base = genre_pattern.split('/')[0]  # Should get '_Жанры'
    genre_dir = root_dir / genre_base
    
    # First scan main collection
    # log.info(f"Scanning {root_dir} for broken symlinks...")
    # for path in root_dir.rglob('*'):
    #     if path.is_symlink():
    #         target = Path(os.readlink(path))
    #         # Convert relative target to absolute if needed
    #         if not target.is_absolute():
    #             target = (path.parent / target).resolve()
                
    #         if not target.exists():
    #             links_to_remove.append(path)
    #             log.warning(f"Found broken symlink: {path} -> {target}")
    
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
                    links_to_remove.append(path)
                    log.debug(f"Found broken symlink: {path} -> {target}")
    
    # Remove broken links if any found
    if links_to_remove:
        successes, failures = 0, 0
        log.info(f"Found {len(links_to_remove)} broken symlinks")
        if not cfg.dry_run:
            for link in links_to_remove:
                try:
                    os.remove(link)
                    log.debug(f"Removed broken symlink: {link}")
                    successes += 1
                except OSError as e:
                    log.error(f"Failed to remove symlink {link}: {e}")
                    failures += 1
                    
            # After removing links, clean up empty directories
            if genre_dir.exists():
                delete_empty_dirs(genre_dir)
        else:
            log.info("Dry run - no symlinks were actually removed")
        if successes > 0:
            log.info(f"[green]Successfully removed {successes} broken symlinks[/green]")
        if failures > 0:
            log.error(f"[red]Failed to remove {failures} broken symlinks[/red]")
    else:
        log.info("No broken symlinks found")
