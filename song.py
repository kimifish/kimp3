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

config_vars = conf_parse.get_config()
logger = logging.getLogger('kimp3')


class UsualFile:
    def __init__(self, filepath):
        self.filepath = filepath
        logger.debug(' + ' + filepath)
        self.path, self.name = os.path.split(self.filepath)
        self.new_filepath, self.new_name, self.new_path = '', '', ''


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
        global logger
        if song_dir:  # если нам передали экземпляр объекта для нашего каталога,
            self.song_dir = song_dir  # сохраним его в поле, пригодится.

        # Открываем файл библятекой глаз3
        if config_vars['tag_reader'] == 'eyed3':
            self.mp3 = eyed3.load(filepath)
            try:
                self.tags = dict(song_title=self.mp3.tag.title,
                                 album_title=self.mp3.tag.album,
                                 song_artist=self.mp3.tag.artist,
                                 album_artist=self.mp3.tag.album_artist,

                                 album_type=self.mp3.tag.album_type,
                                 genre=self.mp3.tag.genre.name if self.mp3.tag.genre is not None else '',
                                 year=self.mp3.tag.best_release_date,

                                 disc_num_N=self.mp3.tag.disc_num[0],
                                 num_of_discs_N=self.mp3.tag.disc_num[1],
                                 track_num_N=self.mp3.tag.track_num[0],
                                 num_of_tracks_N=self.mp3.tag.track_num[1],

                                 # На случай, если проверки тегов не предвидится, нам всё равно нужны эти ключи
                                 disc_num='',
                                 num_of_discs='',
                                 track_num='',
                                 num_of_tracks='',

                                 play_count=self.mp3.tag.play_count,
                                 comments=self.mp3.tag.comments,
                                 rating=self.mp3.tag.comments.get("Rating"),
                                 lastfm_tags=self.mp3.tag.comments.get("LastFM tags"),
                                 lyrics=self.mp3.tag.lyrics)
            except AttributeError as ae:
                logger.warning(filepath + ': ' + str(ae))
        elif config_vars['tag_reader'] == 'taglib':
            from tags import SongTags
            song_tags = SongTags(self)

        self.read_tags()


    def read_tags(self):

        for tag in self.tags.keys():
            if self.tags[tag] is None:
                self.tags[tag] = u''

            if type(self.tags[tag]) in [str] and self.tags[tag] != u'':
                if config_vars[u'decode']:
                    self.tags[tag] = str(self.tags[tag].rstrip()).encode('latin-1').decode('cp1251')
                else:
                    self.tags[tag] = str(self.tags[tag].rstrip())
                logging.info(str(tag) + u": " + self.tags[tag])

        # Строчные номера дисков
        # Поставил их в первый проход, поскольку общие данные об альбоме для этого не нужны,
        # а вот для генерации пути нужно строковое значение номера диска.
        if self.tags[u'num_of_discs_N'] != u'':
            self.tags[u'num_of_discs'] = str(self.tags[u'num_of_discs_N']).zfill(1)
        else:
            self.tags[u'num_of_discs'] = u'1'
            self.tags[u'num_of_discs_N'] = 1

        if self.tags[u'disc_num_N'] != u'':
            self.tags[u'disc_num'] = str(self.tags[u'disc_num_N']).zfill(
                1 if self.tags[u'num_of_discs_N'] < 10 else 2)
        else:
            self.tags[u'disc_num'] = u'1'
            self.tags[u'disc_num_N'] = 1

        # Вместо объекта CommentFrame с заголовком Rating получаем его значение, если оно есть.
        if self.tags[u'rating'] != u'':
            self.tags[u'rating'] = self.tags[u'rating'].text

        # Здесь делаем что-нибудь с определённым артиклем в названии артиста. В общем-то всё просто.
        for tag in [u'song_artist', u'album_artist']:
            if self.tags[tag].lower().startswith(u'the '):
                if config_vars[u'the_the'] == u'remove':
                    self.tags[tag] = self.tags[tag][4:]
                if config_vars[u'the_the'] == u'move':
                    self.tags[tag] = self.tags[tag][4:] + u', the'

        return

    def check_tags(self):

        # Заменяем разную невалидную пунктуацию
        for tag in self.tags.keys():
            tag_value = self.tags[tag]

            if type(tag_value) is str:
                while u"''" in tag_value:
                    tag_value = tag_value.replace(u"''", u"«", 1)
                    tag_value = tag_value.replace(u"''", u"»", 1)

            self.tags[tag] = tag_value

        # А здесь создаём строчные номера песен.
        # для начала пытаемся выяснить число лидирующих нулей
        num_of_leading0s = 2
        if len(self.song_dir.songList) > 99:
            num_of_leading0s = 3

        # а затем собственно создаём их из цифр
        if self.tags[u'track_num_N'] not in [u'', -1]:
            self.tags[u'track_num'] = str(self.tags[u'track_num_N']).zfill(num_of_leading0s)
        if self.tags[u'num_of_tracks_N'] != u'':
            self.tags[u'num_of_tracks'] = str(self.tags[u'num_of_tracks_N']).zfill(num_of_leading0s)

        # album_artist по artist
        if self.tags[u'album_artist'].lower() in config_vars[u'bad_artists']:
            if not self.song_dir.is_compilation:
                self.tags[u'album_artist'] = self.tags[u'song_artist']
            else:
                self.tags[u'album_artist'] = u'Various artists'

        if self.song_dir.is_compilation:
            self.tags[u'album_type'] = u'compilation'

        if self.tags[u'year'] == u'':
            try:
                self.tags[u'year'] = eyed3.core.Date(int(os.path.split(self.path)[1][0:4]), None, None)
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
        if self.tags[u'album_type'] == '':
            if self.song_dir.is_compilation:  # обращается к объекту каталога, в котором лежит
                self.tags[u'album_type'] = u'compilation'

        if self.tags[u'album_type'] is u'compilation':
            pattern = config_vars[u'compilation_pattern']
        else:
            pattern = config_vars[u'album_pattern']

        if for_genre:
            pattern = config_vars[u'genre_pattern']

        new_filepath = config_vars[u'music_collection_dir'].rstrip(u'/') + u"/" + pattern
        logging.debug(u"Using pattern:" + new_filepath)

        if config_vars[u'cut_empty_tags_from_path']:
            logging.info(u"Cutting empty tags from filepath")
            new_filepath = self.cut_empty_tags_from_filepath(new_filepath)

            if config_vars[u'cut_just_year_folders']:
                new_filepath = new_filepath.replace(u'/%year/', u'/')

            logging.debug(u"Result: " + new_filepath)

        for tag in self.tags.keys():
            logging.info(u"Replacing tags in path pattern by values")
            if tag in new_filepath:
                if tag == u'year':
                    tag_value = str(self.tags[tag].year)
                else:
                    tag_value = str(self.tags[tag])

                tag_value = tag_value.replace(u"/", u" | ")
                tag_value = tag_value.replace(u"*", u"\u2022")
                logging.debug(u"   {}: {}".format(tag, tag_value))
                new_filepath = new_filepath.replace("%" + tag, tag_value)

        new_filepath = new_filepath.replace(u'//', u'/')
        self.new_filepath = new_filepath
        self.new_path, self.new_name = os_split_path(self.new_filepath)

        logging.debug(u"Final destination name:" + new_filepath)

        # Возвращает строку абсолютного пути в музыкальной коллекции.
        return

    def cut_empty_tags_from_filepath(self, new_filepath):
        # Для каждого тэга, если он есть в пути, и его значение не задано, то
        for tag in self.tags.keys():
            if tag in new_filepath:
                if (tag == u'disc_num' and self.tags[u'num_of_discs_N'] == 1) or \
                                self.tags[tag] == u'':

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
        lastfm_track = lastfm.get_track(self.tags)
        lastfm_artist = lastfm.get_artist(self.tags)
        lastfm_album = lastfm.get_album(self.tags)

        if config_vars[u'lastfm_autocorrection']:
            self.tags = lastfm.artist_correction(lastfm_artist, self.tags)
            #            self.tags = lastfm.album_correction(lastfm_album, self.tags)
            self.tags = lastfm.track_correction(lastfm_track, self.tags)

        lastfm_tags = lastfm.get_tags(lastfm_track)
        if lastfm_tags:
            self.tags[u'lastfm_tags'] = u''
        for tag in lastfm_tags:
            self.tags[u'lastfm_tags'] += (tag + u', ')
        self.tags[u'lastfm_tags'] = self.tags[u'lastfm_tags'][0:-2]
        return

    def write_tags(self, tags_to_write=u'all'):
        if tags_to_write == u'all':
            for entry in self.tags.keys():
                # if self.tags[entry] is not None:
                self.write_one_tag(entry)
        else:
            self.write_one_tag(tags_to_write)

        # Сохраняем в файл
        self.mp3.tag.save(encoding='utf-8')
        return

    def write_one_tag(self, entry):
        if self.tags[entry] == u'' and entry in [u'play_count']:
            self.tags[entry] = 0

        if entry == u'song_title':
            self.mp3.tag.title = self.tags[entry]
        if entry == u'album_title':
            self.mp3.tag.album = self.tags[entry]

        if entry == u'song_artist':
            self.mp3.tag.artist = self.tags[entry]
        if entry == u'album_artist':
            self.mp3.tag.album_artist = self.tags[entry]

        if entry == u'album_type':
            self.mp3.tag.album_type = self.tags[entry]
        if entry == u'genre':
            self.mp3.tag.genre = self.tags[entry]
        if entry == u'year':
            self.mp3.tag.release_date = self.tags[entry] if self.tags[entry] != u'' else None

        # Смысл всей этой заморочки с номерами дисков и треков в том,
        # что eyed3 здесь всегда общается только с _N версиями тегов (int), тогда как пользователь
        # по задумке должен взаимодействовать со строковым значением (лидирующие нули, все дела).
        if entry == u'disc_num' or u'num_of_discs':
            self.tags[u'num_of_discs_N'] = int(self.tags[u'num_of_discs'])
            self.tags[u'disc_num_N'] = int(self.tags[u'disc_num'])

            self.mp3.tag.disc_num = (self.tags[u'disc_num_N'], self.tags[u'num_of_discs_N'])

        if entry == u'track_num' or u'num_of_tracks':
            self.tags[u'num_of_tracks_N'] = int(self.tags[u'num_of_tracks']) \
                if self.tags[u'num_of_tracks'] != u'' \
                else None
            self.tags[u'track_num_N'] = int(self.tags[u'track_num']) \
                if self.tags[u'track_num'] != u'' \
                else None
            self.mp3.tag.track_num = (self.tags[u'track_num_N'], self.tags[u'num_of_tracks_N'])

        if entry == u'play_count':
            self.mp3.tag.play_count = self.tags[entry]

        if entry == u'rating':
            self.mp3.tag.comments.set(self.tags[u'rating'], u'Rating')

        if entry == u'lastfm_tags':
            self.mp3.tag.comments.set(self.tags[u'lastfm_tags'], u'LastFM tags')

        # Здесь что-то не так, там объекты какие-то передаются...
        # Стоит видимо заглянуть сюда: http://eyed3.nicfit.net/_modules/eyed3/id3/tag.html#Tag.comments

        # if entry == u'comments':
        #     self.mp3.tag.comments = self.tags[entry]
        # if entry == u'lyrics':
        #     self.mp3.tag.lyrics = self.tags[entry]
        # print entry + ": "
        # print self.tags[entry]
        # print type(self.tags[entry])

        return

    def copy_to(self):
        self.build_newpath()
        file_operations.files_to_copy.append(self)

    def move_to(self):
        self.build_newpath()
        file_operations.files_to_move.append(self)

    def _printall(self):
        print(self.filepath)
        print()
        print('Artist: ' + self.tags[u'song_artist'])
        print('Title: ' + self.tags[u'song_title'])
        print('Album artist: ' + self.tags[u'album_artist'])
        print('Album title: ' + self.tags[u'album_title'])
        print('Genre: ' + self.tags[u'genre'])
        print('Year: ' + self.tags[u'year'])
        print('Track: ' + self.tags[u'track_num'] + "/" + self.tags[u'num_of_tracks'])

        # def __str__(self):
        #     print(self.tags[u'song_artist'] + u' — ' + self.tags[u'song_title'])
