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
    def __init__(self, scanpath):
        self.songList = []

        self.is_album = False
        self.is_compilation = False
        self.path = None
        self.newpath = None
        self.album_title = None
        self.album_artist = None
        self.num_of_tracks = None
        self.common_album_files = list()

        # Первый проход: просто читаем теги, декодируем (если нужно).
        for name in os.listdir(scanpath):
            if os.path.isfile(os.path.join(scanpath, name)) is True and \
                    os.path.splitext(name)[1] in cfg.valid_extensions:
                log.debug("Appending " + os.path.join(scanpath, name))
                self.songList.append(song.Song(os.path.join(scanpath, name), self))
            elif name in cfg.common_files:
                log.debug(f"Appending {os.path.join(scanpath, name)} to common files.")
                self.common_album_files.append(name)

        self.is_album, self.album_title = test_is_album(self)

        if self.is_album:
            if cfg.compilation_test:
                self.is_compilation, self.album_artist = test_is_compilation(self)

            self.path = self.songList[0].path
            self.count_num_of_tracks()

        # Второй проход: дополняем и исправляем теги на основе данных по всему альбому

        if cfg.move_or_copy == 'move':
            log.debug("Moving files...")
            self.move_all_songs()
        if cfg.move_or_copy == 'copy':
            log.debug("Copying files...")
            self.copy_all_songs()

    def check_tags(self):
        log.debug("Checking tags...")
        for it_song in self.songList:
            it_song.check_tags()

    def count_num_of_tracks(self):
        # Метод пытается понять, сколько всего должно быть треков в альбоме.
        # Если встречается трек с номером, большим, чем число треков, то возвращает его,
        # Иначе — количество треков.
        max_track_num = 0
        for i in self.songList:
            if i.tags.new['tracknumber'] == '' or None: continue
            if int(i.tags.new['tracknumber']) > max_track_num:
                max_track_num = int(i.tags.new['tracknumber'])
        if max_track_num < len(self.songList):
            max_track_num = len(self.songList)
        self.num_of_tracks = max_track_num
        log.debug("Number of tracks set to " + str(self.num_of_tracks))

    def gather_tag(self, tag, list_needed=False):
        # собирает тэг со всех треков папки в массив и сет
        tag_list = []
        tag_set = set()
        for it_song in self.songList:
            current_tag = it_song.tags.new[tag]
            tag_list.append(current_tag)
            tag_set.add(current_tag)
        if list_needed:
            return tag_list
        else:
            return tag_set

    def copy_all_songs(self):  # вызывает метод копирования файла
        for i in self.songList:
            i.copy_to()
        self.copy_common_album_files(file_operations.files_to_copy)

    def move_all_songs(self):  # вызывает метод перемещения файла
        for i in self.songList:
            i.move_to()
        self.copy_common_album_files(file_operations.files_to_move)

    def copy_common_album_files(self, operation_list):
        # Целевую папку дёргаем у первой песни
        # self.newpath = os.path.split(self.songList[0].new_filepath)[0] if self.is_album else None

        # Проходимся по каталогу включая подкаталоги, находим нужные файлы и добавляем их в
        # список, который передан в аргументах.
        # for current_dir, subdirs, files in os.walk(self.path):
        #     for filename in files:
        #         for common_file in cfg.common_files:
        #             if filename.lower() == common_file.lower():
        #                 usual_file = song.UsualFile(os.path.join(current_dir, filename))
        #                 usual_file.new_path, usual_file.new_name = self.newpath, filename
        #                 usual_file.new_filepath = os.path.join(self.newpath, filename)
        #                 operation_list.append(usual_file)
        for common_file in self.common_album_files:
            usual_file = song.UsualFile(os.path.join(self.path, common_file))
            usual_file.new_path, usual_file.new_name = self.newpath, common_file
            usual_file.new_filepath = os.path.join(self.newpath, common_file)
            operation_list.append(usual_file)


class ScanDir:
    def __init__(self, scanpath):
        self.directories_list = []
        self.scan_directory(scanpath)

    def scan_directory(self, scanpath):
        num_of_audio = 0
        log.debug(f"Scanning {scanpath}…")
        for item in os.listdir(scanpath):
            full_item = os.path.join(scanpath, item)
            if os.path.isdir(full_item):
                if item not in cfg.skip_dirs:
                    self.scan_directory(full_item)
            if os.path.isfile(full_item) and os.path.splitext(item)[1] in cfg.valid_extensions:
                num_of_audio += 1
        if num_of_audio > 0:
            self.directories_list.append(SongDir(scanpath))
            log.info(scanpath + " added to directory list.")

    def check_tags(self):
        for directory in self.directories_list:
            directory.check_tags()

    def copy_all_dirs(self):
        for i in self.directories_list:
            i.copy_all_songs()

    def move_all_dirs(self):
        for i in self.directories_list:
            i.move_all_songs()


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
