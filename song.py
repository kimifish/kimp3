#!/usr/bin/python3
#  -*- coding: utf-8 -*-

import logging
import os
import eyed3
import re
from os.path import split as os_split_path

import conf_parse
import lastfm
import file_operations
from tags import SongTags

config_vars = conf_parse.get_config()
logger = logging.getLogger('kimp3')


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
        # global logger
        if song_dir:  # если нам передали экземпляр объекта для нашего каталога,
            self.song_dir = song_dir  # сохраним его в поле, пригодится.
        self.tags = SongTags(self.filepath)
        self.read_tags()


    def read_tags(self):

        for tag in self.tags.old.keys():
            if self.tags.old[tag] is None:
                self.tags.old[tag] = u''

            if type(self.tags.old[tag]) in [str] and self.tags.old[tag] != u'':
                if config_vars[u'decode']:
                    self.tags.new[tag] = str(self.tags.old[tag].rstrip()).encode('latin-1').decode('cp1251')
                else:
                    self.tags.new[tag] = str(self.tags.old[tag].rstrip())
                logging.info(str(tag) + u": " + self.tags.new[tag])

        # Строчные номера дисков
        # Поставил их в первый проход, поскольку общие данные об альбоме для этого не нужны,
        # а вот для генерации пути нужно строковое значение номера диска.
        if self.tags.old[u'num_of_discs_N'] != u'':
            self.tags.new[u'num_of_discs'] = str(self.tags.old[u'num_of_discs_N']).zfill(1)
        else:
            self.tags.new[u'num_of_discs'] = u'1'
            self.tags.new[u'num_of_discs_N'] = 1

        if self.tags.old[u'disc_num_N'] != u'':
            self.tags.new[u'disc_num'] = str(self.tags.old[u'disc_num_N']).zfill(
                1 if self.tags.old[u'num_of_discs_N'] < 10 else 2)
        else:
            self.tags.new[u'disc_num'] = u'1'
            self.tags.new[u'disc_num_N'] = 1

        # Вместо объекта CommentFrame с заголовком Rating получаем его значение, если оно есть.
        if self.tags.old[u'rating'] != u'':
            self.tags.new[u'rating'] = self.tags.old[u'rating'].text

        # Здесь делаем что-нибудь с определённым артиклем в названии артиста. В общем-то всё просто.
        for tag in [u'song_artist', u'album_artist']:
            if self.tags.old[tag].lower().startswith(u'the '):
                if config_vars[u'the_the'] == u'remove':
                    self.tags.new[tag] = self.tags.old[tag][4:]
                if config_vars[u'the_the'] == u'move':
                    self.tags.new[tag] = self.tags.old[tag][4:] + u', the'

        return

    def check_tags(self):

        # Заменяем разную невалидную пунктуацию
        for tag in self.tags.new.keys():
            tag_value = self.tags.new[tag]

            if type(tag_value) is str:
                while u"''" in tag_value:
                    tag_value = tag_value.replace(u"''", u"«", 1)
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
        if self.tags.old[u'track_num_N'] not in [u'', -1]:
            self.tags.new[u'track_num'] = str(self.tags.old[u'track_num_N']).zfill(num_of_leading0s)
        if self.tags.old[u'num_of_tracks_N'] != u'':
            self.tags.new[u'num_of_tracks'] = str(self.tags.old[u'num_of_tracks_N']).zfill(num_of_leading0s)

        # album_artist по artist
        if self.tags.new[u'album_artist'].lower() in config_vars[u'bad_artists']:
            if not self.song_dir.is_compilation:
                self.tags.new[u'album_artist'] = self.tags.new[u'song_artist']
            else:
                self.tags.new[u'album_artist'] = u'Various artists'

        if self.song_dir.is_compilation:
            self.tags.new[u'album_type'] = u'compilation'

        if self.tags.new[u'year'] == u'':
            try:
                self.tags.new[u'year'] = eyed3.core.Date(int(os.path.split(self.path)[1][0:4]), None, None)
                logger.debug("Tag Year set to " + self.tags.new[u'year'])
            except ValueError:
                # self.tags[u'year'] = eyed3.core.Date(2222, 1, 1)
                pass

        self.lastfm_checks()
        return

    def build_newpath(self, for_genre=False):
        # Метод строит путь, в который затем можно копировать или перемещать файл.
        # Вообще, путей нужно строить несколько, в частности:
        #           • путь для символической ссылки для сортировки по жанрам
        #           • путь для ссылки в папку "Другое" в каталоге исполнителя
        #
        # Ну и что-нибудь ещё в том же духе. По годам например...

        # Проверяет, не являемся ли мы частью сборника
        if self.tags.new[u'album_type'] == '':
            if self.song_dir.is_compilation:  # обращается к объекту каталога, в котором лежит
                self.tags.new[u'album_type'] = u'compilation'

        if self.tags.new[u'album_type'] is u'compilation':
            pattern = config_vars[u'compilation_pattern']
        else:
            pattern = config_vars[u'album_pattern']

        if for_genre:
            pattern = config_vars[u'genre_pattern']

        new_filepath = config_vars[u'music_collection_dir'].rstrip(u'/') + u"/" + pattern
        # logger.debug(u"Using pattern:" + new_filepath)

        if config_vars[u'cut_empty_tags_from_path']:
            # logger.info(u"Cutting empty tags from filepath")
            new_filepath = self.cut_empty_tags_from_filepath(new_filepath)

            if config_vars[u'cut_just_year_folders']:
                new_filepath = new_filepath.replace(u'/%year/', u'/')

            logger.debug(u"Result: " + new_filepath)

        for tag in self.tags.new.keys():
            # logger.info(u"Replacing tags in path pattern by values")
            if tag in new_filepath:
                if tag == u'year':
                    tag_value = str(self.tags.new[tag].year)
                else:
                    tag_value = str(self.tags.new[tag])

                tag_value = tag_value.replace(u"/", u" | ")
                tag_value = tag_value.replace(u"*", u"\u2022")
                # logger.debug(u"   {}: {}".format(tag, tag_value))
                new_filepath = new_filepath.replace("%" + tag, tag_value)

        new_filepath = new_filepath.replace(u'//', u'/')
        self.new_filepath = new_filepath
        self.new_path, self.new_name = os_split_path(self.new_filepath)

        logger.debug(u"Final destination name:" + new_filepath)

        # Возвращает строку абсолютного пути в музыкальной коллекции.
        return

    def cut_empty_tags_from_filepath(self, new_filepath):
        # Для каждого тэга, если он есть в пути, и его значение не задано, то
        for tag in self.tags.new.keys():
            if tag in new_filepath:
                if (tag == u'disc_num' and self.tags.new[u'num_of_discs_N'] == 1) or \
                                self.tags.new[tag] == u'':

                    regex = re.compile('.*(/|%[\w]*|^)(.*)(%{})([^/%]*)(%|/)?.*\.mp3'.format(str(tag)))
                    # разделяем путь регулярным выражением на группы (в скобках):
                    # 1. Либо уровень выше, либо предыдущий тег, либо начало строки.
                    # 2. Любые символы на этом же уровне пути после предыдущего тега, если он есть.
                    # 3. Сам тэг, который будем убирать.
                    # 4. Символы до следующего тега, уровня ниже или расширения файла.
                    # 5. Символ % или / для определения, последний ли это тег на уровне.
                    tag_with_surround = regex.match(new_filepath)

                    # Определяем, является ли тег первым, последним на текущем уровне пути.
                    first_tag = True if tag_with_surround.group(1) in [u'/', u''] else False
                    last_tag = True if tag_with_surround.group(5) != u'%' else False

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
                    new_filepath = new_filepath.replace(text_to_remove, u'')

                    # В случае, если имя файла оказывается пустым, обзываем хотя бы id экземпляра класса.
                    new_filepath = new_filepath.replace(u'/.mp3', u'/id' + str(id(self)) + u'.mp3')
        return new_filepath

    def lastfm_checks(self):
        lastfm_track = lastfm.get_track(self.tags.new)
        lastfm_artist = lastfm.get_artist(self.tags.new)
        lastfm_album, lastfm_genre = lastfm.get_album(self.tags.new)
        lastfm_genre = ", ".join(lastfm_genre)
        # logger.debug("LastFM genre: " + lastfm_genre)


        if config_vars[u'lastfm_autocorrection']:
            self.tags.new = lastfm.artist_correction(lastfm_artist, self.tags.new)
            #            self.tags.new = lastfm.album_correction(lastfm_album, self.tags.new)
            self.tags.new = lastfm.track_correction(lastfm_track, self.tags.new)
            self.tags.new = lastfm.genre_correction(lastfm_genre, self.tags.new)

        lastfm_tags = lastfm.get_tags(lastfm_track)
        if lastfm_tags:
            self.tags.new[u'lastfm_tags'] = u''
        for tag in lastfm_tags:
            self.tags.new[u'lastfm_tags'] += (tag + u', ')
        self.tags.new[u'lastfm_tags'] = self.tags.new[u'lastfm_tags'][0:-2]
        logger.debug("LastFM tags: " + self.tags.new[u'lastfm_tags'])
        return


    def copy_to(self):
        self.build_newpath()
        file_operations.files_to_copy.append(self)

    def move_to(self):
        self.build_newpath()
        file_operations.files_to_move.append(self)

    def print_changes(self):
        for tag in self.tags.old:
            print("{}: {} ---> {}".format(tag, self.tags.old[tag], self.tags.new[tag]))
        super(Song, self).print_changes()
        print("----------------------------------")

    def _printall(self):
        print(self.filepath)
        print()
        print('Artist: ' + self.tags.new[u'song_artist'])
        print('Title: ' + self.tags.new[u'song_title'])
        print('Album artist: ' + self.tags.new[u'album_artist'])
        print('Album title: ' + self.tags.new[u'album_title'])
        print('Genre: ' + self.tags.new[u'genre'])
        print('Year: ' + self.tags.new[u'year'])
        print('Track: ' + self.tags.new[u'track_num'] + "/" + self.tags.new[u'num_of_tracks'])

        # def __str__(self):
        #     print(self.tags[u'song_artist'] + u' — ' + self.tags[u'song_title'])
