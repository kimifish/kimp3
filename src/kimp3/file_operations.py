#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import errno
import song
import tags
import interface.utils
import os
import logging
from shutil import copyfile
from shutil import move, rmtree
from config import cfg, APP_NAME
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
    move_copy_operation(files_to_copy, copyfile)


def move_files():
    move_copy_operation(files_to_move, move)


def move_copy_operation(file_list, operation):
    if operation == move:
        log_text = 'Moving '
    elif operation == copyfile:
        log_text = 'Copying '
    else:
        log_text = 'Dunno wat to do'

    for song_file in file_list:
        if cfg.interactive:
            song_file.print_changes()
            if not interface.utils.yes_or_no("Proceed? (y/n)"):
                continue

        if song_file.filepath == song_file.new_filepath:
            log.info("File " + song_file.new_name + " already in place. Skipping...")
            if isinstance(song_file, song.Song):
                song_file.tags.write_tags()
            continue

        if os.path.isdir(song_file.new_filepath):
            log.warning("File's destination path is occupied by directory. Skipping...")
            continue

        if os.access(song_file.new_path, os.W_OK):
            log.info(log_text + song_file.filepath + " to " + song_file.new_path)
            if not cfg.dry_run:
                operation(song_file.filepath, song_file.new_filepath)
                if isinstance(song_file, song.Song):
                    # song_file.mp3 = eyed3.load(song_file.new_filepath)
                    tags_copy = song_file.tags.new.copy()
                    song_file.tags = tags.SongTags(song_file.new_filepath, tags=tags_copy)
                    song_file.tags.write_tags()


def create_symlinks():
    for action in files_to_create_link:
        # Если ссылка существует, удаляем нахер
        if os.path.islink(action[1]):
            os.remove(action[1])
        os.symlink(action[0], action[1])


def execute():
    log.debug('Copy files list consists of ' + str(len(files_to_copy)) + ' entries.')
    log.debug('Move files list consists of ' + str(len(files_to_move)) + ' entries.')
    create_dirs()
    copy_files()
    move_files()
    create_symlinks()


def delete_empty_dirs(root_dir):
    for current_dir, subdirs, files in os.walk(root_dir):

        # Удаляем мусорные файлы и папки
        for filename in files:
            if filename in cfg.skip_files:
                log.info('Removing junky ' + filename + " from " + current_dir)
                os.remove(os.path.join(current_dir, filename))
                files.remove(filename)
        for dirname in subdirs:
            if dirname in cfg.skip_dirs:
                log.info('Removing junky ' + dirname + " from " + current_dir)
                rmtree(os.path.join(current_dir, dirname))
                subdirs.remove(dirname)

        if len(files) == 0 and len(subdirs) == 0:
            os.rmdir(current_dir)
            log.info("Deleting empty " + current_dir)
