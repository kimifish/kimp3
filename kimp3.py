#!/usr/bin/python3.6
#  -*- coding: utf-8 -*-

import os
import logging
import conf_parse
from datetime import datetime
import song
import file_operations

# logging.basicConfig(filename='/var/log/kimifish/kimp3.log', level=logging.DEBUG)
logger = logging.getLogger('kimp3')
logger.info(u'•' + str(datetime.today()) + u' Starting…')

# Читаем конфиги и аргументы
config_vars = conf_parse.get_config()

log_levels = [logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET, ]
logger.setLevel(log_levels[int(config_vars[u'log_level'])])


def get_config():
    return config_vars


def test_is_album(album):
    # Метод проверяет, является ли каталог альбомом или нет. Возвращает буль.
    # Проверка простая: у всех песен тэг альбома должен быть одинаковым.

    album_title_set = album.gather_tag(u'album_title')

    is_album = True
    album_title = ""

    if len(album_title_set) > 1:
        is_album = False
    else:
        album_title = album_title_set.pop()
    return [is_album, album_title]


def test_is_compilation(album):
    # Метод проверяет, является ли каталог сборником или нет. Возвращает буль.
    # # Сначала просто проверяем, есть ли у всех треков тэг сборника.
    # album_type_set = album.gather_tag(u'album_type')
    #
    # if album_type_set == {u'compilation'}:
    #     is_compilation = True
    #     album_artist = ""
    #     logger.info(u"Album type was compilation already")

    # если тэга сборника нет, а конфиг говорит, что надо бы проверить по артистам, то проверяем по ним:
    song_artists = {}

    for it_song in album.songList:

        # причём, если строка альбомного артиста содержится в песенном, то считаем альбомного
        if it_song.tags[u'album_artist'] in it_song.tags[u'song_artist']:
            if not it_song.tags[u'album_artist'] in song_artists.keys():
                song_artists[it_song.tags[u'album_artist']] = 1
            else:
                song_artists[it_song.tags[u'album_artist']] += 1
        else:
            if not it_song.tags[u'song_artist'] in song_artists.keys():
                song_artists[it_song.tags[u'song_artist']] = 1
            else:
                song_artists[it_song.tags[u'song_artist']] += 1

    # Если один артист исполняет меньше определённой доли песен от всех песен в каталоге,
    # (а насколько именно — задаётся в конфиг.файле), то каталог признаётся сборником
    # ОДНАКО, метод ничто никуда не пишет, только возвращает булевое значение.
    is_compilation = True
    album_artist = u"Various artists"

    for artist_name in song_artists.keys():
        if song_artists[artist_name] / len(album.songList) > float(config_vars[u'compilation_coef']):
            is_compilation = False
            album_artist = artist_name
            break

    return is_compilation, album_artist


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

        # Первый проход: просто читаем теги, декодируем (если нужно).
        for name in os.listdir(scanpath):
            if os.path.isfile(os.path.join(scanpath, name)) is True and name[-4:] == '.mp3':
                self.songList.append(song.Song(os.path.join(scanpath, name), self))

        self.is_album, self.album_title = test_is_album(self)

        if self.is_album:
            if config_vars['compilation_test']:
                self.is_compilation, self.album_artist = test_is_compilation(self)

            self.path = self.songList[0].path
            self.count_num_of_tracks()

        # Второй проход: дополняем и исправляем теги на основе данных по всему альбому
        if config_vars[u'check_tags']:
            for it_song in self.songList:
                it_song.check_tags()

        if config_vars[u'move_or_copy'] == u'move':
            self.move_all_songs()
        if config_vars[u'move_or_copy'] == u'copy':
            self.copy_all_songs()

    def count_num_of_tracks(self):
        # Метод пытается понять, сколько всего должно быть треков в альбоме.
        # Если встречается трек с номером, большим, чем число треков, то возвращает его,
        # Иначе — количество треков.
        max_track_num = 0
        for i in self.songList:
            if i.tags[u'track_num_N'] == u'': continue
            if int(i.tags[u'track_num_N']) > max_track_num:
                max_track_num = int(i.tags[u'track_num_N'])
        if max_track_num < len(self.songList):
            max_track_num = len(self.songList)
        self.num_of_tracks = max_track_num

        # Остался непонятный кусок со странной логикой. Подтереть
        # if max_track_num == len(self.songList):
        #     self.num_of_tracks = max_track_num



    def gather_tag(self, tag, list_needed=False):
        # собирает тэг со всех треков папки в массив и сет
        tag_list = []
        tag_set = set()
        for it_song in self.songList:
            current_tag = it_song.tags[tag]
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
        self.newpath = os.path.split(self.songList[0].new_filepath)[0] if self.is_album else None

        # Проходимся по каталогу включая подкаталоги, находим нужные файлы и добавляем их в
        # список, который передан в аргументах.
        for current_dir, subdirs, files in os.walk(self.path):
            for filename in files:
                for common_file in config_vars[u'common_files']:
                    if filename.lower() == common_file.lower():
                        usual_file = song.UsualFile(os.path.join(current_dir, filename))
                        usual_file.new_path, usual_file.new_name = self.newpath, filename
                        usual_file.new_filepath = os.path.join(self.newpath, filename)
                        operation_list.append(usual_file)


class ScanDir:
    def __init__(self, scanpath):
        self.directories_list = []
        self.dirscan(scanpath)

    def dirscan(self, scanpath):
        num_of_mp3 = 0
        for item in os.listdir(scanpath):
            full_item = scanpath + '/' + item
            if os.path.isdir(full_item):
                if item not in config_vars['skip_dirs']:
                    self.dirscan(full_item)
            if os.path.isfile(full_item) and item[-4:] == '.mp3':
                num_of_mp3 += 1
        if num_of_mp3 > 0:
            self.directories_list.append(SongDir(scanpath))
            logger.info(scanpath + " added to directory list.")

    def copy_all_dirs(self):
        for i in self.directories_list:
            i.copy_all_songs()

    def move_all_dirs(self):
        for i in self.directories_list:
            i.move_all_songs()


if __name__ == '__main__':

    # config_vars[u'scan_dir_list'] = ['/media/kimifish/MediaStore/Музыка/Hills']
    config_vars[u'scan_dir_list'] = ['/home/kimifish/Музыка/Aerosmith']

    for folder in config_vars[u'scan_dir_list']:
        if os.path.isdir(folder):
            if os.access(folder, os.R_OK):
                x = ScanDir(folder)
            else:
                logger.critical(u'Access to ' + folder + u' denied.')
                quit()
        else:
            logger.critical(u'Directory ' + folder + u' doesn\'t exist.')
            quit()

        # if config_vars[u'move_or_copy'] == u'move':
        #     x.move_all_dirs()
        # elif config_vars[u'move_or_copy'] == u'copy':
        #     x.copy_all_dirs()

        file_operations.execute()
        if config_vars[u'delete_empty_dirs']:
            file_operations.delete_empty_dirs(folder)
