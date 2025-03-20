#!/usr/bin/python3
#  -*- coding: utf-8 -*-

import logging
import os
import re
from os.path import split as os_split_path

import eyed3

import file_operations
import lastfm
from config import cfg
from tags import SongTags

logger = logging.getLogger(__name__)


class UsualFile:
    def __init__(self, filepath):
        self.filepath = filepath
        logger.debug(' + ' + filepath)
        self.path, self.name = os.path.split(self.filepath)
        self.new_filepath, self.new_name, self.new_path = '', '', ''

    def print_changes(self):
        print("{} ---> {}".format(self.filepath, self.new_filepath))


class Song(UsualFile):
    """
    Классу передаётся полное имя файла,
    в экземпляре должны быть все теги и некоторые методы,
    например перемещение файла в заранее уготованное тёплое местечко.
    """

    # Заполняем переменные значениями по умолчанию
    # Переменных, кстати, нужно гораздо больше, например общее число треков и тп. Короче, все теги желательны

    # Типы альбомов: (скопипастил из глаз3 просто для ознакомления)
    # LP_TYPE = u"lp"
    # EP_TYPE = u"ep"
    # COMP_TYPE = u"compilation"
    # LIVE_TYPE = u"live"
    # VARIOUS_TYPE = u"various"
    # DEMO_TYPE = u"demo"
    # SINGLE_TYPE = u"single"
    # ALBUM_TYPE_IDS = [LP_TYPE, EP_TYPE, COMP_TYPE, LIVE_TYPE, VARIOUS_TYPE,
    #                   DEMO_TYPE, SINGLE_TYPE]

    # Заполняются после копирования/перемещения
    # newfilepath = None
    # newname = None
    # newpath = None

    def __init__(self, filepath, song_dir=None):

        super().__init__(filepath)
        self.genre_paths = []
        # global logger
        if song_dir:  # если нам передали экземпляр объекта для нашего каталога,
            self.song_dir = song_dir  # сохраним его в поле, пригодится.
        self.tags = SongTags(self.filepath)
        self.read_tags()

    def read_tags(self):

        for tag in self.tags.old.keys():
            if self.tags.old[tag] is None:
                self.tags.old[tag] = ''
                self.tags.new[tag] = ''

            if type(self.tags.old[tag]) in [str] and self.tags.old[tag] != '':
                if cfg.decode:
                    self.tags.new[tag] = (self.tags.old[tag].rstrip()).encode('latin-1').decode('windows-1251')
                else:
                    self.tags.new[tag] = str(self.tags.old[tag].rstrip())
                logging.info(str(tag) + ": " + self.tags.new[tag])

        # Строчные номера дисков
        # Поставил их в первый проход, поскольку общие данные об альбоме для этого не нужны,
        # а вот для генерации пути нужно строковое значение номера диска.
        if self.tags.old['num_of_discs_N'] != '':
            self.tags.new['num_of_discs'] = str(self.tags.old['num_of_discs_N']).zfill(1)
        else:
            self.tags.new['num_of_discs'] = '1'
            self.tags.new['num_of_discs_N'] = 1

        if self.tags.old['disc_num_N'] != '':
            self.tags.new['disc_num'] = str(self.tags.old['disc_num_N']).zfill(
                1 if self.tags.old['num_of_discs_N'] < 10 else 2)
        else:
            self.tags.new['disc_num'] = '1'
            self.tags.new['disc_num_N'] = 1

        # Вместо объекта CommentFrame с заголовком Rating получаем его значение, если оно есть.
        if self.tags.old['rating'] != u'':
            self.tags.new['rating'] = self.tags.old['rating'].text

        # Здесь делаем что-нибудь с определённым артиклем в названии артиста. В общем-то всё просто.
        for tag in ['song_artist', 'album_artist']:
            if self.tags.old[tag].lower().startswith('the '):
                if cfg.the_the == 'remove':
                    self.tags.new[tag] = self.tags.old[tag][4:]
                if cfg.the_the == 'move':
                    self.tags.new[tag] = self.tags.old[tag][4:] + ', the'

        return

    def check_tags(self):

        # Заменяем разную невалидную пунктуацию
        for tag in self.tags.new.keys():
            tag_value = self.tags.new[tag]

            if type(tag_value) is str:
                while "''" in tag_value:
                    tag_value = tag_value.replace("''", "«", 1)
                    tag_value = tag_value.replace(u"''", u"»", 1)

            if self.tags.new[tag] != tag_value:
                logger.debug(str.format("Tag {} changed from {} to {}.", tag, self.tags.new[tag], tag_value))
            self.tags.new[tag] = tag_value

        # А здесь создаём строчные номера песен.
        # для начала пытаемся выяснить число лидирующих нулей
        num_of_leading0s = 2
        if len(self.song_dir.songList) > 99:
            num_of_leading0s = 3

        # а затем собственно создаём их из цифр
        if self.tags.old['track_num_N'] not in ['', -1]:
            self.tags.new['track_num'] = str(self.tags.old['track_num_N']).zfill(num_of_leading0s)
        if self.tags.old['num_of_tracks_N'] != '':
            self.tags.new['num_of_tracks'] = str(self.tags.old['num_of_tracks_N']).zfill(num_of_leading0s)

        # album_artist по artist
        if self.tags.new['album_artist'].lower() in cfg.bad_artists:
            if not self.song_dir.is_compilation:
                self.tags.new['album_artist'] = self.tags.new['song_artist']
            else:
                self.tags.new['album_artist'] = 'Various artists'

        if self.song_dir.is_compilation:
            self.tags.new['album_type'] = 'compilation'

        if self.tags.new['year'] == '':
            try:
                self.tags.new['year'] = eyed3.core.Date(int(os.path.split(self.path)[1][0:4]), None, None)
                logger.debug("Tag Year set to " + self.tags.new['year'])
            except ValueError:
                # self.tags[u'year'] = eyed3.core.Date(2222, 1, 1)
                pass

        self.lastfm_checks()
        return

    def build_paths(self, for_genre=False):
        # Метод строит путь, в который затем можно копировать или перемещать файл.
        # Вообще, путей нужно строить несколько, в частности:
        #           • путь для символической ссылки для сортировки по жанрам
        #           • путь для ссылки в папку "Другое" в каталоге исполнителя
        #
        # Ну и что-нибудь ещё в том же духе. По годам например...

        # Проверяет, не являемся ли мы частью сборника
        if self.tags.new['album_type'] == '':
            if self.song_dir.is_compilation:  # обращается к объекту каталога, в котором лежит
                self.tags.new['album_type'] = 'compilation'

        if self.tags.new['album_type'] is 'compilation':
            pattern = cfg.compilation_pattern
        else:
            pattern = cfg.album_pattern

        if for_genre:
            genre_pattern = cfg.music_collection_dir.rstrip('/') + u"/" + cfg.genre_pattern
            genre_pattern = self.cut_empty_tags_from_filepath(genre_pattern)
            for genre in self.tags.new['genre'].split(','):
                self.genre_paths.append(
                    self._build_path_by_pattern(genre_pattern, genre=genre.strip())
                )

        new_filepath = cfg.music_collection_dir.rstrip('/') + "/" + pattern
        # logger.debug(u"Using pattern:" + new_filepath)

        if cfg.cut_empty_tags_from_path:
            # logger.info(u"Cutting empty tags from filepath")
            new_filepath = self.cut_empty_tags_from_filepath(new_filepath)

            if cfg.cut_just_year_folders:
                new_filepath = new_filepath.replace('/%year/', '/')

            logger.debug("Result: " + new_filepath)

        self.new_filepath = self._build_path_by_pattern(new_filepath)
        self.new_path, self.new_name = os_split_path(self.new_filepath)

        logger.debug("Final destination name:" + new_filepath)

        # Возвращает строку абсолютного пути в музыкальной коллекции.
        return

    def _build_path_by_pattern(self, path, genre=None):
        for tag in self.tags.new.keys():
            # logger.info(u"Replacing tags in path pattern by values")
            if tag in path:
                if tag == 'year':
                    tag_value = str(self.tags.new[tag].year)
                elif tag == 'genre' and genre:
                    tag_value = str(genre)
                else:
                    tag_value = str(self.tags.new[tag])

                tag_value = tag_value.replace("/", " | ")
                tag_value = tag_value.replace("*", "\u2022")
                # logger.debug(u"   {}: {}".format(tag, tag_value))
                path = path.replace("%" + tag, tag_value)

        path = path.replace('//', '/')
        return path

    def cut_empty_tags_from_filepath(self, new_filepath):
        # Для каждого тэга, если он есть в пути, и его значение не задано, то
        for tag in self.tags.new.keys():
            if tag in new_filepath:
                if (tag == 'disc_num' and self.tags.new['num_of_discs_N'] == 1) or \
                        self.tags.new[tag] == '':

                    regex = re.compile('.*(/|%[\w]*|^)(.*)(%{})([^/%]*)(%|/)?.*\.mp3'.format(str(tag)))
                    # разделяем путь регулярным выражением на группы (в скобках):
                    # 1. Либо уровень выше, либо предыдущий тег, либо начало строки.
                    # 2. Любые символы на этом же уровне пути после предыдущего тега, если он есть.
                    # 3. Сам тэг, который будем убирать.
                    # 4. Символы до следующего тега, уровня ниже или расширения файла.
                    # 5. Символ % или / для определения, последний ли это тег на уровне.
                    tag_with_surround = regex.match(new_filepath)

                    # Определяем, является ли тег первым, последним на текущем уровне пути.
                    first_tag = True if tag_with_surround.group(1) in ['/', ''] else False
                    last_tag = True if tag_with_surround.group(5) != '%' else False

                    # В эту переменную будем собирать всё, что подлежит удалению
                    text_to_remove = tag_with_surround.group(3)

                    if first_tag:
                        text_to_remove = tag_with_surround.group(2) + text_to_remove
                        if not last_tag:
                            text_to_remove += tag_with_surround.group(4)
                    else:
                        if not last_tag:
                            text_to_remove += tag_with_surround.group(4)
                        else:
                            text_to_remove = tag_with_surround.group(2) + text_to_remove + tag_with_surround.group(4)

                    # Удаляем то, что получилось
                    new_filepath = new_filepath.replace(text_to_remove, '')

                    # В случае, если имя файла оказывается пустым, обзываем хотя бы id экземпляра класса.
                    new_filepath = new_filepath.replace('/.mp3', '/id' + str(id(self)) + '.mp3')
        return new_filepath

    def lastfm_checks(self):
        lastfm_track = lastfm.get_track(self.tags.new)
        lastfm_artist = lastfm.get_artist(self.tags.new)
        lastfm_album = lastfm.get_album(self.tags.new)
        lastfm_genre = lastfm.get_genre(lastfm_album, lastfm_artist)
        # logger.debug("LastFM genre: " + lastfm_genre)

        if cfg.lastfm_autocorrection:
            self.tags.new = lastfm.artist_correction(lastfm_artist, self.tags.new)
            #            self.tags.new = lastfm.album_correction(lastfm_album, self.tags.new)
            self.tags.new = lastfm.track_correction(lastfm_track, self.tags.new)
            self.tags.new = lastfm.genre_correction(lastfm_genre, self.tags.new)

        lastfm_tags = lastfm.get_tags(lastfm_track)
        if lastfm_tags:
            self.tags.new['lastfm_tags'] = u''
            for tag in lastfm_tags:
                self.tags.new['lastfm_tags'] += (tag + ', ')
            self.tags.new['lastfm_tags'] = self.tags.new['lastfm_tags'][0:-2]
        logger.debug("LastFM tags: " + self.tags.new['lastfm_tags'])
        return

    def copy_to(self):
        self.build_paths(for_genre=True)
        file_operations.files_to_copy.append(self)
        for genre_path in self.genre_paths:
            file_operations.files_to_create_link.append([self.new_filepath, genre_path])

    def move_to(self):
        self.build_paths(for_genre=True)
        file_operations.files_to_move.append(self)
        for genre_path in self.genre_paths:
            file_operations.files_to_create_link.append([self.new_filepath, genre_path])

    def print_changes(self):
        for tag in self.tags.old:
            print("{}: {} ---> {}".format(tag, self.tags.old[tag], self.tags.new[tag]))
        super(Song, self).print_changes()
        print("----------------------------------")

    def _printall(self):
        print(self.filepath)
        print()
        print('Artist: ' + self.tags.new['song_artist'])
        print('Title: ' + self.tags.new['song_title'])
        print('Album artist: ' + self.tags.new['album_artist'])
        print('Album title: ' + self.tags.new['album_title'])
        print('Genre: ' + self.tags.new['genre'])
        print('Year: ' + self.tags.new['year'])
        print('Track: ' + self.tags.new['track_num'] + "/" + self.tags.new['num_of_tracks'])

        # def __str__(self):
        #     print(self.tags[u'song_artist'] + u' — ' + self.tags[u'song_title'])
