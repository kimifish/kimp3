#!/usr/bin/python
#  -*- coding: utf-8 -*-

import eyed3
import os
import argparse
import logging
import re
import pylast
import lastfm
import conf_parse
from shutil import copyfile
from shutil import move
from datetime import datetime

logging.basicConfig(filename='/var/log/kimifish/kimp3.log', level=logging.DEBUG)
logging.critical(u'•' + unicode(datetime.today()) + u' Starting…' )

# Читаем конфиг
config_vars = conf_parse.go("/.config/kimp3.conf")

# Парсер аргументов:
logging.info(u"Parsing args")
parser = argparse.ArgumentParser(description='Поиск, сортировка mp3 и обработка тэгов. '
                                             'Значения по-умолчанию читаются из ~/.config/kimp3.conf')
parser.add_argument("-s",
                    "--scan_dir",
                    type=str,
                    help="Каталог для поиска mp3-файлов")

mv_or_cp = parser.add_mutually_exclusive_group()
mv_or_cp.add_argument("-m",
                      "--move",
                      help="Переместить найденные файлы",
                      action="store_true")

mv_or_cp.add_argument("-c",
                      "--copy",
                      help="Копировать найденные файлы",
                      action="store_true")

parser.add_argument("-t",
                    "--check_tags",
                    help="Проверить и дополнить недостающие теги. По-умолчанию — " + str(config_vars[u'check_tags']),
                    default=config_vars[u'check_tags'],
                    action="store_true")

parser.add_argument("-C",
                    "--is_compilation",
                    help="Проверить, не является ли альбом сборником. \n "
                         "Проверяет только альбомы по соотношению исполнителей. По-умолчанию — "
                         + str(config_vars[u'compilation_test']),
                    default=config_vars[u'compilation_test'],
                    action="store_true")

parser.add_argument("-d",
                    "--decode",
                    help="Перекодировать тэги из lat1→utf8 в cp1251→utf8. Значение по-умолчанию — False",
                    action="store_true")

args = parser.parse_args()

if args.scan_dir:
    config_vars[u'scan_dir_list'] = [args.scan_dir]
    logging.debug(u"scan_dir_list: " + unicode(args.scan_dir, 'utf-8'))

if args.check_tags:
    config_vars[u'check_tags'] = True
    logging.debug(u"check_tags: " + unicode(config_vars[u'check_tags']))

if args.copy:
    config_vars[u'move_or_copy'] = u'copy'
elif args.move:
    config_vars[u'move_or_copy'] = u'move'
logging.debug(u'move_or_copy: ' + config_vars[u'move_or_copy'])

# Логинимся в Last.FM:
network = pylast.LastFMNetwork(api_key=config_vars[u'lastfm_API_KEY'],
                               api_secret=config_vars[u'lastfm_API_SECRET'],
                               username=config_vars[u'lastfm_username'],
                               password_hash=config_vars[u'lastfm_password_hash'])

# Now you can use that object everywhere
# artist = network.get_artist("System of a Down")
# artist.shout("<3")
# track = network.get_track("Iron Maiden", "The Nomad")
# track.love()
# track.add_tags(("awesome", "favorite"))

# Type help(pylast.LastFMNetwork) or help(pylast) in a Python interpreter to get more help
# about anything and see examples of how it works

