#  -*- coding: utf-8 -*-
# pyright: basic
# pyright: reportAttributeAccessIssue=false

import logging
from config import cfg, APP_NAME
log = logging.getLogger(f"{APP_NAME}.{__name__}")


def test_is_album(album):
    # Метод проверяет, является ли каталог альбомом или нет. Возвращает буль.
    # Проверка простая: у всех песен тэг альбома должен быть одинаковым.

    album_title_set = album.gather_tag('album_title')

    is_album = True
    album_title = ""

    if len(album_title_set) > 1:
        is_album = False
    else:
        album_title = album_title_set.pop()

    log.debug("Directory is album: " + str(is_album) + ", Album title: " + album_title)
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
        if it_song.tags.old['album_artist'] in it_song.tags.old['song_artist']:
            if not it_song.tags.old['album_artist'] in song_artists.keys():
                song_artists[it_song.tags.old['album_artist']] = 1
            else:
                song_artists[it_song.tags.old['album_artist']] += 1
        else:
            if not it_song.tags.old['song_artist'] in song_artists.keys():
                song_artists[it_song.tags.old['song_artist']] = 1
            else:
                song_artists[it_song.tags.old['song_artist']] += 1

    # Если один артист исполняет меньше определённой доли песен от всех песен в каталоге,
    # (а насколько именно — задаётся в конфиг.файле), то каталог признаётся сборником
    # ОДНАКО, метод ничто никуда не пишет, только возвращает булевое значение.
    is_compilation = True
    album_artist = "Various artists"

    for artist_name in song_artists.keys():
        if song_artists[artist_name] / len(album.songList) > float(cfg.compilation_coef):
            is_compilation = False
            album_artist = artist_name
            break

    log.info("Album is compilation: " + str(is_compilation) + ", Album artist: " + album_artist)
    return is_compilation, album_artist
