#!/usr/bin/python3.6
#  -*- coding: utf-8 -*-

import os
from shutil import copyfile
from shutil import move, rmtree

import errno
import logging
import eyed3

import conf_parse
import song

logger = logging.getLogger('kimp3')

dirs_to_create = []
files_to_copy = []
files_to_move = []
dirs_to_remove = []


def create_dirs():
    for future_file in (files_to_copy + files_to_move):
        if not os.path.exists(future_file.new_path):
            try:
                os.makedirs(future_file.new_path, mode=0o755)
                logger.info("Creating directory " + future_file.new_path)
                if conf_parse.config_vars[u'dry run']:
                    os.rmdir(future_file.new_path)
            except OSError as e:
                if e != errno.EEXIST:
                    raise


def copy_files():
    move_copy_operation(files_to_copy, copyfile)


def move_files():
    move_copy_operation(files_to_move, move)


def move_copy_operation(file_list, operation):
    if operation == move:
        log_text = u'Moving '
    elif operation == copyfile:
        log_text = u'Copying '
    else:
        log_text = u'Dunno wat to do'

    for song_file in file_list:
        if song_file.filepath == song_file.new_filepath:
            logger.info("File " + song_file.new_name + " already in place. Skipping...")
            continue

        if os.path.isdir(song_file.new_filepath):
            logger.warning(u"File's destination path is occupied by directory. Skipping...")
            continue

        if os.access(song_file.new_path, os.W_OK):
            logger.info(log_text + song_file.filepath + u" to " + song_file.new_path)
            if not conf_parse.config_vars[u'dry run']:
                operation(song_file.filepath, song_file.new_filepath)
                if isinstance(song_file, song.Song):
                    song_file.mp3 = eyed3.load(song_file.new_filepath)
                    song_file.write_tags()


def execute():
    logger.debug(u'Copy files list consists of ' + str(len(files_to_copy)) + u' entries.')
    logger.debug(u'Move files list consists of ' + str(len(files_to_move)) + u' entries.')
    create_dirs()
    copy_files()
    move_files()


def delete_empty_dirs(root_dir):
    for current_dir, subdirs, files in os.walk(root_dir):

        # Удаляем мусорные файлы и папки
        for filename in files:
            if filename in conf_parse.config_vars[u'skip_files']:
                logger.info(u'Removing junky ' + filename + u" from " + current_dir)
                os.remove(os.path.join(current_dir, filename))
                files.remove(filename)
        for dirname in subdirs:
            if dirname in conf_parse.config_vars[u'skip_dirs']:
                logger.info(u'Removing junky ' + dirname + u" from " + current_dir)
                rmtree(os.path.join(current_dir, dirname))
                subdirs.remove(dirname)

        if len(files) == 0 and len(subdirs) == 0:
            os.rmdir(current_dir)
            logger.info("Deleting empty " + current_dir)