class Song:
    """
    Классу передаётся полное имя файла,
    в экземпляре должны быть все теги и некоторые методы,
    например перемещение файла в заранее уготованное тёплое местечко.
    """

    # Загружаем нужные конфиги
    coll_path = unicode(config_vars['music_collection_dir'].rstrip('/'))
    del_depth = config_vars['delete_dir_depth']  # насколько глубоко удалять пустые каталоги

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

    def __init__(self, filepath, songdir=None):

        self.filepath = filepath
        self.path, self.name = os.path.split(self.filepath)
        self.newfilepath = u''

        if songdir:  # если нам передали экземпляр объекта для нашего каталога,
            self.songdir = songdir  # сохраним его в поле, пригодится.

        # Открываем файл библятекой глаз3
        self.mp3 = eyed3.load(filepath)

        self.tags = dict(song_title=self.mp3.tag.title,
                         album_title=self.mp3.tag.album,
                         song_artist=self.mp3.tag.artist,
                         album_artist=self.mp3.tag.album_artist,

                         album_type=self.mp3.tag.album_type,
                         genre=self.mp3.tag.genre.name if self.mp3.tag.genre is not None else u'',
                         year=self.mp3.tag.best_release_date,

                         disc_num_N=self.mp3.tag.disc_num[0],
                         num_of_discs_N=self.mp3.tag.disc_num[1],
                         track_num_N=self.mp3.tag.track_num[0],
                         num_of_tracks_N=self.mp3.tag.track_num[1],

                         # На случай, если проверки тегов не предвидится, нам всё равно нужны эти ключи
                         disc_num=u'',
                         num_of_discs=u'',
                         track_num=u'',
                         num_of_tracks=u'',

                         play_count=self.mp3.tag.play_count,
                         comments=self.mp3.tag.comments,
                         rating=self.mp3.tag.comments.get(u"Rating"),
                         lyrics=self.mp3.tag.lyrics)
        self.read_tags()

    def read_tags(self):

        for tag in self.tags.keys():
            if self.tags[tag] is None:
                self.tags[tag] = u''

            if type(self.tags[tag]) in [str, unicode] and self.tags[tag] != u'':
                if args.decode:
                    self.tags[tag] = unicode(self.tags[tag].rstrip()).encode('latin-1').decode('cp1251')
                else:
                    self.tags[tag] = unicode(self.tags[tag].rstrip())
                logging.info(unicode(tag) + u": " + self.tags[tag])

        # Строчные номера дисков
        # Поставил их в первый проход, поскольку общие данные об альбоме для этого не нужны,
        # а вот для генерации пути нужно строковое значение номера диска.
        if self.tags[u'num_of_discs_N'] != u'':
            self.tags[u'num_of_discs'] = unicode(self.tags[u'num_of_discs_N']).zfill(1)
        else:
            self.tags[u'num_of_discs'] = u'1'
            self.tags[u'num_of_discs_N'] = 1

        if self.tags[u'disc_num_N'] != u'':
            self.tags[u'disc_num'] = unicode(self.tags[u'disc_num_N']).zfill(
                1 if self.tags[u'num_of_discs_N'] < 10 else 2)
        else:
            self.tags[u'disc_num'] = u'1'
            self.tags[u'disc_num_N'] = 1

        # Вместо объекта CommentFrame с заголовком Rating получаем его значение, если оно есть.
        if self.tags[u'rating'] != u'':
            self.tags[u'rating'] = self.tags[u'rating'].text

        return

    def check_tags(self):

        # Заменяем разную невалидную пунктуацию
        for tag in self.tags.keys():
            tag_value = self.tags[tag]

            if type(tag_value) is unicode:
                while u"''" in tag_value:
                    tag_value = tag_value.replace(u"''", u"«", 1)
                    tag_value = tag_value.replace(u"''", u"»", 1)

            self.tags[tag] = tag_value

        # А здесь создаём строчные номера песен.
        # для начала пытаемся выяснить число лидирующих нулей
        num_of_leading0s = 2
        if len(self.songdir.songList) > 99:
            num_of_leading0s = 3

        # а затем собственно создаём их из цифр
        if self.tags[u'track_num_N'] not in [u'', -1]:
                self.tags[u'track_num'] = unicode(self.tags[u'track_num_N']).zfill(num_of_leading0s)
        if self.tags[u'num_of_tracks_N'] != u'':
                self.tags[u'num_of_tracks'] = unicode(self.tags[u'num_of_tracks_N']).zfill(num_of_leading0s)

        # album_artist по artist
        if self.tags[u'album_artist'].lower() in config_vars[u'bad_artists']:
            if not self.songdir.is_compilation:
                self.tags[u'album_artist'] = self.tags[u'song_artist']
            else:
                self.tags[u'album_artist'] = u'Various artists'

        if self.songdir.is_compilation:
            self.tags[u'album_type'] = u'compilation'

        if self.tags[u'year'] == u'':
            try:
                self.tags[u'year'] = eyed3.core.Date(int(os.path.split(self.path)[1][0:4]), None, None)
            except ValueError:
                # self.tags[u'year'] = eyed3.core.Date(2222, 1, 1)
                pass
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
            if self.songdir.is_compilation:  # обращается к объекту каталога, в котором лежит
                self.tags[u'album_type'] = u'compilation'

        if self.tags[u'album_type'] is u'compilation':
            pattern = config_vars[u'compilation_pattern']
        else:
            pattern = config_vars[u'album_pattern']

        if for_genre:
            pattern = config_vars[u'genre_pattern']

        newfilepath = self.coll_path + u"/" + pattern
        logging.debug(u"Using pattern:" + newfilepath)

        if config_vars[u'cut_empty_tags_from_path']:
            logging.info(u"Cutting empty tags from filepath")
            newfilepath = self.cut_empty_tags_from_filepath(newfilepath)

            if config_vars[u'cut_just_year_folders']:
                newfilepath = newfilepath.replace(u'/%year/', u'/')

            logging.debug(u"Result: " + newfilepath)

        for tag in self.tags.keys():
            logging.info(u"Replacing tags in path pattern by values")
            if tag in newfilepath:
                if tag == u'year':
                    tag_value = unicode(self.tags[tag].year)
                else:
                    tag_value = unicode(self.tags[tag])

                tag_value = tag_value.replace(u"/", u" | ")
                tag_value = tag_value.replace(u"*", u"\u2022")
                logging.debug(u"   {}: {}".format(tag, tag_value))
                newfilepath = newfilepath.replace("%" + tag, tag_value)

        newfilepath = newfilepath.replace(u'//', u'/')
        self.newfilepath = newfilepath
        logging.debug(u"Final destination name:" + newfilepath)

        # Возвращает строку абсолютного пути в музыкальной коллекции.
        return

    def cut_empty_tags_from_filepath(self, newfilepath):
        # Для каждого тэга, если он есть в пути, и его значение не задано, то
        for tag in self.tags.keys():
            if tag in newfilepath:
                if (tag == u'disc_num' and self.tags[u'num_of_discs_N'] == 1) or \
                                self.tags[tag] == u'':

                    regex = re.compile('.*(/|%[\w]*|^)(.*)(%{})([^/%]*)(%|/)?.*\.mp3'.format(str(tag)))
                    # разделяем путь регулярным выражением на группы (в скобках):
                    # 1. Либо уровень выше, либо предыдущий тег, либо начало строки.
                    # 2. Любые символы на этом же уровне пути после предыдущего тега, если он есть.
                    # 3. Сам тэг, который будем убирать.
                    # 4. Символы до следующего тега, уровня ниже или расширения файла.
                    # 5. Символ % или / для определения, последний ли это тег на уровне.
                    tag_with_surround = regex.match(newfilepath)

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
                    newfilepath = newfilepath.replace(text_to_remove, u'')

                    # В случае, если имя файла оказывается пустым, обзываем хотя бы id экземпляра класса.
                    newfilepath = newfilepath.replace(u'/.mp3', u'/id' + unicode(id(self)) + u'.mp3')
        return newfilepath

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
        newpath, newname = os.path.split(self.newfilepath)

        # проверяем, на случай, если файл уже там, где должен быть
        if self.filepath != self.newfilepath:

            if not os.access(newpath, os.W_OK):
                logging.info(u"Making new path — " + newpath)
                os.makedirs(newpath, mode=0755)

            # копируем файл в созданный путь
            if os.access(newpath, os.W_OK):
                logging.info(u"Copying " + self.filepath + u" to " + newpath)
                copyfile(self.filepath, self.newfilepath)

        self.mp3 = eyed3.load(self.newfilepath)
        self.write_tags()

    def move_to(self):
        self.build_newpath()
        newpath, newname = os.path.split(self.newfilepath)

        if os.path.isdir(self.newfilepath):
            logging.warning(u"File's destination path is occupied by directory. Skipping...")
            return

        # проверяем, на случай, если файл уже там, где должен быть
        if self.filepath != self.newfilepath:

            if not os.access(newpath, os.W_OK):
                logging.info(u"Making new path — " + newpath)
                os.makedirs(newpath, mode=0755)

            # перемещаем файл в созданный путь
            if os.access(newpath, os.W_OK):
                logging.info(u"Moving " + self.filepath + u" to " + self.newfilepath)
                move(self.filepath, self.newfilepath)

            # если после перемещения в каталоге ничего не осталось, удаляем каталог
            i = int(self.del_depth)
            while i > 0:
                if self.path != u'' and len(os.listdir(self.path)) == 0:
                    os.rmdir(self.path)
                    self.path = os.path.split(self.path)[0]
                    i -= 1
                else:
                    break
        self.mp3 = eyed3.load(self.newfilepath)
        self.write_tags()

    def _printall(self):
        print self.filepath
        print
        print 'Artist: ' + self.tags[u'song_artist']
        print 'Title: ' + self.tags[u'song_title']
        print 'Album artist: ' + self.tags[u'album_artist']
        print 'Album title: ' + self.tags[u'album_title']
        print 'Genre: ' + self.tags[u'genre']
        print 'Year: ' + self.tags[u'year']
        print 'Track: ' + self.tags[u'track_num'] + "/" + self.tags[u'num_of_tracks']

    # def __str__(self):
    #     print(self.tags[u'song_artist'] + u' — ' + self.tags[u'song_title'])


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
            if os.path.isfile(scanpath + u'/' + name) is True and name[-4:] == '.mp3':
                self.songList.append(Song(scanpath + u'/' + name, self))

        self.test_is_album()

        if self.is_album:
            self.test_is_compilation()
            self.path = self.songList[0].path
            self.count_num_of_tracks()

        # Второй проход: дополняем и исправляем теги на основе данных по всему альбому
        if config_vars[u'check_tags']:
            for song in self.songList:
                song.check_tags()

        if config_vars[u'move_or_copy'] == u'move':
            self.move_all_songs()
        if config_vars[u'move_or_copy'] == u'copy':
            self.copy_all_songs()


    def count_num_of_tracks(self):
        max_track_num = 0
        for i in self.songList:
            # todo Избавиться от всех этих проверок на None. Похоже, проще всего приравнять все ноны к нулю, а при
            # todo записи возвращать обратно в None.
            if int(i.tags[u'track_num_N']) > max_track_num:
                max_track_num = int(i.tags[u'track_num_N'])
        if max_track_num == len(self.songList):
            self.num_of_tracks = max_track_num

    def test_is_compilation(self):
        # Метод проверяет, является ли каталог сборником или нет. Возвращает буль.
        # Сначала просто проверяем, есть ли у всех треков тэг сборника.
        album_type_set = self.gather_tag(u'album_type')

        if album_type_set == {u'compilation'}:
            self.is_compilation = True
            logging.info(u"Album type was compilation already")

        # если тэга сборника нет, а конфиг говорит, что надо бы проверить по артистам, то проверяем по ним:
        elif config_vars[u'compilation_test']:
            song_artists = {}

            for song in self.songList:

                # причём, если строка альбомного артиста содержится в песенном, то считаем альбомного
                if song.tags[u'album_artist'] in song.tags[u'song_artist']:
                    if not song.tags[u'album_artist'] in song_artists.keys():
                        song_artists[song.tags[u'album_artist']] = 1
                    else:
                        song_artists[song.tags[u'album_artist']] += 1
                else:
                    if not song.tags[u'song_artist'] in song_artists.keys():
                        song_artists[song.tags[u'song_artist']] = 1
                    else:
                        song_artists[song.tags[u'song_artist']] += 1

            # Если один артист исполняет меньше определённой доли песен от всех песен в каталоге,
            # (а насколько именно — задаётся в конфиг.файле), то каталог признаётся сборником
            # ОДНАКО, метод ничто никуда не пишет, только возвращает булевое значение.
            self.is_compilation = True
            self.album_artist = u"Various artists"

            for artist_name in song_artists.keys():
                if song_artists[artist_name] / len(self.songList) > float(config_vars[u'compilation_coef']):
                    self.is_compilation = False
                    self.album_artist = artist_name
                    break

        return

    def test_is_album(self):
        # Метод проверяет, является ли каталог альбомом или нет. Возвращает буль.
        # Проверка простая: у всех песен тэг альбома должен быть одинаковым.

        album_title_set = self.gather_tag(u'album_title')

        self.is_album = True
        if len(album_title_set) > 1:
            self.is_album = False
        else:
            self.album_title = album_title_set.pop()

        return

    def gather_tag(self, tag, list_needed=False):
        # собирает тэг со всех треков папки в массив и сет
        tag_list = []
        tag_set = set()
        for song in self.songList:
            current_tag = song.tags[tag]
            tag_list.append(current_tag)
            tag_set.add(current_tag)
        if list_needed:
            return tag_list
        else:
            return tag_set

    def copy_all_songs(self):  # вызывает метод копирования файла
        for i in self.songList:
            i.copy_to()

        self.copy_common_album_files()

    def move_all_songs(self):  # вызывает метод перемещения файла
        for i in self.songList:
            i.move_to()

        self.copy_common_album_files()

    def copy_common_album_files(self):
        self.newpath = os.path.split(self.songList[0].newfilepath)[0] if self.is_album else None

        # Копируем общие файлы
        if self.newpath is None:
            return
        if not os.path.exists(self.path):
            return

        if os.path.isdir(self.newpath):
            for common_file in config_vars[u'common_files']:
                common_filepath = self.path + u'/' + common_file
                if os.path.isfile(common_filepath):
                    copyfile(common_filepath, self.newpath + u'/' + common_file)
                    if config_vars[u'move_or_copy'] == u'move':
                        os.remove(common_filepath)


class ScanDir:

    def __init__(self, scanpath):
        self.directories_list = []
        self.dirscan(scanpath)

    def dirscan(self, scanpath):
        num_of_mp3 = 0
        for item in os.listdir(scanpath):
            full_item = scanpath + '/' + item
            if os.path.isdir(full_item):
                self.dirscan(full_item)
            if os.path.isfile(full_item) and item[-4:] == '.mp3':
                num_of_mp3 += 1
        if num_of_mp3 > 0:
            self.directories_list.append(SongDir(scanpath))
            print "adding to dlist " + scanpath

    def copy_all_dirs(self):
        for i in self.directories_list:
            i.copy_all_songs()

    def move_all_dirs(self):
        for i in self.directories_list:
            i.move_all_songs()


# ============================================================================================
# ну а это тестовое веселье в песочнице, развлекайся на здоровье
if __name__ == '__main__':

    # config_vars[u'scan_dir_list'] = ['/media/kimifish/MediaStore/Музыка/Hills']
    # config_vars[u'scan_dir_list'] = ['/home/kimifish/Музыка/Hills']

    for folder in config_vars[u'scan_dir_list']:
        if os.path.isdir(folder):
            if os.access(folder, os.R_OK):
                x = ScanDir(unicode(folder.decode('utf-8')))
            else:
                logging.critical(u'Access to ' + folder + u' denied.')
                quit()
        else:
            logging.critical(u'Directory ' + folder + u' doesn\'t exist.')
            quit()

        # if config_vars[u'move_or_copy'] == u'move':
        #     x.move_all_dirs()
        # elif config_vars[u'move_or_copy'] == u'copy':
        #     x.copy_all_dirs()
